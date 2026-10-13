"""Network: the VM's IP addresses with their reverse DNS, setting rDNS, resetting the network configuration."""
from __future__ import annotations

import ipaddress

from ..errors import ContractError, ServiceError
from .common import dns_name, ok, panel_answer, post_form, require_element, require_post, settle, tolerant, value
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

def _check_reset(ctx, vm):
    page = ctx.product_page(vm)
    path = f"/customer/rootserver/{vm}/resetnetwork"
    page.require_endpoint(path)
    # The panel's script copies the root-password form: it posts two (empty) password fields along.
    require_post(page, path, "password", "password_confirmation")
    require_element(page, "#networkResetModal", "the network reset dialog")
    return page, path


@feature("network-reset", "destroy",
         "Reset the VM's network configuration and software firewall (the panel's 'Netzwerk-Reset'): "
         "everything you configured there is lost",
         verify=lambda ctx, vm, result: ok(result), check=_check_reset)
def _network_reset(ctx, vm):
    page, path = _check_reset(ctx, vm)
    return ctx.send(f"POST {path} password='' password_confirmation='' (as the panel's own button does)",
                    lambda: panel_answer(post_form(ctx, page, path, {"password": "", "password_confirmation": ""})))
