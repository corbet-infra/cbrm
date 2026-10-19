"""Private (internal) networks and firewalls of the whole account, from the panel's /customer/network page.

Internal networks: list, create, edit title and description, add and remove servers, delete. Firewalls: list and
read (templates, assigned servers, default policy and rules), create from a template, rename and set the default
policies (the rules are sent back as the panel holds them), and remove a server. Adding, changing or deleting rules,
assigning a server and deleting a firewall are not covered: the panel renders those controls only in states that could
not be recorded read-only, and cbrm does not send what it has not seen. All account-wide: the VM argument only names
the account context (see `common`); what they touch is the whole account, not limited by the VM allow-list.

The panel gives a network's subnet itself and allows a few per account; both are only read. The buttons that add
a server and delete a network only exist while they apply (a network with servers cannot be deleted, a network
that already holds every server has nobody to add), so those two methods are found in the rendering of the
network's own block, never assumed.
"""
from __future__ import annotations

import re

from ..errors import ContractError, ServiceError
from ..livewire import Component, Page
from .common import clean, settle, site_page, tolerant, value
from .common import text as squash
from .registry import Param, feature

PAGE = "/customer/network"
TITLE_MAX, DESCRIPTION_MAX = 255, 2000
_KEY = re.compile(r"internal-network-(\d+)")
_CALL = re.compile(r"\s*(\w+)\(\s*(\d+)\s*\)\s*")


def _component(ctx, vm, fresh=False):
    return site_page(ctx, vm, PAGE, fresh).component("internal-networks")


def _network_id(v) -> str:
    v = str(v).strip()
    if not re.fullmatch(r"[0-9]{1,12}", v):
        raise ServiceError("a network is addressed by its id (see `account-networks`)")
    return v


def _networks(comp: Component) -> dict:
    tree = comp.tree
    chip = next((squash(c) for c in tree.css(".bt-card-head .bt-chip") if re.fullmatch(r"\d+ / \d+", squash(c))), None)
    if chip is None:
        raise ContractError("internal-networks: the usage chip ('used / limit') is gone")
    used, limit = (int(x) for x in chip.split(" / "))
    networks = []
    for node in tree.css("[wire\\:key^='internal-network-']"):
        m = _KEY.fullmatch(node.attributes["wire:key"])
        if m is None:
            continue  # a server row inside a network
        nid = m.group(1)
        title = node.css_first(".fw-bold")
        subnet = next((squash(c) for c in node.css(".bt-chip.font-monospace")), None)
        if title is None or subnet is None or not re.fullmatch(r"[0-9.]+/\d+", subnet):
            raise ContractError(f"internal-networks: network {nid} without a title or a subnet")
        description = node.css_first("small.d-block")
        servers = []
        for row in node.css(f"[wire\\:key^='internal-network-{nid}-server-']"):
            vm = row.attributes["wire:key"].rsplit("-", 1)[-1]
            name, address = row.css_first(".fw-bold"), row.css_first("small")
            if not vm.isdigit() or name is None or address is None:
                raise ContractError(f"internal-networks: a server row of network {nid} without a number, name or address")
            servers.append({"vm": vm, "name": squash(name), "address": squash(address)})
        networks.append({"id": nid, "title": squash(title), "description": squash(description) if description else "",
                         "subnet": subnet, "servers": servers})
    if used != len(networks):
        raise ContractError(f"internal-networks: the page counts {used} networks but shows {len(networks)}")
    return {"networks": networks, "used": used, "limit": limit}


def _find(listing: dict, nid: str) -> dict:
    for n in listing["networks"]:
        if n["id"] == nid:
            return n
    raise ServiceError(f"the account has no internal network {nid}; it has {[n['id'] for n in listing['networks']]}")


def _check_list(ctx, vm):
    comp = _component(ctx, vm)
    _networks(comp)
    return comp


def _check_create(ctx, vm):
    comp = _check_list(ctx, vm)
    if comp.tree.css_first("form[wire\\:submit='create']") is not None:  # hidden once the account's limit is reached
        comp.require("create", models=("title", "description"))
    return comp


def _check_edit(ctx, vm):
    comp = _check_list(ctx, vm)
    if _networks(comp)["networks"]:
        comp.require("startEdit")
    value(comp, "editingId"), value(comp, "editTitle"), value(comp, "editDescription")
    return comp


def _own_calls(node, method: str) -> set[str]:
    """The ids that `method(<id>)` buttons inside `node` pass."""
    found = set()
    for el in node.css("*"):
        for attr, v in el.attributes.items():
            if attr == "wire:click" or attr.startswith("wire:click."):
                m = _CALL.fullmatch(v or "")
                if m and m.group(1) == method:
                    found.add(m.group(2))
    return found


def _block(comp: Component, nid: str):
    for node in comp.tree.css(f"[wire\\:key='internal-network-{nid}']"):
        return node
    raise ContractError(f"internal-networks: the block of network {nid} is gone from the rendering")


def _check_remove(ctx, vm):
    comp = _check_list(ctx, vm)
    servers = [(n["id"], s["vm"]) for n in _networks(comp)["networks"] for s in n["servers"]]
    if servers:
        comp.require("removeServer")
        for nid, svm in servers:
            row = next(iter(_block(comp, nid).css(f"[wire\\:key='internal-network-{nid}-server-{svm}']")))
            if _own_calls(row, "removeServer") != {svm}:
                raise ContractError(f"internal-networks: the remove button of server {svm} names another server")
    return comp


def _add_controls(comp: Component, nid: str):
    """(the select's model name, the add method) in network `nid`'s block, or None while the panel offers none."""
    block = _block(comp, nid)
    select = next((s for s in block.css("select") if "serverToAdd" in " ".join(
        v or "" for k, v in s.attributes.items() if k.startswith("wire:model"))), None)
    if select is None:
        return None
    model = next(v for k, v in select.attributes.items() if k.startswith("wire:model") and "serverToAdd" in (v or ""))
    methods = {m.group(1) for el in block.css("*") for k, v in el.attributes.items()
               if (k == "wire:click" or k.startswith("wire:click.")) and (m := re.fullmatch(r"\s*(add\w*)\(\s*(\d+)\s*\)\s*", v or ""))
               and m.group(2) == nid}
    if len(methods) != 1:
        raise ContractError(f"internal-networks: network {nid} offers a server selection but not exactly one add button")
    return model, methods.pop(), [(o.attributes.get("value") or "", squash(o)) for o in select.css("option")
                                 if o.attributes.get("value")]


def _check_add(ctx, vm):
    comp = _check_list(ctx, vm)
    value(comp, "serverToAdd")
    for n in _networks(comp)["networks"]:
        _add_controls(comp, n["id"])  # raises only if a selection is shown without exactly one matching button
    return comp


def _delete_method(comp: Component, nid: str) -> str | None:
    block = _block(comp, nid)
    methods = {m.group(1) for el in block.css("*") for k, v in el.attributes.items()
               if (k == "wire:click" or k.startswith("wire:click.")) and (m := _CALL.fullmatch(v or ""))
               and m.group(2) == nid and re.fullmatch(r"(delete|destroy|remove)(?!Server)\w*", m.group(1))}
    if len(methods) > 1:
        raise ContractError(f"internal-networks: network {nid} offers several delete buttons {sorted(methods)}")
    return methods.pop() if methods else None


def _check_delete(ctx, vm):
    comp = _check_list(ctx, vm)
    for n in _networks(comp)["networks"]:
        _delete_method(comp, n["id"])
    return comp


# -- reading ----------------------------------------------------------------------------------------------

@feature("account-networks", "read",
         "Internal networks of the account (account-wide): id, title, description, subnet (assigned by the panel), "
         "servers with their internal address, and how many networks the account may have", check=_check_list)
def _account_networks(ctx, vm):
    return _networks(_component(ctx, vm))


# -- changing ---------------------------------------------------------------------------------------------

@tolerant
def _verify_create(ctx, vm, result, title, description=None):
    return settle(lambda: any(n["id"] == result["id"] and n["title"] == result["title"]
                              for n in _networks(_component(ctx, vm, fresh=True))["networks"])
                  if result.get("id") else None)


@feature("account-network-create", "change",
         "Create an internal network (account-wide, not limited by the VM allow-list; free). The panel assigns the "
         "subnet itself, at most a few networks per account (see `account-networks`)",
         (Param("title", "the network's name, at most 255 characters"),
          Param("description", "a description, at most 2000 characters", required=False)),
         verify=_verify_create, check=_check_create)
def _account_network_create(ctx, vm, title, description=None):
    title = clean(title, "title", 1, TITLE_MAX)
    description = clean(description or "", "description", 0, DESCRIPTION_MAX) if description else ""
    comp = _check_create(ctx, vm)
    listing = _networks(comp)
    if listing["used"] >= listing["limit"]:
        raise ServiceError(f"the account has {listing['used']} of {listing['limit']} networks; delete one first")
    comp.require("create", models=("title", "description"))
    for sel, hi in (("#internalNetworkTitle", TITLE_MAX), ("#internalNetworkDescription", DESCRIPTION_MAX)):
        node = comp.tree.css_first(sel)
        if node is None or int(node.attributes.get("maxlength") or 0) != hi:
            raise ContractError(f"internal-networks: {sel} no longer has the length limit {hi}")
    known = {n["id"] for n in listing["networks"]}

    def go():
        done = comp.call(("create", []), updates={"title": title, "description": description})
        after = _networks(_component(ctx, vm, fresh=True))["networks"]
        new = [n for n in after if n["id"] not in known]
        return {"id": new[0]["id"] if len(new) == 1 else None, "title": title,
                "subnet": new[0]["subnet"] if len(new) == 1 else None, "messages": done.messages()}
    return ctx.send(f"Livewire internal-networks: title={title!r}, description=<{len(description)} characters>, create()", go)


def squash_text(s: str) -> str:
    return " ".join(s.split())


@tolerant
def _verify_edit(ctx, vm, result, network, title=None, description=None):
    n = _find(_networks(_component(ctx, vm, fresh=True)), result["id"])
    return n["title"] == squash_text(result["title"]) and n["description"] == squash_text(result["description"])


@feature("account-network-edit", "change",
         "Change an internal network's title and/or description (account-wide, not limited by the VM allow-list; "
         "what you leave out stays as it is; an empty description clears it)",
         (Param("network", "the network's id from `account-networks`"),
          Param("title", "the new title, at most 255 characters", required=False),
          Param("description", "the new description, at most 2000 characters; empty (\"\") clears it", required=False, allow_empty=True)),
         verify=_verify_edit, check=_check_edit)
def _account_network_edit(ctx, vm, network, title=None, description=None):
    nid = _network_id(network)
    if title is None and description is None:
        raise ServiceError("give a new title and/or a new description")
    title = clean(title, "title", 1, TITLE_MAX) if title is not None else None
    description = clean(description, "description", 0, DESCRIPTION_MAX) if description is not None else None
    comp = _check_edit(ctx, vm).require("startEdit")
    current = _find(_networks(comp), nid)

    def go():
        started = comp.call(("startEdit", [int(nid)]))
        if str(value(started, "editingId")) != nid:
            raise ContractError("internal-networks: startEdit did not open the network asked for; nothing was changed")
        started.require("saveEdit", models=("editTitle", "editDescription"))
        for sel, hi in (("#internalNetworkEditTitle", TITLE_MAX), ("#internalNetworkEditDescription", DESCRIPTION_MAX)):
            node = started.tree.css_first(sel)
            if node is None or int(node.attributes.get("maxlength") or 0) != hi:
                raise ContractError(f"internal-networks: {sel} no longer has the length limit {hi}")
        new_title = title if title is not None else value(started, "editTitle")
        new_description = description if description is not None else value(started, "editDescription")
        done = started._send({"editTitle": new_title, "editDescription": new_description}, [("saveEdit", [])])
        return {"id": nid, "title": new_title, "description": new_description, "messages": done.messages()}
    return ctx.send(f"Livewire internal-networks: startEdit({nid}), editTitle={title if title is not None else current['title']!r}, "
                    f"editDescription=<{len(description) if description is not None else 'unchanged'}>, saveEdit()", go)


@tolerant
def _verify_add(ctx, vm, result, network, server):
    return settle(lambda: result["vm"] in [s["vm"] for s in _find(_networks(_component(ctx, vm, fresh=True)), result["id"])["servers"]])


@feature("account-network-server-add", "change",
         "Add a server of the account to an internal network (account-wide, not limited by the VM allow-list; free). "
         "Only servers the panel offers for that network can be added",
         (Param("network", "the network's id from `account-networks`"),
          Param("server", "the server's VM number, as `status` shows it")),
         verify=_verify_add, check=_check_add)
def _account_network_server_add(ctx, vm, network, server):
    nid = _network_id(network)
    svm = str(server).strip().lstrip("#")
    comp = _check_add(ctx, vm)
    listing = _networks(comp)
    net = _find(listing, nid)
    if svm in [s["vm"] for s in net["servers"]]:
        raise ServiceError(f"server {svm} is already in network {nid}")
    controls = _add_controls(comp, nid)
    if controls is None:
        raise ServiceError(f"the panel offers no server to add to network {nid} (every server of the account is in it?)")
    model, method, options = controls
    if svm not in [v for v, _ in options]:
        raise ServiceError(f"the panel does not offer server {svm} for network {nid}; it offers {[v for v, _ in options]}")

    def go():
        done = comp.call((method, [int(nid)]), updates={model: svm})
        return {"id": nid, "vm": svm, "messages": done.messages()}
    return ctx.send(f"Livewire internal-networks: {model}={svm!r}, {method}({nid})", go)


@tolerant
def _verify_remove(ctx, vm, result, network, server):
    return settle(lambda: result["vm"] not in [s["vm"] for s in
                                               _find(_networks(_component(ctx, vm, fresh=True)), result["id"])["servers"]])


@feature("account-network-server-remove", "change",
         "Remove a server from an internal network (account-wide, not limited by the VM allow-list). The server "
         "loses its internal address; the panel assigns one again when it is added back",
         (Param("network", "the network's id from `account-networks`"),
          Param("server", "the server's VM number, as `status` shows it")),
         verify=_verify_remove, check=_check_remove)
def _account_network_server_remove(ctx, vm, network, server):
    nid = _network_id(network)
    svm = str(server).strip().lstrip("#")
    comp = _check_remove(ctx, vm)
    listing = _networks(comp)
    net = _find(listing, nid)
    if svm not in [s["vm"] for s in net["servers"]]:
        raise ServiceError(f"server {svm} is not in network {nid}; it holds {[s['vm'] for s in net['servers']]}")
    if sum(svm in [s["vm"] for s in n["servers"]] for n in listing["networks"]) != 1:
        raise ServiceError(f"server {svm} is in several networks and the panel's remove button names no network")
    comp.require("removeServer")

    def go():
        done = comp.call(("removeServer", [int(svm)]))
        return {"id": nid, "vm": svm, "messages": done.messages()}
    return ctx.send(f"Livewire internal-networks: removeServer({svm}) [network {nid}: {net['title']}]", go)


@tolerant
def _verify_delete(ctx, vm, result, network):
    return settle(lambda: result["id"] not in [n["id"] for n in _networks(_component(ctx, vm, fresh=True))["networks"]])


@feature("account-network-delete", "destroy",
         "Delete an internal network (account-wide, not limited by the VM allow-list). Only a network the panel "
         "offers a delete button for (one without servers); the subnet is gone and may be assigned to another network",
         (Param("network", "the network's id from `account-networks`"),), verify=_verify_delete, check=_check_delete)
def _account_network_delete(ctx, vm, network):
    nid = _network_id(network)
    comp = _check_delete(ctx, vm)
    net = _find(_networks(comp), nid)
    method = _delete_method(comp, nid)
    if method is None:
        raise ServiceError(f"the panel offers no delete for network {nid}"
                           + (f" (it still holds {len(net['servers'])} server(s): remove them first)" if net["servers"] else ""))
    comp.require(method)

    def go():
        done = comp.call((method, [int(nid)]))
        return {"id": nid, "title": net["title"], "subnet": net["subnet"], "messages": done.messages()}
    return ctx.send(f"Livewire internal-networks: {method}({nid}) [{net['title']}, {net['subnet']}]", go)


# -- firewalls (read only) --------------------------------------------------------------------------------

def _firewall_component(ctx, vm):
    return site_page(ctx, vm, PAGE).component("firewalls")


def _firewalls(comp: Component) -> dict:
    tree = comp.tree
    chip = next((squash(c) for c in tree.css(".bt-card-head .bt-chip") if re.fullmatch(r"\d+ / \d+", squash(c))), None)
    if chip is None:
        raise ContractError("firewalls: the usage chip ('used / limit') is gone")
    used, limit = (int(x) for x in chip.split(" / "))
    firewalls = []
    for node in tree.css("[wire\\:key^='firewall-']"):
        m = re.fullmatch(r"firewall-(\d+)", node.attributes["wire:key"])
        if m is None:
            continue
        name, servers = node.css_first("a.fw-bold"), node.css_first("small")
        if name is None or servers is None:
            raise ContractError(f"firewalls: firewall {m.group(1)} without a name")
        firewalls.append({"id": m.group(1), "name": squash(name),
                          "servers": [s.strip() for s in squash(servers).split(",") if s.strip()]})
    if used != len(firewalls):
        raise ContractError(f"firewalls: the page counts {used} firewalls but shows {len(firewalls)}")
    templates = [{"id": o.attributes["value"], "label": squash(o)} for o in tree.css("select option[wire\\:key^='firewall-template-']")]
    return {"firewalls": firewalls, "used": used, "limit": limit, "templates": templates}


def _check_firewalls(ctx, vm):
    _firewalls(_firewall_component(ctx, vm))


@feature("account-firewalls", "read",
         "Firewalls of the account (account-wide): id, name, the servers each is assigned to, how many the account "
         "may have, and the templates the panel offers for a new one", check=_check_firewalls)
def _account_firewalls(ctx, vm):
    return _firewalls(_firewall_component(ctx, vm))


def _firewall(ctx, vm, fid: str) -> dict:
    site_page(ctx, vm, PAGE)
    comp = Page(ctx.panel, f"{PAGE}/firewall/{fid}").component("firewall-editor")
    if value(comp, "loadFailed"):
        raise ContractError("firewall-editor: the panel could not load the firewall")
    if str(value(comp, "firewallId")) != fid:
        raise ContractError("firewall-editor: the panel shows another firewall than asked for")
    servers = []
    for row in comp.tree.css("[wire\\:key^='firewall-server-']"):
        name = row.css_first(".fw-bold")
        servers.append({"vm": row.attributes["wire:key"].rsplit("-", 1)[-1], "name": squash(name) if name else "",
                        "uses_this_firewall": "nutzt diese Firewall" in squash(row)})
    return {"id": fid, "name": value(comp, "title"), "policy_in": value(comp, "policyIn"),
            "policy_out": value(comp, "policyOut"), "rules": value(comp, "rules"), "servers": servers}


def _check_firewall(ctx, vm):
    listing = _firewalls(_firewall_component(ctx, vm))
    if listing["firewalls"]:
        _firewall(ctx, vm, listing["firewalls"][0]["id"])


@feature("account-firewall", "read",
         "One firewall (account-wide): name, default policy per direction (ACCEPT or DROP), the rules as the panel "
         "stores them, and the account's servers with whether each uses this firewall",
         (Param("firewall", "the firewall's id from `account-firewalls`"),), check=_check_firewall)
def _account_firewall(ctx, vm, firewall):
    fid = str(firewall).strip()
    if not re.fullmatch(r"[0-9]{1,12}", fid):
        raise ServiceError("a firewall is addressed by its id (see `account-firewalls`)")
    return _firewall(ctx, vm, fid)


# -- firewalls: create, edit, remove a server -------------------------------------------------------------

FIREWALL_TITLE_MAX = 100
POLICIES = ("ACCEPT", "DROP")


def _firewall_id(v) -> str:
    v = str(v).strip()
    if not re.fullmatch(r"[0-9]{1,12}", v):
        raise ServiceError("a firewall is addressed by its id (see `account-firewalls`)")
    return v


def _check_firewall_create(ctx, vm):
    comp = _firewall_component(ctx, vm)
    _firewalls(comp)
    if comp.tree.css_first("form[wire\\:submit='create']") is None:
        raise ContractError("firewalls: the 'Firewall anlegen' form is gone")
    comp.require("create", models=("title", "template"))
    node = comp.tree.css_first("#firewallTitle")
    if node is None or int(node.attributes.get("maxlength") or 0) != FIREWALL_TITLE_MAX:
        raise ContractError(f"firewalls: #firewallTitle no longer has the length limit {FIREWALL_TITLE_MAX}")
    value(comp, "template")
    return comp


@tolerant
def _verify_firewall_create(ctx, vm, result, title, template=None):
    return settle(lambda: any(f["id"] == result["id"] and f["name"] == result["title"]
                              for f in _firewalls(site_page(ctx, vm, PAGE, fresh=True).component("firewalls"))["firewalls"])
                  if result.get("id") else None)


@feature("account-firewall-create", "change",
         "Create a firewall from one of the panel's templates (account-wide, not limited by the VM allow-list; free). It "
         "applies to no server until one is assigned; the account may have a limited number (see `account-firewalls`)",
         (Param("title", "the firewall's name, at most 100 characters"),
          Param("template", "a template id from `account-firewalls` (empty, linux, windows, webserver, ...); default: "
                            "the panel's preselected one", required=False)),
         verify=_verify_firewall_create, check=_check_firewall_create)
def _account_firewall_create(ctx, vm, title, template=None):
    title = clean(title, "title", 1, FIREWALL_TITLE_MAX)
    comp = _check_firewall_create(ctx, vm)
    listing = _firewalls(comp)
    if listing["used"] >= listing["limit"]:
        raise ServiceError(f"the account has {listing['used']} of {listing['limit']} firewalls")
    offered = [t["id"] for t in listing["templates"]]
    template = (template or str(value(comp, "template"))).strip()
    if template not in offered:
        raise ServiceError(f"template must be one of {offered}")
    known = {f["id"] for f in listing["firewalls"]}

    def go():
        done = comp.call(("create", []), updates={"title": title, "template": template})
        after = _firewalls(site_page(ctx, vm, PAGE, fresh=True).component("firewalls"))["firewalls"]
        new = [f for f in after if f["id"] not in known]
        return {"id": new[0]["id"] if len(new) == 1 else None, "title": title, "template": template,
                "messages": done.messages()}
    return ctx.send(f"Livewire firewalls: title={title!r}, template={template!r}, create()", go)


def _editor(ctx, vm, fid: str) -> Component:
    site_page(ctx, vm, PAGE)  # also proves the VM belongs to the account
    comp = Page(ctx.panel, f"{PAGE}/firewall/{fid}").component("firewall-editor")
    if value(comp, "loadFailed"):
        raise ContractError("firewall-editor: the panel could not load the firewall")
    if str(value(comp, "firewallId")) != fid:
        raise ContractError("firewall-editor: the panel shows another firewall than asked for")
    return comp


def _policy_select(comp: Component, model: str):
    return next((s for s in comp.tree.css("select")
                 if any(k.startswith("wire:model") and v == model for k, v in s.attributes.items())), None)


def _check_editor(comp: Component) -> Component:
    comp.require("save", models=("title", "policyIn", "policyOut"))
    node = comp.tree.css_first("#firewallEditorTitle")
    if node is None or int(node.attributes.get("maxlength") or 0) != FIREWALL_TITLE_MAX:
        raise ContractError(f"firewall-editor: #firewallEditorTitle no longer has the length limit {FIREWALL_TITLE_MAX}")
    for model in ("policyIn", "policyOut"):
        sel = _policy_select(comp, model)
        if sel is None or {o.attributes.get("value") for o in sel.css("option")} != set(POLICIES):
            raise ContractError(f"firewall-editor: the {model} selection no longer offers exactly {list(POLICIES)}")
    value(comp, "rules"), value(comp, "lockoutWarningFor")
    return comp


def _check_firewall_edit(ctx, vm):
    listing = _firewalls(_firewall_component(ctx, vm))
    if listing["firewalls"]:
        _check_editor(_editor(ctx, vm, listing["firewalls"][0]["id"]))


@tolerant
def _verify_firewall_edit(ctx, vm, result, firewall, title=None, policy_in=None, policy_out=None):
    now = _firewall(ctx, vm, result["id"])
    return (now["name"], now["policy_in"], now["policy_out"]) == (result["title"], result["policy_in"], result["policy_out"])


@feature("account-firewall-edit", "change",
         "Rename a firewall and/or set its default policy per direction (ACCEPT or DROP; account-wide, not limited by the "
         "VM allow-list). It applies to every server the firewall is assigned to after about a minute: DROP inbound "
         "without a rule for SSH locks you out. The rules stay as they are; what you leave out stays as it is",
         (Param("firewall", "the firewall's id from `account-firewalls`"),
          Param("title", "the new name, at most 100 characters", required=False),
          Param("policy_in", "default for incoming traffic", required=False, choices=POLICIES),
          Param("policy_out", "default for outgoing traffic", required=False, choices=POLICIES)),
         verify=_verify_firewall_edit, check=_check_firewall_edit)
def _account_firewall_edit(ctx, vm, firewall, title=None, policy_in=None, policy_out=None):
    fid = _firewall_id(firewall)
    if title is None and policy_in is None and policy_out is None:
        raise ServiceError("give a new title, policy_in and/or policy_out")
    title = clean(title, "title", 1, FIREWALL_TITLE_MAX) if title is not None else None
    _find_firewall(ctx, vm, fid)
    comp = _check_editor(_editor(ctx, vm, fid))
    current = {"title": value(comp, "title"), "policyIn": value(comp, "policyIn"), "policyOut": value(comp, "policyOut")}
    updates = {k: v for k, v in (("title", title), ("policyIn", policy_in), ("policyOut", policy_out)) if v is not None}
    want = {**current, **updates}

    def go():
        done = comp.call(("save", []), updates=updates)
        out = {"id": fid, "title": want["title"], "policy_in": want["policyIn"], "policy_out": want["policyOut"],
               "messages": done.messages()}
        warning = value(done, "lockoutWarningFor")
        if warning:
            out["lockout_warning"] = warning  # the panel warns that this change could lock you out
        return out
    return ctx.send(f"Livewire firewall-editor {fid}: " + ", ".join(f"{k}={v!r}" for k, v in updates.items())
                    + f", save() [was {current}; the rules are sent as they are]", go)


def _find_firewall(ctx, vm, fid: str) -> dict:
    listing = _firewalls(_firewall_component(ctx, vm))
    for f in listing["firewalls"]:
        if f["id"] == fid:
            return f
    raise ServiceError(f"the account has no firewall {fid}; it has {[f['id'] for f in listing['firewalls']]}")


def _check_firewall_server_remove(ctx, vm):
    listing = _firewalls(_firewall_component(ctx, vm))
    for f in listing["firewalls"][:1]:
        comp = _editor(ctx, vm, f["id"])
        for row in comp.tree.css("[wire\\:key^='firewall-server-']"):
            svm = row.attributes["wire:key"].rsplit("-", 1)[-1]
            if "nutzt diese Firewall" in squash(row) and _own_calls(row, "unassignServer") != {svm}:
                raise ContractError(f"firewall-editor: the remove button of server {svm} names another server")


@tolerant
def _verify_firewall_server_remove(ctx, vm, result, firewall, server):
    return settle(lambda: not any(s["vm"] == result["vm"] and s["uses_this_firewall"]
                                  for s in _firewall(ctx, vm, result["id"])["servers"]))


@feature("account-firewall-server-remove", "change",
         "Remove a server from a firewall (the editor's 'Entfernen'; account-wide, not limited by the VM allow-list): the "
         "firewall's rules stop applying to that server after about a minute",
         (Param("firewall", "the firewall's id from `account-firewalls`"),
          Param("server", "the server's VM number, as `account-firewall` lists it")),
         verify=_verify_firewall_server_remove, check=_check_firewall_server_remove)
def _account_firewall_server_remove(ctx, vm, firewall, server):
    fid = _firewall_id(firewall)
    svm = str(server).strip().lstrip("#")
    if not svm.isdigit():
        raise ServiceError("a server is addressed by its VM number")
    _find_firewall(ctx, vm, fid)
    comp = _editor(ctx, vm, fid)
    row = next(iter(comp.tree.css(f"[wire\\:key='firewall-server-{svm}']")), None)
    if row is None or "nutzt diese Firewall" not in squash(row):
        raise ServiceError(f"server {svm} does not use firewall {fid}")
    if _own_calls(row, "unassignServer") != {svm}:
        raise ContractError(f"firewall-editor: the remove button of server {svm} names another server")
    comp.require("unassignServer")
    name = row.css_first(".fw-bold")

    def go():
        done = comp.call(("unassignServer", [int(svm)]))
        return {"id": fid, "vm": svm, "messages": done.messages()}
    return ctx.send(f"Livewire firewall-editor {fid}: unassignServer({svm}) [{squash(name) if name else svm}]", go)
