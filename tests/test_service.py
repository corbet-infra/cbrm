"""The rules every interface relies on, checked against a fake panel (no network)."""
from pathlib import Path

import pytest

from cbrm.errors import ContractError, ServiceError
from cbrm.features import REGISTRY
from cbrm.service import Service

FIXTURE = (Path(__file__).parent / "fixtures" / "product.html").read_text()


class FakePanel:
    def __init__(self, tmp: Path, html: str = FIXTURE):
        self.state_dir, self.calls, self.html = tmp, [], html

    def products(self): return {"1": "2", "3": "4"}
    def page(self, path): return self.html
    def status(self, vm): return {"vm": vm, "state": "Online"}
    def power(self, vm, action): self.calls.append(("power", vm, action)); return {"state": "success"}
    def templates(self, vm): return {"Arch Linux": "53"}
    def ssh_keys(self, vm): return {"Personal": "1839"}
    def root_password(self, vm): return "secret-value"
    def reinstall(self, vm, t, k): self.calls.append(("reinstall", vm, t, tuple(k))); return {"state": "success"}
    def get_json(self, path, params=None): self.calls.append(("get", path, params)); return {"state": "success"}


@pytest.fixture
def svc(tmp_path):
    return Service(FakePanel(tmp_path), allow=["1"])


def test_allow_list(svc):
    assert [v["vm"] for v in svc.vms()] == ["1"]
    with pytest.raises(ServiceError):
        svc.run("status", "3")


@pytest.mark.parametrize("name", [n for n, f in REGISTRY.items() if f.risk != "read"])
def test_every_non_read_feature_needs_confirm(svc, name):
    with pytest.raises(ServiceError):
        svc.run(name, "1", {}, confirm="3")
    assert svc.panel.calls == []


def test_destroy_needs_both_confirmations(svc):
    args = {"template": "Arch Linux", "ssh_keys": ["Personal"]}
    for c, d in (("1", None), ("1", "3"), (None, "1")):
        with pytest.raises(ServiceError):
            svc.run("reinstall", "1", args, confirm=c, confirm_destroy=d)
    assert svc.panel.calls == []
    svc.run("reinstall", "1", args, confirm="1", confirm_destroy="1")
    assert svc.panel.calls == [("reinstall", "1", "53", ("1839",))]


def test_dry_run_sends_nothing(svc):
    r = svc.run("reinstall", "1", {"template": "Arch Linux"}, dry_run=True)
    assert r["dry_run"] and "reinstall" in r["would"] and svc.panel.calls == []


def test_unknown_names_and_arguments_are_refused(svc):
    with pytest.raises(ServiceError):
        svc.run("reinstall", "1", {"template": "Arch"}, confirm="1", confirm_destroy="1")
    with pytest.raises(ServiceError):
        svc.run("status", "1", {"bogus": 1})
    with pytest.raises(ServiceError):
        svc.run("power", "1", {"action": "reinstall"}, confirm="1")
    assert svc.panel.calls == []


def test_secrets_never_reach_the_audit_log(svc):
    with pytest.raises(ServiceError):
        svc.run("root-password", "1")
    assert svc.run("root-password", "1", confirm="1")["root_password"] == "secret-value"
    assert "secret-value" not in svc.audit_path.read_text()


def test_parsers_against_the_panel_snapshot(svc):
    assert svc.run("drives", "1") == [{"drive": "ide0", "content": ""}, {"drive": "ide2", "content": "nixos-installer.iso"}]
    assert [i["key"] for i in svc.run("boot-order", "1")] == ["scsi0", "ide0", "net0"]


def test_boot_order_must_be_a_permutation(svc):
    with pytest.raises(ServiceError):
        svc.run("boot-order-set", "1", {"order": ["ide0", "scsi0"]}, confirm="1")
    r = svc.run("boot-order-set", "1", {"order": ["ide0", "scsi0", "net0"]}, dry_run=True)
    assert "boot_order=ide0;scsi0;net0" in r["would"]


def test_a_changed_panel_stops_before_sending(tmp_path):
    changed = FIXTURE.replace("boot_order", "boot_sequence").replace("unmountIso", "ejectIso")
    svc = Service(FakePanel(tmp_path, changed), allow=["1"])
    with pytest.raises(ContractError):
        svc.run("boot-order-set", "1", {"order": ["ide0", "scsi0", "net0"]}, confirm="1")
    with pytest.raises(ContractError):
        svc.run("iso-unmount", "1", {"drive": "ide2"}, confirm="1")
    assert svc.panel.calls == []
    report = svc.check("1")
    assert report["boot-order-set"].startswith("BROKEN") and report["iso-unmount"].startswith("BROKEN")


def test_mount_counts_only_the_exact_file(tmp_path, monkeypatch):
    """The panel reports success for an own ISO that has not finished downloading; nothing is inserted."""
    from cbrm.features import media
    from cbrm.features.registry import Ctx
    monkeypatch.setattr(media.time, "sleep", lambda s: None)
    ctx = Ctx(FakePanel(tmp_path))
    assert media._verify_mount(ctx, "1", {"mounted": {"file": "nixos-installer.iso"}}, "ide2", "x")
    assert not media._verify_mount(ctx, "1", {"mounted": {"file": "other.iso"}}, "ide2", "x")
    assert not media._verify_mount(ctx, "1", {"mounted": {"file": "nixos-installer.iso"}}, "ide0", "x")
