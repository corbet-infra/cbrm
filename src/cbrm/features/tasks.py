"""Scheduled tasks ('Aufgaben'): actions the panel runs regularly for the VM. The automatic backup is one of them
(action `dump`, usually weekly)."""
from __future__ import annotations

import datetime
import re

from ..errors import ContractError, ServiceError
from .common import (get_json, panel_answer, panel_date, post_form, require_names, require_post, settle, text, tolerant)
from .registry import Param, feature


def _component(ctx, vm):
    return ctx.product_page(vm).component("task")


def _form_options(page) -> dict[str, dict[str, str]]:
    """The panel's own choices for a new task: field name -> {value: label}."""
    require_names(page, "methode", "interval", "next_execution_at")
    out = {}
    for field in ("methode", "interval"):
        sel = page.tree.css_first(f'select[name="{field}"]')
        if sel is None:
            raise ContractError(f"{page.path}: the task form's '{field}' is no longer a selection")
        out[field] = {o.attributes["value"]: text(o) for o in sel.css("option") if o.attributes.get("value")}
        if not out[field]:
            raise ContractError(f"{page.path}: the task form offers no {field} choices")
    return out


def _read(comp, labels: dict[str, str] | None = None) -> list[dict]:
    """The component's tasks. `labels` maps an action's value to its label, to name the action by its value."""
    if comp.tree.css_first(".rootserver-task-item-new") is None:
        raise ContractError("task: the 'new task' tile is gone from the rendering")
    by_label = {v: k for k, v in (labels or {}).items()}
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
        out.append({"id": ids.pop(), "action": by_label.get(text(title), text(title)), "label": text(title),
                    "repeat": facts.get("Wiederholung"), "next": panel_date(facts.get("Nächste Aktion"))})
    return out


def _tasks(ctx, vm) -> list[dict]:
    page = ctx.product_page(vm)
    return _read(page.component("task"), _form_options(page)["methode"])


@feature("tasks", "read", "The VM's scheduled tasks: id, action, repeat interval and next run (panel time)")
def _tasks_feature(ctx, vm):
    return _tasks(ctx, vm)


def _check_create(ctx, vm):
    page = ctx.product_page(vm)
    path = f"/customer/rootserver/{vm}/scheduled_task/create"
    page.require_endpoint(path)
    require_post(page, path, "methode", "interval", "next_execution_at")
    options = _form_options(page)
    _read(page.component("task"))
    return page, path, options


@tolerant
def _verify_create(ctx, vm, result, action, interval, start):
    def seen():
        ctx.fresh(vm)
        return any(t["id"] not in result["known_ids"] and t["label"] == result["task"]["action"]
                   and t["repeat"] == result["task"]["interval"] and t["next"] == result["task"]["next"]
                   for t in _tasks(ctx, vm))
    return result.get("state") == "success" and settle(seen)


@feature("task-create", "change",
         "Schedule an action for the VM (action dump = backup, start, restart, shutdown, stop; interval daily, 2-days, "
         "3-days, 5-days, weekly, 2-weeks, monthly, yearly). A stop/restart task keeps interrupting the VM",
         (Param("action", "what to run: the panel's own choices (dump, start, restart, shutdown, stop)"),
          Param("interval", "how often: the panel's own choices (daily, 2-days, 3-days, 5-days, weekly, 2-weeks, "
                            "monthly, yearly)"),
          Param("start", "first run in panel time (Europe/Berlin), YYYY-MM-DD HH:MM")),
         verify=_verify_create, check=_check_create)
def _task_create(ctx, vm, action, interval, start):
    page, path, options = _check_create(ctx, vm)
    for field, given, name in (("methode", action, "action"), ("interval", interval, "interval")):
        if given not in options[field]:
            raise ServiceError(f"{name} must be one of {', '.join(options[field])}")
    try:
        when = datetime.datetime.strptime(start.strip().replace("T", " "), "%Y-%m-%d %H:%M")
    except ValueError:
        raise ServiceError("start must look like 2026-10-14 03:30 (panel time, Europe/Berlin)") from None
    known = [t["id"] for t in _read(page.component("task"))]
    data = {"methode": action, "interval": interval, "next_execution_at": when.strftime("%Y-%m-%dT%H:%M")}
    expected = {"action": options["methode"][action], "interval": options["interval"][interval],
                "next": when.strftime("%d.%m.%Y %H:%M")}
    return ctx.send(f"POST {path} {data}",
                    lambda: {**panel_answer(post_form(ctx, page, path, data)), "task": expected, "known_ids": known})


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


@feature("task-delete", "change", "Delete a scheduled task (deleting the weekly backup task switches the automatic backup off)",
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
