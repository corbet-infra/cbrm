"""Account-wide features: the SSH keys stored in the panel account (they can be baked into a reinstall).

These are not per VM. The VM argument names the account context: it must belong to the account, the
allow-list applies to it, and `confirm=<vm>` repeats it like for every other changing feature.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import struct

from ..errors import ContractError, ServiceError
from .common import account_page, clean, settle, text, tolerant, value
from .registry import Param, feature

PUBLIC_KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
                    "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com")


def parse_public_key(raw: str) -> tuple[str, str]:
    """-> (the key as one clean line, its MD5 fingerprint as the panel shows it). Refuses everything that is not
    exactly one OpenSSH public key; private keys are rejected without echoing any of the input."""
    t = (raw or "").strip()
    if "-----" in t or "PRIVATE" in t.upper():
        raise ServiceError("this looks like a private key: never give one to cbrm or the panel; pass the public key (*.pub)")
    if "\n" in t or "\r" in t:
        raise ServiceError("give exactly one public key, on one line")
    parts = t.split(None, 2)
    if len(parts) < 2 or parts[0] not in PUBLIC_KEY_TYPES:
        raise ServiceError(f"not an OpenSSH public key; it must start with one of {', '.join(PUBLIC_KEY_TYPES)}")
    try:
        blob = base64.b64decode(parts[1], validate=True)
        (n,) = struct.unpack(">I", blob[:4])
        declared = blob[4:4 + n].decode("ascii")
    except (binascii.Error, struct.error, UnicodeDecodeError):
        raise ServiceError("not an OpenSSH public key: the key data is not valid") from None
    if declared != parts[0] or len(blob) <= 4 + n:
        raise ServiceError("not an OpenSSH public key: the key data does not match its type")
    digest = hashlib.md5(blob, usedforsecurity=False).hexdigest()
    return " ".join(parts), ":".join(digest[i:i + 2] for i in range(0, 32, 2))


def _component(ctx, vm, fresh=False):
    return account_page(ctx, vm, fresh).component("ssh-keys")


def _keys(comp) -> list[dict]:
    if comp.tree.css_first("[wire\\:key='addNewSshKeyToAccount']") is None:
        raise ContractError("ssh-keys: the 'add SSH key' tile is gone from the rendering")
    out = []
    for node in comp.tree.css("[wire\\:key^='existingSshKey']"):
        name, fingerprint = node.css_first("h3 span"), node.css_first("small")
        if name is None or fingerprint is None:
            raise ContractError("ssh-keys: a key tile without a name or a fingerprint")
        out.append({"id": node.attributes["wire:key"].removeprefix("existingSshKey"), "name": text(name),
                    "fingerprint": text(fingerprint)})
    return out


def _check_keys(ctx, vm):
    comp = _component(ctx, vm)
    _keys(comp)
    return comp


def _check_import(ctx, vm):
    return _check_keys(ctx, vm).require("showAddSshKeyImportContent")


def _check_delete(ctx, vm):
    comp = _check_keys(ctx, vm).require("deleteSshKey")
    return comp.require("selectSshKey") if _keys(comp) else comp  # only the key tiles offer selectSshKey


@feature("account-ssh-keys", "read", "SSH keys stored in the panel account (account-wide): id, name, MD5 fingerprint",
         check=_check_keys)
def _account_ssh_keys(ctx, vm):
    return _keys(_component(ctx, vm))


@tolerant
def _verify_import(ctx, vm, result, name, public_key):
    return settle(lambda: any(k["fingerprint"] == result["fingerprint"] and k["name"] == result["name"]
                              for k in _keys(_component(ctx, vm, fresh=True))))


@feature("account-ssh-key-import", "change",
         "Store a public SSH key in the panel account (account-wide; it can then be baked into a reinstall)",
         (Param("name", "the key's name"), Param("public_key", "one OpenSSH public key line (never a private key)",
                                                 secret=True)),
         verify=_verify_import, check=_check_import)
def _account_ssh_key_import(ctx, vm, name, public_key):
    name = clean(name, "name", 1, 100)
    key, fingerprint = parse_public_key(public_key)
    comp = _check_import(ctx, vm)
    stored = _keys(comp)
    if any(k["fingerprint"] == fingerprint for k in stored):
        raise ServiceError("this key is already stored in the account")
    if any(k["name"] == name for k in stored):
        raise ServiceError(f"a key named {name!r} already exists; names must be unique to be addressable")

    def go():
        shown = comp.call(("showAddSshKeyImportContent", []))  # the panel's import form
        shown.require("importSshKey", models=("importSshKeyName", "importSshKeyPublicKey"))
        done = shown._send({"importSshKeyName": name, "importSshKeyPublicKey": key}, [("importSshKey", [])])
        return {"name": name, "fingerprint": fingerprint, "messages": done.messages()}
    return ctx.send(f"Livewire account.ssh-keys: showAddSshKeyImportContent(), importSshKeyName={name!r}, "
                    f"importSshKeyPublicKey=<{fingerprint}>, importSshKey()", go)


@tolerant
def _verify_delete(ctx, vm, result, key):
    return settle(lambda: result["id"] not in [k["id"] for k in _keys(_component(ctx, vm, fresh=True))])


@feature("account-ssh-key-delete", "change",
         "Delete an SSH key from the panel account (account-wide; servers already installed keep it)",
         (Param("key", "the key's id or name from `account-ssh-keys`"),), verify=_verify_delete, check=_check_delete)
def _account_ssh_key_delete(ctx, vm, key):
    comp = _check_keys(ctx, vm).require("deleteSshKey")
    found = [k for k in _keys(comp) if key in (k["id"], k["name"])]
    if len(found) != 1:
        raise ServiceError(f"{key!r} matches {len(found)} stored keys; use the id from `account-ssh-keys`")
    comp.require("selectSshKey")
    target = found[0]

    def go():
        selected = comp.call(("selectSshKey", [int(target["id"])]))  # the panel's delete dialog refers to this key
        if value(selected, "selectedKeyId") != int(target["id"]):
            raise ContractError("ssh-keys: selectSshKey did not select the key; nothing was deleted")
        selected.require("deleteSshKey")
        done = selected._send({}, [("deleteSshKey", [])])
        return {**target, "messages": done.messages()}
    return ctx.send(f"Livewire account.ssh-keys: selectSshKey({target['id']}), deleteSshKey() "
                    f"[{target['name']}, {target['fingerprint']}]", go)
