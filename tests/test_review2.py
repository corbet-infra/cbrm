"""Regression tests for the findings of the second independent review: each test here fails on the code
as it was before the fix. The panel is mocked (no network), see test_wave2.py and test_service.py."""
import json
import re
from dataclasses import replace

import pytest

from cbrm.errors import ContractError, PanelError, ServiceError
from cbrm.features import REGISTRY, common, registry
from cbrm.service import Service

import test_service
from test_wave2 import A, ACCOUNT, EMPTY, P, PRODUCT, fingerprint, make_key, sent_nothing, svc_for


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
