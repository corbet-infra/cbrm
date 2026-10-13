"""Regression tests for the findings of the second independent review: each test here fails on the code
as it was before the fix. The panel is mocked (no network), see test_wave2.py and test_service.py."""
import base64
import json
import re
import string
import struct
from dataclasses import replace

import pytest

from cbrm.errors import ContractError, ServiceError
from cbrm.features import account, common, registry
from cbrm.service import Service

import test_service
from test_wave2 import ACCOUNT, PRODUCT, fingerprint, make_key, sent_nothing, svc_for


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
