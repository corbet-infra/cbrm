"""A VM's own internal-network membership, from the "Interne Netzwerke" card of its product page.

Three changes: connect the VM to an internal network, disconnect it, and change its internal IP in the network.
(Creating, editing and deleting networks, and adding servers from the network side, are the account-wide
`account-network-*` features in `internal_networks`.) These act on one VM, so the normal allow-list applies.

The card is one Livewire component (`internal-network`). While the VM is connected it shows the network, the
subnet and the VM's address and offers `saveAddress` (model `address`) and `disconnect`; while it is not, it
offers a network selection (model `selectedNetworkId`) and a connect button. The panel's own text says the IP
is only a proposal and is not configured on the VM, and that the second NIC appears about a minute after
connecting: cbrm changes the panel's record, never the guest.

The connect button of an unconnected VM is found in the rendering (the one `connect…` method next to the
selection), never assumed; if the card looks different from that, nothing is sent.
"""
from __future__ import annotations

import ipaddress
import re

from ..errors import ContractError, ServiceError
from ..livewire import Component
from .common import settle, tolerant, value
from .common import text as squash
from .registry import Param, feature

_GUIDE = re.compile(r"internal-network-guide-(\d+)-")
_CALL = re.compile(r"\s*(connect\w*)\s*(?:\(\s*\))?\s*")
ADDRESS_MAX = 15


def _component(ctx, vm, fresh=False) -> Component:
    page = ctx.fresh(vm) if fresh else ctx.product_page(vm)
    return page.component("internal-network")


def _methods(comp: Component, pattern: re.Pattern) -> set[str]:
    found = set()
    for el in comp.tree.css("*"):
        for attr, v in el.attributes.items():
            if attr in ("wire:click", "wire:submit") or attr.startswith(("wire:click.", "wire:submit.")):
                m = pattern.fullmatch(v or "")
                if m:
                    found.add(m.group(1))
    return found


def _select(comp: Component):
    return next((s for s in comp.tree.css("select")
                 if any(k.startswith("wire:model") and v == "selectedNetworkId" for k, v in s.attributes.items())), None)


def _state(comp: Component) -> dict:
    """{"connected": True, network, title, subnet, address} or {"connected": False, options: [(id, label)]}."""
    value(comp, "selectedNetworkId"), value(comp, "address")
    if comp.offers("disconnect"):
        tree = comp.tree
        name = tree.css_first(".ncd-name")
        subnet = tree.css_first(".ncd-pill[title='Subnetz']")
        pill = tree.css_first(".ncd-pill[title='Interne IP']")
        guide = next(iter(tree.css("[wire\\:key^='internal-network-guide-']")), None)
        m = _GUIDE.match(guide.attributes["wire:key"]) if guide is not None else None
        if name is None or subnet is None or pill is None or m is None:
            raise ContractError("internal-network: the connected card no longer shows network, subnet, address and guide")
        address, net = squash(pill), squash(subnet)
        if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", address) or not re.fullmatch(r"\d+\.\d+\.\d+\.\d+/\d+", net):
            raise ContractError("internal-network: unreadable subnet or internal IP")
        if str(value(comp, "address")) != address:
            raise ContractError("internal-network: the component's address differs from the one shown")
        return {"connected": True, "network": m.group(1), "title": squash(name), "subnet": net, "address": address}
    sel = _select(comp)
    options = [(o.attributes["value"], squash(o)) for o in sel.css("option") if o.attributes.get("value")] if sel is not None else []
    return {"connected": False, "options": options}


def _connect_method(comp: Component) -> str:
    methods = _methods(comp, _CALL)
    if len(methods) != 1:
        raise ContractError(f"internal-network: expected exactly one connect button next to the network selection, found {sorted(methods)}")
    return methods.pop()


def _check_connect(ctx, vm):
    comp = _component(ctx, vm)
    if not _state(comp)["connected"] and _select(comp) is not None:
        comp.require(_connect_method(comp), models=("selectedNetworkId",))
    return comp


def _check_disconnect(ctx, vm):
    comp = _component(ctx, vm)
    if _state(comp)["connected"]:
        comp.require("disconnect")
    return comp


def _check_address(ctx, vm):
    comp = _component(ctx, vm)
    if _state(comp)["connected"]:
        comp.require("saveAddress", models=("address",))
        node = comp.tree.css_first("#internalAddress")
        if node is None or int(node.attributes.get("maxlength") or 0) != ADDRESS_MAX:
            raise ContractError(f"internal-network: #internalAddress no longer has the length limit {ADDRESS_MAX}")
    return comp


def _network_id(v) -> str:
    v = str(v).strip()
    if not re.fullmatch(r"[0-9]{1,12}", v):
        raise ServiceError("a network is addressed by its id (see `account-networks`)")
    return v


# -- connect ----------------------------------------------------------------------------------------------

@tolerant
def _verify_connect(ctx, vm, result, network):
    return settle(lambda: (s := _state(_component(ctx, vm, fresh=True)))["connected"] and s["network"] == result["network"])


@feature("network-connect", "change", "Connect the VM to an internal network",
         "Connect the VM to an internal network (free; the panel assigns the VM's address in the subnet, change it "
         "with `network-address-set`). The VM must not be connected yet: disconnect it first to move it. The guest's "
         "second NIC appears about a minute later and is not configured by the panel",
         (Param("network", "the network's id from `account-networks`"),), verify=_verify_connect, check=_check_connect)
def _network_connect(ctx, vm, network):
    nid = _network_id(network)
    comp = _check_connect(ctx, vm)
    state = _state(comp)
    if state["connected"]:
        raise ServiceError(f"VM {vm} is already connected to network {state['network']} ({state['title']}); "
                           "disconnect it first (`network-disconnect`)")
    if _select(comp) is None:
        raise ServiceError("the panel offers this VM no network to connect to (create one with `account-network-create`)")
    if nid not in [v for v, _ in state["options"]]:
        raise ServiceError(f"the panel does not offer network {nid} for VM {vm}; it offers {[v for v, _ in state['options']]}")
    method = _connect_method(comp)

    def go():
        done = comp.call((method, []), updates={"selectedNetworkId": nid})
        after = _state(_component(ctx, vm, fresh=True))
        return {"vm": vm, "network": nid, "connected": after["connected"], "address": after.get("address"),
                "messages": done.messages()}
    return ctx.send(f"Livewire internal-network: selectedNetworkId={nid!r}, {method}()", go)


# -- disconnect -------------------------------------------------------------------------------------------

@tolerant
def _verify_disconnect(ctx, vm, result):
    return settle(lambda: not _state(_component(ctx, vm, fresh=True))["connected"])


@feature("network-disconnect", "change", "Disconnect the VM from its internal network",
         "Disconnect the VM from its internal network. The VM loses its internal address (a new connection gets one "
         "assigned again); traffic over the second NIC stops",
         verify=_verify_disconnect, check=_check_disconnect)
def _network_disconnect(ctx, vm):
    comp = _check_disconnect(ctx, vm)
    state = _state(comp)
    if not state["connected"]:
        raise ServiceError(f"VM {vm} is not connected to an internal network")
    comp.require("disconnect")

    def go():
        done = comp.call(("disconnect", []))
        return {"vm": vm, "network": state["network"], "title": state["title"], "was": state["address"],
                "messages": done.messages()}
    return ctx.send(f"Livewire internal-network: disconnect() [network {state['network']}: {state['title']}, {state['address']}]", go)


# -- change the address -----------------------------------------------------------------------------------

@tolerant
def _verify_address(ctx, vm, result, address):
    return settle(lambda: _state(_component(ctx, vm, fresh=True))["address"] == result["address"])


@feature("network-address-set", "change", "Change the VM's internal IP address",
         "Change the VM's internal IP in its internal network (any free address of the subnet, not the network or "
         "broadcast address). The panel only records it: the guest's NIC is configured by you",
         (Param("address", "the new IPv4 address, inside the network's subnet"),),
         verify=_verify_address, check=_check_address)
def _network_address_set(ctx, vm, address):
    try:
        new = ipaddress.IPv4Address(str(address).strip())
    except ValueError:
        raise ServiceError("address must be an IPv4 address like 10.0.0.5") from None
    comp = _check_address(ctx, vm)
    state = _state(comp)
    if not state["connected"]:
        raise ServiceError(f"VM {vm} is not connected to an internal network (`network-connect` first)")
    net = ipaddress.IPv4Network(state["subnet"], strict=False)
    if new not in net or new in (net.network_address, net.broadcast_address):
        raise ServiceError(f"{new} is not a usable address of {net}")
    if str(new) == state["address"]:
        raise ServiceError(f"VM {vm} already has {new} in network {state['network']}")
    comp.require("saveAddress", models=("address",))

    def go():
        done = comp.call(("saveAddress", []), updates={"address": str(new)})
        return {"vm": vm, "network": state["network"], "address": str(new), "was": state["address"],
                "messages": done.messages()}
    return ctx.send(f"Livewire internal-network: address={str(new)!r}, saveAddress() [network {state['network']}, was {state['address']}]", go)
