"""The 0.6.0 features against reduced, anonymised renderings of the recorded panel (tests/fixtures/product_wave3.html,
firewall_editor.html, shares.html, transfers.html, accounting.html) and a fake panel without network: parsers, risk
gating, dry runs that send nothing changing, the exact request each change sends, verification, and refusal when the
panel looks different.

States the live panel did not show while it was recorded (pending updates, a running task, locked mail ports, a
protected backup) are derived from the recordings by the smallest change and are marked as such below."""
import base64
import json
from pathlib import Path

import httpx
import pytest

from cbrm import cli
from cbrm.errors import ContractError, PanelError, ServiceError
from cbrm.features import REGISTRY
from cbrm.service import Service

FIX = Path(__file__).parent / "fixtures"
PRODUCT = (FIX / "product_wave3.html").read_text()
NET = (FIX / "network.html").read_text()
EDITOR = (FIX / "firewall_editor.html").read_text()
SHARES, TRANSFERS = (FIX / "shares.html").read_text(), (FIX / "transfers.html").read_text()
ACCOUNTING = (FIX / "accounting.html").read_text()
P, FW = "/customer/products/2", "/customer/network/firewall/23"
PDF = b"%PDF-1.7\n% fixture\n"


class Resp:
    def __init__(self, body=None, status=200, headers=None, content=b""):
        self.body, self.status_code, self.headers, self.content = body, status, headers or {}, content

    def json(self):
        if self.body is None:
            raise ValueError("not json")
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("failed", request=None, response=None)


class Wire:
    """A Livewire update endpoint: records every call; `on[method]` may change the panel's pages (what a later
    fresh read sees) or return the component's new data fields."""

    def __init__(self):
        self.log, self.on = [], {}

    def __call__(self, req):
        c = req["components"][0]
        snap = json.loads(c["snapshot"])
        data = snap["data"]
        self.log.append((snap["memo"]["name"].rsplit(".", 1)[-1], c["updates"], [(x["method"], x["params"]) for x in c["calls"]]))
        data.update(c["updates"])
        for call in c["calls"]:
            if call["method"] in self.on:
                data.update(self.on[call["method"]](call["params"]) or {})
        return {"components": [{"snapshot": json.dumps({"data": data, "memo": snap["memo"]}), "effects": {}}]}

    def methods(self):
        return [m for _, _, calls in self.log for m, _ in calls]


READS = {"__lazyLoad", "updateDrivesContent", "updateBootOrderContent", "nextPage"}


class Http:
    def __init__(self):
        self.wire, self.forms, self.answers = Wire(), [], {}

    def post(self, url, headers=None, json=None, data=None):
        if json is not None:
            return Resp(self.wire(json))
        path = url.removeprefix("https://bero-host.de")
        self.forms.append((path, dict(data)))
        hook = self.answers.get(path)
        return Resp(hook() if callable(hook) else hook or {"state": "success", "message": "ok"})

    def get(self, url, params=None, headers=None):
        raise AssertionError(f"unexpected GET {url}")


class FakePanel:
    def __init__(self, tmp, **pages):
        self.state_dir, self.http = tmp, Http()
        self.pages = {P: PRODUCT, "/customer/network": NET, FW: EDITOR, "/customer/shares": SHARES,
                      "/customer/transfers": TRANSFERS, "/customer/accounting": ACCOUNTING, **pages}
        self.files, self.downloads = {"/customer/rechnungen/herunterladen/2610-00001-02": (PDF, "application/pdf")}, []

    def products(self):
        return {"1": "2", "3": "4"}

    def page(self, path):
        return self.pages[path]

    def download(self, path):
        self.downloads.append(path)
        return self.files[path]


def changes(svc):
    """What was sent that is not a read: Livewire methods other than refreshes, and every form post."""
    return [m for m in svc.panel.http.wire.methods() if m not in READS] + svc.panel.http.forms


@pytest.fixture
def svc(tmp_path):
    return Service(FakePanel(tmp_path), allow=["1"])


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    from cbrm.features import common
    monkeypatch.setattr(common.time, "sleep", lambda s: None)


def swap(svc, path, old, new):
    assert old in svc.panel.pages[path], old
    svc.panel.pages[path] = svc.panel.pages[path].replace(old, new)


# -- reads ------------------------------------------------------------------------------------------------

def test_activity(svc):
    assert svc.run("activity", "1") == [
        {"id": "987", "actor": "you", "action": "Aufgabe angelegt", "date": "19.10.2026 16:46"},
        {"id": "986", "actor": "Alex Example", "action": "Konsole genutzt", "date": "19.10.2026 02:30"},
        {"id": "652", "actor": "you", "action": "Hostname geändert", "date": "18.10.2026 20:05"}]
    assert len(svc.run("activity", "1", {"n": 1})) == 1
    with pytest.raises(ServiceError):
        svc.run("activity", "1", {"n": 0})


def test_activity_without_its_heading_is_a_contract_error(tmp_path):
    s = Service(FakePanel(tmp_path, **{P: PRODUCT.replace("Aktivitäten", "Verlauf")}), allow=["1"])
    with pytest.raises(ContractError):
        s.run("activity", "1")


def test_updates_and_running_task(svc):
    assert svc.run("updates", "1") == {"pending": False, "updates": []}
    assert svc.run("running-task", "1") == {"running": False, "text": None}


PENDING = ('<p class="m-0"> Keine Updates ausstehend 💪 </p>', '<button data-bs-target="#serverUpdatesModal">Updates anzeigen</button>')
PENDING_BODY = ('<div class="modal-body"><div> </div></div>', '<div class="modal-body"><div><p>QEMU 9.2</p><p>Neustart nötig</p></div></div>')


def pending(svc):  # synthetic: the recorded server had no pending updates
    swap(svc, P, *PENDING)
    swap(svc, P, *PENDING_BODY)


def test_pending_updates_are_listed(svc):
    pending(svc)
    assert svc.run("updates", "1") == {"pending": True, "updates": ["QEMU 9.2", "Neustart nötig"]}


def test_running_task_text(svc):  # synthetic: nothing was running while the panel was recorded
    swap(svc, P, '<div class="toast-container position-fixed bottom-0 end-0 p-3"> </div>',
         '<div class="toast-container position-fixed bottom-0 end-0 p-3"><div class="toast">Backup wird erstellt (42 %)</div></div>')
    assert svc.run("running-task", "1") == {"running": True, "text": "Backup wird erstellt (42 %)"}


def test_firewall_card(svc):
    assert svc.run("firewall", "1") == {
        "vm": "1", "firewall": {"id": "23", "name": "node-fw"},
        "mail_ports": {"unlocked": True, "since": "18.10.2026", "state": "E-Mail-Ports 25, 465, 587, 2525 freigeschaltet seit 18.10.2026"},
        "mail_unlock_requestable": False}


def test_firewall_card_of_another_server_is_a_contract_error(tmp_path):
    s = Service(FakePanel(tmp_path, **{P: PRODUCT.replace("&quot;rootserverId&quot;: 1,", "&quot;rootserverId&quot;: 3,")}), allow=["1"])
    with pytest.raises(ContractError):
        s.run("firewall", "1")


def test_tasks_show_the_notification(svc):
    assert svc.run("tasks", "1") == [{"id": "7001", "action": "dump", "label": "Backup erstellen",
                                      "repeat": "Wöchentlich", "next": "26.10.2026 01:42",
                                      "notification": {"mode": "failed_only", "email": None, "label": "Nur bei Fehlern"}}]


def test_logs_with_status_search_and_page(svc):
    assert svc.run("logs", "1") == [{"date": "08.10.2026 12:46", "action": "Starten", "status": "failed"},
                                    {"date": "08.10.2026 12:46", "action": "Starten", "status": "ok"},
                                    {"date": "08.10.2026 12:26", "action": "Rootserver installieren", "status": "ok"}]
    assert len(svc.run("logs", "1", {"n": 2})) == 2
    svc.run("logs", "1", {"search": " Starten ", "page": 2})
    assert svc.panel.http.wire.log[-1] == ("logs-table", {"logSearch": "Starten", "paginators.logPage": 2}, [])
    with pytest.raises(ServiceError):
        svc.run("logs", "1", {"page": 0})


def test_backup_protection_is_read(tmp_path):
    from cbrm.features import backups

    class C:  # one backup tile as the panel's stylesheet describes it (no protected backup was on screen)
        name = "backup"
        html = ('<div><div class="rootserver-backup-item"><h3><span>Vorher</span></h3>'
                '<button class="rootserver-backup-protect is-protected"></button>'
                '<button onclick="showDeleteBackupModal(5)"></button></div>'
                '<div class="rootserver-backup-item"><h3><span>Nachher</span></h3>'
                '<button class="rootserver-backup-protect"></button><button onclick="showRecreateBackupModal(6)"></button></div></div>')

        @property
        def tree(self):
            from selectolax.lexbor import LexborHTMLParser
            return LexborHTMLParser(self.html)
    assert [(b["id"], b["protected"]) for b in backups._read(C())["backups"]] == [("5", True), ("6", False)]


def test_account_codes(svc):
    assert svc.run("account-codes", None) == {"share_code": "00000000-0000-4000-8000-00000000000a",
                                               "transfer_code": "00000000-0000-4000-8000-00000000000b"}


def test_account_code_that_is_no_uuid_is_a_contract_error(tmp_path):
    s = Service(FakePanel(tmp_path, **{"/customer/shares": SHARES.replace("00000000-0000-4000-8000-00000000000a", "hidden")}), allow=["1"])
    with pytest.raises(ContractError):
        s.run("account-codes", None)


def test_invoice_pdf(svc):
    assert svc.run("account-invoice-download", None, {"invoice": "2610-00001-02"}) == PDF
    assert svc.panel.downloads == ["/customer/rechnungen/herunterladen/2610-00001-02"]
    assert REGISTRY["account-invoice-download"].returns == "pdf"


def test_invoice_not_on_the_page_is_searched_and_refused(svc):
    with pytest.raises(ServiceError):
        svc.run("account-invoice-download", None, {"invoice": "2610-00009-01"})
    assert svc.panel.http.wire.log == [("invoices-table", {"searchInvoices": "2610-00009-01"}, [])]
    assert svc.panel.downloads == []
    with pytest.raises(ServiceError):
        svc.run("account-invoice-download", None, {"invoice": "../account"})


def test_invoice_that_is_not_a_pdf_is_a_panel_error(svc):
    svc.panel.files["/customer/rechnungen/herunterladen/2610-00001-02"] = (b"<html>login</html>", "text/html")
    with pytest.raises(PanelError):
        svc.run("account-invoice-download", None, {"invoice": "2610-00001-02"})


# -- changes on the VM ------------------------------------------------------------------------------------

def test_new_changes_need_confirmation(svc):
    for name, args in (("firewall-unassign", {}), ("drive-add", {}), ("updates-install", {}),
                       ("mail-unlock-request", {"purpose": "x", "hostname": "mail.example.org", "accept_terms": "yes"}),
                       ("task-notification-set", {"task": "7001", "notification_mode": "always"})):
        assert REGISTRY[name].risk == "change"
        with pytest.raises(ServiceError):
            svc.run(name, "1", args)
    assert changes(svc) == []


def test_firewall_unassign(svc):
    assert svc.run("firewall-unassign", "1", dry_run=True)["would"].startswith("Livewire rootserver.firewall: unassign()")
    assert changes(svc) == []
    svc.panel.http.wire.on["unassign"] = lambda params: swap(
        svc, P, '<span class="rs-net-label mb-1">Aktive Firewall</span><div class="ncd-name">node-fw</div>', '')
    r = svc.run("firewall-unassign", "1", confirm="1")
    assert r["result"]["firewall"] == {"id": "23", "name": "node-fw"} and r["verified"] is True
    assert svc.panel.http.wire.methods() == ["unassign"]
    with pytest.raises(ServiceError):  # nothing left to remove
        svc.run("firewall-unassign", "1", confirm="1")


LOCKED = ("E-Mail-Ports 25, 465, 587, 2525 freigeschaltet seit 18.10.2026",
          'E-Mail-Ports 25, 465, 587, 2525 gesperrt</div><button data-bs-target="#mailUnlockModal">Freischaltung beantragen</button><div>')


def test_mail_unlock_request_refused_while_unlocked(svc):
    with pytest.raises(ServiceError):
        svc.run("mail-unlock-request", "1", {"purpose": "Our mail server", "hostname": "mail.example.org",
                                             "accept_terms": "yes"}, confirm="1")
    assert changes(svc) == []


def test_mail_unlock_request(svc):  # synthetic: the recorded server's ports were already unlocked
    swap(svc, P, *LOCKED)
    assert svc.run("firewall", "1")["mail_unlock_requestable"] is True
    args = {"purpose": "Mail for example.org\nabout 50 mails a day", "hostname": "Mail.Example.org.", "accept_terms": "yes"}
    assert "acceptTerms=true" in svc.run("mail-unlock-request", "1", args, dry_run=True)["would"]
    assert changes(svc) == []
    svc.panel.http.wire.on["requestMailUnlock"] = lambda params: swap(svc, P, "gesperrt", "beantragt")
    r = svc.run("mail-unlock-request", "1", args, confirm="1")
    assert r["verified"] is True
    assert svc.panel.http.wire.log[-1] == ("firewall", {"purpose": "Mail for example.org\nabout 50 mails a day",
                                                        "mailHostname": "mail.example.org", "acceptTerms": True},
                                           [("requestMailUnlock", [])])


def test_mail_unlock_request_checks_its_input(svc):
    swap(svc, P, *LOCKED)
    for bad in ({"accept_terms": "no"}, {"hostname": "not a host"}, {"purpose": ""}, {"purpose": "x" * 2001}):
        with pytest.raises(ServiceError):
            svc.run("mail-unlock-request", "1", {"purpose": "p", "hostname": "mail.example.org", "accept_terms": "yes", **bad},
                    confirm="1")
    assert changes(svc) == []


def test_updates_install(svc):
    with pytest.raises(ServiceError):  # nothing pending
        svc.run("updates-install", "1", confirm="1")
    pending(svc)
    assert "installUpdates()" in svc.run("updates-install", "1", dry_run=True)["would"]
    assert changes(svc) == []
    svc.panel.http.wire.on["installUpdates"] = lambda params: swap(svc, P, *reversed(PENDING))
    r = svc.run("updates-install", "1", confirm="1")
    assert r["verified"] is True and r["result"]["updates"] == ["QEMU 9.2", "Neustart nötig"]
    assert svc.panel.http.wire.methods()[-1] == "installUpdates"


def test_drive_add(svc):
    assert svc.run("drive-add", "1", dry_run=True)["would"] == "Livewire drive: addDrive() [drives now: ['ide2']]"
    assert changes(svc) == []
    svc.panel.http.wire.on["addDrive"] = lambda params: swap(
        svc, P, 'wire:key="existingDriveFromRootserveride2">',
        'wire:key="existingDriveFromRootserveride0"><h3><span>Laufwerk ide0</span></h3><p>Leer</p></div>'
        '<div class="rootserver-backup-item" wire:key="existingDriveFromRootserveride2">')
    r = svc.run("drive-add", "1", confirm="1")
    assert r["result"]["drives_before"] == ["ide2"] and r["verified"] is True
    assert "addDrive" in svc.panel.http.wire.methods()


def test_drive_add_refused_without_the_tile(tmp_path):
    s = Service(FakePanel(tmp_path, **{P: PRODUCT.replace('wire:key="addNewDriveToRootserver"', 'wire:key="other"')}), allow=["1"])
    with pytest.raises(ServiceError):
        s.run("drive-add", "1", confirm="1")
    assert changes(s) == []


def test_task_notification_set(svc):
    would = svc.run("task-notification-set", "1", {"task": "7001", "notification_mode": "always",
                                                   "notification_email": "ops@example.org"}, dry_run=True)["would"]
    assert would.startswith("POST /customer/rootserver/1/scheduled_task/notification/7001 ")
    assert changes(svc) == []

    def saved():
        swap(svc, P, 'data-mode="failed_only" data-email=""', 'data-mode="always" data-email="ops@example.org"')
        return {"state": "success", "message": "gespeichert"}
    svc.panel.http.answers["/customer/rootserver/1/scheduled_task/notification/7001"] = saved
    r = svc.run("task-notification-set", "1", {"task": "7001", "notification_mode": "always",
                                               "notification_email": "ops@example.org"}, confirm="1")
    assert r["verified"] is True
    assert svc.panel.http.forms == [("/customer/rootserver/1/scheduled_task/notification/7001",
                                     {"_token": "TOKEN", "notification_mode": "always", "notification_email": "ops@example.org"})]


def test_task_notification_none_and_refusals(svc):
    svc.run("task-notification-set", "1", {"task": "7001", "notification_mode": "none"}, confirm="1")
    assert svc.panel.http.forms[-1][1] == {"_token": "TOKEN", "notification_mode": "", "notification_email": ""}
    for bad in ({"notification_mode": "sometimes"}, {"notification_mode": "none", "notification_email": "a@example.org"},
                {"notification_mode": "always", "notification_email": "no-address"}, {"task": "7002"}):
        with pytest.raises(ServiceError):
            svc.run("task-notification-set", "1", {"task": "7001", "notification_mode": "always", **bad}, confirm="1")
    assert len(svc.panel.http.forms) == 1


def test_task_notification_contract(tmp_path):
    changed = PRODUCT.replace("notification_email: document", "email: document")
    s = Service(FakePanel(tmp_path, **{P: changed}), allow=["1"])
    with pytest.raises(ContractError):
        s.run("task-notification-set", "1", {"task": "7001", "notification_mode": "always"}, confirm="1")
    assert s.check("1")["task-notification-set"].startswith("BROKEN")


# -- account-wide changes ---------------------------------------------------------------------------------

def test_account_firewall_create(svc):
    assert REGISTRY["account-firewall-create"].risk == "change"
    assert svc.run("account-firewall-create", None, {"title": "web"}, dry_run=True)["would"] == \
        "Livewire firewalls: title='web', template='linux', create()"
    assert changes(svc) == []

    def created(params):
        swap(svc, "/customer/network", '<span class="bt-chip">1 / 10</span>', '<span class="bt-chip">2 / 10</span>')
        swap(svc, "/customer/network", '<div class="bt-row" wire:key="firewall-23">',
             '<div class="bt-row" wire:key="firewall-24"><div><a class="fw-bold" href="/customer/network/firewall/24">web</a>'
             '<small class="bt-muted d-block"></small></div></div><div class="bt-row" wire:key="firewall-23">')
    svc.panel.http.wire.on["create"] = created
    r = svc.run("account-firewall-create", None, {"title": "web", "template": "webserver"}, confirm="account")
    assert svc.panel.http.wire.log[-1] == ("firewalls", {"title": "web", "template": "webserver"}, [("create", [])])
    assert r["result"]["id"] == "24" and r["verified"] is True


def test_account_firewall_create_refusals(tmp_path, svc):
    with pytest.raises(ServiceError):
        svc.run("account-firewall-create", None, {"title": "web", "template": "windows-xp"}, confirm="account")
    with pytest.raises(ServiceError):
        svc.run("account-firewall-create", None, {"title": "x" * 101}, confirm="account")
    full = Service(FakePanel(tmp_path, **{"/customer/network": NET.replace("1 / 10", "1 / 1")}), allow=["1"])
    with pytest.raises(ServiceError):
        full.run("account-firewall-create", None, {"title": "web"}, confirm="account")
    assert changes(svc) == [] and changes(full) == []


def test_account_firewall_edit(svc):
    with pytest.raises(ServiceError):
        svc.run("account-firewall-edit", None, {"firewall": "23"}, confirm="account")
    with pytest.raises(ServiceError):
        svc.run("account-firewall-edit", None, {"firewall": "23", "policy_in": "REJECT"}, confirm="account")
    would = svc.run("account-firewall-edit", None, {"firewall": "23", "policy_in": "DROP"}, dry_run=True)["would"]
    assert "policyIn='DROP', save()" in would and "rules are sent as they are" in would
    assert changes(svc) == []

    def saved(params):
        swap(svc, FW, "&quot;policyIn&quot;: &quot;ACCEPT&quot;", "&quot;policyIn&quot;: &quot;DROP&quot;")
        return {"lockoutWarningFor": "IN"}
    svc.panel.http.wire.on["save"] = saved
    r = svc.run("account-firewall-edit", None, {"firewall": "23", "policy_in": "DROP", "title": "edge"}, confirm="account")
    assert svc.panel.http.wire.log[-1] == ("firewall-editor", {"title": "edge", "policyIn": "DROP"}, [("save", [])])
    assert r["result"]["lockout_warning"] == "IN"
    assert r["result"]["policy_out"] == "ACCEPT"
    assert r["verified"] is False  # the title did not change in the (fake) panel: look again


def test_account_firewall_edit_unknown_firewall(svc):
    with pytest.raises(ServiceError):
        svc.run("account-firewall-edit", None, {"firewall": "99", "title": "x"}, confirm="account")


def test_account_firewall_server_remove(svc):
    assert svc.run("account-firewall-server-remove", None, {"firewall": "23", "server": "9001"}, dry_run=True)["would"] == \
        "Livewire firewall-editor 23: unassignServer(9001) [node-1.example.test]"
    svc.panel.http.wire.on["unassignServer"] = lambda params: swap(
        svc, FW, '<span class="bt-pill bt-pill--completed">nutzt diese Firewall</span></small></div>\n  '
                 '<button class="bt-btn-ghost btn-sm" type="button" wire:click="unassignServer(9001)"', '</small></div>\n  <button ')
    r = svc.run("account-firewall-server-remove", None, {"firewall": "23", "server": "#9001"}, confirm="account")
    assert svc.panel.http.wire.log[-1] == ("firewall-editor", {}, [("unassignServer", [9001])])
    assert r["verified"] is True
    with pytest.raises(ServiceError):
        svc.run("account-firewall-server-remove", None, {"firewall": "23", "server": "9002"}, confirm="account")


def test_account_firewall_server_remove_button_must_name_the_server(tmp_path):
    s = Service(FakePanel(tmp_path, **{FW: EDITOR.replace("unassignServer(9001)", "unassignServer(9003)")}), allow=["1"])
    with pytest.raises(ContractError):
        s.run("account-firewall-server-remove", None, {"firewall": "23", "server": "9001"}, confirm="account")
    assert changes(s) == []


def test_account_code_regenerate(svc):
    with pytest.raises(ServiceError):
        svc.run("account-code-regenerate", None, {"code": "secret"}, confirm="account")
    svc.panel.http.wire.on["regenerate"] = lambda params: swap(
        svc, "/customer/transfers", "00000000-0000-4000-8000-00000000000b", "00000000-0000-4000-8000-00000000000c")
    r = svc.run("account-code-regenerate", None, {"code": "transfer"}, confirm="account")
    assert r["verified"] is True and r["result"]["was"] == "00000000-0000-4000-8000-00000000000b"
    assert svc.panel.http.wire.log == [("transfer-code", {}, [("regenerate", [])])]


def test_doctor_checks_every_new_feature(svc):
    new = ["activity", "updates", "updates-install", "running-task", "firewall", "firewall-unassign", "mail-unlock-request",
           "drive-add", "task-notification-set", "logs", "account-codes", "account-code-regenerate",
           "account-firewall-create", "account-firewall-edit", "account-firewall-server-remove", "account-invoice-download"]
    report = svc.check("1")
    assert {n: report[n] for n in new} == {n: "ok" for n in new}
    assert changes(svc) == []


# -- interfaces ---------------------------------------------------------------------------------------------

def test_cli_version(capsys):
    from cbrm import __version__
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0 and capsys.readouterr().out.strip() == f"cbrm {__version__}"


def test_every_command_has_complete_help(capsys):
    parser = cli._parser()
    names = ["vms", "features", "doctor", "serve", *REGISTRY]
    for name in names:
        with pytest.raises(SystemExit) as e:
            parser.parse_args([name, "--help"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        if name in REGISTRY:
            f = REGISTRY[name]
            assert cli.marker(f) in out and " ".join(f.help.split()[:4]) in " ".join(out.split()), name
            if f.scope == "account":
                assert "not limited by the VM allow-list" in " ".join(out.split()), name
            for p in f.params:
                assert "--" + p.name.replace("_", "-") in out, (name, p.name)
            if f.risk != "read":
                assert "--confirm" in out and "--dry-run" in out, name
            if f.risk == "destroy":
                assert "--confirm-destroy" in out, name


def test_features_list_needs_no_login(capsys, monkeypatch):
    for v in ("CBRM_USER", "CBRM_PASSWORD", "CBRM_CREDENTIALS_CMD", "CBRM_API_URL"):
        monkeypatch.delenv(v, raising=False)
    cli.main(["features"])
    out = capsys.readouterr().out
    assert all(name in out for name in REGISTRY)


def test_cli_writes_a_pdf(tmp_path, monkeypatch, capsys):
    class B:
        def run(self, name, vm, args, **kw):
            assert (name, vm, args) == ("account-invoice-download", "account", {"invoice": "2610-00001-02"})
            return PDF
    monkeypatch.setattr("cbrm.client.backend", lambda: B())
    out = tmp_path / "invoice.pdf"
    cli.main(["account-invoice-download", "--invoice", "2610-00001-02", "--out", str(out)])
    assert out.read_bytes() == PDF


def test_api_serves_a_pdf(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from cbrm.api import create_app
    monkeypatch.setenv("CBRM_API_TOKEN", "t")
    client = TestClient(create_app(Service(FakePanel(tmp_path), allow=["1"])))
    r = client.get("/vms/account/account-invoice-download", params={"invoice": "2610-00001-02"},
                   headers={"Authorization": "Bearer t"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content == PDF


def test_mcp_returns_a_pdf_as_base64(tmp_path, monkeypatch):
    import anyio

    from cbrm import mcp
    monkeypatch.setattr(mcp, "_b", Service(FakePanel(tmp_path), allow=["1"]))
    tool = mcp._tool(REGISTRY["account-invoice-download"])
    r = anyio.run(lambda: tool(vm=None, invoice="2610-00001-02"))
    assert r["type"] == "application/pdf" and base64.b64decode(r["base64"]) == PDF


def test_reinstall_refuses_a_form_field_cbrm_does_not_send(tmp_path):
    from test_service import FIXTURE  # the product page with the reinstall form
    from test_service import FakePanel as ServicePanel
    changed = FIXTURE.replace('<form id="reinstallServerForm">', '<form id="reinstallServerForm"><input name="password" value="">', 1)
    assert changed != FIXTURE
    s = Service(ServicePanel(tmp_path, changed), allow=["1"])
    with pytest.raises(ContractError):
        s.run("reinstall", "1", {"template": "Debian 12"}, confirm="1", confirm_destroy="1")
