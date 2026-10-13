"""The rules every interface relies on, checked against a fake panel (no network)."""
from pathlib import Path

import pytest

from cbrm.service import Service, ServiceError


class FakePanel:
    def __init__(self, tmp: Path):
        self.state_dir, self.calls = tmp, []

    def products(self): return {"1": "p1", "2": "p2"}
    def status(self, vm): return {"vm": vm, "state": "Online"}
    def power(self, vm, action): self.calls.append((vm, action)); return {"state": "success"}
    def templates(self, vm): return {"Arch Linux": "53"}
    def ssh_keys(self, vm): return {"Personal": "1839"}
    def reinstall(self, vm, t, k): self.calls.append((vm, "reinstall", t, tuple(k))); return {"state": "success"}
    def root_password(self, vm): return "secret-value"


@pytest.fixture
def svc(tmp_path):
    return Service(FakePanel(tmp_path), allow=["1"])


def test_allow_list_limits_reading(svc):
    assert [v["vm"] for v in svc.vms()] == ["1"]
    with pytest.raises(ServiceError):
        svc.status("2")


def test_changing_needs_the_target_repeated(svc):
    for confirm in ("", "2", None):
        with pytest.raises(ServiceError):
            svc.power("1", "restart", confirm)
    assert svc.panel.calls == []


def test_power_is_audited(svc):
    assert svc.power("1", "restart", "1") == {"state": "success"}
    assert svc.panel.calls == [("1", "restart")]
    log = svc.audit_path.read_text()
    assert "power 1 restart requested" in log and "power 1 restart ->" in log


def test_unknown_action_is_refused(svc):
    with pytest.raises(ServiceError):
        svc.power("1", "reinstall", "1")
    assert svc.panel.calls == []


def test_reinstall_needs_both_confirmations(svc):
    for c, d in (("1", ""), ("1", "2"), ("", "1"), ("2", "1")):
        with pytest.raises(ServiceError):
            svc.reinstall("1", "Arch Linux", ["Personal"], c, d)
    assert svc.panel.calls == []
    svc.reinstall("1", "Arch Linux", ["Personal"], "1", "1")
    assert svc.panel.calls == [("1", "reinstall", "53", ("1839",))]


def test_reinstall_refuses_unknown_names(svc):
    with pytest.raises(ServiceError):
        svc.reinstall("1", "Arch", ["Personal"], "1", "1")
    with pytest.raises(ServiceError):
        svc.reinstall("1", "Arch Linux", ["nope"], "1", "1")
    assert svc.panel.calls == []


def test_root_password_is_audited_without_value(svc):
    with pytest.raises(ServiceError):
        svc.root_password("1", "")
    assert svc.root_password("1", "1")["root_password"] == "secret-value"
    assert "secret-value" not in svc.audit_path.read_text()
