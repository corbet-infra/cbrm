"""Runtime, renewal prices and credit: reading only. cbrm never pays: extending, upgrading and topping up
credit stay in the panel, by hand (Julian's decision, 2026-10-13)."""
from __future__ import annotations

import math
import re

from ..errors import ContractError
from .common import account_page, require_element, text, value
from .registry import feature

# What the panel prints for the payment: "42,00 € via PayPal (<the payer's account, an e-mail address>)". Only
# the amount and the method's name are kept; the method is plain words (no digits, '@' or dots: nothing that
# could identify an account), whatever follows is dropped, and a line in another shape yields no payment.
_PAYMENT = re.compile(r"^\s*(?P<amount>-?[\d.]*\d,\d{2}\s*€)\s+via\s+"
                      r"(?P<method>[^\W\d_]{1,30}(?:[ -][^\W\d_]{1,30}){0,2})\s*(?:\(|$)")


def _credit(page) -> dict:
    node = require_element(page, "#guthabenHeader", "the credit display")
    m = re.search(r"Guthaben\s+(-?[\d.]*\d,\d{2})\s*€", text(node))
    if m is None:
        raise ContractError(f"{page.path}: the credit display no longer reads 'Guthaben 0,00 €'")
    try:
        eur = float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        raise ContractError(f"{page.path}: the credit display holds a number cbrm cannot read") from None
    return {"balance": f"{m.group(1)} €", "balance_eur": eur}


def _switch(comp, selector: str):
    node = comp.tree.css_first(selector)
    return None if node is None else "checked" in node.attributes


def _auto_renew(comp) -> dict:
    enabled = _switch(comp, "#serverRenewSwitchButton")
    if enabled is None:
        raise ContractError("automatic-renew: the renewal switch is gone from the rendering")
    out = {"enabled": enabled, "renews_on": None, "runtime": None, "new_end": None, "price": None, "payment": None,
           "options": [], "pays_automatically": _switch(comp, "#automaticPaymentSwitchButton"),
           "credit_first": _switch(comp, "#automaticPaymentUseCreditSwitchButton")}
    names = {"Verlängerung am": "renews_on", "Laufzeit": "runtime", "Neue Laufzeit bis": "new_end", "Preis": "price"}
    for label in comp.tree.css(".row .text-muted"):
        key = names.get(text(label))
        sibling = label.next
        while sibling is not None and sibling.tag == "-text":
            sibling = sibling.next
        if key and sibling is not None:
            out[key] = text(sibling)
    pay = next((text(n) for n in comp.tree.css(".col-12") if text(n).startswith("Zahlung:")), None)
    paid = _PAYMENT.match(pay.removeprefix("Zahlung:")) if pay else None
    if paid:  # amount and method name only: the panel appends the account (an e-mail address)
        out["payment"] = f"{' '.join(paid['amount'].split())} via {paid['method']}"
    chosen = value(comp, "automaticRenewRuntimeId") if "automaticRenewRuntimeId" in comp.data else None
    for o in comp.tree.css("select#automaticRenewRuntimeSelect option"):
        m = re.match(r"(\d+) Tage\s*[–-]\s*(\S+ €)", text(o))
        if m is None:
            raise ContractError("automatic-renew: a runtime option no longer reads 'N Tage – 42,00 €'")
        out["options"].append({"id": o.attributes["value"], "days": int(m.group(1)), "price": m.group(2),
                               "default": "(Standard)" in text(o), "selected": str(chosen) == o.attributes["value"]})
    return out


def _upgrade(comp) -> dict:
    note = text(comp.tree.root)
    if "feste Konfiguration" in note:
        return {"possible": False, "note": "fixed configuration: this server cannot be changed"}
    # A layout cbrm has not seen. cbrm's own words, not the component's text: that is the panel's to show.
    return {"possible": None, "note": "the panel's upgrade section looks different than cbrm knows; see the panel"}


@feature("renewal", "read", "Remaining runtime, automatic renewal (runtimes with the prices the panel quotes, payment method), "
         "whether the server can be upgraded, and the account credit")
def _renewal(ctx, vm):
    page = ctx.product_page(vm)
    m = re.search(r"var secondsTillEnd = (-?[\d.]+);", page.html)
    if m is None:
        raise ContractError(f"{page.path}: the remaining runtime (secondsTillEnd) is gone from the page")
    try:
        seconds = float(m.group(1))
    except ValueError:
        raise ContractError(f"{page.path}: the remaining runtime (secondsTillEnd) is not a number") from None
    return {"vm": vm, "remaining_days": math.floor(seconds / 86400) if seconds > 0 else 0,
            "remaining_seconds": int(seconds), "expired": seconds <= 0,
            "auto_renew": _auto_renew(page.component("automatic-renew")),
            "upgrade": _upgrade(page.component("product-upgrade")), **_credit(page)}


@feature("account-credit", "read", "The account's credit balance as the panel shows it (account-wide)")
def _account_credit(ctx, vm):
    return _credit(account_page(ctx, vm))
