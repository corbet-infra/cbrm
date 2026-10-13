"""Regression tests for the findings of the second independent review: each test here fails on the code
as it was before the fix. The panel is mocked (no network), see test_wave2.py and test_service.py."""
import base64
import datetime
import json
import re
import string
import struct
import zoneinfo
from dataclasses import replace

import pytest

from cbrm.errors import ContractError, PanelError, ServiceError
from cbrm.features import REGISTRY, account, common, registry, tasks
from cbrm.service import Service

import test_service
from test_wave2 import ACCOUNT, P, PRODUCT, fingerprint, make_key, sent_nothing, svc_for


@pytest.fixture
def svc(tmp_path):
    return svc_for(tmp_path)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """`settle` re-reads a few times with a pause; nothing here may really wait."""
    monkeypatch.setattr(common.time, "sleep", lambda s: None)


# -- 4: an unknown verification stays unknown -------------------------------------------------------------

@pytest.mark.parametrize("answer,expected", [(None, None), (True, True), (False, False), (0, False), ("yes", True)])
def test_verified_none_is_not_turned_into_false(tmp_path, monkeypatch, answer, expected):
    svc = Service(test_service.FakePanel(tmp_path), allow=["1"])
    monkeypatch.setitem(registry.REGISTRY, "power", replace(registry.REGISTRY["power"], verify=lambda *a, **k: answer))
    r = svc.run("power", "1", {"action": "restart"}, confirm="1")
    assert r["verified"] is expected and "verify_error" not in r
    assert f"verified={expected}" in svc.audit_path.read_text()


# -- 9: only `state` and `message` of the panel's answers are kept ---------------------------------------

EXTRA = {"state": "success", "message": "ok", "account": "payer@example.test", "token": "leak-1234"}
FAR = "2099-01-01 03:30"  # always in the future, whatever the clock says


@pytest.mark.parametrize("name,args,path", [
    ("hostname-set", {"hostname": "web1.example.org"}, "/customer/rootserver/1/sethostname"),
    ("rename", {"name": "My server"}, "/customer/service/setdisplayname/2"),
    ("backup-create", {"title": "before upgrade"}, "/customer/rootserver/1/backup/create"),
    ("backup-delete", {"backup": "9001"}, "/customer/rootserver/1/backup/delete/9001"),
    ("backup-restore", {"backup": "9001"}, "/customer/rootserver/1/backup/restore/9001"),
    ("network-reset", {}, "/customer/rootserver/1/resetnetwork"),
    ("task-create", {"action": "restart", "interval": "weekly", "start": FAR}, "/customer/rootserver/1/scheduled_task/create"),
    ("task-delete", {"task": "7001"}, "/customer/rootserver/1/scheduled_task/delete/7001"),
])
def test_results_keep_only_state_and_message_of_the_panels_answer(svc, name, args, path):
    svc.panel.http.answers[path] = EXTRA
    r = svc.run(name, "1", args, confirm="1", confirm_destroy="1")
    assert r["result"]["state"] == "success" and r["result"]["message"] == "ok"
    assert "leak-1234" not in json.dumps(r) and "payer@example.test" not in json.dumps(r)
    assert "leak-1234" not in svc.audit_path.read_text()


def test_results_of_the_panel_helpers_keep_only_state_and_message(tmp_path):
    panel = test_service.FakePanel(tmp_path)
    panel.power = lambda vm, action: dict(EXTRA)
    panel.reinstall = lambda vm, t, k: dict(EXTRA)
    panel.set_root_password = lambda vm, password: dict(EXTRA)
    panel.get_json = lambda path, params=None: dict(EXTRA)
    svc = Service(panel, allow=["1"])
    runs = [("power", {"action": "restart"}, {}), ("reinstall", {"template": "Arch Linux"}, {"confirm_destroy": "1"}),
            ("set-root-password", {"password": "pw"}, {}), ("boot-order-set", {"order": ["ide0", "scsi0", "net0"]}, {})]
    for name, args, more in runs:
        r = svc.run(name, "1", args, confirm="1", **more)
        assert {"state", "message"} >= set(r["result"]) - {"root_password"}, name
    assert "leak-1234" not in svc.audit_path.read_text() and "payer@example.test" not in svc.audit_path.read_text()


@pytest.mark.parametrize("line,payment", [
    ("42,00 € via PayPal (payer@example.test)", "42,00 € via PayPal"),
    ("42,00 € via PayPal payer@example.test", None),  # no parentheses: nothing to cut at, so nothing is kept
    ("42,00 € via Lastschrift (DE89 3704 0044 0532 0130 00)", "42,00 € via Lastschrift"),
    ("42,00 € via payer@example.test", None),
    ("Guthaben", None),
])
def test_renewal_keeps_only_amount_and_method_of_the_payment(tmp_path, line, payment):
    old = "42,00 € via PayPal (payer@example.test)"
    assert old in PRODUCT
    r = svc_for(tmp_path, PRODUCT.replace(old, line)).run("renewal", "1")
    assert r["auto_renew"]["payment"] == payment
    assert "payer" not in json.dumps(r) and "DE89" not in json.dumps(r)


def test_renewal_does_not_return_the_upgrade_components_text(tmp_path):
    fixed = "Diesen Server kannst du nicht ändern, da es eine feste Konfiguration ist."
    assert fixed in PRODUCT
    for text in (fixed + " Kontakt: payer@example.test", "Upgrade auf Paket L für 12,00 € (payer@example.test)"):
        r = svc_for(tmp_path, PRODUCT.replace(fixed, text)).run("renewal", "1")
        assert r["upgrade"]["possible"] is (False if "feste" in text else None)
        assert "payer" not in json.dumps(r) and "Server" not in r["upgrade"]["note"] and "Paket" not in r["upgrade"]["note"]


# -- 10: unparseable panel values are contract errors, never a raw ValueError ----------------------------------

def test_renewal_with_an_unreadable_runtime_is_a_contract_error(tmp_path):
    page = re.sub(r"var secondsTillEnd = [-\d.]+;", "var secondsTillEnd = 1.2.3;", PRODUCT)
    assert page != PRODUCT
    with pytest.raises(ContractError):
        svc_for(tmp_path, page).run("renewal", "1")


@pytest.mark.parametrize("error", [ValueError("could not convert string to float: '1.2.3'"), KeyError("wire:key"),
                                   AttributeError("'NoneType' object has no attribute 'attributes'")])
def test_the_command_line_never_prints_a_traceback_for_odd_panel_content(monkeypatch, capsys, error):
    import cbrm.client
    from cbrm import cli

    class Broken:
        def run(self, *a, **k):
            raise error
    monkeypatch.setattr(cbrm.client, "backend", lambda: Broken())
    monkeypatch.delenv("CBRM_DEBUG", raising=False)
    with pytest.raises(SystemExit) as e:
        cli.main(["status", "1"])
    assert isinstance(e.value.code, str) and e.value.code.startswith("cbrm: unexpected content")
    assert "Traceback" not in capsys.readouterr().err


# -- 1: account-ssh-key-delete only deletes the key its tile shows -------------------------------------------

def selecting_wire(svc, name="laptop"):
    """A panel whose selectSshKey does what the tile's button says and which records the deleteSshKey call."""
    def select(data, params):
        data["selectedKeyId"], data["selectedKeyName"] = params[0], name
    svc.panel.http.wire.on["selectSshKey"] = select
    return svc.panel.http.wire


def called(wire):
    return [c[2][0][0] for c in wire.log]


def test_ssh_key_delete_refuses_a_tile_whose_button_selects_another_key(tmp_path):
    other = ACCOUNT.replace('wire:click="selectSshKey(301)"', 'wire:click="selectSshKey(302)"')
    assert other != ACCOUNT
    svc = svc_for(tmp_path, acct=other)
    wire = selecting_wire(svc)  # a cooperating panel: cbrm's own id would "match" what cbrm itself sent
    for dry in (True, False):
        with pytest.raises(ContractError):
            svc.run("account-ssh-key-delete", "1", {"key": "301"}, dry_run=dry, **({} if dry else {"confirm": "1"}))
    assert wire.log == [] and sent_nothing(svc)
    assert svc.check("1")["account-ssh-key-delete"].startswith("BROKEN")


def test_ssh_key_delete_refuses_a_tile_without_a_select_button(tmp_path):
    other = ACCOUNT.replace('wire:click="selectSshKey(301)"', 'x-on:click="$wire.selectSshKey(301)"')
    svc = svc_for(tmp_path, acct=other)
    with pytest.raises(ContractError):
        svc.run("account-ssh-key-delete", "1", {"key": "laptop"}, confirm="1")
    assert sent_nothing(svc)


def test_ssh_key_delete_stops_when_the_selected_name_is_not_the_tiles_name(svc):
    wire = selecting_wire(svc, name="somebody-elses-key")  # the right id, another key's name
    with pytest.raises(ContractError):
        svc.run("account-ssh-key-delete", "1", {"key": "laptop"}, confirm="1")
    assert called(wire) == ["selectSshKey"]  # deleteSshKey was never sent


def test_ssh_key_delete_compares_the_name_as_the_tile_shows_it(svc):
    wire = selecting_wire(svc, name="  laptop ")
    wire_delete = []
    svc.panel.http.wire.on["deleteSshKey"] = lambda data, params: wire_delete.append(1)
    svc.run("account-ssh-key-delete", "1", {"key": "laptop"}, confirm="1")
    assert called(wire) == ["selectSshKey", "deleteSshKey"] and wire_delete == [1]


# -- 10: a key tile whose id is not a number is a contract error, not a ValueError ---------------------------

def test_a_non_numeric_key_id_is_a_contract_error(tmp_path):
    page = ACCOUNT.replace("existingSshKey301", "existingSshKeyx1").replace("selectSshKey(301)", "selectSshKey(x1)")
    svc = svc_for(tmp_path, acct=page)
    with pytest.raises(ContractError):
        svc.run("account-ssh-keys", "1")
    with pytest.raises(ContractError):  # even a dry run: the id is parsed before anything is described or sent
        svc.run("account-ssh-key-delete", "1", {"key": "laptop"}, dry_run=True)
    assert sent_nothing(svc)


# -- 7: the Livewire state the import writes to must be there before anything is sent ------------------------

@pytest.mark.parametrize("field", ["importSshKeyName", "importSshKeyPublicKey", "addSshKeyContentType"])
def test_ssh_key_import_needs_its_livewire_state_before_it_sends_anything(tmp_path, field):
    page = ACCOUNT.replace(f"&quot;{field}&quot;", "&quot;renamed&quot;")
    assert page != ACCOUNT
    svc = svc_for(tmp_path, acct=page)
    for dry in (True, False):
        with pytest.raises(ContractError):
            svc.run("account-ssh-key-import", "1", {"name": "ci", "public_key": make_key()}, dry_run=dry,
                    **({} if dry else {"confirm": "1"}))
    assert sent_nothing(svc)
    assert svc.check("1")["account-ssh-key-import"].startswith("BROKEN")


# -- 6: exactly one OpenSSH public key, parsed strictly ---------------------------------------------------

def sshstr(b: bytes) -> bytes:
    return struct.pack(">I", len(b)) + b


def mpint(n: int) -> bytes:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return sshstr(b"\0" + raw if raw[0] & 0x80 else raw)


def key_line(key_type: str, *fields: bytes, comment: str = "me@host", trailing: bytes = b"") -> str:
    blob = sshstr(key_type.encode()) + b"".join(fields) + trailing
    return f"{key_type} {base64.b64encode(blob).decode()}" + (f" {comment}" if comment else "")


RSA_N = (1 << 2047) | (1 << 1000) | 1
POINT = {"nistp256": b"\x04" + bytes(range(64)), "nistp384": b"\x04" + bytes(range(96)),
         "nistp521": b"\x04" + bytes(i % 251 for i in range(132))}  # 0x04 || X || Y
APP = sshstr(b"ssh:")

VALID = {
    "ed25519": key_line("ssh-ed25519", sshstr(bytes(range(32)))),
    "rsa": key_line("ssh-rsa", mpint(65537), mpint(RSA_N)),
    "p256": key_line("ecdsa-sha2-nistp256", sshstr(b"nistp256"), sshstr(POINT["nistp256"])),
    "p384": key_line("ecdsa-sha2-nistp384", sshstr(b"nistp384"), sshstr(POINT["nistp384"])),
    "p521": key_line("ecdsa-sha2-nistp521", sshstr(b"nistp521"), sshstr(POINT["nistp521"])),
    "sk-ed25519": key_line("sk-ssh-ed25519@openssh.com", sshstr(bytes(range(32))), APP),
    "sk-p256": key_line("sk-ecdsa-sha2-nistp256@openssh.com", sshstr(b"nistp256"), sshstr(POINT["nistp256"]), APP),
    "no comment": key_line("ssh-ed25519", sshstr(bytes(range(32))), comment=""),
    "benign dashes in the comment": key_line("ssh-ed25519", sshstr(bytes(range(32))), comment="a-----b"),
    "words in the comment": key_line("ssh-ed25519", sshstr(bytes(range(32))), comment="my private key backup"),
}


@pytest.mark.parametrize("which", sorted(VALID))
def test_parse_public_key_accepts_every_supported_type(which):
    line = VALID[which]
    key, fp = account.parse_public_key("  " + line + "\n")
    assert key == line and fp == fingerprint(line)


def _short_n():
    return key_line("ssh-rsa", mpint(65537), mpint((1 << 2046) | 1))


def _noncanonical(line: str) -> str:
    """The same bytes with other (non-zero) padding bits in the last base64 character."""
    t, b64, rest = line.split(" ", 2)
    alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + "+/"
    body = b64.rstrip("=")
    changed = body[:-1] + alphabet[alphabet.index(body[-1]) ^ 1] + b64[len(body):]
    assert changed != b64 and base64.b64decode(changed, validate=True) == base64.b64decode(b64)
    return f"{t} {changed} {rest}"


BAD = {
    "trailing bytes": key_line("ssh-ed25519", sshstr(bytes(range(32))), trailing=b"\0"),
    "trailing string": key_line("ssh-ed25519", sshstr(bytes(range(32))), trailing=sshstr(b"x")),
    "ed25519 31 bytes": key_line("ssh-ed25519", sshstr(bytes(31))),
    "ed25519 33 bytes": key_line("ssh-ed25519", sshstr(bytes(33))),
    "ed25519 empty": key_line("ssh-ed25519"),
    "rsa 2047 bits": _short_n(),
    "rsa e zero": key_line("ssh-rsa", sshstr(b""), mpint(RSA_N)),
    "rsa negative n": key_line("ssh-rsa", mpint(65537), sshstr(b"\xff" * 256)),
    "rsa non-minimal n": key_line("ssh-rsa", mpint(65537), sshstr(b"\0" + ((1 << 2046) | 1).to_bytes(256, "big"))),
    "rsa without n": key_line("ssh-rsa", mpint(65537)),
    "rsa trailing": key_line("ssh-rsa", mpint(65537), mpint(RSA_N), trailing=b"\1"),
    "ecdsa wrong curve": key_line("ecdsa-sha2-nistp256", sshstr(b"nistp384"), sshstr(POINT["nistp256"])),
    "ecdsa short point": key_line("ecdsa-sha2-nistp256", sshstr(b"nistp256"), sshstr(POINT["nistp256"][:-1])),
    "ecdsa compressed point": key_line("ecdsa-sha2-nistp256", sshstr(b"nistp256"), sshstr(b"\x02" + bytes(64))),
    "ecdsa p384 with a p256 point": key_line("ecdsa-sha2-nistp384", sshstr(b"nistp384"), sshstr(POINT["nistp256"])),
    "ecdsa trailing": key_line("ecdsa-sha2-nistp256", sshstr(b"nistp256"), sshstr(POINT["nistp256"]), trailing=b"\0"),
    "sk without application": key_line("sk-ssh-ed25519@openssh.com", sshstr(bytes(range(32)))),
    "sk with a control character in the application": key_line("sk-ssh-ed25519@openssh.com", sshstr(bytes(range(32))),
                                                               sshstr(b"ssh:\x00")),
    "sk with an application that is not UTF-8": key_line("sk-ssh-ed25519@openssh.com", sshstr(bytes(range(32))),
                                                         sshstr(b"\xff\xfe")),
    "sk with trailing bytes": key_line("sk-ssh-ed25519@openssh.com", sshstr(bytes(range(32))), APP, trailing=b"\0"),
    "sk-ecdsa without application": key_line("sk-ecdsa-sha2-nistp256@openssh.com", sshstr(b"nistp256"),
                                             sshstr(POINT["nistp256"])),
    "cut off": f"ssh-ed25519 {base64.b64encode(sshstr(b'ssh-ed25519') + struct.pack('>I', 32) + bytes(5)).decode()} x",
    "inner type differs": "ssh-rsa " + VALID["ed25519"].split()[1] + " x",
    "not canonical base64": _noncanonical(VALID["p256"]),
    "not base64 at all": "ssh-ed25519 !!!notbase64!!! x",
    "non-ascii key data": "ssh-ed25519 é x",
    "ssh-dss": "ssh-dss " + VALID["ed25519"].split()[1] + " x",
    "options prefix": 'command="x" ' + VALID["ed25519"],
    "two keys": VALID["ed25519"] + "\n" + VALID["ed25519"],
    "carriage return": VALID["ed25519"] + "\r" + VALID["ed25519"],
    "private key armor": "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----",
    "private key armor in one line": "x -----BEGIN RSA PRIVATE KEY----- b3BlbnNzaC1rZXk",
    "comment with a bell": key_line("ssh-ed25519", sshstr(bytes(range(32))), comment="me\x07host"),
    "comment with a tab": key_line("ssh-ed25519", sshstr(bytes(range(32))), comment="me\thost"),
    "comment with a line separator": key_line("ssh-ed25519", sshstr(bytes(range(32))), comment="me host"),
    "line over 8 KiB": key_line("ssh-ed25519", sshstr(bytes(range(32))), comment="c" * 9000),
    "empty": "",
}


@pytest.mark.parametrize("which", sorted(BAD))
def test_parse_public_key_refuses_everything_else_without_echoing_it(which):
    bad = BAD[which]
    with pytest.raises(ServiceError) as e:
        account.parse_public_key(bad)
    echoed = {t for t in re.split(r"[\s=]", bad) if len(t) > 8} & {t for t in re.split(r"[\s=]", str(e.value)) if t}
    assert not echoed


def test_a_refused_key_never_reaches_the_panel(svc):
    for which in ("trailing bytes", "rsa 2047 bits", "ecdsa compressed point", "not canonical base64"):
        with pytest.raises(ServiceError):
            svc.run("account-ssh-key-import", "1", {"name": "ci", "public_key": BAD[which]}, confirm="1")
    assert sent_nothing(svc)


# -- 5: a backup tile without exactly one id is a contract error --------------------------------------------

NO_ID = PRODUCT.replace("showRecreateBackupModal(9001)", "restore()").replace("showDeleteBackupModal(9001)", "remove()")
TWO_IDS = PRODUCT.replace("showRecreateBackupModal(9001)", "showRecreateBackupModal(9002)")


@pytest.mark.parametrize("page", [NO_ID, TWO_IDS], ids=["no id", "two ids"])
def test_a_backup_tile_without_exactly_one_id_is_a_contract_error(tmp_path, page):
    assert page != PRODUCT
    svc = svc_for(tmp_path, page)
    with pytest.raises(ContractError):
        svc.run("backups", "1")
    for name, args in (("backup-create", {"title": "backup"}), ("backup-delete", {"backup": "9001"}),
                       ("backup-restore", {"backup": "9001"})):
        with pytest.raises(ContractError):  # even a dry run
            svc.run(name, "1", args, dry_run=True)
    assert sent_nothing(svc)
    report = svc.check("1")
    assert all(report[n].startswith("BROKEN") for n in ("backups", "backup-create", "backup-delete", "backup-restore"))


# -- 2: backup-create is verified by re-reading; restore and network reset claim nothing -----------------------

ITEM = re.compile(r'<div class="rootserver-backup-container rootserver-backup-item p-4">.*?(?=\s*<!--\[if ENDBLOCK\]>'
                  r'<!\[endif\]-->\s*<!--\[if BLOCK\]><!\[endif\]-->\s*<div class="rootserver-backup-container '
                  r'rootserver-backup-item-new)', re.S)
NEW_TILE = re.compile(r'<div class="rootserver-backup-container rootserver-backup-item-new.*?</div>\s*</div>', re.S)


def one_more_backup(page):  # a new backup appeared, the number of free slots is the same
    item = ITEM.search(page).group(0)
    return page.replace(item, item + item.replace("9001", "9002"))


def one_slot_less(page):  # a slot is used, no new backup is listed (yet)
    return NEW_TILE.sub("", page, count=1)


CREATE = "/customer/rootserver/1/backup/create"


@pytest.mark.parametrize("after,verified", [(one_more_backup, True), (one_slot_less, True), (lambda page: page, False)],
                         ids=["a new backup", "one slot less", "nothing changed"])
def test_backup_create_is_verified_only_when_the_panel_shows_the_backup(svc, after, verified):
    assert after(PRODUCT) != PRODUCT or verified is False
    svc.panel.http.hooks[CREATE] = lambda: svc.panel.pages.__setitem__(P, after(PRODUCT))
    r = svc.run("backup-create", "1", {"title": "before upgrade"}, confirm="1")
    assert r["verified"] is verified and "verify_error" not in r


def test_backup_create_is_not_verified_when_the_panel_says_it_failed(svc):
    svc.panel.http.answers[CREATE] = {"state": "failed", "message": "no"}
    svc.panel.http.hooks[CREATE] = lambda: svc.panel.pages.__setitem__(P, one_more_backup(PRODUCT))
    assert svc.run("backup-create", "1", {"title": "backup"}, confirm="1")["verified"] is False


def test_backup_create_verification_is_unknown_when_the_panel_cannot_be_read_afterwards(svc):
    def broken(path):
        raise PanelError("GET: the panel hiccuped")
    svc.panel.http.hooks[CREATE] = lambda: setattr(svc.panel, "page", broken)
    r = svc.run("backup-create", "1", {"title": "backup"}, confirm="1")
    assert r["verified"] is None and "verify_error" not in r  # unknown, not "failed", and not an error either


@pytest.mark.parametrize("name,args", [("backup-restore", {"backup": "9001"}), ("network-reset", {})])
def test_features_without_a_visible_effect_do_not_claim_to_be_verified(svc, name, args):
    assert REGISTRY[name].verify is None
    r = svc.run(name, "1", args, confirm="1", confirm_destroy="1")
    assert r["verified"] is None and "verify_error" not in r


# -- 8: network-reset posts what the page's own input fields hold, and only if they are empty -----------------

@pytest.mark.parametrize("attribute", ['value="hunter2-luks"', "value=hunter2-luks"])
def test_network_reset_refuses_inputs_that_are_not_empty_without_echoing_them(tmp_path, attribute):
    page = PRODUCT.replace('id="changeRootpasswordPassword"', f'id="changeRootpasswordPassword" {attribute}')
    assert page != PRODUCT
    svc = svc_for(tmp_path, page)
    for dry in (True, False):
        with pytest.raises(ContractError) as e:
            svc.run("network-reset", "1", {}, dry_run=dry, **({} if dry else {"confirm": "1", "confirm_destroy": "1"}))
        assert "hunter2" not in str(e.value)
    assert sent_nothing(svc)
    assert svc.check("1")["network-reset"].startswith("BROKEN")


def test_network_reset_sends_the_values_of_the_inputs_it_found(svc):
    r = svc.run("network-reset", "1", {}, confirm="1", confirm_destroy="1")
    assert svc.panel.http.forms == [("/customer/rootserver/1/resetnetwork", {"_token": "TOKEN", "password": "",
                                                                             "password_confirmation": ""})]
    explicit = svc_for(svc.panel.state_dir, PRODUCT.replace('id="changeRootpasswordPasswordConfirmation"',
                                                            'id="changeRootpasswordPasswordConfirmation" value=""'))
    explicit.run("network-reset", "1", {}, confirm="1", confirm_destroy="1")
    assert explicit.panel.http.forms == svc.panel.http.forms and r["verified"] is None


# -- 3: task-create acts later and repeatedly: destroying, never in the past, never twice --------------------

NOW = datetime.datetime(2026, 10, 13, 12, 0)  # panel time
TASK = {"action": "dump", "interval": "weekly", "start": "2026-10-14 13:50"}  # exactly the fixture's existing task


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(tasks, "_panel_now", lambda: NOW)


def test_task_create_is_a_destroying_feature_with_both_confirmations(svc):
    f = REGISTRY["task-create"]
    assert f.risk == "destroy" and "DESTROYING" in f.help and "repeatedly" in f.help
    args = {"action": "restart", "interval": "weekly", "start": "2099-01-01 03:30"}
    for confirmations in ({"confirm": "1"}, {"confirm_destroy": "1"}, {}):
        with pytest.raises(ServiceError):
            svc.run("task-create", "1", args, **confirmations)
    assert sent_nothing(svc)
    svc.run("task-create", "1", args, confirm="1", confirm_destroy="1")
    assert len(svc.panel.http.forms) == 1


def test_task_create_refuses_a_start_in_the_past(svc, clock):
    for start in ("2026-10-13 11:59", "2026-10-13T11:59", "2025-01-01 00:00"):
        for dry in (True, False):
            with pytest.raises(ServiceError, match="in the past"):
                svc.run("task-create", "1", {"action": "restart", "interval": "daily", "start": start}, dry_run=dry,
                        **({} if dry else {"confirm": "1", "confirm_destroy": "1"}))
    assert sent_nothing(svc)
    r = svc.run("task-create", "1", {"action": "restart", "interval": "daily", "start": "2026-10-13 12:00"}, dry_run=True)
    assert r["dry_run"]  # now itself is not earlier than now


def test_task_create_judges_the_start_by_the_panels_time_zone():
    berlin = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/Berlin")).replace(tzinfo=None)
    assert abs((tasks._panel_now() - berlin).total_seconds()) < 5 and tasks._panel_now().tzinfo is None


def test_task_create_with_the_real_clock(svc):
    day = datetime.timedelta(days=1)
    for start, ok_ in ((tasks._panel_now() - day, False), (tasks._panel_now() + day, True)):
        args = {"action": "restart", "interval": "daily", "start": f"{start:%Y-%m-%d %H:%M}"}
        if ok_:
            assert svc.run("task-create", "1", args, dry_run=True)["dry_run"]
        else:
            with pytest.raises(ServiceError):
                svc.run("task-create", "1", args, dry_run=True)


def test_task_create_without_a_time_zone_database_refuses(svc, monkeypatch):
    def missing(key):
        raise zoneinfo.ZoneInfoNotFoundError(key)
    monkeypatch.setattr(tasks, "ZoneInfo", missing)
    with pytest.raises(ServiceError, match="time zone"):
        svc.run("task-create", "1", {"action": "restart", "interval": "daily", "start": "2099-01-01 03:30"}, dry_run=True)
    assert sent_nothing(svc)


def test_task_create_refuses_an_identical_task(svc, clock):
    assert svc.run("tasks", "1")[0]["next"] == "14.10.2026 13:50"
    for dry in (True, False):
        with pytest.raises(ServiceError, match="already has this task"):
            svc.run("task-create", "1", TASK, dry_run=dry, **({} if dry else {"confirm": "1", "confirm_destroy": "1"}))
    assert sent_nothing(svc)
    for other in ({"start": "2026-10-14 13:51"}, {"interval": "daily"}, {"action": "restart"}):  # differs in one point
        assert svc.run("task-create", "1", {**TASK, **other}, dry_run=True)["dry_run"]


def test_task_create_dry_run_says_the_task_repeats_until_it_is_deleted(svc, clock):
    for interval in ("weekly", "2-weeks", "yearly"):
        would = svc.run("task-create", "1", {"action": "restart", "interval": interval, "start": "2026-11-01 03:00"},
                        dry_run=True)["would"]
        assert f"repeats {interval}" in would and "until it is deleted" in would and "task-delete" in would
    assert sent_nothing(svc)
