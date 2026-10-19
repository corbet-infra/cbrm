"""The account's two codes: the share code (others use it to share a product with you, /customer/shares) and the
transfer code (others use it to transfer a server to you, /customer/transfers). Each can be regenerated; the old
code stops working. Neither reveals the e-mail address or the customer number, and every share or transfer still
has to be accepted in the panel.

Account-wide, like every `account-*` feature: the VM argument only names the account context (see `common`).
"""
from __future__ import annotations

import re

from ..errors import ContractError
from .common import settle, site_page, text, tolerant
from .registry import Param, feature

CODES = {"share": ("/customer/shares", "share-code"), "transfer": ("/customer/transfers", "transfer-code")}
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _component(ctx, vm, which: str, fresh=False):
    path, name = CODES[which]
    return site_page(ctx, vm, path, fresh).component(name)


def _code(comp) -> str:
    node = comp.tree.css_first(".bt-code")
    shown = text(node) if node is not None else ""
    if not _UUID.fullmatch(shown):
        raise ContractError(f"{comp.name}: the code is no longer shown as one UUID in .bt-code")
    return shown


def _check(ctx, vm):
    for which in CODES:
        _code(_component(ctx, vm, which))


@feature("account-codes", "read",
         "The account's share code and transfer code (account-wide): what others enter to share a product or transfer a "
         "server to this account; neither reveals the e-mail address, and each share or transfer must be accepted",
         check=_check)
def _account_codes(ctx, vm):
    return {f"{which}_code": _code(_component(ctx, vm, which)) for which in CODES}


def _check_regenerate(ctx, vm):
    for which in CODES:
        comp = _component(ctx, vm, which)
        _code(comp)
        comp.require("regenerate")


@tolerant
def _verify_regenerate(ctx, vm, result, code):
    return settle(lambda: _code(_component(ctx, vm, code, fresh=True)) != result["was"])


@feature("account-code-regenerate", "change",
         "Replace the account's share or transfer code with a new one (account-wide, not limited by the VM allow-list): "
         "the old code stops working at once",
         (Param("code", "which code", choices=tuple(CODES)),), verify=_verify_regenerate, check=_check_regenerate)
def _account_code_regenerate(ctx, vm, code):
    comp = _component(ctx, vm, code)
    old = _code(comp)
    comp.require("regenerate")

    def go():
        done = comp.call(("regenerate", []))
        return {"code": code, "was": old, "messages": done.messages()}
    return ctx.send(f"Livewire {comp.name}: regenerate() (the {code} code {old} stops working)", go)
