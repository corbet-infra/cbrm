"""Helpers shared by the feature modules: Livewire values, exact contract checks for the page's own
POSTs, panel requests with readable errors, input validation and tolerant verification.

Account-wide features (their names start with `account-`) still take the VM argument: it names the
account context, so the allow-list and `confirm=<vm>` of `cbrm.service.Service` apply to them exactly as
to every other feature. `account_page` checks that the VM belongs to the account.
"""
from __future__ import annotations

import functools
import re
import time
from typing import Callable

import httpx

from ..errors import ContractError, PanelError, ServiceError
from ..livewire import Component, Page

XHR = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}


# -- Livewire values and page text ----------------------------------------------------------------------

def plain(v):
    """A snapshot value without Livewire's type wrappers: `[data, {"s": "arr"}]` becomes `data`, recursively."""
    if isinstance(v, list) and len(v) == 2 and isinstance(v[1], dict) and "s" in v[1]:
        return plain(v[0])
    if isinstance(v, list):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    return v


def value(comp: Component, name: str):
    """A field of the component's state, unwrapped; `ContractError` if the panel no longer has it."""
    try:
        return plain(comp.data[name])
    except KeyError:
        raise ContractError(f"{comp.name}: the component's state has no '{name}'") from None


def text(node) -> str:
    return " ".join(node.text(separator=" ").split())


def panel_date(s: str | None) -> str | None:
    """'07.10.2026 | 13:50 Uhr' or '14.10.2026 13:50' -> '07.10.2026 13:50' (the format `logs` uses)."""
    if not s:
        return None
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*\|?\s*(\d{2}:\d{2})", s)
    return f"{m.group(1)} {m.group(2)}" if m else s


def timestamp(s: str | None) -> str | None:
    """'2026-10-07 13:50:35' (panel time) -> '07.10.2026 13:50'."""
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2})", s)
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)} {m.group(4)}" if m else s


# -- contract checks -------------------------------------------------------------------------------------

def require_post(page: Page, path: str, *fields: str) -> None:
    """The page's own script still POSTs exactly these fields (besides `_token`) to exactly this path."""
    m = re.search(r"\$\.post\(\s*'(?:https?://[^'/]+)?" + re.escape(path) + r"'\s*,\s*\{(.*?)\}\s*,\s*function",
                  page.html, re.S)
    if m is None:
        raise ContractError(f"{page.path}: the panel no longer posts to {path}")
    keys = set(re.findall(r"(?m)(?:^|[{,])\s*([A-Za-z_]\w*)\s*:", m.group(1)))
    if keys != set(fields) | {"_token"}:
        raise ContractError(f"{page.path}: the panel's post to {path} sends {sorted(keys - {'_token'})}, "
                            f"cbrm sends {sorted(fields)}")


def require_names(page: Page, *names: str) -> None:
    """The page has form fields with these `name` attributes."""
    missing = [n for n in names if page.tree.css_first(f'[name="{n}"]') is None]
    if missing:
        raise ContractError(f"{page.path}: the panel's form no longer has the field(s) {', '.join(missing)}")


def require_element(page: Page, selector: str, what: str):
    node = page.tree.css_first(selector)
    if node is None:
        raise ContractError(f"{page.path}: {what} is gone ({selector})")
    return node


def limits(page: Page, selector: str, what: str) -> tuple[int, int]:
    """minlength/maxlength of the panel's own input: the panel's rule, not ours."""
    node = require_element(page, selector, what)
    try:
        return int(node.attributes.get("minlength") or 1), int(node.attributes.get("maxlength") or 255)
    except ValueError:
        raise ContractError(f"{page.path}: {what} has unreadable length limits") from None


def account_page(ctx, vm: str, fresh: bool = False) -> Page:
    """/customer/account for account-wide features. `vm` names the account context and must belong to it."""
    if vm not in ctx.panel.products():
        raise ServiceError(f"VM {vm} is not in this account")
    if fresh:
        ctx._pages.pop("@account", None)
    if "@account" not in ctx._pages:
        ctx._pages["@account"] = Page(ctx.panel, "/customer/account")
    return ctx._pages["@account"]


# -- the panel's JSON endpoints --------------------------------------------------------------------------

def _json(r, what: str) -> dict:
    try:
        body = r.json()
    except ValueError:
        body = None
    if r.status_code >= 300 or not isinstance(body, dict):
        detail = body.get("message") if isinstance(body, dict) else None
        raise PanelError(f"{what}: HTTP {r.status_code}" + (f": {detail}" if detail else ""))
    return body


def post_form(ctx, page: Page, path: str, data: dict) -> dict:
    """POST a form the way the page's own script does ($.post with the page's CSRF token)."""
    try:
        return _json(ctx.panel.http.post(path, data={"_token": page.csrf, **data}, headers=XHR), path)
    except httpx.HTTPError as e:  # transport errors too (connection reset, timeout)
        raise PanelError(f"POST {path}: {type(e).__name__}: {e}") from e


def get_json(ctx, path: str, params: dict | None = None) -> dict:
    try:
        return _json(ctx.panel.http.get(path, params=params, headers=XHR), path)
    except httpx.HTTPError as e:
        raise PanelError(f"GET {path}: {type(e).__name__}: {e}") from e


def ok(result) -> bool:
    """The panel's own answer to a changing request: {"state": "success", "message": …}."""
    return isinstance(result, dict) and result.get("state") == "success"


# -- verification ----------------------------------------------------------------------------------------

def tolerant(fn: Callable) -> Callable:
    """A verify() that answers None (unknown) instead of raising when the panel hiccups while re-reading."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (PanelError, ServiceError, httpx.HTTPError):
            return None
    return wrapper


def settle(seen: Callable[[], bool], tries: int = 3, delay: float = 3.0) -> bool:
    """True as soon as `seen()` is; re-reads a few times because the panel applies some changes a moment later."""
    for i in range(tries):
        if seen():
            return True
        if i < tries - 1:
            time.sleep(delay)
    return False


# -- input -----------------------------------------------------------------------------------------------

def clean(v: str, what: str, lo: int = 1, hi: int = 255) -> str:
    v = (v or "").strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in v):
        raise ServiceError(f"{what} must not contain control characters")
    if not lo <= len(v) <= hi:
        raise ServiceError(f"{what} must be {lo}..{hi} characters long")
    return v


_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def dns_name(v: str, what: str, lo: int = 2, hi: int = 253) -> str:
    """A host or domain name: letters, digits, hyphens and dots; lower-cased, one trailing dot dropped."""
    v = clean(v, what, 1, 1000).lower().removesuffix(".")
    if not lo <= len(v) <= hi or not all(_LABEL.match(label) for label in v.split(".")):
        raise ServiceError(f"{what} must be a valid host name ({lo}..{hi} characters; letters, digits, hyphens, "
                           "dots; labels of 1..63 characters not starting or ending with a hyphen)")
    return v
