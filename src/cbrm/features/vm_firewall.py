"""A server's own firewall card on its product page: which firewall it uses, removing it, the state of the mail
ports, and asking BERO to unlock them.

The card is one Livewire component (`rootserver.firewall`, its `rootserverId` is the VM). While a firewall is
assigned it shows "Aktive Firewall" with the firewall's name, a link to its editor and `unassign`. The mail ports
(25, 465, 587, 2525) are blocked for every server until BERO unlocks them on request (`requestMailUnlock` with
`purpose`, `mailHostname` and `acceptTerms`); BERO staff answer such a request in a support ticket.

Firewalls themselves (create, rename, policies, servers) are the account-wide `account-firewall-*` features.
"""
from __future__ import annotations

import re

from ..errors import ContractError, ServiceError
from ..livewire import Component
from .common import dns_name, settle, text, tolerant, value
from .registry import Param, feature

_EDITOR = re.compile(r"/customer/network/firewall/(\d+)$")
_UNLOCKED = re.compile(r"freigeschaltet seit (\d{2}\.\d{2}\.\d{4})")
PURPOSE_MAX, HOSTNAME_MAX = 2000, 253


def _component(ctx, vm, fresh=False) -> Component:
    page = ctx.fresh(vm) if fresh else ctx.product_page(vm)
    comp = page.component("rootserver.firewall")
    if str(value(comp, "rootserverId")) != str(vm):
        raise ContractError(f"rootserver.firewall: the card belongs to server {value(comp, 'rootserverId')}, not {vm}")
    return comp


def _labelled(comp: Component) -> dict[str, str]:
    """Each `.rs-net-label` with the `.ncd-name` that follows it (document order)."""
    out, label = {}, None
    for node in comp.tree.css(".rs-net-label, .ncd-name"):
        classes = (node.attributes.get("class") or "").split()
        if "rs-net-label" in classes:
            label = text(node)
        elif label is not None and label not in out:
            out[label] = text(node)
    return out


def _state(comp: Component) -> dict:
    names = _labelled(comp)
    if "E-Mail-Ports" not in names:
        raise ContractError("rootserver.firewall: the mail-port state is gone from the card")
    firewall = None
    if "Aktive Firewall" in names:
        links = {m.group(1) for a in comp.tree.css("a[href]") if (m := _EDITOR.search(a.attributes.get("href") or ""))}
        if len(links) != 1 or not comp.offers("unassign"):
            raise ContractError("rootserver.firewall: an active firewall without exactly one editor link and 'unassign'")
        firewall = {"id": links.pop(), "name": names["Aktive Firewall"]}
    mail = names["E-Mail-Ports"]
    unlocked = _UNLOCKED.search(mail)
    requestable = (comp.tree.css_first("[data-bs-target='#mailUnlockModal']") is not None
                   and comp.tree.css_first("form[wire\\:submit='requestMailUnlock']") is not None)
    return {"firewall": firewall,
            "mail_ports": {"unlocked": unlocked is not None, "since": unlocked.group(1) if unlocked else None,
                           "state": mail},
            "mail_unlock_requestable": requestable and unlocked is None}


@feature("firewall", "read", "Show the server's firewall and mail-port state",
         "The server's firewall (id and name, or none) and its mail ports (25, 465, 587, 2525): "
         "unlocked since when, or locked and whether an unlock can be requested",
         check=lambda ctx, vm: _state(_component(ctx, vm)))
def _firewall(ctx, vm):
    return {"vm": vm, **_state(_component(ctx, vm))}


# -- removing the firewall --------------------------------------------------------------------------------

@tolerant
def _verify_unassign(ctx, vm, result):
    return settle(lambda: _state(_component(ctx, vm, fresh=True))["firewall"] is None)


def _check_unassign(ctx, vm):
    comp = _component(ctx, vm)
    if _state(comp)["firewall"] is not None:
        comp.require("unassign")
    return comp


@feature("firewall-unassign", "change", "Remove the firewall from the server",
         "Remove the firewall from the server (the panel's 'Entfernen' on the server's card): its rules stop applying to "
         "this server after about a minute; the firewall itself stays for its other servers",
         verify=_verify_unassign, check=_check_unassign)
def _firewall_unassign(ctx, vm):
    comp = _check_unassign(ctx, vm)
    current = _state(comp)["firewall"]
    if current is None:
        raise ServiceError(f"VM {vm} has no firewall")
    comp.require("unassign")

    def go():
        done = comp.call(("unassign", []))
        return {"vm": vm, "firewall": current, "messages": done.messages()}
    return ctx.send(f"Livewire rootserver.firewall: unassign() [firewall {current['id']}: {current['name']}]", go)


# -- the mail ports ---------------------------------------------------------------------------------------

def _message(v: str, what: str, hi: int) -> str:
    """A text area's text: line breaks and tabs are fine, other control characters are not."""
    v = (v or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if any((ord(c) < 32 and c not in "\n\t") or ord(c) == 127 for c in v):
        raise ServiceError(f"{what} must not contain control characters")
    if not 1 <= len(v) <= hi:
        raise ServiceError(f"{what} must be 1..{hi} characters long")
    return v


def _limit(comp: Component, selector: str, hi: int) -> None:
    node = comp.tree.css_first(selector)
    if node is None or int(node.attributes.get("maxlength") or 0) != hi:
        raise ContractError(f"rootserver.firewall: {selector} no longer has the length limit {hi}")


def _check_request(ctx, vm):
    comp = _component(ctx, vm)
    _state(comp)
    comp.require("requestMailUnlock", models=("purpose", "mailHostname", "acceptTerms"))
    _limit(comp, "#mailUnlockPurpose", PURPOSE_MAX)
    _limit(comp, "#mailUnlockHostname", HOSTNAME_MAX)
    return comp


@tolerant
def _verify_request(ctx, vm, result, purpose, hostname, accept_terms):
    return settle(lambda: _state(_component(ctx, vm, fresh=True))["mail_ports"]["state"] != result["was"])


@feature("mail-unlock-request", "change", "Ask BERO to unlock the mail ports",
         "Ask BERO to unlock the mail ports (25, 465, 587, 2525) of the server (the panel's 'Freischaltung beantragen'). "
         "BERO staff review it and answer in a support ticket: write the purpose as a person would. Only while the "
         "ports are locked and the panel offers the request",
         (Param("purpose", "what the mail ports are for, at most 2000 characters (BERO staff read it)"),
          Param("hostname", "the mail server's host name, e.g. mail.example.org"),
          Param("accept_terms", "yes: you confirm that you send no spam or unsolicited bulk mail and keep BERO's terms "
                                "(the panel's checkbox)", choices=("yes",))),
         verify=_verify_request, check=_check_request)
def _mail_unlock_request(ctx, vm, purpose, hostname, accept_terms):
    purpose = _message(purpose, "purpose", PURPOSE_MAX)
    hostname = dns_name(hostname, "hostname", 3, HOSTNAME_MAX)
    if accept_terms != "yes":
        raise ServiceError("accept_terms must be yes")
    comp = _check_request(ctx, vm)
    state = _state(comp)
    if state["mail_ports"]["unlocked"]:
        raise ServiceError(f"the mail ports of VM {vm} are already unlocked (since {state['mail_ports']['since']})")
    if not state["mail_unlock_requestable"]:
        raise ServiceError(f"the panel offers no unlock request for VM {vm} now ({state['mail_ports']['state']!r})")

    def go():
        done = comp.call(("requestMailUnlock", []),
                         updates={"purpose": purpose, "mailHostname": hostname, "acceptTerms": True})
        return {"vm": vm, "hostname": hostname, "was": state["mail_ports"]["state"], "messages": done.messages()}
    return ctx.send(f"Livewire rootserver.firewall: purpose=<{len(purpose)} characters>, mailHostname={hostname!r}, "
                    "acceptTerms=true, requestMailUnlock()", go)
