"""Desired state (`cbrm plan`, `cbrm apply`): the file format, the steps a plan finds, that a plan only reads, that apply
changes nothing without every confirmation and then runs the features with their own gates, and that a VM which
already matches gives `no change` through the real task parser."""
import datetime

import pytest
from test_wave3 import FakePanel, changes

from cbrm import cli, desired
from cbrm.errors import ServiceError
from cbrm.service import Service

NOW = datetime.datetime(2026, 10, 20, 1, 30)  # a Tuesday, panel time

WEEKLY = """schema = 1
[vms.17761]
machine = "brh-fra-k8s-01"
[[vms.17761.tasks]]
action = "dump"
interval = "weekly"
weekday = "monday"
time = "01:42"
notification_mode = "failed_only"
[vms.17762]
[[vms.17762.tasks]]
action = "dump"
interval = "weekly"
weekday = "tuesday"
time = "01:42"
notification_mode = "failed_only"
"""


def task(id_, next_, mode="failed_only", interval="weekly", action="dump"):
    return {"id": id_, "action": action, "label": "Backup erstellen", "interval": interval, "repeat": "Wöchentlich",
            "next": next_, "notification": {"mode": mode, "email": None, "label": "x"}}


class Backend:
    """Service's interface: `tasks` answers from `live`; every other call is recorded and changes nothing."""

    def __init__(self, live):
        self.live, self.calls = live, []

    def run(self, name, vm, args=None, *, confirm=None, confirm_destroy=None, dry_run=False):
        if name == "tasks":
            return [dict(t) for t in self.live.get(vm, [])]
        self.calls.append((name, vm, args, confirm, confirm_destroy))
        return {"result": {"state": "success"}, "verified": True}


@pytest.fixture
def wanted(tmp_path):
    path = tmp_path / "tasks.toml"
    path.write_text(WEEKLY)
    return desired.load(path)


def test_matching_panel_is_no_change(wanted):
    live = {"17761": [task("1", "26.10.2026 01:42")], "17762": [task("2", "20.10.2026 01:42")]}
    assert desired.plan(Backend(live), wanted, NOW) == []


def test_missing_wrong_and_extra_tasks(wanted):
    live = {"17761": [task("1", "26.10.2026 01:42", mode="none"), task("9", "21.10.2026 03:00", interval="daily")],
            "17762": [task("2", "21.10.2026 01:42")]}  # a Wednesday: not the declared Tuesday
    steps = desired.plan(Backend(live), wanted, NOW)
    assert [(s["vm"], s["feature"], s["args"], s["risk"]) for s in steps] == [
        ("17761", "task-notification-set", {"task": "1", "notification_mode": "failed_only"}, "change"),
        ("17761", "task-delete", {"task": "9"}, "change"),
        ("17762", "task-create", {"action": "dump", "interval": "weekly", "start": "2026-10-20 01:42",
                                  "notification_mode": "failed_only"}, "destroy"),
        ("17762", "task-delete", {"task": "2"}, "change")]
    assert steps[0]["machine"] == "brh-fra-k8s-01"


def test_first_start_is_the_next_declared_slot_with_a_lead():
    want = {"time": "01:42", "weekday": "tuesday"}
    assert desired.first_start(want, NOW) == "2026-10-20 01:42"
    assert desired.first_start(want, datetime.datetime(2026, 10, 20, 1, 35)) == "2026-10-27 01:42"
    assert desired.first_start({"time": "03:00", "weekday": None}, NOW) == "2026-10-20 03:00"


def test_apply_needs_every_confirmation_and_then_runs_the_features(wanted):
    live = {"17761": [task("1", "26.10.2026 01:42", mode="none")], "17762": []}
    backend = Backend(live)
    for confirm, destroy in (([], []), (["17761"], ["17762"]), (["17761", "17762"], [])):
        with pytest.raises(ServiceError, match="apply changes nothing"):
            desired.apply(backend, wanted, confirm, destroy, NOW)
        assert backend.calls == []
    res = desired.apply(backend, wanted, ["17761", "17762"], ["17762"], NOW)
    assert res["complete"] and res["changes"] == 2
    assert [(c[0], c[1], c[3], c[4]) for c in backend.calls] == [
        ("task-notification-set", "17761", "17761", None), ("task-create", "17762", "17762", "17762")]


def test_apply_stops_when_the_panel_does_not_show_a_change(wanted):
    class Unverified(Backend):
        def run(self, name, vm, args=None, **kw):
            out = super().run(name, vm, args, **kw)
            return out if name == "tasks" else {"result": {}, "verified": False}
    backend = Unverified({"17761": [], "17762": []})
    res = desired.apply(backend, wanted, ["17761", "17762"], ["17761", "17762"], NOW)
    assert not res["complete"] and len(backend.calls) == 1


@pytest.mark.parametrize("text, message", [
    ("schema = 2\n", "schema = 1"),
    ("schema = 1\n[vms.x]\n", "VM number"),
    ("schema = 1\n[[vms.1.tasks]]\naction='dump'\ninterval='weekly'\ntime='01:42'\n", "weekday"),
    ("schema = 1\n[[vms.1.tasks]]\naction='dump'\ninterval='daily'\nweekday='monday'\ntime='01:42'\n", "weekday"),
    ("schema = 1\n[[vms.1.tasks]]\naction='dump'\ninterval='daily'\ntime='1:42'\n", "time"),
    ("schema = 1\n[[vms.1.tasks]]\naction='dump'\ninterval='daily'\ntime='01:42'\nnotification_email='a@b.c'\n", "mode"),
    ("schema = 1\n[[vms.1.tasks]]\naction='dump'\ninterval='daily'\ntime='01:42'\ncolour='red'\n", "knows"),
])
def test_file_errors(tmp_path, text, message):
    path = tmp_path / "bad.toml"
    path.write_text(text)
    with pytest.raises(ServiceError, match=message):
        desired.load(path)


def test_the_real_task_parser_gives_no_change_and_sends_nothing(tmp_path, capsys, monkeypatch):
    """VM 1 of the anonymised panel rendering has the weekly backup on Monday 01:42 with failed_only e-mail."""
    svc = Service(FakePanel(tmp_path), allow=["1"])
    path = tmp_path / "tasks.toml"
    path.write_text(WEEKLY.split("[vms.17762]")[0].replace("17761", "1"))
    assert desired.plan(svc, desired.load(path), NOW) == []
    assert changes(svc) == []
    monkeypatch.setattr("cbrm.client.backend", lambda: svc)
    cli.main(["plan", str(path)])
    assert capsys.readouterr().out.strip() == "no change"
    cli.main(["apply", str(path)])  # nothing to change: no confirmation needed, nothing sent
    assert capsys.readouterr().out.strip() == "no change" and changes(svc) == []


def test_several_files_form_one_state_and_a_vm_is_declared_once(tmp_path):
    first, second = tmp_path / "a.toml", tmp_path / "b.toml"
    first.write_text(WEEKLY.split("[vms.17762]")[0])
    second.write_text("schema = 1\n[vms.17762]\n" + WEEKLY.split("[vms.17762]")[1])
    assert sorted(desired.load_all([first, second])) == ["17761", "17762"]
    with pytest.raises(ServiceError, match="already declared"):
        desired.load_all([first, first])
