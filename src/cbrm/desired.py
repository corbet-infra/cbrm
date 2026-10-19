"""Desired state: the scheduled tasks some VMs should have, compared with what the panel shows (`cbrm plan`) and made
so (`cbrm apply`). The panel has no API and keeps no declaration of its own, so this is where a fleet keeps it.

The file is TOML; every listed VM's task list is COMPLETE (a task the panel shows and the file does not is deleted
on apply), a VM that is not listed is not touched:

    schema = 1

    [vms.10001]
    machine = "web-01"                  # optional, for people only
    [[vms.10001.tasks]]
    action = "dump"                     # the panel's values, as `task-create` takes them
    interval = "weekly"
    weekday = "monday"                  # weekly and 2-weeks only: the day the task runs
    time = "01:42"                      # panel time (Europe/Berlin)
    notification_mode = "failed_only"   # none (default), always, failed_only
    # notification_email = "ops@example.test"   # optional: another address than the account's

A task matches when action, interval, weekday and time of its next run agree; its e-mail notification is then
compared on its own. The plan's steps are ordinary features (`task-create`, `task-notification-set`, `task-delete`)
with their own checks, audit and verification; `apply` needs every VM it changes repeated in `--confirm` and, for a
`task-create` (a destroying feature: it acts later and repeatedly), in `--confirm-destroy` as well.
"""
from __future__ import annotations

import datetime
import re
import tomllib
from pathlib import Path

from .errors import ServiceError
from .features import REGISTRY, tasks

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEKDAY_INTERVALS = ("weekly", "2-weeks")
TASK_KEYS = {"action", "interval", "weekday", "time", "notification_mode", "notification_email"}
MODES = ("none", "always", "failed_only")
LEAD = datetime.timedelta(minutes=10)  # a task created now starts at least this far ahead (the panel refuses the past)


def load(path: str | Path) -> dict[str, dict]:
    """The file as {vm: {"machine": str | None, "tasks": [task, ...]}}, every task with all keys."""
    try:
        doc = tomllib.loads(Path(path).read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ServiceError(f"{path}: {e}") from None
    if doc.get("schema") != 1 or set(doc) - {"schema", "vms"}:
        raise ServiceError(f"{path}: needs `schema = 1` and `vms`, nothing else")
    out = {}
    for vm, entry in (doc.get("vms") or {}).items():
        if not re.fullmatch(r"\d+", vm) or not isinstance(entry, dict) or set(entry) - {"machine", "tasks"}:
            raise ServiceError(f"{path}: vms.{vm}: a VM number with `tasks` (and optionally `machine`)")
        wanted = []
        for i, t in enumerate(entry.get("tasks", [])):
            where = f"{path}: vms.{vm}.tasks[{i}]"
            if set(t) - TASK_KEYS or not {"action", "interval", "time"} <= set(t):
                raise ServiceError(f"{where}: needs action, interval and time; knows {', '.join(sorted(TASK_KEYS))}")
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(t["time"])):
                raise ServiceError(f"{where}: time must look like 01:42 (panel time)")
            weekday = t.get("weekday")
            if (weekday is None) != (t["interval"] not in WEEKDAY_INTERVALS) or (weekday and weekday not in WEEKDAYS):
                raise ServiceError(f"{where}: weekday (monday … sunday) is required for {' and '.join(WEEKDAY_INTERVALS)} "
                                   "and not allowed for other intervals")
            mode, email = t.get("notification_mode", "none"), t.get("notification_email") or ""
            if mode not in MODES or (email and mode == "none"):
                raise ServiceError(f"{where}: notification_mode must be one of {', '.join(MODES)}; an address needs a mode")
            wanted.append({"action": t["action"], "interval": t["interval"], "weekday": weekday, "time": t["time"],
                           "notification_mode": mode, "notification_email": email})
        out[vm] = {"machine": entry.get("machine"), "tasks": wanted}
    return out


def load_all(paths) -> dict[str, dict]:
    """Several files (e.g. one per machine) as one desired state; a VM may appear in one file only."""
    out = {}
    for path in paths:
        for vm, entry in load(path).items():
            if vm in out:
                raise ServiceError(f"{path}: VM {vm} is already declared in another file")
            out[vm] = entry
    return out


def _next_run(live: dict) -> datetime.datetime | None:
    try:
        return datetime.datetime.strptime(live.get("next") or "", "%d.%m.%Y %H:%M")  # noqa: DTZ007  panel wall clock
    except ValueError:
        return None


def _matches(want: dict, live: dict) -> bool:
    when = _next_run(live)
    return (live["action"] == want["action"] and live.get("interval") == want["interval"] and when is not None
            and when.strftime("%H:%M") == want["time"]
            and (want["weekday"] is None or WEEKDAYS[when.weekday()] == want["weekday"]))


def _notification(live: dict) -> tuple[str, str]:
    n = live.get("notification") or {}
    return n.get("mode") or "none", n.get("email") or ""


def first_start(want: dict, now: datetime.datetime) -> str:
    """The first run of a new task: the next `weekday` at `time` (or the next `time`), at least LEAD from now."""
    hour, minute = map(int, want["time"].split(":"))
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    while start < now + LEAD or (want["weekday"] and WEEKDAYS[start.weekday()] != want["weekday"]):
        start += datetime.timedelta(days=1)
    return start.strftime("%Y-%m-%d %H:%M")


def plan(backend, desired: dict[str, dict], now: datetime.datetime | None = None) -> list[dict]:
    """The steps that make the panel show `desired`; reads only (the `tasks` feature of every listed VM)."""
    now = now or tasks._panel_now()
    steps = []
    for vm, entry in desired.items():
        live = list(backend.run("tasks", vm))
        creates, updates = [], []
        for want in entry["tasks"]:
            found = next((t for t in live if _matches(want, t)), None)
            if found is None:
                args = {"action": want["action"], "interval": want["interval"], "start": first_start(want, now)}
                if want["notification_mode"] != "none":
                    args["notification_mode"] = want["notification_mode"]
                if want["notification_email"]:
                    args["notification_email"] = want["notification_email"]
                creates.append({"feature": "task-create", "args": args, "why": "missing: " + describe(want)})
                continue
            live.remove(found)
            if _notification(found) != (want["notification_mode"], want["notification_email"]):
                args = {"task": found["id"], "notification_mode": want["notification_mode"]}
                if want["notification_email"]:
                    args["notification_email"] = want["notification_email"]
                updates.append({"feature": "task-notification-set", "args": args,
                                "why": f"notification is {'/'.join(x for x in _notification(found) if x)}"})
        # New tasks first and deletions last, so a moved backup is never missing in between.
        deletes = [{"feature": "task-delete", "args": {"task": t["id"]},
                    "why": f"not declared: {t['label']}, {t['repeat']}, next {t['next']}"} for t in live]
        for step in creates + updates + deletes:
            steps.append({"vm": vm, "machine": entry["machine"], "risk": REGISTRY[step["feature"]].risk, **step})
    return steps


def describe(want: dict) -> str:
    day = f" {want['weekday']}" if want["weekday"] else ""
    note = f", e-mail {want['notification_mode']}" if want["notification_mode"] != "none" else ""
    return f"{want['action']} {want['interval']}{day} {want['time']}{note}"


def apply(backend, desired: dict[str, dict], confirm: list[str], confirm_destroy: list[str],
          now: datetime.datetime | None = None) -> dict:
    """Plan afresh, then run the steps, but only when every changed VM is confirmed (all or nothing)."""
    steps = plan(backend, desired, now)
    missing = sorted({s["vm"] for s in steps} - set(confirm))
    missing_destroy = sorted({s["vm"] for s in steps if s["risk"] == "destroy"} - set(confirm_destroy))
    if missing or missing_destroy:
        raise ServiceError("apply changes nothing unless every VM it changes is repeated: "
                           + (f"--confirm {' '.join(missing)} " if missing else "")
                           + (f"--confirm-destroy {' '.join(missing_destroy)}" if missing_destroy else "")
                           + " (see `cbrm plan`)")
    done = []
    for s in steps:
        result = backend.run(s["feature"], s["vm"], s["args"], confirm=s["vm"],
                             confirm_destroy=s["vm"] if s["risk"] == "destroy" else None)
        done.append({**s, "verified": result.get("verified") if isinstance(result, dict) else None})
        if done[-1]["verified"] is False:
            break  # the panel does not show the effect: look before going on
    return {"steps": done, "changes": len(done), "complete": len(done) == len(steps)
            and all(d["verified"] is not False for d in done)}
