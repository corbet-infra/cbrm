"""Backups of the VM: the list, the automatic-backup status, create, restore, delete.

The panel limits the number of backups per VM and shows one 'Neues Backup' tile per free slot. A backup's
id is the number in its tile's buttons; create, restore and delete are the endpoints those buttons call.
"""
from __future__ import annotations

import re

from ..errors import ContractError, ServiceError
from .common import (clean, get_json, limits, ok, panel_answer, panel_date, post_form, require_post, settle, text,
                     timestamp, tolerant, value)
from .registry import Param, feature


def _component(ctx, vm):
    return ctx.product_page(vm).component("backup")


def _read(comp) -> dict:
    items = []
    for node in comp.tree.css(".rootserver-backup-item"):
        html = node.html
        ids = set(re.findall(r"show(?:Delete|Recreate)BackupModal\((\d+)\)", html))
        if len(ids) > 1:
            raise ContractError("backup: the restore and delete buttons of a backup name different ids")
        title = node.css_first("h3 span")
        if title is None:
            raise ContractError("backup: a backup without a title in the rendering")
        facts = {}
        for p in node.css("p.rootserver-backup-p"):
            label, _, val = text(p).partition(":")
            facts[label.strip()] = val.strip()
        items.append({"id": ids.pop() if ids else None, "title": text(title), "size": facts.get("Größe"),
                      "date": panel_date(facts.get("Datum"))})
    free = len(comp.tree.css(".rootserver-backup-item-new"))
    if not items and not free:
        raise ContractError("backup: neither backups nor 'new backup' tiles found in the rendering")
    return {"backups": items, "free_slots": free}


def _backup_ids(ctx, vm) -> list[str]:
    return [b["id"] for b in _read(_component(ctx, vm))["backups"] if b["id"]]


def _pick(ctx, vm, backup: str) -> dict:
    items = _read(_component(ctx, vm))["backups"]
    found = [b for b in items if b["id"] == str(backup)]
    if not found:
        raise ServiceError(f"VM {vm} has no backup {backup!r}; it has {[b['id'] for b in items if b['id']]}")
    return found[0]


def _check(*endpoints: str, post: tuple[str, ...] | None = None):
    """check/precondition: the page's script still calls these backup endpoints (and posts these fields)."""
    def check(ctx, vm):
        page = ctx.product_page(vm)
        for e in endpoints:
            page.require_endpoint(f"/customer/rootserver/{vm}/backup/{e}")
        if post is not None:
            require_post(page, f"/customer/rootserver/{vm}/backup/create", *post)
        _read(page.component("backup"))
        return page
    return check


def _gone(ctx, vm, backup) -> bool:
    ctx.fresh(vm)
    return backup not in _backup_ids(ctx, vm)


# -- reading -----------------------------------------------------------------------------------------

@feature("backups", "read", "The VM's backups (id, title, size, date; panel time) and how many backup slots are free")
def _backups(ctx, vm):
    return _read(_component(ctx, vm))


@feature("automatic-backup-status", "read", "Whether the automatic backup is enabled, and its last and next run (panel time)")
def _automatic_backup_status(ctx, vm):
    comp = ctx.product_page(vm).component("automatic-backup-status")
    enabled = value(comp, "autoBackupEnabled")
    if not isinstance(enabled, bool):
        raise ContractError("automatic-backup-status: 'autoBackupEnabled' is not a boolean any more")
    return {"enabled": enabled, "last": timestamp(value(comp, "lastBackupTimestamp")),
            "next": timestamp(value(comp, "nextBackupTimestamp"))}


# -- changing ----------------------------------------------------------------------------------------

_check_create = _check("create", post=("title",))


@feature("backup-create", "change", "Create a backup now (the panel makes it in the background; needs a free slot, see `backups`)",
         (Param("title", "the backup's name"),), verify=lambda ctx, vm, result, title: ok(result),
         check=_check_create)
def _backup_create(ctx, vm, title):
    page = _check_create(ctx, vm)
    lo, hi = limits(page, "#new_backup_name", "the backup name field")
    title = clean(title, "title", lo, hi)
    if _read(page.component("backup"))["free_slots"] < 1:
        raise ServiceError(f"VM {vm} has no free backup slot; delete a backup first (`backups`)")
    path = f"/customer/rootserver/{vm}/backup/create"
    return ctx.send(f"POST {path} title={title!r}", lambda: panel_answer(post_form(ctx, page, path, {"title": title})))


@tolerant
def _verify_delete(ctx, vm, result, backup):
    return ok(result) and settle(lambda: _gone(ctx, vm, backup))


_check_delete = _check("delete/")


@feature("backup-delete", "destroy", "Delete a backup. THE BACKUP IS GONE",
         (Param("backup", "the backup's id from `backups`"),), verify=_verify_delete, check=_check_delete)
def _backup_delete(ctx, vm, backup):
    _check_delete(ctx, vm)
    found = _pick(ctx, vm, backup)
    path = f"/customer/rootserver/{vm}/backup/delete/{found['id']}"
    return ctx.send(f"GET {path} [{found['title']}, {found['date']}]", lambda: panel_answer(get_json(ctx, path)))


_check_restore = _check("restore/")


def _restore_contract(ctx, vm):
    page = _check_restore(ctx, vm)
    if "?liverestore=" not in page.html:
        raise ContractError(f"{page.path}: the panel's restore call no longer takes ?liverestore=")


@feature("backup-restore", "destroy", "Restore the whole VM from a backup. OVERWRITES THE DISK with the backup's state",
         (Param("backup", "the backup's id from `backups`"),
          Param("live", "yes: the VM starts at once while the data is restored in the background (the panel's "
                        "default); no: it is restored first", choices=("yes", "no"), required=False, default="yes")),
         verify=lambda ctx, vm, result, backup, live: ok(result), check=_restore_contract)
def _backup_restore(ctx, vm, backup, live="yes"):
    _restore_contract(ctx, vm)
    found = _pick(ctx, vm, backup)
    path = f"/customer/rootserver/{vm}/backup/restore/{found['id']}"
    params = {"liverestore": "1" if live == "yes" else "0"}
    return ctx.send(f"GET {path}?liverestore={params['liverestore']} [{found['title']}, {found['date']}]",
                    lambda: panel_answer(get_json(ctx, path, params)))
