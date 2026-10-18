"""Support tickets, internal networks, firewalls and the accounting lists, against reduced renderings of the
panel's pages (tests/fixtures; anonymised, no account data) and a fake panel without network: parsers, risk gating,
dry runs that send nothing, the request each change sends, verification, and refusal when the panel looks different.

The network fixture's second network ("spare") models the add-server selection and the delete button, which the
live panel renders only while they apply (they were not on screen when the page was recorded)."""
import json
from pathlib import Path

import httpx
import pytest

from cbrm.errors import ContractError, PanelError, ServiceError
from cbrm.features import REGISTRY, tickets
from cbrm.service import Service

FIX = Path(__file__).parent / "fixtures"
NET, NET_FULL = (FIX / "network.html").read_text(), (FIX / "network_full.html").read_text()
TICKETS, OPEN, CLOSED = ((FIX / n).read_text() for n in ("tickets.html", "ticket_open.html", "ticket_closed.html"))
FIREWALL, ACCOUNTING = (FIX / "firewall.html").read_text(), (FIX / "accounting.html").read_text()
LIST, VIEW = "/customer/support/ticket", "/customer/support/ticket/view/"


class Resp:
    def __init__(self, body=None, status=200, headers=None):
        self.body, self.status_code, self.headers = body, status, headers or {}

    def json(self):
        if self.body is None:
            raise ValueError("not json")
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("failed", request=None, response=None)


EDIT_FORM = ('<div><form wire:submit="saveEdit"><input id="internalNetworkEditTitle" wire:model="editTitle" maxlength="255">'
             '<textarea id="internalNetworkEditDescription" wire:model="editDescription" maxlength="2000"></textarea></form></div>')


class Wire:
    def __init__(self):
        self.log, self.on, self.html = [], {}, {"startEdit": EDIT_FORM}

    def __call__(self, req):
        c = req["components"][0]
        snap = json.loads(c["snapshot"])
        data = snap["data"]
        self.log.append((c["updates"], [(x["method"], x["params"]) for x in c["calls"]]))
        data.update(c["updates"])
        effects = {}
        for call in c["calls"]:
            if call["method"] in self.on:
                self.on[call["method"]](data, call["params"])
            if call["method"] in self.html:
                effects["html"] = self.html[call["method"]]
        return {"components": [{"snapshot": json.dumps({"data": data, "memo": snap["memo"]}), "effects": effects}]}


class Http:
    def __init__(self):
        self.wire, self.forms, self.gets, self.redirects = Wire(), [], [], {}

    def post(self, url, headers=None, json=None, data=None, files=None):
        if json is not None:
            return Resp(self.wire(json))
        self.forms.append((url, dict(data), [f[1][0] for f in files or []]))
        return Resp(status=302, headers={"location": self.redirects.get(url, "https://bero-host.de/customer/support/ticket")})

    def get(self, url, params=None, headers=None):
        self.gets.append(url)
        return Resp(status=302, headers={"location": LIST + "/view/3002"})


class FakePanel:
    def __init__(self, tmp, **pages):
        self.state_dir, self.http = tmp, Http()
        self.pages = {"/customer/network": NET, LIST: TICKETS, VIEW + "3002": OPEN, VIEW + "3001": CLOSED,
                      "/customer/network/firewall/23": FIREWALL, "/customer/accounting": ACCOUNTING, **pages}

    def products(self):
        return {"1": "2", "3": "4"}

    def page(self, path):
        return self.pages[path]


@pytest.fixture
def svc(tmp_path):
    return Service(FakePanel(tmp_path), allow=["1"])


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    from cbrm.features import common
    monkeypatch.setattr(common.time, "sleep", lambda s: None)


def nothing_sent(svc):
    h = svc.panel.http
    return h.wire.log == [] and h.forms == [] and h.gets == []


# -- reading ------------------------------------------------------------------------------------------

def test_ticket_list(svc):
    r = svc.run("account-tickets", "1")
    assert r["tickets"] == [
        {"id": "3002", "subject": "Network question", "date": "19.10.2026 00:00", "status": "Offen"},
        {"id": "3001", "subject": "Earlier question", "date": "07.10.2026 12:52", "status": "Geschlossen"}]
    assert (r["page"], r["more"]) == (1, False)


def test_ticket_list_search_and_page_use_the_components_own_state(svc):
    svc.run("account-tickets", "1", {"search": " network ", "page": 3})
    assert svc.panel.http.wire.log == [({"searchTickets": "network", "paginators.ticketsPage": 3}, [])]
    with pytest.raises(ServiceError):
        svc.run("account-tickets", "1", {"page": 0})


def test_open_ticket(svc):
    t = svc.run("account-ticket", "1", {"ticket": "#3002"})
    assert (t["status"], t["can_close"], t["subject"], t["created"], t["handler"], t["product"]) == (
        "open", True, "Network question", "19.10.2026 00:00", None, "KVM Server: #9001 (node-1)")
    assert t["messages"] == [{"from": "customer", "date": "19.10.2026 00:00", "attachments": [],
                              "text": "Hello,\n\ncould we have another subnet? Thanks!"}]


def test_closed_ticket_thread_with_staff_and_events(svc):
    t = svc.run("account-ticket", "1", {"ticket": "3001"})
    assert (t["status"], t["can_close"], t["handler"], t["product"]) == ("closed", False, "Alex", None)
    assert [(m["from"], m["date"]) for m in t["messages"]] == [
        ("customer", "04.10.2026 00:26"), ("system", "04.10.2026 00:58"), ("support", "04.10.2026 01:01"),
        ("system", "07.10.2026 12:52")]
    assert t["messages"][2]["text"] == "Hello!\n\nHere is an answer."


def test_ticket_id_must_be_a_number(svc):
    with pytest.raises(ServiceError):
        svc.run("account-ticket", "1", {"ticket": "../network"})


def test_networks(svc):
    r = svc.run("account-networks", "1")
    assert (r["used"], r["limit"]) == (2, 5)
    backbone = r["networks"][0]
    assert (backbone["id"], backbone["title"], backbone["subnet"]) == ("7", "backbone", "10.0.1.0/24")
    assert backbone["description"].startswith("Private link")
    assert backbone["servers"] == [{"vm": "9001", "name": "node-1.example.test", "address": "10.0.1.10"},
                                   {"vm": "9002", "name": "node-2.example.test", "address": "10.0.1.2"}]
    assert r["networks"][1]["servers"] == [] and r["networks"][1]["description"] == ""


def test_firewalls(svc):
    r = svc.run("account-firewalls", "1")
    assert r["firewalls"] == [{"id": "23", "name": "node-fw", "servers": ["node-1.example.test", "node-2.example.test"]}]
    assert (r["used"], r["limit"]) == (1, 10)
    assert [t["id"] for t in r["templates"]] == ["empty", "linux", "webserver"]
    f = svc.run("account-firewall", "1", {"firewall": "23"})
    assert (f["policy_in"], f["policy_out"], f["rules"]) == ("DROP", "ACCEPT", [{"protocol": "tcp", "port": "22"}])
    assert f["servers"] == [{"vm": "9001", "name": "node-1.example.test", "uses_this_firewall": True},
                            {"vm": "9003", "name": "node-3.example.test", "uses_this_firewall": False}]


def test_accounting_lists(svc):
    assert svc.run("account-invoices", "1")["rows"] == [{"number": "2610-00001-02", "amount": "0,00 €", "date": "07.10.2026 10:13"}]
    assert svc.run("account-orders", "1")["rows"] == [{"status": "Abgeschlossen", "product": "KVM Rootserver #9001 (node-1)",
                                                       "type": "Neubestellung", "date": "07.10.2026 10:12"}]
    assert svc.run("account-transactions", "1")["rows"] == [{"status": "success", "description": "Example order",
                                                             "amount": "-1,00 €", "date": "07.10.2026 10:19"}]
    svc.run("account-orders", "1", {"search": "KVM", "page": 2})
    assert svc.panel.http.wire.log[-1] == ({"searchOrders": "KVM", "paginators.ordersPage": 2}, [])


def test_account_features_need_a_vm_of_the_account_and_the_allow_list(svc):
    with pytest.raises(ServiceError):
        svc.run("account-networks", "3")  # on the account but not allowed
    with pytest.raises(ServiceError):
        Service(svc.panel, allow=[]).run("account-networks", "9")  # not in the account


# -- risk classes -------------------------------------------------------------------------------------

def test_risk_classes():
    risks = {n: REGISTRY[n].risk for n in REGISTRY if n.startswith(("account-ticket", "account-network", "account-firewall"))}
    assert risks["account-network-delete"] == "destroy"
    changing = {"account-ticket-create", "account-ticket-reply", "account-ticket-close", "account-network-create",
                "account-network-edit", "account-network-server-add", "account-network-server-remove"}
    assert {n for n, r in risks.items() if r == "change"} == changing
    assert all(r == "read" for n, r in risks.items() if n not in changing | {"account-network-delete"})
    for name in changing | {"account-network-delete"}:
        assert "not limited by the VM allow-list" in REGISTRY[name].help


@pytest.mark.parametrize("name,args", [
    ("account-ticket-create", {"subject": "Network question", "text": "Please look at this."}),
    ("account-ticket-reply", {"ticket": "3002", "text": "Please look at this."}),
    ("account-ticket-close", {"ticket": "3002"}),
    ("account-network-create", {"title": "new"}),
    ("account-network-edit", {"network": "7", "title": "renamed"}),
    ("account-network-server-add", {"network": "8", "server": "9003"}),
    ("account-network-server-remove", {"network": "7", "server": "9001"}),
    ("account-network-delete", {"network": "8"}),
])
def test_changes_need_confirmation_and_dry_runs_send_nothing(svc, name, args):
    with pytest.raises(ServiceError):
        svc.run(name, "1", args)
    r = svc.run(name, "1", args, dry_run=True)
    assert r["dry_run"] and r["would"]
    assert nothing_sent(svc)


def test_network_delete_needs_both_confirmations(svc):
    with pytest.raises(ServiceError):
        svc.run("account-network-delete", "1", {"network": "8"}, confirm="1")
    svc.run("account-network-delete", "1", {"network": "8"}, confirm="1", confirm_destroy="1")


# -- tickets: changing --------------------------------------------------------------------------------

def test_ticket_create(svc):
    svc.panel.http.redirects["/customer/support/ticket/neu"] = "https://bero-host.de/customer/support/ticket/view/3002"
    out = svc.run("account-ticket-create", "1", {"subject": "Network question", "text": "Hello,\r\nplease look.", "product": "#9002"},
                  confirm="1")
    assert out["result"] == {"id": "3002", "subject": "Network question", "product": "KVM Server: #9002 (node-2)"}
    assert out["verified"] is True
    assert svc.panel.http.forms == [("/customer/support/ticket/neu", {
        "_token": "FORMTOKEN", "service": "5002", "subject": "Network question", "text": "Hello,\nplease look."}, [])]


def test_ticket_create_without_product_links_none(svc):
    svc.panel.http.redirects["/customer/support/ticket/neu"] = "/customer/support/ticket/view/3002"
    svc.run("account-ticket-create", "1", {"subject": "Network question", "text": "Please look at this."}, confirm="1")
    assert svc.panel.http.forms[0][1]["service"] == "null"


@pytest.mark.parametrize("args", [{"subject": "abc", "text": "Please look at this."},
                                  {"subject": "Network question", "text": "short"},
                                  {"subject": "Network\nquestion", "text": "Please look at this."},
                                  {"subject": "Network question", "text": "bad \x00 byte here"},
                                  {"subject": "Network question", "text": "Please look at this.", "product": "424242"}])
def test_ticket_create_refuses_what_the_form_would_refuse(svc, args):
    with pytest.raises(ServiceError):
        svc.run("account-ticket-create", "1", args, confirm="1")
    assert nothing_sent(svc)


def test_ticket_create_not_accepted_by_the_panel(svc):
    with pytest.raises(PanelError, match="nothing is known to have been created"):
        svc.run("account-ticket-create", "1", {"subject": "Network question", "text": "Please look at this."}, confirm="1")


def test_attachments_only_from_the_configured_directory(svc, tmp_path, monkeypatch):
    svc.panel.http.redirects["/customer/support/ticket/neu"] = "/customer/support/ticket/view/3002"
    args = {"subject": "Network question", "text": "Please look at this.", "attach": ["log.txt"]}
    monkeypatch.delenv("CBRM_ATTACH_DIR", raising=False)
    with pytest.raises(ServiceError, match="CBRM_ATTACH_DIR"):
        svc.run("account-ticket-create", "1", args, confirm="1")
    share = tmp_path / "share"
    share.mkdir()
    (share / "log.txt").write_text("hello")
    (tmp_path / "secret.txt").write_text("no")
    monkeypatch.setenv("CBRM_ATTACH_DIR", str(share))
    for bad in ("../secret.txt", str(tmp_path / "secret.txt"), "missing.txt"):
        with pytest.raises(ServiceError):
            svc.run("account-ticket-create", "1", {**args, "attach": [bad]}, confirm="1")
    (share / "link").symlink_to(tmp_path / "secret.txt")
    with pytest.raises(ServiceError):  # a link out of the directory
        svc.run("account-ticket-create", "1", {**args, "attach": ["link"]}, confirm="1")
    assert nothing_sent(svc)
    svc.run("account-ticket-create", "1", args, confirm="1")
    assert svc.panel.http.forms[0][2] == ["log.txt"]
    with pytest.raises(ServiceError):
        svc.run("account-ticket-create", "1", {**args, "attach": ["log.txt"] * 6}, confirm="1")


def test_ticket_reply(svc):
    svc.panel.http.redirects["/customer/support/ticket/antworten/3002"] = "https://bero-host.de/customer/support/ticket/view/3002"
    out = svc.run("account-ticket-reply", "1", {"ticket": "3002", "text": "Thanks for looking."}, confirm="1")
    assert svc.panel.http.forms == [("/customer/support/ticket/antworten/3002", {"_token": "REPLYTOKEN", "answer": "Thanks for looking."}, [])]
    assert out["result"] == {"id": "3002", "messages_before": 1}
    assert out["verified"] is False  # the fake panel's thread did not grow: "does not show it", never a guess


def test_ticket_reply_verifies_when_the_thread_grows(svc):
    grown = OPEN.replace("</div>\n<div class=\"mb-4\">", "<div class=\"d-flex justify-content-end mb-5\"><div class=\"support-message support-message-user\">"
                         "<p class=\"support-message-message\">Thanks for looking.</p><div class=\"support-message-user-date\">19.10.2026 | 01:00 Uhr</div>"
                         "</div></div></div>\n<div class=\"mb-4\">")
    svc.panel.http.redirects["/customer/support/ticket/antworten/3002"] = "/customer/support/ticket/view/3002"
    real_post = svc.panel.http.post

    def post(*a, **kw):
        r = real_post(*a, **kw)
        svc.panel.pages[VIEW + "3002"] = grown
        return r
    svc.panel.http.post = post
    assert svc.run("account-ticket-reply", "1", {"ticket": "3002", "text": "Thanks for looking."}, confirm="1")["verified"] is True


def test_closed_ticket_takes_no_reply_and_no_close(svc):
    with pytest.raises(ServiceError, match="closed"):
        svc.run("account-ticket-reply", "1", {"ticket": "3001", "text": "Thanks for looking."}, confirm="1")
    with pytest.raises(ServiceError, match="no close action"):
        svc.run("account-ticket-close", "1", {"ticket": "3001"}, confirm="1")
    assert nothing_sent(svc)


def test_ticket_close(svc):
    out = svc.run("account-ticket-close", "1", {"ticket": "3002"}, confirm="1")
    assert svc.panel.http.gets == ["/customer/support/ticket/changestatus/3002"]
    assert out["result"] == {"id": "3002"} and out["verified"] is False


def test_ticket_forms_that_changed_are_refused(tmp_path):
    for old, new in (('name="answer"', 'name="message"'), ("antworten", "reply")):
        s = Service(FakePanel(tmp_path, **{VIEW + "3002": OPEN.replace(old, new)}), allow=["1"])
        with pytest.raises((ContractError, ServiceError)):
            s.run("account-ticket-reply", "1", {"ticket": "3002", "text": "Thanks for looking."}, confirm="1")
        assert nothing_sent(s)
    s = Service(FakePanel(tmp_path, **{LIST: TICKETS.replace('name="subject"', 'name="title"')}), allow=["1"])
    with pytest.raises(ContractError):
        s.run("account-ticket-create", "1", {"subject": "Network question", "text": "Please look at this."}, confirm="1")
    assert nothing_sent(s)


# -- networks: changing -------------------------------------------------------------------------------

def test_network_edit_keeps_what_is_left_out(svc):
    wire = svc.panel.http.wire
    wire.on["startEdit"] = lambda d, p: d.update(editingId=p[0], editTitle="backbone", editDescription="Exact\ntext")
    svc.panel.http.wire.on["saveEdit"] = lambda d, p: None
    out = svc.run("account-network-edit", "1", {"network": "7", "title": "core"}, confirm="1")
    assert wire.log == [({}, [("startEdit", [7])]),
                        ({"editTitle": "core", "editDescription": "Exact\ntext"}, [("saveEdit", [])])]
    assert out["result"]["title"] == "core" and out["verified"] is False  # the page fixture still shows "backbone"


def test_network_edit_same_values_verifies(svc):
    wire = svc.panel.http.wire
    wire.on["startEdit"] = lambda d, p: d.update(editingId=p[0], editTitle="backbone", editDescription="x")
    desc = svc.run("account-networks", "1")["networks"][0]["description"]
    out = svc.run("account-network-edit", "1", {"network": "7", "title": "backbone", "description": desc}, confirm="1")
    assert out["verified"] is True


def test_network_edit_refuses_wrong_input_and_wrong_network(svc):
    for args in ({"network": "7"}, {"network": "7", "title": "x" * 256}, {"network": "99", "title": "x"},
                 {"network": "7", "description": "y" * 2001}, {"network": "7;x", "title": "x"}):
        with pytest.raises(ServiceError):
            svc.run("account-network-edit", "1", args, confirm="1")
    assert nothing_sent(svc)


def test_network_edit_stops_if_the_panel_opens_another_network(svc):
    svc.panel.http.wire.on["startEdit"] = lambda d, p: d.update(editingId=8, editTitle="spare", editDescription="")
    with pytest.raises(ContractError, match="nothing was changed"):
        svc.run("account-network-edit", "1", {"network": "7", "title": "x"}, confirm="1")
    assert [c for _, calls in svc.panel.http.wire.log for c, _ in calls] == ["startEdit"]


def test_network_create(svc):
    after = NET.replace("2 / 5", "3 / 5").replace('<form wire:submit="create">', '<div class="p-3 mb-3" wire:key="internal-network-9">'
        '<div class="fw-bold">edge</div><span class="bt-chip font-monospace">10.0.3.0/24</span></div><form wire:submit="create">')
    svc.panel.http.wire.on["create"] = lambda d, p: svc.panel.pages.update({"/customer/network": after})
    out = svc.run("account-network-create", "1", {"title": "edge", "description": "d"}, confirm="1")
    assert svc.panel.http.wire.log == [({"title": "edge", "description": "d"}, [("create", [])])]
    assert out["result"]["id"] == "9" and out["result"]["subnet"] == "10.0.3.0/24" and out["verified"] is True


def test_network_create_refuses_at_the_accounts_limit(tmp_path):
    full = NET.replace("2 / 5", "5 / 5")
    s = Service(FakePanel(tmp_path, **{"/customer/network": full}), allow=["1"])
    with pytest.raises(ContractError):  # the page counts 5 but shows 2
        s.run("account-network-create", "1", {"title": "x"}, confirm="1")
    five = NET_FULL.replace("1 / 5", "1 / 1")
    s = Service(FakePanel(tmp_path, **{"/customer/network": five}), allow=["1"])
    with pytest.raises(ServiceError, match="1 of 1"):
        s.run("account-network-create", "1", {"title": "x"}, confirm="1")
    assert nothing_sent(s)


def test_network_server_add(svc):
    out = svc.run("account-network-server-add", "1", {"network": "8", "server": "#9003"}, confirm="1")
    assert svc.panel.http.wire.log == [({"serverToAdd.8": "9003"}, [("addServer", [8])])]
    assert out["result"]["vm"] == "9003" and out["verified"] is False
    with pytest.raises(ServiceError, match="does not offer"):
        svc.run("account-network-server-add", "1", {"network": "8", "server": "9002"}, confirm="1")
    with pytest.raises(ServiceError, match="already in"):
        svc.run("account-network-server-add", "1", {"network": "7", "server": "9001"}, confirm="1")
    with pytest.raises(ServiceError, match="offers no server"):
        svc.run("account-network-server-add", "1", {"network": "7", "server": "9003"}, confirm="1")


def test_network_server_add_refuses_a_selection_without_exactly_one_button(tmp_path):
    s = Service(FakePanel(tmp_path, **{"/customer/network": NET.replace("addServer(8)", "reset(8)")}), allow=["1"])
    with pytest.raises(ContractError):
        s.run("account-network-server-add", "1", {"network": "8", "server": "9003"}, confirm="1")
    assert nothing_sent(s)


def test_network_server_remove(svc):
    out = svc.run("account-network-server-remove", "1", {"network": "7", "server": "9001"}, confirm="1")
    assert svc.panel.http.wire.log == [({}, [("removeServer", [9001])])]
    assert out["result"]["vm"] == "9001"
    with pytest.raises(ServiceError, match="not in network"):
        svc.run("account-network-server-remove", "1", {"network": "7", "server": "9003"}, confirm="1")


def test_network_server_remove_refuses_when_the_button_names_another_server(tmp_path):
    s = Service(FakePanel(tmp_path, **{"/customer/network": NET.replace("removeServer(9001)", "removeServer(9002)")}), allow=["1"])
    with pytest.raises(ContractError, match="another server"):
        s.run("account-network-server-remove", "1", {"network": "7", "server": "9001"}, confirm="1")
    assert nothing_sent(s)


def test_network_server_remove_refuses_a_server_in_two_networks(tmp_path):
    twice = NET.replace('<select wire:model="serverToAdd.8">', '<div class="bt-row" wire:key="internal-network-8-server-9001">'
        '<div class="fw-bold">node-1.example.test</div><small>10.0.2.10</small><button wire:click="removeServer(9001)">E</button></div>'
        '<select wire:model="serverToAdd.8">').replace("0 Server", "1 Server")
    s = Service(FakePanel(tmp_path, **{"/customer/network": twice}), allow=["1"])
    with pytest.raises(ServiceError, match="several networks"):
        s.run("account-network-server-remove", "1", {"network": "7", "server": "9001"}, confirm="1")


def test_network_delete(svc):
    out = svc.run("account-network-delete", "1", {"network": "8"}, confirm="1", confirm_destroy="1")
    assert svc.panel.http.wire.log == [({}, [("deleteNetwork", [8])])]
    assert out["result"]["title"] == "spare" and out["verified"] is False
    with pytest.raises(ServiceError, match="still holds 2 server"):
        svc.run("account-network-delete", "1", {"network": "7"}, confirm="1", confirm_destroy="1")


def test_network_delete_does_not_guess_other_buttons(tmp_path):
    odd = NET.replace("deleteNetwork(8)", "deleteNetwork(7)")  # a button in block 8 that names network 7
    s = Service(FakePanel(tmp_path, **{"/customer/network": odd}), allow=["1"])
    with pytest.raises(ServiceError, match="no delete"):
        s.run("account-network-delete", "1", {"network": "8"}, confirm="1", confirm_destroy="1")
    assert nothing_sent(s)


def test_panel_changes_are_contract_errors_and_send_nothing(tmp_path):
    for old, new, feature, args in (
            ("startEdit", "beginEdit", "account-network-edit", {"network": "7", "title": "x"}),
            ('wire:model="title"', 'wire:model="name"', "account-network-create", {"title": "x"}),
            ("removeServer(9001)", "stop(9001)", "account-network-server-remove", {"network": "7", "server": "9001"})):
        s = Service(FakePanel(tmp_path, **{"/customer/network": NET.replace(old, new)}), allow=["1"])
        with pytest.raises((ContractError, ServiceError)):
            s.run(feature, "1", args, confirm="1")
        assert s.panel.http.wire.log == []


# -- doctor -------------------------------------------------------------------------------------------

def test_doctor_checks_the_new_features(svc):
    new = [n for n in REGISTRY if n.startswith(("account-ticket", "account-network", "account-firewall", "account-inv",
                                                  "account-ord", "account-trans"))]
    assert len(new) == 16
    report = svc.check("1")
    assert {n: report[n] for n in new} == {n: "ok" for n in new}


def test_doctor_reports_a_changed_panel(tmp_path):
    s = Service(FakePanel(tmp_path, **{"/customer/network": NET.replace("startEdit", "beginEdit"),
                                       LIST: TICKETS.replace("searchTickets", "q")}), allow=["1"])
    report = s.check("1")
    assert report["account-network-edit"].startswith("BROKEN")
    assert report["account-tickets"].startswith("BROKEN") and report["account-ticket-create"] == "ok"
    assert report["account-networks"] == "ok"


def test_fixtures_hold_no_account_data():
    for f in FIX.glob("*.html"):
        if f.name.startswith(("network", "ticket", "firewall", "accounting")):
            body = f.read_text().lower()
            assert not any(w in body for w in ("corbet", "k8s", "fra-", "@", "kd-nr")), f.name
