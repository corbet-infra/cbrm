"""Network, backups, tasks, names, statistics, account SSH keys and renewal reads, against anonymised panel
renderings (tests/fixtures) and a fake panel without network: parsers, risk gating, dry runs that send nothing,
the request each change sends, verification, and refusal when the panel looks different."""
import base64
import hashlib
import json
import re
import struct
from pathlib import Path

import httpx
import pytest

from cbrm.errors import ContractError, PanelError, ServiceError
from cbrm.features import REGISTRY, account, common
from cbrm.features.common import plain
from cbrm.service import Service

FIX = Path(__file__).parent / "fixtures"
PRODUCT = (FIX / "product_wave2.html").read_text()
EMPTY = (FIX / "product_empty.html").read_text()
ACCOUNT = (FIX / "account.html").read_text()
P, A = "/customer/products/2", "/customer/account"


def make_key(comment="laptop") -> str:
    blob = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes(range(32))
    return f"ssh-ed25519 {base64.b64encode(blob).decode()} {comment}"


def fingerprint(key: str) -> str:
    digest = hashlib.md5(base64.b64decode(key.split()[1])).hexdigest()
    return ":".join(digest[i:i + 2] for i in range(0, 32, 2))


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        if self.body is None:
            raise ValueError("not json")
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("failed", request=None, response=None)


class Wire:
    """A Livewire update endpoint: records every call and answers with the component's state afterwards."""

    def __init__(self):
        self.log, self.on, self.html = [], {}, {}

    def __call__(self, req):
        c = req["components"][0]
        snap = json.loads(c["snapshot"])
        data = snap["data"]
        self.log.append((snap["memo"]["name"].rsplit(".", 1)[-1], c["updates"],
                         [(x["method"], x["params"]) for x in c["calls"]]))
        data.update(c["updates"])
        effects = {}
        for call in c["calls"]:
            if call["method"] in self.on:
                toasts = self.on[call["method"]](data, call["params"])
                if toasts:
                    effects["dispatches"] = [{"name": "toast", "params": {"message": t}} for t in toasts]
            if call["method"] in self.html:
                effects["html"] = self.html[call["method"]]
        return {"components": [{"snapshot": json.dumps({"data": data, "memo": snap["memo"]}), "effects": effects}]}


def default_get(url, params):
    if url.endswith("/updatestats"):
        return {"state": "success", "state_text": "Gestartet", "cpu_percent": "8.51", "ram_percent": "26.90",
                "current_memory": "3.23GB", "current_traffic": "0.00B", "uptime": 954, "template_name": "Arch Linux",
                "cores": 4, "memory": "12.00GB", "disk": "300.00GB", "disk_percent": "0.00", "ping": 5.89,
                "rescue_system": False}
    if url.endswith("/live_statistics"):
        return {"cpu": 8.41, "mem": 26.91, "netin": 2273582403, "netout": 24027803, "diskread": 620.22, "diskwrite": 5782.82}
    if url.endswith("/statistics"):
        n = len(params["data"].split(","))
        return {"labels": ["2026-10-13 18:25:00", "2026-10-13 18:26:00", "2026-10-13 18:27:00"],
                "data": [[1.0, None, 3.0] for _ in range(n)]}
    return {"state": "success", "message": "ok"}


class Http:
    def __init__(self):
        self.wire, self.forms, self.gets, self.answers, self.hooks = Wire(), [], [], {}, {}

    def post(self, url, headers=None, json=None, data=None):
        if json is not None:
            return Resp(self.wire(json))
        path = url.removeprefix("https://bero-host.de")
        self.forms.append((path, dict(data)))
        if path in self.hooks:
            self.hooks[path]()
        return Resp(self.answers.get(path, {"state": "success", "message": "ok"}))

    def get(self, url, params=None, headers=None):
        self.gets.append((url, dict(params or {})))
        if url in self.hooks:
            self.hooks[url]()
        return Resp(self.answers.get(url, default_get(url, params)))

    @property
    def sent(self):
        return self.wire.log, self.forms, self.gets


class FakePanel:
    def __init__(self, tmp, product=PRODUCT, acct=ACCOUNT):
        self.state_dir, self.pages, self.http = tmp, {P: product, A: acct}, Http()

    def products(self):
        return {"1": "2", "3": "4"}

    def page(self, path):
        return self.pages[path]


def svc_for(tmp, product=PRODUCT, acct=ACCOUNT):
    return Service(FakePanel(tmp, product, acct), allow=["1"])


@pytest.fixture
def svc(tmp_path):
    return svc_for(tmp_path)


def sent_nothing(svc):
    wire, forms, gets = svc.panel.http.sent
    return wire == [] and forms == [] and gets == []


# -- parsers ------------------------------------------------------------------------------------------

def test_addresses_and_rdns_state(svc):
    assert svc.run("addresses", "1") == [
        {"address": "192.0.2.10", "version": 4, "prefix": 24, "gateway": "192.0.2.1", "rdns": "ptr.default"},
        {"address": "2001:db8:0:1::", "version": 6, "prefix": 64, "gateway": "fe80::1", "rdns": "default.rdns.example"}]


def test_backups_and_slots(tmp_path, svc):
    assert svc.run("backups", "1") == {"backups": [{"id": "9001", "title": "Geplantes Backup", "size": "300.00GB",
                                                    "date": "07.10.2026 13:50"}], "free_slots": 2}
    assert svc.run("automatic-backup-status", "1") == {"enabled": True, "last": "07.10.2026 13:50", "next": "14.10.2026 13:50"}
    empty = svc_for(tmp_path, EMPTY)
    assert empty.run("backups", "1") == {"backups": [], "free_slots": 3}
    assert empty.run("automatic-backup-status", "1") == {"enabled": False, "last": None, "next": None}


def test_tasks(tmp_path, svc):
    assert svc.run("tasks", "1") == [{"id": "7001", "action": "dump", "label": "Backup erstellen",
                                      "repeat": "Wöchentlich", "next": "14.10.2026 13:50"}]
    assert svc_for(tmp_path, EMPTY).run("tasks", "1") == []


def test_renewal_quotes_prices_and_hides_the_payment_account(svc):
    r = svc.run("renewal", "1")
    assert (r["remaining_days"], r["expired"], r["balance"], r["upgrade"]["possible"]) == (1089, False, "0,00 €", False)
    ar = r["auto_renew"]
    assert (ar["enabled"], ar["price"], ar["renews_on"], ar["payment"]) == (True, "42,00 €", "04.10.2029", "42,00 € via PayPal")
    assert [(o["id"], o["days"], o["price"], o["selected"]) for o in ar["options"]] == [
        ("340", 365, "42,00 €", True), ("341", 720, "84,00 €", False), ("1080" and "342", 1080, "126,00 €", False)]
    assert "example.test" not in json.dumps(r)


def test_account_reads(svc):
    assert svc.run("account-credit", "1") == {"balance": "0,00 €", "balance_eur": 0.0}
    assert [k["name"] for k in svc.run("account-ssh-keys", "1")] == ["laptop"]
    assert svc.run("account-ssh-keys", "1")[0]["id"] == "301"
    with pytest.raises(ServiceError):  # the VM must belong to the account (and to the allow-list)
        svc.run("account-credit", "3")


def test_stats(svc):
    s = svc.run("stats", "1")
    assert (s["state"], s["cpu_percent"], s["ram_total"], s["uptime_seconds"], s["ping_ms"]) == ("Gestartet", 8.51, "12.00GB", 954, 5.89)
    assert s["counters"]["net_in_bytes"] == 2273582403
    h = svc.run("stats-history", "1", {"timeframe": "day", "metric": "network"})
    assert svc.panel.http.gets[-1] == ("/customer/rootserver/1/statistics", {"timeframe": "day", "type": "AVERAGE", "data": "netin,netout"})
    assert [s["name"] for s in h["series"]] == ["in", "out"] and h["series"][0] == {"name": "in", "min": 1.0, "max": 3.0, "average": 2.0, "last": 3.0}


def test_stats_refuse_answers_that_changed(svc):
    svc.panel.http.answers["/customer/rootserver/1/updatestats"] = {"state": "success", "cpu": 1}
    with pytest.raises(ContractError):
        svc.run("stats", "1")
    svc.panel.http.answers["/customer/rootserver/1/statistics"] = {"labels": [1, 2], "data": [[1.0]]}
    with pytest.raises(ContractError):
        svc.run("stats-history", "1")


# -- risk classes and gating --------------------------------------------------------------------------

NEW = {"addresses": "read", "backups": "read", "automatic-backup-status": "read", "tasks": "read", "stats": "read",
       "stats-history": "read", "renewal": "read", "account-credit": "read", "account-ssh-keys": "read",
       "rdns-set": "change", "hostname-set": "change", "rename": "change", "backup-create": "change",
       "task-create": "change", "task-delete": "change", "account-ssh-key-import": "change",
       "account-ssh-key-delete": "change", "network-reset": "destroy", "backup-delete": "destroy",
       "backup-restore": "destroy"}


def test_risk_classes():
    assert {n: REGISTRY[n].risk for n in NEW} == NEW
    assert not [n for n, f in REGISTRY.items() if f.risk == "cost" and n in NEW]


def test_account_wide_features_are_named_so():
    assert all(n.startswith("account-") for n in NEW if n in ("account-credit", "account-ssh-keys", "account-ssh-key-import",
                                                              "account-ssh-key-delete"))


def test_the_key_parameter_is_secret():
    assert next(p for p in REGISTRY["account-ssh-key-import"].params if p.name == "public_key").secret


ARGS = {"rdns-set": {"address": "192.0.2.10", "name": "mail.example.org"}, "hostname-set": {"hostname": "web1.example.org"},
        "rename": {"name": "My server"}, "backup-create": {"title": "before upgrade"},
        "task-create": {"action": "restart", "interval": "weekly", "start": "2026-10-20 03:30"},
        "task-delete": {"task": "7001"}, "account-ssh-key-import": {"name": "ci", "public_key": make_key()},
        "account-ssh-key-delete": {"key": "laptop"}, "network-reset": {}, "backup-delete": {"backup": "9001"},
        "backup-restore": {"backup": "9001"}}


@pytest.mark.parametrize("name", sorted(ARGS))
def test_changes_need_their_confirmations_and_dry_runs_send_nothing(svc, name):
    destroy = REGISTRY[name].risk == "destroy"
    with pytest.raises(ServiceError):
        svc.run(name, "1", ARGS[name])
    with pytest.raises(ServiceError):
        svc.run(name, "1", ARGS[name], confirm="3", confirm_destroy="3")
    if destroy:
        with pytest.raises(ServiceError):
            svc.run(name, "1", ARGS[name], confirm="1")
    assert sent_nothing(svc)
    r = svc.run(name, "1", ARGS[name], dry_run=True)
    assert r["dry_run"] and r["would"]
    assert sent_nothing(svc)  # no form display, no model update, no changing request


# -- the request each change sends --------------------------------------------------------------------

def test_rdns_set_selects_the_address_then_changes_and_verifies(svc):
    http = svc.panel.http

    def open_modal(data, params):
        entry = next(a for a in plain(data["addresses"]) if a["address"] == params[0])
        data["currentAddress"], data["rdnsEntry"] = [entry, {"s": "std"}], entry["rdns"]

    http.wire.on["openRdnsModal"] = open_modal
    http.wire.on["changeRdns"] = lambda data, params: (
        svc.panel.pages.__setitem__(P, PRODUCT.replace("ptr.default", data["rdnsEntry"])), ["rDNS gespeichert"])[1]
    r = svc.run("rdns-set", "1", {"address": "192.0.2.10", "name": "Mail.Example.org."}, confirm="1")
    assert r["verified"] is True and r["result"]["messages"] == ["rDNS gespeichert"]
    assert http.wire.log == [("i-p-table", {}, [("openRdnsModal", ["192.0.2.10"])]),
                             ("i-p-table", {"rdnsEntry": "mail.example.org"}, [("changeRdns", [])])]


def test_rdns_set_refuses_when_the_dialog_selects_another_address(svc):
    svc.panel.http.wire.on["openRdnsModal"] = lambda data, params: None  # currentAddress stays the first address
    with pytest.raises(ContractError):
        svc.run("rdns-set", "1", {"address": "2001:db8:0:1:0::", "name": "mail.example.org"}, confirm="1")
    assert [c[2][0][0] for c in svc.panel.http.wire.log] == ["openRdnsModal"]  # changeRdns was never sent


def test_rdns_set_input_is_checked(svc):
    for args in ({"address": "192.0.2.99", "name": "a.example.org"}, {"address": "nonsense", "name": "a.example.org"},
                 {"address": "192.0.2.10", "name": "-bad-.example.org"}, {"address": "192.0.2.10", "name": "a b"},
                 {"address": "192.0.2.10", "name": "x"}):
        with pytest.raises(ServiceError):
            svc.run("rdns-set", "1", args, dry_run=True)
    assert sent_nothing(svc)


def test_network_reset_posts_what_the_panels_button_posts(svc):
    r = svc.run("network-reset", "1", {}, confirm="1", confirm_destroy="1")
    assert svc.panel.http.forms == [("/customer/rootserver/1/resetnetwork", {"_token": "TOKEN", "password": "",
                                                                             "password_confirmation": ""})]
    assert r["verified"] is None and r["result"]["state"] == "success"  # nothing to re-read: not "verified"
    svc.panel.http.answers["/customer/rootserver/1/resetnetwork"] = {"state": "failed", "message": "no"}
    r = svc.run("network-reset", "1", {}, confirm="1", confirm_destroy="1")
    assert r["verified"] is None and r["result"] == {"state": "failed", "message": "no"}


def test_hostname_set_posts_and_verifies(svc):
    svc.panel.http.hooks["/customer/rootserver/1/sethostname"] = lambda: svc.panel.pages.__setitem__(
        P, PRODUCT.replace("kvm1.example.test", "web1.example.org"))
    r = svc.run("hostname-set", "1", {"hostname": "Web1.Example.org"}, confirm="1")
    assert svc.panel.http.forms == [("/customer/rootserver/1/sethostname", {"_token": "TOKEN", "hostname": "web1.example.org"})]
    assert r["verified"] is True and r["result"]["was"] == "kvm1.example.test"


def test_hostname_set_unverified_when_the_panel_keeps_the_old_name(svc):
    assert svc.run("hostname-set", "1", {"hostname": "web1.example.org"}, confirm="1")["verified"] is False


@pytest.mark.parametrize("bad", ["a", "-a.example.org", "a..b", "a_b.example.org", "x" * 64 + ".org", "a b", "ä.example.org"])
def test_hostname_set_refuses_bad_names(svc, bad):
    with pytest.raises(ServiceError):
        svc.run("hostname-set", "1", {"hostname": bad}, dry_run=True)


def test_rename_uses_the_panels_own_limits(svc):
    svc.panel.http.hooks["/customer/service/setdisplayname/2"] = lambda: svc.panel.pages.__setitem__(
        P, PRODUCT.replace("KVM Rootserver #2\n</h2>", "My server\n</h2>"))
    r = svc.run("rename", "1", {"name": "My server"}, confirm="1")
    assert svc.panel.http.forms == [("/customer/service/setdisplayname/2", {"_token": "TOKEN", "displayname": "My server"})]
    assert r["verified"] is True
    for bad in ("x" * 36, "x", "two\nlines"):  # maxlength 35 and minlength 2 come from the panel's input
        with pytest.raises(ServiceError):
            svc.run("rename", "1", {"name": bad}, dry_run=True)


def test_backup_create_needs_a_free_slot_and_posts_the_title(tmp_path, svc):
    svc.panel.http.hooks["/customer/rootserver/1/backup/create"] = lambda: svc.panel.pages.__setitem__(
        P, with_second_backup(PRODUCT))
    r = svc.run("backup-create", "1", {"title": "before upgrade"}, confirm="1")
    assert svc.panel.http.forms == [("/customer/rootserver/1/backup/create", {"_token": "TOKEN", "title": "before upgrade"})]
    assert r["verified"] is True
    full = svc_for(tmp_path, re.sub(r'<div class="rootserver-backup-container rootserver-backup-item-new.*?</div>\s*</div>',
                                    "", PRODUCT, flags=re.S))
    assert full.run("backups", "1")["free_slots"] == 0
    with pytest.raises(ServiceError):
        full.run("backup-create", "1", {"title": "one too many"}, confirm="1")
    assert sent_nothing(full)


def with_second_backup(page: str) -> str:
    """The product page after a backup was created: a second backup tile (id 9002) in place of one 'new backup' tile."""
    item = re.search(r'<div class="rootserver-backup-container rootserver-backup-item p-4">.*?(?=\s*<!--\[if ENDBLOCK\]>'
                     r'<!\[endif\]-->\s*<!--\[if BLOCK\]><!\[endif\]-->\s*<div class="rootserver-backup-container '
                     r'rootserver-backup-item-new)', page, re.S).group(0)
    page = page.replace(item, item + item.replace("9001", "9002").replace("Geplantes Backup", "before upgrade"))
    return re.sub(r'<div class="rootserver-backup-container rootserver-backup-item-new.*?</div>\s*</div>', "", page,
                  count=1, flags=re.S)


def test_backup_delete_only_known_ids_and_verified_by_rereading(svc):
    for bad in ("1", "9001; DROP", ""):
        with pytest.raises(ServiceError):
            svc.run("backup-delete", "1", {"backup": bad}, confirm="1", confirm_destroy="1")
    assert sent_nothing(svc)
    svc.panel.http.hooks["/customer/rootserver/1/backup/delete/9001"] = lambda: svc.panel.pages.__setitem__(P, EMPTY)
    r = svc.run("backup-delete", "1", {"backup": "9001"}, confirm="1", confirm_destroy="1")
    assert svc.panel.http.gets == [("/customer/rootserver/1/backup/delete/9001", {})] and r["verified"] is True


def test_backup_delete_unverified_while_the_backup_is_still_listed(svc, monkeypatch):
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    assert svc.run("backup-delete", "1", {"backup": "9001"}, confirm="1", confirm_destroy="1")["verified"] is False


def test_backup_restore_takes_the_live_choice(svc):
    svc.run("backup-restore", "1", {"backup": "9001"}, confirm="1", confirm_destroy="1")
    svc.run("backup-restore", "1", {"backup": "9001", "live": "no"}, confirm="1", confirm_destroy="1")
    assert svc.panel.http.gets == [("/customer/rootserver/1/backup/restore/9001", {"liverestore": "1"}),
                                   ("/customer/rootserver/1/backup/restore/9001", {"liverestore": "0"})]
    with pytest.raises(ServiceError):
        svc.run("backup-restore", "1", {"backup": "9001", "live": "maybe"}, confirm="1", confirm_destroy="1")


def with_second_task(page: str) -> str:
    item = re.search(r'<div class="rootserver-task-container rootserver-task-item p-4">.*?(?=<!--\[if ENDBLOCK\]><!\[endif\]-->\s*<div class="rootserver-task-container rootserver-task-item-new)', page, re.S).group(0)
    new = item.replace("7001", "7002").replace("14.10.2026 13:50", "20.10.2026 03:30").replace("Backup erstellen", "Neustarten")
    return page.replace(item, item + new)


def test_task_create_follows_the_panels_form_and_verifies(svc):
    svc.panel.http.hooks["/customer/rootserver/1/scheduled_task/create"] = lambda: svc.panel.pages.__setitem__(
        P, with_second_task(PRODUCT))
    r = svc.run("task-create", "1", {"action": "restart", "interval": "weekly", "start": "2026-10-20T03:30"}, confirm="1")
    assert svc.panel.http.forms == [("/customer/rootserver/1/scheduled_task/create", {
        "_token": "TOKEN", "methode": "restart", "interval": "weekly", "next_execution_at": "2026-10-20T03:30"})]
    assert r["verified"] is True


@pytest.mark.parametrize("args", [{"action": "format", "interval": "weekly", "start": "2026-10-20 03:30"},
                                  {"action": "stop", "interval": "hourly", "start": "2026-10-20 03:30"},
                                  {"action": "stop", "interval": "daily", "start": "tomorrow"},
                                  {"action": "stop", "interval": "daily", "start": "2026-13-45 03:30"}])
def test_task_create_refuses_what_the_form_does_not_offer(svc, args):
    with pytest.raises(ServiceError):
        svc.run("task-create", "1", args, dry_run=True)
    assert sent_nothing(svc)


def test_task_delete(svc):
    with pytest.raises(ServiceError):
        svc.run("task-delete", "1", {"task": "1"}, confirm="1")
    svc.panel.http.hooks["/customer/rootserver/1/scheduled_task/delete/7001"] = lambda: svc.panel.pages.__setitem__(P, EMPTY)
    r = svc.run("task-delete", "1", {"task": "7001"}, confirm="1")
    assert svc.panel.http.gets == [("/customer/rootserver/1/scheduled_task/delete/7001", {})] and r["verified"] is True


# -- account SSH keys ---------------------------------------------------------------------------------

IMPORT_FORM = ('<div><input wire:model.live="importSshKeyName"><textarea wire:model.live="importSshKeyPublicKey"></textarea>'
               '<button wire:click.prevent="importSshKey">x</button></div>')


def test_ssh_key_import_shows_the_form_then_sends_name_and_key(svc):
    key = make_key("me@host")
    svc.panel.http.wire.html["showAddSshKeyImportContent"] = IMPORT_FORM
    svc.panel.http.wire.on["importSshKey"] = lambda data, params: None
    r = svc.run("account-ssh-key-import", "1", {"name": "ci", "public_key": key}, confirm="1")
    assert svc.panel.http.wire.log == [("ssh-keys", {}, [("showAddSshKeyImportContent", [])]),
                                       ("ssh-keys", {"importSshKeyName": "ci", "importSshKeyPublicKey": key}, [("importSshKey", [])])]
    assert r["result"]["fingerprint"] == fingerprint(key)
    audit = svc.audit_path.read_text()
    assert key.split()[1] not in audit and "<given>" in audit  # the key parameter is secret: only "given" is logged


def test_ssh_key_import_is_verified_by_fingerprint_and_name(svc):
    key = make_key()
    svc.panel.http.wire.html["showAddSshKeyImportContent"] = IMPORT_FORM

    def stored(data, params):
        tile = re.search(r'<div class="rootserver-backup-container rootserver-backup-item p-4" wire:key="existingSshKey301">.*?'
                         r'(?=<div class="rootserver-backup-container rootserver-backup-item-new)', ACCOUNT, re.S).group(0)
        new = tile.replace("301", "302").replace("laptop", "ci").replace(re.search(r"(?:[0-9a-f]{2}:){15}[0-9a-f]{2}", tile).group(0),
                                                                          fingerprint(key))
        svc.panel.pages[A] = ACCOUNT.replace(tile, tile + new)
    svc.panel.http.wire.on["importSshKey"] = stored
    assert svc.run("account-ssh-key-import", "1", {"name": "ci", "public_key": key}, confirm="1")["verified"] is True


@pytest.mark.parametrize("bad", ["-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----",
                                 "", "ssh-ed25519", "ssh-ed25519 !!!notbase64!!! x", "ssh-dss AAAAB3NzaC1kc3M= x",
                                 make_key() + "\n" + make_key(), 'command="x" ' + make_key(),
                                 "ssh-rsa " + make_key().split()[1] + " type-mismatch"])
def test_ssh_key_import_refuses_everything_but_one_public_key(svc, bad):
    with pytest.raises(ServiceError) as e:
        svc.run("account-ssh-key-import", "1", {"name": "ci", "public_key": bad}, confirm="1")
    assert not {"b3BlbnNz", "notbase64", "type-mismatch", 'command="x"'} & {t for t in re.split(r"[\s=]", str(e.value)) if t}
    assert sent_nothing(svc)


def test_ssh_key_import_refuses_duplicates(svc):
    stored = make_key()
    page = ACCOUNT.replace(re.search(r"(?:[0-9a-f]{2}:){15}[0-9a-f]{2}", ACCOUNT).group(0), fingerprint(stored))
    other = svc_for(svc.panel.state_dir, acct=page)
    with pytest.raises(ServiceError):
        other.run("account-ssh-key-import", "1", {"name": "second", "public_key": stored}, confirm="1")
    with pytest.raises(ServiceError):
        svc.run("account-ssh-key-import", "1", {"name": "laptop", "public_key": make_key("x")}, confirm="1")
    assert sent_nothing(svc) and sent_nothing(other)


def test_parse_public_key():
    key = make_key("me@host")
    assert account.parse_public_key("  " + key + "\n") == (key, fingerprint(key))


def test_ssh_key_delete_selects_checks_then_deletes(svc):
    http = svc.panel.http

    def select(data, params):
        data["selectedKeyId"], data["selectedKeyName"] = params[0], "laptop"
    http.wire.on["selectSshKey"] = select
    http.wire.on["deleteSshKey"] = lambda data, params: svc.panel.pages.__setitem__(
        A, re.sub(r'<div class="rootserver-backup-container rootserver-backup-item p-4" wire:key="existingSshKey301">.*?'
                  r'(?=<div class="rootserver-backup-container rootserver-backup-item-new)', "", ACCOUNT, flags=re.S))
    r = svc.run("account-ssh-key-delete", "1", {"key": "laptop"}, confirm="1")
    assert http.wire.log == [("ssh-keys", {}, [("selectSshKey", [301])]), ("ssh-keys", {}, [("deleteSshKey", [])])]
    assert r["verified"] is True
    with pytest.raises(ServiceError):
        svc.run("account-ssh-key-delete", "1", {"key": "nobody"}, confirm="1")


def test_ssh_key_delete_stops_when_the_wrong_key_would_be_deleted(svc):
    svc.panel.http.wire.on["selectSshKey"] = lambda data, params: data.update(selectedKeyId=999)
    with pytest.raises(ContractError):
        svc.run("account-ssh-key-delete", "1", {"key": "301"}, confirm="1")
    assert [c[2][0][0] for c in svc.panel.http.wire.log] == ["selectSshKey"]


# -- the panel looks different: nothing is sent --------------------------------------------------------

CHANGES = [  # feature, args, risk-confirmations, (page, old, new)
    ("hostname-set", ARGS["hostname-set"], P, "sethostname", "sethost"),
    ("hostname-set", ARGS["hostname-set"], P, "hostname: document.getElementById('hostnameChangeInput').value",
     "host_name: document.getElementById('hostnameChangeInput').value"),
    ("rename", ARGS["rename"], P, "setdisplayname/2", "setname/2"),
    ("rename", ARGS["rename"], P, "displayname: document", "name: document"),
    ("network-reset", {}, P, "resetnetwork", "resetnet"),
    ("network-reset", {}, P, "password_confirmation: document.getElementById('changeRootpasswordPasswordConfirmation').value",
     "password_confirmation: document.getElementById('x').value, extra: 1"),
    ("backup-create", ARGS["backup-create"], P, "backup/create", "backup/new"),
    ("backup-create", ARGS["backup-create"], P, "title: document", "name: document"),
    ("backup-delete", ARGS["backup-delete"], P, "backup/delete/", "backup/remove/"),
    ("backup-restore", ARGS["backup-restore"], P, "backup/restore/", "backup/recover/"),
    ("backup-restore", ARGS["backup-restore"], P, "?liverestore=", "?live="),
    ("task-create", ARGS["task-create"], P, "scheduled_task/create", "scheduled_task/add"),
    ("task-create", ARGS["task-create"], P, "next_execution_at: document", "start: document"),
    ("task-create", ARGS["task-create"], P, 'name="methode"', 'name="method"'),
    ("task-delete", ARGS["task-delete"], P, "scheduled_task/delete/", "scheduled_task/remove/"),
    ("rdns-set", ARGS["rdns-set"], P, "openRdnsModal", "openDnsModal"),
    ("rdns-set", ARGS["rdns-set"], P, 'wire:model.live="rdnsEntry"', 'wire:model.live="entry"'),
    ("rdns-set", ARGS["rdns-set"], P, "changeRdns()", "saveRdns()"),
    ("account-ssh-key-import", ARGS["account-ssh-key-import"], A, "showAddSshKeyImportContent", "showImport"),
    ("account-ssh-key-delete", ARGS["account-ssh-key-delete"], A, "deleteSshKey", "removeSshKey"),
    ("account-ssh-key-delete", ARGS["account-ssh-key-delete"], A, "selectSshKey", "pickSshKey"),
    ("account-ssh-key-delete", ARGS["account-ssh-key-delete"], A, "addNewSshKeyToAccount", "addKey"),
]


@pytest.mark.parametrize("name,args,page,old,new", CHANGES)
def test_a_changed_panel_stops_before_sending(tmp_path, name, args, page, old, new):
    src = PRODUCT if page == P else ACCOUNT
    assert old in src, old
    changed = src.replace(old, new)
    svc = svc_for(tmp_path, changed if page == P else PRODUCT, changed if page == A else ACCOUNT)
    risk = REGISTRY[name].risk
    kwargs = {"confirm": "1", **({"confirm_destroy": "1"} if risk == "destroy" else {})}
    for dry in (True, False):
        with pytest.raises(ContractError):
            svc.run(name, "1", args, dry_run=dry, **({} if dry else kwargs))
    assert sent_nothing(svc)
    assert svc.check("1")[name].startswith("BROKEN")


@pytest.mark.parametrize("name,page,old,new", [
    ("addresses", PRODUCT, "&quot;netmask&quot;", "&quot;mask&quot;"),
    ("backups", EMPTY, "rootserver-backup-item-new", "rootserver-backup-slot"),
    ("tasks", EMPTY, "rootserver-task-item-new", "rootserver-task-slot"),
    ("tasks", PRODUCT, "showDeleteTaskModal(7001)", "showSomething(7001)"),
    ("automatic-backup-status", PRODUCT, "autoBackupEnabled", "autoBackup"),
    ("renewal", PRODUCT, "secondsTillEnd", "secondsLeft"),
    ("renewal", PRODUCT, 'id="serverRenewSwitchButton"', 'id="renewSwitch"'),
    ("renewal", PRODUCT, 'id="guthabenHeader"', 'id="credit"'),
], ids=lambda v: v if isinstance(v, str) and len(v) < 40 and "<" not in v else "")
def test_parsers_raise_contract_errors_instead_of_guessing(tmp_path, name, page, old, new):
    assert old in page
    svc = svc_for(tmp_path, page.replace(old, new))
    with pytest.raises(ContractError):
        svc.run(name, "1")


def test_doctor_is_happy_with_the_current_panel(svc):
    report = svc.check("1")
    assert {n: report[n] for n in NEW} == {n: "ok" if (f := REGISTRY[n]).check or f.risk == "read" else "untested"
                                           for n in NEW}


def test_panel_errors_are_readable(svc):
    svc.panel.http.answers["/customer/rootserver/1/sethostname"] = None
    svc.panel.http.post = lambda url, headers=None, json=None, data=None: Resp({"message": "The hostname is invalid."}, 422)
    with pytest.raises(PanelError, match="invalid"):
        svc.run("hostname-set", "1", {"hostname": "web1.example.org"}, confirm="1")


def test_the_command_line_builds_for_every_feature():
    """argparse formats every help string: a stray '%' in a feature's help breaks the whole CLI."""
    from cbrm.cli import _parser
    parser = _parser()
    for name in REGISTRY:
        with pytest.raises(SystemExit) as e:
            parser.parse_args([name, "--help"])
        assert e.value.code == 0
