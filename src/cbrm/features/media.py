"""CD drives, ISO images (public and your own), rescue system and boot order."""
from __future__ import annotations

import re
import time

from ..errors import ContractError, ServiceError
from .registry import Param, feature


def _rows(comp, button: str) -> list[dict]:
    """Rows of the panel's 'Titel / Datei / Größe / [button(id)]' lists (ISOs, rescue images)."""
    out = []
    for b in comp.tree.css(f"[wire\\:click\\.prevent^='{button}(']"):
        row, cells = b.parent.parent, {}
        for label in ("Titel", "Datei", "Größe"):
            node = next((n for n in row.css("b") if n.text().strip().startswith(label)), None)
            if node is not None:
                cells[label] = node.parent.text().split(":", 1)[1].strip()
        ident = re.search(r"\((\d+)\)", b.attributes["wire:click.prevent"]).group(1)
        out.append({"id": ident, "title": cells.get("Titel", ""), "file": cells.get("Datei", ""),
                    "size": cells.get("Größe", "")})
    return out


def _live(ctx, vm, name: str, refresh: str):
    """A component after its refresh method ran: the panel caches drives and boot order and shows the
    hypervisor's state only after the (hidden) Update button's method."""
    comp = ctx.product_page(vm).component(name)
    return comp._send({}, [(refresh, [])]) if comp.offers(refresh) else comp


# -- reading -----------------------------------------------------------------------------------------

@feature("drives", "read", "The VM's CD drives and what is inserted (live state from the hypervisor)")
def _drives(ctx, vm):
    comp = _live(ctx, vm, "drive", "updateDrivesContent")
    out = []
    for node in comp.tree.css("[wire\\:key^='existingDriveFromRootserver']"):
        lines = [l.strip() for l in node.text(separator="\n").splitlines() if l.strip()]
        content = lines[1] if len(lines) > 1 and lines[1] not in ("ISO einlegen", "Löschen") else ""
        out.append({"drive": node.attributes["wire:key"].removeprefix("existingDriveFromRootserver"),
                    "content": "" if content == "Leer" else content})
    if not out:
        raise ContractError("drive: no drives found in the rendering")
    return out


@feature("isos", "read", "ISO images the panel can insert (public ones and the account's own), optionally filtered",
         (Param("search", "filter by title or file name", required=False, default=""),))
def _isos(ctx, vm, search=""):
    comp = ctx.product_page(vm).component("drive")
    if search:
        comp = comp.set(availableIsoSearch=search)
    seen, out = set(), []
    for _ in range(40):  # pages of 8 entries
        rows = [r for r in _rows(comp, "mountIso") if r["id"] not in seen]
        if not rows:
            break
        seen.update(r["id"] for r in rows)
        out += rows
        if not comp.offers("nextPage"):
            break
        comp = comp._send({}, [("nextPage", ["availableisos_page"])])
    return out


@feature("rescue", "read", "Rescue system state and the available rescue images")
def _rescue(ctx, vm):
    comp = ctx.product_page(vm).component("rescue")
    text = " ".join(comp.tree.text(separator=" ").split())
    return {"active": "Rescue System ist deaktiviert" not in text, "images": _rows(comp, "enableRescue")}


@feature("boot-order", "read", "Boot devices in order (scsi0 = disk, ide0/ide2 = CD drives, net0 = network)")
def _boot_order(ctx, vm):
    comp = _live(ctx, vm, "boot", "updateBootOrderContent")
    items = [{"key": n.attributes["data-bootkey"], "label": " ".join(n.text(separator=" ").split())}
             for n in comp.tree.css("[data-bootkey]")]
    if not items:
        raise ContractError("boot: no boot devices found in the rendering")
    return items


# -- changing ----------------------------------------------------------------------------------------

def _drive_component(ctx, vm, drive):
    names = [d["drive"] for d in _drives(ctx, vm)]
    if drive not in names:
        raise ServiceError(f"VM {vm} has no drive {drive!r}; it has {names}")
    return ctx.product_page(vm).component("drive")


def _drive_content(ctx, vm, drive) -> str:
    ctx.fresh(vm)
    return next(d["content"] for d in _drives(ctx, vm) if d["drive"] == drive)


def _verify_mount(ctx, vm, result, drive, iso):
    """Only the exact file counts: the panel reports success even when an own ISO has not finished
    downloading, and then nothing is inserted."""
    want = result["mounted"]["file"]
    for _ in range(12):
        if want in _drive_content(ctx, vm, drive):
            return True
        time.sleep(5)
    return False


@feature("iso-mount", "change", "Insert an ISO (id, title or file name from `isos`) into a CD drive",
         (Param("drive", "the drive, e.g. ide0"), Param("iso", "id, title or file name")), verify=_verify_mount,
         check=lambda ctx, vm: ctx.product_page(vm).component("drive").require("setCurrentDrive", "mountIso"))
def _iso_mount(ctx, vm, drive, iso):
    comp = _drive_component(ctx, vm, drive).require("setCurrentDrive", "mountIso")
    rows = _isos(ctx, vm, "" if iso.isdigit() else iso)
    match = [r for r in rows if iso in (r["id"], r["title"], r["file"])]
    if len(match) != 1:
        raise ServiceError(f"ISO {iso!r} matches {len(match)} images; use its id from `isos`")
    found = match[0]
    return ctx.send(f"Livewire drive: setCurrentDrive({drive!r}), mountIso({found['id']}) [{found['title']}]",
                    lambda: {"drive": drive, "mounted": found, "messages": comp._send(
                        {}, [("setCurrentDrive", [drive]), ("mountIso", [int(found["id"])])]).messages()})


@feature("iso-unmount", "change", "Remove the ISO from a CD drive", (Param("drive", "the drive, e.g. ide0"),),
         verify=lambda ctx, vm, result, drive: _drive_content(ctx, vm, drive) == "",
         check=lambda ctx, vm: ctx.product_page(vm).component("drive").require("setCurrentDrive", "unmountIso"))
def _iso_unmount(ctx, vm, drive):
    comp = _drive_component(ctx, vm, drive).require("setCurrentDrive", "unmountIso")
    return ctx.send(f"Livewire drive: setCurrentDrive({drive!r}), unmountIso()",
                    lambda: {"drive": drive, "messages": comp._send(
                        {}, [("setCurrentDrive", [drive]), ("unmountIso", [])]).messages()})


@feature("iso-add", "change", "Add your own ISO to the account from a public download URL (kept at least 6 months)",
         (Param("url", "HTTP(S) URL of the ISO file"), Param("title", "title shown in the panel")),
         check=lambda ctx, vm: ctx.product_page(vm).component("drive").require("displayDownloadForm"))
def _iso_add(ctx, vm, url, title):
    if not re.match(r"https?://", url):
        raise ServiceError("url must be http(s)")
    comp = ctx.product_page(vm).component("drive").call(("displayDownloadForm", []))
    comp = comp.set(downloadUrlTitle=title, downloadUrl=url)
    comp.require("downloadIso")
    return ctx.send(f"Livewire drive: downloadUrlTitle={title!r}, downloadUrl={url!r}, downloadIso()",
                    lambda: {"requested": {"title": title, "url": url},
                             "messages": comp._send({}, [("downloadIso", [])]).messages(),
                             "note": "the panel downloads in the background; `isos --search <title>` lists it when done"})


def _verify_boot(ctx, vm, result, order):
    ctx.fresh(vm)
    return [i["key"] for i in _boot_order(ctx, vm)] == list(order)


@feature("boot-order-set", "change", "Set the boot order: every device key from `boot-order`, first boots first",
         (Param("order", "device keys in the new order, e.g. ide0 scsi0 net0 ide2", multiple=True),),
         verify=_verify_boot,
         check=lambda ctx, vm: ctx.product_page(vm).require_endpoint(f"/customer/rootserver/{vm}/boot_order"))
def _boot_order_set(ctx, vm, order):
    current = [i["key"] for i in _boot_order(ctx, vm)]
    if sorted(order) != sorted(current):
        raise ServiceError(f"order must list exactly these devices once each: {current}")
    ctx.product_page(vm).require_endpoint(f"/customer/rootserver/{vm}/boot_order")
    query = ";".join(order)
    return ctx.send(f"GET /customer/rootserver/{vm}/boot_order?boot_order={query}",
                    lambda: ctx.panel.get_json(f"/customer/rootserver/{vm}/boot_order", {"boot_order": query}))


def _rescue_is(want: bool):
    def verify(ctx, vm, result, **_):
        ctx.fresh(vm)
        return _rescue(ctx, vm)["active"] is want
    return verify


@feature("rescue-enable", "change", "Boot the next time into a rescue image (id or title from `rescue`)",
         (Param("image", "id, title or file name"),), verify=_rescue_is(True),
         check=lambda ctx, vm: ctx.product_page(vm).component("rescue").require("enableRescue"))
def _rescue_enable(ctx, vm, image):
    comp = ctx.product_page(vm).component("rescue").require("enableRescue")
    match = [r for r in _rows(comp, "enableRescue") if image in (r["id"], r["title"], r["file"])]
    if len(match) != 1:
        raise ServiceError(f"rescue image {image!r} matches {len(match)} images")
    return ctx.send(f"Livewire rescue: enableRescue({match[0]['id']}) [{match[0]['title']}]",
                    lambda: {"enabled": match[0], "messages": comp._send(
                        {}, [("enableRescue", [int(match[0]["id"])])]).messages()})


@feature("rescue-disable", "change", "Leave the rescue system", verify=_rescue_is(False),
         check=lambda ctx, vm: ctx.product_page(vm).component("rescue").require("disableRescue"))
def _rescue_disable(ctx, vm):
    comp = ctx.product_page(vm).component("rescue").require("disableRescue")
    return ctx.send("Livewire rescue: disableRescue()",
                    lambda: {"messages": comp._send({}, [("disableRescue", [])]).messages()})


@feature("drive-delete", "change", "Remove a CD drive from the VM (a VM should have one CD drive, the disk and network)",
         (Param("drive", "the drive, e.g. ide0"),),
         verify=lambda ctx, vm, result, drive: (ctx.fresh(vm), drive not in [d["drive"] for d in _drives(ctx, vm)])[1],
         check=lambda ctx, vm: ctx.product_page(vm).component("drive").require("setCurrentDrive", "deleteDrive"))
def _drive_delete(ctx, vm, drive):
    drives = _drives(ctx, vm)
    if drive not in [d["drive"] for d in drives]:
        raise ServiceError(f"VM {vm} has no drive {drive!r}")
    if len(drives) == 1:
        raise ServiceError(f"{drive} is the VM's only CD drive; keep one")
    comp = ctx.product_page(vm).component("drive").require("setCurrentDrive", "deleteDrive")
    return ctx.send(f"Livewire drive: setCurrentDrive({drive!r}), deleteDrive()",
                    lambda: {"drive": drive, "messages": comp._send(
                        {}, [("setCurrentDrive", [drive]), ("deleteDrive", [])]).messages()})
