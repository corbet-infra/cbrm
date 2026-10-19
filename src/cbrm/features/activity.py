"""What the panel tells about a server beyond its overview: the activity list (who did what, and when), pending
server updates (and installing them), and the task the panel is running right now.

The activity list ("Aktivitäten") is the product's own record of actions in the panel, by you or by a customer the
product is shared with. It is not the hypervisor log (`logs`).
"""
from __future__ import annotations

import re

from ..errors import ContractError, ServiceError
from .common import settle, text, tolerant
from .registry import Param, feature

_ACTIVITY_KEY = re.compile(r"service-activity-(\d+)")
_DATE = re.compile(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}")
NO_UPDATES = "Keine Updates ausstehend"


# -- activity ---------------------------------------------------------------------------------------------

def _activity_rows(comp) -> list[dict]:
    if "Aktivitäten" not in text(comp.tree.root):
        raise ContractError("activity-log: the 'Aktivitäten' list is gone from the rendering")
    out = []
    for row in comp.tree.css("[wire\\:key^='service-activity-']"):
        m = _ACTIVITY_KEY.fullmatch(row.attributes.get("wire:key") or "")
        body, actor, when = row.css_first(".sal-text"), row.css_first(".sal-actor"), row.css_first(".sal-date")
        if m is None or body is None or actor is None or when is None:
            raise ContractError("activity-log: an entry without id, text, actor or date")
        who = text(actor)
        action = text(body).removeprefix(who).strip().lstrip("·").strip()
        date = (when.attributes.get("title") or "").strip()
        if not _DATE.fullmatch(date):
            raise ContractError("activity-log: an entry whose date is not 'DD.MM.YYYY HH:MM'")
        out.append({"id": m.group(1), "actor": "you" if who == "Du" else who, "action": action, "date": date})
    return out


@feature("activity", "read", "Show who did what to the server in the panel",
         "Who did what to the server in the panel, and when (the panel's activity list, newest "
         "first, panel time): `you`, or the customer the product is shared with",
         (Param("n", "how many entries (1..200)", int, False, default=20),),
         check=lambda ctx, vm: _activity_rows(ctx.product_page(vm).component("activity-log")))
def _activity(ctx, vm, n=20):
    if not 1 <= int(n) <= 200:
        raise ServiceError("n must be 1..200")
    return _activity_rows(ctx.product_page(vm).component("activity-log"))[: int(n)]


# -- pending updates --------------------------------------------------------------------------------------

def _updates(comp) -> dict:
    modal = comp.tree.css_first("#serverUpdatesModal")
    if modal is None:
        raise ContractError("updates: the updates dialog (#serverUpdatesModal) is gone from the rendering")
    body = modal.css_first(".modal-body")
    outside = text(comp.tree.root).replace(text(modal), "")
    pending = NO_UPDATES not in outside
    items = [] if body is None else [line.strip() for line in body.text(separator="\n").splitlines() if line.strip()]
    return {"pending": pending, "updates": items if pending else []}


@feature("updates", "read", "Show the pending server updates",
         "Pending server updates the panel offers to install (`pending` and the list the panel "
         "shows; the panel's own words)",
         check=lambda ctx, vm: _updates(ctx.product_page(vm).component("rootserver.updates")))
def _updates_feature(ctx, vm):
    return _updates(ctx.product_page(vm).component("rootserver.updates"))


def _check_install(ctx, vm):
    comp = ctx.product_page(vm).component("rootserver.updates")
    _updates(comp)
    return comp.require("installUpdates")


@tolerant
def _verify_install(ctx, vm, result):
    return settle(lambda: not _updates(ctx.fresh(vm).component("rootserver.updates"))["pending"])


@feature("updates-install", "change", "Install the pending server updates",
         "Install the pending server updates (the panel's 'Updates installieren'; read `updates` first: what they do "
         "is the panel's, the server may be restarted). Only while the panel lists pending updates",
         verify=_verify_install, check=_check_install)
def _updates_install(ctx, vm):
    comp = _check_install(ctx, vm)
    state = _updates(comp)
    if not state["pending"]:
        raise ServiceError(f"VM {vm} has no pending updates (the panel says '{NO_UPDATES}')")

    def go():
        done = comp.call(("installUpdates", []))
        return {"vm": vm, "updates": state["updates"], "messages": done.messages()}
    return ctx.send(f"Livewire rootserver.updates: installUpdates() [{len(state['updates'])} line(s) listed]", go)


# -- the running task -------------------------------------------------------------------------------------

def _running(comp) -> dict:
    box = comp.tree.css_first(".toast-container")
    if box is None:
        raise ContractError("running-task: the progress area (.toast-container) is gone from the rendering")
    shown = text(box)
    return {"running": bool(shown), "text": shown or None}


@feature("running-task", "read", "Show the task the panel is running right now",
         "The task the panel is running on the server right now (for example an installation "
         "or a backup), as the panel's progress notice shows it; `running: false` when there is none",
         check=lambda ctx, vm: _running(ctx.product_page(vm).component("running-task")))
def _running_task(ctx, vm):
    return _running(ctx.product_page(vm).component("running-task"))
