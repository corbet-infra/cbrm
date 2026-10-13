"""Network: the VM's IP addresses with their reverse DNS, setting rDNS, resetting the network configuration."""
from __future__ import annotations

import ipaddress
import re

from ..errors import ContractError, ServiceError
from .common import dns_name, panel_answer, post_body, post_form, require_element, require_post, settle, tolerant, value
from .registry import Param, feature


def _component(ctx, vm):
    return ctx.product_page(vm).component("i-p-table")


def _addresses(comp) -> list[dict]:
    try:
        out = [{"address": r["address"], "version": int(r["version"]), "prefix": int(r["netmask"]),
                "gateway": r["gateway"], "rdns": r["rdns"]} for r in value(comp, "addresses")]
    except (KeyError, TypeError, ValueError):
        raise ContractError("i-p-table: an address entry lacks address, version, netmask, gateway or rdns") from None
    if not out:
        raise ContractError("i-p-table: no addresses found")
    return out


def _find(addresses: list[dict], address: str) -> dict:
    try:
        want = ipaddress.ip_address(address.strip().split("/")[0])
    except ValueError:
        raise ServiceError(f"{address!r} is not an IP address") from None
    for a in addresses:
        try:
            if ipaddress.ip_address(a["address"]) == want:
                return a
        except ValueError:
            raise ContractError(f"i-p-table: the panel lists {a['address']!r}, which is not an IP address") from None
    raise ServiceError(f"the VM has no address {address}; it has {[a['address'] for a in addresses]}")


@feature("addresses", "read", "The VM's IPv4/IPv6 addresses with prefix length, gateway and reverse DNS entry")
def _addresses_feature(ctx, vm):
    return _addresses(_component(ctx, vm))


# -- reverse DNS --------------------------------------------------------------------------------------

def _check_rdns(ctx, vm):
    comp = _component(ctx, vm).require("openRdnsModal", "changeRdns", models=("rdnsEntry",))
    _addresses(comp)
    return comp


@tolerant
def _verify_rdns(ctx, vm, result, address, name):
    def seen():
        ctx.fresh(vm)
        return _find(_addresses(_component(ctx, vm)), address)["rdns"] == result["rdns"]
    return settle(seen)


@feature("rdns-set", "change", "Set the reverse DNS name of one of the VM's IP addresses (see `addresses`)",
         (Param("address", "the IP address, as `addresses` lists it"),
          Param("name", "the host name the address should resolve to, e.g. mail.example.org")),
         verify=_verify_rdns, check=_check_rdns)
def _rdns_set(ctx, vm, address, name):
    name = dns_name(name, "name")
    comp = _check_rdns(ctx, vm)
    entry = _find(_addresses(comp), address)

    def go():
        opened = comp.call(("openRdnsModal", [entry["address"]]))  # selects the address in the panel's dialog
        current = value(opened, "currentAddress")
        if not isinstance(current, dict) or current.get("address") != entry["address"]:
            raise ContractError("i-p-table: openRdnsModal did not select the address; nothing was changed")
        opened.require("changeRdns", models=("rdnsEntry",))
        done = opened._send({"rdnsEntry": name}, [("changeRdns", [])])
        return {"address": entry["address"], "rdns": name, "was": entry["rdns"], "messages": done.messages()}
    return ctx.send(f"Livewire i-p-table: openRdnsModal({entry['address']!r}), rdnsEntry={name!r}, changeRdns()", go)


# -- network reset ------------------------------------------------------------------------------------

# The panel's reset script copies the root-password form: it posts what is in these two input fields. cbrm
# sends exactly what those fields hold on the page, and only if both are there and empty.
RESET_INPUTS = {"password": "changeRootpasswordPassword", "password_confirmation": "changeRootpasswordPasswordConfirmation"}


def _reset_fields(page, path) -> dict[str, str]:
    body = post_body(page, path) or ""
    fields = {}
    for field, ident in RESET_INPUTS.items():
        read = re.search(r"(?m)(?:^|[{,])\s*" + field + r"\s*:\s*document\.getElementById\('([^']*)'\)\.value", body)
        if read is None or read.group(1) != ident:
            raise ContractError(f"{page.path}: the panel's reset script no longer reads '{field}' from #{ident}")
        node = require_element(page, f"#{ident}", f"the input #{ident} that the panel's reset script reads")
        if node.tag != "input":
            raise ContractError(f"{page.path}: #{ident} is no longer an input field")
        fields[field] = node.attributes.get("value") or ""
        if fields[field] != "":  # not echoed: it could be a password
            raise ContractError(f"{page.path}: #{ident} is not empty, so the panel's reset would post something else "
                                "than cbrm expects")
    return fields


def _check_reset(ctx, vm):
    page = ctx.product_page(vm)
    path = f"/customer/rootserver/{vm}/resetnetwork"
    page.require_endpoint(path)
    require_post(page, path, *RESET_INPUTS)
    require_element(page, "#networkResetModal", "the network reset dialog")
    return page, path, _reset_fields(page, path)


@feature("network-reset", "destroy",
         "Reset the VM's network configuration and software firewall (the panel's 'Netzwerk-Reset'): "
         "everything you configured there is lost",
         check=_check_reset)  # no verify: the panel shows no sign of a network reset to re-read
def _network_reset(ctx, vm):
    page, path, fields = _check_reset(ctx, vm)
    return ctx.send(f"POST {path} password={fields['password']!r} password_confirmation={fields['password_confirmation']!r} "
                    "(what the panel's own button posts: the two empty password fields of its page)",
                    lambda: panel_answer(post_form(ctx, page, path, fields)))
