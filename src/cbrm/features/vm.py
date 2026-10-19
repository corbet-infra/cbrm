"""VM features: state, log, console, root password, power, console input, reinstall."""
from __future__ import annotations

import secrets
import string
import time

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..errors import ContractError, ServiceError
from ..panel import POWER_ACTIONS
from .common import panel_answer, panel_date, text
from .registry import Param, feature

# -- reading -----------------------------------------------------------------------------------------

@feature("status", "read", "Show state, host name, addresses and last backup",
         "State, hostname, addresses, last backup and last installed template")
def _status(ctx, vm):
    return ctx.panel.status(vm)


_LOG_STATUS = {"text-success": "ok", "text-danger": "failed", "text-warning": "running"}


def _log_rows(comp) -> list[dict]:
    """Rows of the `logs-table` component: 'Status: <dot>  Datum : 11.10.2026 | 00:02 Uhr  Aktion: Starten'."""
    out = []
    for row in comp.tree.css("div.grey-transparent-background"):
        cells = {}
        for label in row.css("b.d-xl-none"):
            key = text(label).rstrip(":").strip()
            cells[key] = (label.parent, text(label.parent).removeprefix(text(label)).strip())
        if "Datum" not in cells or "Aktion" not in cells:
            raise ContractError("logs-table: a row without 'Datum' or 'Aktion'")
        dot = cells["Status"][0].css_first("i") if "Status" in cells else None
        classes = (dot.attributes.get("class") or "").split() if dot is not None else []
        status = next((v for k, v in _LOG_STATUS.items() if k in classes),
                      next((c.removeprefix("text-") for c in classes if c.startswith("text-")), None))
        out.append({"date": panel_date(cells["Datum"][1]), "action": cells["Aktion"][1], "status": status})
    return out


def _check_logs(ctx, vm):
    comp = ctx.product_page(vm).component("logs-table").require(models=("logSearch",))
    _log_rows(comp)
    return comp


@feature("logs", "read", "Show the panel's action log, newest first",
         "The panel's action log, newest first, in panel time (Europe/Berlin): date, action and "
         "status (ok, failed); a page of the log, optionally filtered with the panel's own search",
         (Param("n", "how many entries of the page", int, False, default=20),
          Param("search", "only entries matching this text (the panel's own search)", required=False),
          Param("page", "page number, 1 is the newest", int, required=False, default=1)), check=_check_logs)
def _logs(ctx, vm, n=20, search=None, page=1):
    if not 1 <= int(page) <= 1000:
        raise ServiceError("page must be 1..1000")
    comp = _check_logs(ctx, vm)
    updates = {}
    if search:
        updates["logSearch"] = search.strip()
    if int(page) != 1:
        updates["paginators.logPage"] = int(page)  # the component's own page state
    if updates:
        comp = comp._send(updates, [])
    return _log_rows(comp)[: int(n)]


def _check_console(ctx, vm):
    ctx.panel.console_session(vm)  # raises if the panel stops handing out a noVNC session


def _check_root_password(ctx, vm):
    if HTMLParser(ctx.product_page(vm).html).css_first("#password[data-password]") is None:
        raise ContractError("product page: the root password field is gone")


@feature("console", "read", "Take a screenshot of the VNC console",
         "A screenshot of the VNC console (PNG)", returns="png", check=_check_console)
def _console(ctx, vm):
    from ..console import Console
    with Console(*ctx.panel.console_session(vm)) as c:
        return c.png()


@feature("templates", "read", "List the operating systems the panel can install",
         "Operating systems the panel can install: name -> template id")
def _templates(ctx, vm):
    return ctx.panel.templates(vm)


@feature("ssh-keys", "read", "List the stored SSH keys by name",
         "SSH keys stored in the panel account: name -> id")
def _ssh_keys(ctx, vm):
    return ctx.panel.ssh_keys(vm)


@feature("root-password", "secret", "Show the root password",
         "The root password as the panel shows it", secret_result=True,
         check=_check_root_password)
def _root_password(ctx, vm):
    return {"vm": vm, "root_password": ctx.panel.root_password(vm)}


# -- changing ----------------------------------------------------------------------------------------

def _wait_state(ctx, vm, want: str, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if ctx.panel.status(vm).get("state") == want:
            return True
        time.sleep(5)
    return False


def _verify_power(ctx, vm, result, action):
    return _wait_state(ctx, vm, "Offline" if action in ("stop", "shutdown") else "Online", 180)


def _check_power(ctx, vm):
    page = ctx.product_page(vm)
    for a in POWER_ACTIONS:
        page.require_endpoint(f"/customer/rootserver/{vm}/{a}")


@feature("power", "change", "Start, stop, shut down or restart the VM",
         "Start, stop (hard), shut down (ACPI) or restart the VM",
         (Param("action", "what to do", choices=POWER_ACTIONS),), verify=_verify_power, check=_check_power)
def _power(ctx, vm, action):
    _check_power(ctx, vm)
    return ctx.send(f"GET /customer/rootserver/{vm}/{action}", lambda: panel_answer(ctx.panel.power(vm, action)))


def _check_set_root_password(ctx, vm):
    page = ctx.product_page(vm)
    page.require_endpoint(f"/customer/rootserver/{vm}/setrootpassword")
    page.require_text("password_confirmation")


@feature("set-root-password", "change", "Set or generate the root password",
         "Set the root password (generated if omitted); returns it",
         (Param("password", "the new password", required=False, secret=True),), secret_result=True,
         check=_check_set_root_password)
def _set_root_password(ctx, vm, password=None):
    _check_set_root_password(ctx, vm)
    password = password or "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))
    return ctx.send(f"POST /customer/rootserver/{vm}/setrootpassword",
                    lambda: {**panel_answer(ctx.panel.set_root_password(vm, password)), "root_password": password})


@feature("console-input", "change", "Type text and press keys at the console",
         "Type text, then press keys (vncdotool names: enter, ctrl-c, down, f1, ...); "
         "repeat the keys to catch a boot menu",
         (Param("text", "text to type (kept out of the audit log)", required=False, default="", secret=True),
          Param("keys", "keys to press after the text", required=False, multiple=True, default=()),
          Param("repeat", "press the keys this many times (max 120)", int, False, default=1),
          Param("interval", "seconds between repeats", float, False, default=1.0)),
         check=_check_console)
def _console_input(ctx, vm, text="", keys=(), repeat=1, interval=1.0):
    repeat, interval = int(repeat), float(interval)
    if not 1 <= repeat <= 120 or not 0.1 <= interval <= 30 or repeat * interval > 120:
        raise ServiceError("repeat must be 1..120, interval 0.1..30 s, and repeat x interval at most 120 s")

    def go():
        from ..console import Console
        with Console(*ctx.panel.console_session(vm)) as c:
            if text:
                c.type(text)
            if keys:
                c.keys(*keys, repeat=repeat, interval=interval)
        return {"sent": True}
    return ctx.send(f"console of {vm}: type {len(text)} characters, then keys {list(keys)} x{repeat}", go)


# -- destroying --------------------------------------------------------------------------------------

REINSTALL_FIELDS = {"_token", "template"}  # what the panel's form serializes, besides the ssh_keys[] its script adds


def _check_reinstall(ctx, vm):
    page = ctx.product_page(vm)
    page.require_endpoint(f"/customer/rootserver/{vm}/reinstall")
    if HTMLParser(page.html).css_first('select#rootserverTemplate[name="template"]') is None:
        raise ContractError("reinstall form: template selection missing")
    page.require_text('name="ssh_keys[]"')  # the field the panel's script builds for the chosen keys
    form = page.tree.css_first("#reinstallServerForm")
    if form is not None:  # the panel posts the form serialized: a named field cbrm does not send would change the request
        named = {n.attributes.get("name") for n in form.css("input[name], select[name], textarea[name]")} - {"ssh_keys[]"}
        if named - REINSTALL_FIELDS:
            raise ContractError(f"reinstall form: the panel's form also sends {sorted(named - REINSTALL_FIELDS)}, which "
                                "cbrm does not send")


@feature("reinstall", "destroy", "Reinstall from a template, erasing the disk",
         "Reinstall from a template with stored SSH keys baked in. ERASES THE DISK",
         (Param("template", "name from `templates`"),
          Param("ssh_keys", "names from `ssh-keys`", required=False, multiple=True, default=())),
         check=_check_reinstall)
def _reinstall(ctx, vm, template, ssh_keys=()):
    _check_reinstall(ctx, vm)
    templates, keys = ctx.panel.templates(vm), ctx.panel.ssh_keys(vm)
    if template not in templates:
        raise ServiceError(f"unknown template {template!r}; one of: {', '.join(templates)}")
    missing = [k for k in ssh_keys if k not in keys]
    if missing:
        raise ServiceError(f"unknown SSH key(s) {missing}; stored: {', '.join(keys)}")
    ids = [keys[k] for k in ssh_keys]
    return ctx.send(f"POST /customer/rootserver/{vm}/reinstall template={templates[template]} ssh_keys={ids}",
                    lambda: panel_answer(ctx.panel.reinstall(vm, templates[template], ids)))
