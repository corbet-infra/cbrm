"""VM features: state, log, console, root password, power, console input, reinstall."""
from __future__ import annotations

import secrets
import string
import time

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..errors import ContractError, ServiceError
from ..panel import POWER_ACTIONS
from .registry import Param, feature


# -- reading -----------------------------------------------------------------------------------------

@feature("status", "read", "State, hostname, addresses, last backup and last installed template")
def _status(ctx, vm):
    return ctx.panel.status(vm)


@feature("logs", "read", "The panel's action log, newest first, in panel time (Europe/Berlin)",
         (Param("n", "how many entries", int, False, default=20),))
def _logs(ctx, vm, n=20):
    return [e.__dict__ for e in ctx.panel.logs(vm)[: int(n)]]


def _check_console(ctx, vm):
    ctx.panel.console_session(vm)  # raises if the panel stops handing out a noVNC session


def _check_root_password(ctx, vm):
    if HTMLParser(ctx.product_page(vm).html).css_first("#password[data-password]") is None:
        raise ContractError("product page: the root password field is gone")


@feature("console", "read", "A screenshot of the VNC console (PNG)", returns="png", check=_check_console)
def _console(ctx, vm):
    from ..console import Console
    with Console(*ctx.panel.console_session(vm)) as c:
        return c.png()


@feature("templates", "read", "Operating systems the panel can install: name -> template id")
def _templates(ctx, vm):
    return ctx.panel.templates(vm)


@feature("ssh-keys", "read", "SSH keys stored in the panel account: name -> id")
def _ssh_keys(ctx, vm):
    return ctx.panel.ssh_keys(vm)


@feature("root-password", "secret", "The root password as the panel shows it", secret_result=True,
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


@feature("power", "change", "Start, stop (hard), shut down (ACPI) or restart the VM",
         (Param("action", "what to do", choices=POWER_ACTIONS),), verify=_verify_power, check=_check_power)
def _power(ctx, vm, action):
    _check_power(ctx, vm)
    return ctx.send(f"GET /customer/rootserver/{vm}/{action}", lambda: ctx.panel.power(vm, action))


@feature("set-root-password", "change", "Set the root password (generated if omitted); returns it",
         (Param("password", "the new password", required=False, secret=True),), secret_result=True,
         check=lambda ctx, vm: ctx.product_page(vm).require_endpoint(f"/customer/rootserver/{vm}/setrootpassword"))
def _set_root_password(ctx, vm, password=None):
    password = password or "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))
    r = ctx.send(f"POST /customer/rootserver/{vm}/setrootpassword", lambda: ctx.panel.set_root_password(vm, password))
    return r if r.get("dry_run") else {**r, "root_password": password}


@feature("console-input", "change", "Type text, then press keys (vncdotool names: enter, ctrl-c, down, f1, ...); "
         "repeat the keys to catch a boot menu",
         (Param("text", "text to type", required=False, default=""),
          Param("keys", "keys to press after the text", required=False, multiple=True, default=()),
          Param("repeat", "press the keys this many times (max 120)", int, False, default=1),
          Param("interval", "seconds between repeats", float, False, default=1.0)),
         check=_check_console)
def _console_input(ctx, vm, text="", keys=(), repeat=1, interval=1.0):
    repeat, interval = int(repeat), float(interval)
    if not 1 <= repeat <= 120 or not 0.1 <= interval <= 30:
        raise ServiceError("repeat must be 1..120 and interval 0.1..30 seconds")

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

def _check_reinstall(ctx, vm):
    page = ctx.product_page(vm)
    page.require_endpoint(f"/customer/rootserver/{vm}/reinstall")
    if HTMLParser(page.html).css_first("select#rootserverTemplate") is None:
        raise ContractError("reinstall form: template selection missing")


@feature("reinstall", "destroy", "Reinstall from a template with stored SSH keys baked in. ERASES THE DISK",
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
                    lambda: ctx.panel.reinstall(vm, templates[template], ids))
