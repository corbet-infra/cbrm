"""Scheduled tasks ('Aufgaben'): actions the panel runs regularly for the VM. The automatic backup is one of them
(action `dump`, usually weekly).

Creating a task is a `destroy` feature on purpose: it does nothing now, but the panel then acts on its own, again
and again, until the task is deleted: a stop or restart task keeps interrupting the VM, and a backup task may
rotate or overwrite the backups.
"""
from __future__ import annotations

import datetime
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..errors import ContractError, ServiceError
from .common import get_json, panel_answer, panel_date, post_form, require_names, require_post, settle, text, tolerant
from .registry import Param, feature

PANEL_TIME_ZONE = "Europe/Berlin"


def _panel_now() -> datetime.datetime:
    """Now in panel time (Europe/Berlin), as the naive wall-clock time the panel's forms use."""
    try:
        return datetime.datetime.now(ZoneInfo(PANEL_TIME_ZONE)).replace(tzinfo=None)
    except ZoneInfoNotFoundError:
        raise ServiceError(f"cannot tell the panel's time ({PANEL_TIME_ZONE}): this system has no time zone database "
                           "(install the tzdata package)") from None


def _component(ctx, vm):
    return ctx.product_page(vm).component("task")


def _form_options(page) -> dict[str, dict[str, str]]:
    """The panel's own choices for a new task: field name -> {value: label}."""
    require_names(page, "methode", "interval", "next_execution_at", "notification_mode", "notification_email")
    out = {}
    for field in ("methode", "interval", "notification_mode"):
        sel = page.tree.css_first(f'select[name="{field}"]')
        if sel is None:
            raise ContractError(f"{page.path}: the task form's '{field}' is no longer a selection")
        out[field] = {o.attributes["value"]: text(o) for o in sel.css("option") if o.attributes.get("value")}
        if not out[field]:
            raise ContractError(f"{page.path}: the task form offers no {field} choices")
    if "" not in {o.attributes.get("value") for o in page.tree.css('select[name="notification_mode"] option')}:
        raise ContractError(f"{page.path}: the task form no longer offers 'no e-mail' as the notification default")
    return out


def _read(comp, labels: dict[str, str] | None = None, intervals: dict[str, str] | None = None) -> list[dict]:
    """The component's tasks. `labels` and `intervals` map an action's and an interval's value to its label, to name
    them by their values (the ones `task-create` takes); an interval the form does not offer stays None."""
    if comp.tree.css_first(".rootserver-task-item-new") is None:
        raise ContractError("task: the 'new task' tile is gone from the rendering")
    by_label = {v: k for k, v in (labels or {}).items()}
    by_interval = {v: k for k, v in (intervals or {}).items()}
    out = []
    for node in comp.tree.css(".rootserver-task-item"):
        ids = set(re.findall(r"showDeleteTaskModal\((\d+)\)", node.html))
        title = node.css_first("h3 span")
        if len(ids) != 1 or title is None:
            raise ContractError("task: a task without an id or a title in the rendering")
        facts = {}
        for p in node.css("p.rootserver-task-p"):
            label, _, val = text(p).partition(":")
            facts[label.strip()] = val.strip()
        bell = node.css_first("[data-task-id]")
        notification = None
        if bell is not None:
            notification = {"mode": bell.attributes.get("data-mode") or "none",
                            "email": bell.attributes.get("data-email") or None,
                            "label": facts.get("E-Mail-Benachrichtigung")}
        task_id = ids.pop()
        if bell is not None and bell.attributes.get("data-task-id") != task_id:
            raise ContractError(f"task: the notification button of task {task_id} names another task")
        out.append({"id": task_id, "action": by_label.get(text(title), text(title)), "label": text(title),
                    "interval": by_interval.get(facts.get("Wiederholung")),
                    "repeat": facts.get("Wiederholung"), "next": panel_date(facts.get("Nächste Aktion")),
                    "notification": notification})
    return out


def _tasks(ctx, vm) -> list[dict]:
    page = ctx.product_page(vm)
    options = _form_options(page)
    return _read(page.component("task"), options["methode"], options["interval"])


@feature("tasks", "read", "List the scheduled tasks",
         "The VM's scheduled tasks: id, action and interval (the values task-create takes), the interval's label, "
         "next run (panel time) and the e-mail notification (mode none, always or failed_only, and the address if "
         "not the account's)")
def _tasks_feature(ctx, vm):
    return _tasks(ctx, vm)


def _check_create(ctx, vm):
    page = ctx.product_page(vm)
    path = f"/customer/rootserver/{vm}/scheduled_task/create"
    page.require_endpoint(path)
    require_post(page, path, "methode", "interval", "next_execution_at", "notification_mode",
                 "notification_email")
    options = _form_options(page)
    _read(page.component("task"))
    return page, path, options


@tolerant
def _verify_create(ctx, vm, result, action, interval, start, notification_mode=None, notification_email=None):
    def seen():
        ctx.fresh(vm)
        return any(t["id"] not in result["known_ids"] and t["label"] == result["task"]["action"]
                   and t["repeat"] == result["task"]["interval"] and t["next"] == result["task"]["next"]
                   for t in _tasks(ctx, vm))
    return result.get("state") == "success" and settle(seen)


@feature("task-create", "destroy", "Schedule a repeating action such as a backup",
         "Schedule an action for the VM (action dump = backup, start, restart, shutdown, stop; interval daily, 2-days, "
         "3-days, 5-days, weekly, 2-weeks, monthly, yearly). DESTROYING: the task acts later and repeatedly without you "
         "until it is deleted (a stop or restart task keeps interrupting the VM, a backup task may rotate or overwrite "
         "backups), so it needs both confirmations",
         (Param("action", "what to run: the panel's own choices (dump, start, restart, shutdown, stop)"),
          Param("interval", "how often: the panel's own choices (daily, 2-days, 3-days, 5-days, weekly, 2-weeks, "
                            "monthly, yearly)"),
          Param("start", "first run in panel time (Europe/Berlin), YYYY-MM-DD HH:MM, not in the past"),
          Param("notification_mode", "optional e-mail notification: the panel's own choices (always, failed_only); "
                                     "default: none (the panel's 'Keine E-Mail')", required=False),
          Param("notification_email", "optional: send the notification to this address instead of the account's "
                                      "(needs notification_mode); default: the account's own address",
                required=False)),
         verify=_verify_create, check=_check_create)
def _task_create(ctx, vm, action, interval, start, notification_mode=None, notification_email=None):
    page, path, options = _check_create(ctx, vm)
    for field, given, name in (("methode", action, "action"), ("interval", interval, "interval")):
        if given not in options[field]:
            raise ServiceError(f"{name} must be one of {', '.join(options[field])}")
    try:
        when = datetime.datetime.strptime(start.strip().replace("T", " "), "%Y-%m-%d %H:%M")  # noqa: DTZ007  panel wall-clock time
    except ValueError:
        raise ServiceError("start must look like 2026-10-14 03:30 (panel time, Europe/Berlin)") from None
    mode, email = (notification_mode or "").strip(), (notification_email or "").strip()
    if mode and mode not in options["notification_mode"]:
        raise ServiceError(f"notification_mode must be one of {', '.join(options['notification_mode'])} "
                           "(or left out for no e-mail)")
    if email and not mode:
        raise ServiceError("notification_email needs a notification_mode (the panel sends no e-mail without one)")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ServiceError("notification_email must be an e-mail address")
    now = _panel_now()
    if when < now:
        raise ServiceError(f"start {when:%Y-%m-%d %H:%M} is in the past: it is {now:%Y-%m-%d %H:%M} in panel time "
                           f"({PANEL_TIME_ZONE})")
    tasks = _read(page.component("task"))
    data = {"methode": action, "interval": interval, "next_execution_at": when.strftime("%Y-%m-%dT%H:%M"),
            "notification_mode": mode, "notification_email": email}
    expected = {"action": options["methode"][action], "interval": options["interval"][interval],
                "next": when.strftime("%d.%m.%Y %H:%M")}
    same = [t for t in tasks if (t["label"], t["repeat"], t["next"]) == (expected["action"], expected["interval"],
                                                                         expected["next"])]
    if same:
        raise ServiceError(f"VM {vm} already has this task (id {same[0]['id']}: {expected['action']}, "
                           f"{expected['interval']}, next {expected['next']}); creating it again would run it twice")
    return ctx.send(f"POST {path} {data}: creates the task '{expected['action']}' for {when:%Y-%m-%d %H:%M} panel time; "
                    f"it then repeats {interval} ({expected['interval']}) until it is deleted (`task-delete`)",
                    lambda: {**panel_answer(post_form(ctx, page, path, data)), "task": expected,
                             "known_ids": [t["id"] for t in tasks]})


def _check_delete(ctx, vm):
    page = ctx.product_page(vm)
    page.require_endpoint(f"/customer/rootserver/{vm}/scheduled_task/delete/")
    return page


@tolerant
def _verify_delete(ctx, vm, result, task):
    def gone():
        ctx.fresh(vm)
        return task not in [t["id"] for t in _tasks(ctx, vm)]
    return result.get("state") == "success" and settle(gone)


@feature("task-delete", "change", "Delete a scheduled task",
         "Delete a scheduled task (deleting the weekly backup task switches the automatic backup off)",
         (Param("task", "the task's id from `tasks`"),), verify=_verify_delete,
         check=_check_delete)
def _task_delete(ctx, vm, task):
    _check_delete(ctx, vm)
    tasks = _tasks(ctx, vm)
    found = [t for t in tasks if t["id"] == str(task)]
    if not found:
        raise ServiceError(f"VM {vm} has no task {task!r}; it has {[t['id'] for t in tasks]}")
    path = f"/customer/rootserver/{vm}/scheduled_task/delete/{found[0]['id']}"
    return ctx.send(f"GET {path} [{found[0]['label']}, {found[0]['repeat']}, next {found[0]['next']}]",
                    lambda: panel_answer(get_json(ctx, path)))


# -- the e-mail notification of a task -----------------------------------------------------------------------

def _notification_options(page) -> dict[str, str]:
    """The panel's choices in the task notification dialog: value -> label ('' = no e-mail)."""
    sel = page.tree.css_first("select#task_notification_mode_select")
    if sel is None or page.tree.css_first("#task_notification_email") is None:
        raise ContractError(f"{page.path}: the task notification dialog's fields are gone")
    options = {o.attributes.get("value") or "": text(o) for o in sel.css("option")}
    if "" not in options or len(options) < 2:
        raise ContractError(f"{page.path}: the task notification dialog no longer offers 'no e-mail' and the modes")
    return options


def _check_notification(ctx, vm):
    page = ctx.product_page(vm)
    path = f"/customer/rootserver/{vm}/scheduled_task/notification/"
    require_post(page, path, "notification_mode", "notification_email", suffixed=True)
    options = _notification_options(page)
    _read(page.component("task"))
    return page, path, options


@tolerant
def _verify_notification(ctx, vm, result, task, notification_mode, notification_email=None):
    def seen():
        ctx.fresh(vm)
        t = next((t for t in _tasks(ctx, vm) if t["id"] == result["task"]), None)
        n = t and t["notification"]
        return bool(n) and n["mode"] == result["mode"] and (n["email"] or "") == result["email"]
    return result.get("state") == "success" and settle(seen)


@feature("task-notification-set", "change", "Set a scheduled task's e-mail notification",
         "Set a scheduled task's e-mail notification (the panel's bell on the task): none, always or failed_only, "
         "optionally to another address than the account's",
         (Param("task", "the task's id from `tasks`"),
          Param("notification_mode", "none, or the panel's own choices (always, failed_only)"),
          Param("notification_email", "optional: send it to this address instead of the account's (needs a mode other "
                                      "than none)", required=False)),
         verify=_verify_notification, check=_check_notification)
def _task_notification_set(ctx, vm, task, notification_mode, notification_email=None):
    page, path, options = _check_notification(ctx, vm)
    mode = notification_mode.strip()
    mode = "" if mode == "none" else mode
    modes = [m for m in options if m]
    if mode not in options:
        raise ServiceError(f"notification_mode must be none or one of {', '.join(modes)}")
    email = (notification_email or "").strip()
    if email and not mode:
        raise ServiceError("notification_email needs a notification_mode other than none")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ServiceError("notification_email must be an e-mail address")
    tasks = _read(page.component("task"))
    found = [t for t in tasks if t["id"] == str(task).strip()]
    if not found:
        raise ServiceError(f"VM {vm} has no task {task!r}; it has {[t['id'] for t in tasks]}")
    if found[0]["notification"] is None:
        raise ContractError(f"task: task {found[0]['id']} has no notification button")
    data = {"notification_mode": mode, "notification_email": email}
    target = f"{path}{found[0]['id']}"
    return ctx.send(f"POST {target} {data} [{found[0]['label']}, {found[0]['repeat']}; was "
                    f"{found[0]['notification']['mode']}]",
                    lambda: {**panel_answer(post_form(ctx, page, target, data)), "task": found[0]["id"],
                             "mode": mode or "none", "email": email})
