"""Account-wide features: the SSH keys stored in the panel account (they can be baked into a reinstall).

These are not per VM. The VM argument only names the account context: it must belong to the account, it must be
on the allow-list, and `confirm=<vm>` repeats it like for every other changing feature. What these features touch
is the whole account (every stored key, whichever servers use it): their effect is NOT limited by the VM
allow-list, which only decides which VM may be named.
"""
from __future__ import annotations

import base64
import hashlib
import re
import struct

from ..errors import ContractError, ServiceError
from .common import account_page, clean, settle, text, tolerant, value
from .registry import Param, feature

PUBLIC_KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
                    "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com")
MAX_KEY_LINE = 8 * 1024  # bytes: a public key line is far shorter (a 16384-bit RSA key is about 3 KiB)
MIN_RSA_BITS = 2048
_ECDSA = {"ecdsa-sha2-nistp256": ("nistp256", 32), "ecdsa-sha2-nistp384": ("nistp384", 48),
          "ecdsa-sha2-nistp521": ("nistp521", 66), "sk-ecdsa-sha2-nistp256@openssh.com": ("nistp256", 32)}
# PEM/OpenSSH armor lines of a private key; not the same dashes or words inside a comment ("a-----b", "my private key")
_ARMOR = re.compile(r"-----\s*(?:BEGIN|END)\b|PRIVATE KEY\s*-----", re.I)


class _Blob:
    """A strict reader of the SSH wire format (RFC 4251): every read is bounds-checked, every violation a ValueError
    with a fixed message (never any part of the input)."""

    def __init__(self, blob: bytes):
        self.blob, self.pos = blob, 0

    def string(self) -> bytes:
        if self.pos + 4 > len(self.blob):
            raise ValueError("the key data is cut off")
        (n,) = struct.unpack_from(">I", self.blob, self.pos)
        end = self.pos + 4 + n
        if end > len(self.blob):
            raise ValueError("the key data is cut off")
        out, self.pos = self.blob[self.pos + 4:end], end
        return out

    def mpint(self) -> int:
        """A positive multiple-precision integer in its shortest two's-complement form (what OpenSSH accepts)."""
        raw = self.string()
        if not raw or raw[0] & 0x80:
            raise ValueError("the key data holds a zero or negative number")
        if len(raw) > 1 and raw[0] == 0 and not raw[1] & 0x80:
            raise ValueError("the key data holds a number in a non-minimal form")
        n = int.from_bytes(raw, "big")
        if n == 0:
            raise ValueError("the key data holds a zero or negative number")
        return n

    def exactly(self, what: str, size: int) -> bytes:
        raw = self.string()
        if len(raw) != size:
            raise ValueError(f"the {what} does not have the length of its type")
        return raw

    def application(self) -> None:
        """The 'application' string of a security-key (sk-*) public key, e.g. 'ssh:'."""
        try:
            ok = self.string().decode("utf-8").isprintable()
        except UnicodeDecodeError:
            ok = False
        if not ok:
            raise ValueError("the key data holds an unreadable application name")

    def end(self) -> None:
        if self.pos != len(self.blob):
            raise ValueError("the key data has bytes after the key")


def _check_blob(key_type: str, blob: bytes) -> None:
    """The exact layout of each supported key type, nothing after it. Raises ValueError (fixed message)."""
    r = _Blob(blob)
    if r.string() != key_type.encode("ascii"):
        raise ValueError("the key data does not match its type")
    if key_type == "ssh-ed25519":
        r.exactly("public key", 32)
    elif key_type == "ssh-rsa":
        r.mpint()  # e
        if r.mpint().bit_length() < MIN_RSA_BITS:  # n
            raise ValueError(f"RSA keys must have at least {MIN_RSA_BITS} bits")
    elif key_type in _ECDSA:
        curve, size = _ECDSA[key_type]
        if r.string() != curve.encode("ascii"):
            raise ValueError("the key data does not match its curve")
        if r.exactly("EC point", 1 + 2 * size)[0] != 4:  # uncompressed: 0x04 || X || Y
            raise ValueError("the key data holds a compressed EC point")
        if key_type.startswith("sk-"):
            r.application()
    elif key_type == "sk-ssh-ed25519@openssh.com":
        r.exactly("public key", 32)
        r.application()
    else:  # PUBLIC_KEY_TYPES and this function must stay in step
        raise ValueError("this key type is not supported")
    r.end()


def parse_public_key(raw: str) -> tuple[str, str]:
    """-> (the key as one clean line, its MD5 fingerprint as the panel shows it). Refuses everything that is not
    exactly one OpenSSH public key: `<type> <base64> [comment]` on one line of at most 8 KiB, the base64 decoding to
    exactly the layout of that type (no bytes after it; RSA at least 2048 bits). Private keys are rejected
    without echoing any of the input; so are all other refusals."""
    t = (raw or "").strip()
    if len(t.encode("utf-8", "replace")) > MAX_KEY_LINE:
        raise ServiceError(f"not an OpenSSH public key: the line is longer than {MAX_KEY_LINE // 1024} KiB")
    if _ARMOR.search(t):
        raise ServiceError("this looks like a private key: never give one to cbrm or the panel; pass the public key (*.pub)")
    if "\n" in t or "\r" in t:
        raise ServiceError("give exactly one public key, on one line")
    parts = t.split(None, 2)
    if len(parts) < 2 or parts[0] not in PUBLIC_KEY_TYPES:
        raise ServiceError(f"not an OpenSSH public key; it must start with one of {', '.join(PUBLIC_KEY_TYPES)}")
    key_type, encoded = parts[0], parts[1]
    try:
        blob = base64.b64decode(encoded, validate=True)  # ValueError (binascii.Error too) for anything not base64
        if base64.b64encode(blob).decode("ascii") != encoded:  # non-canonical padding bits
            raise ValueError("not canonical base64")
    except ValueError:
        raise ServiceError("not an OpenSSH public key: the key data is not valid") from None
    try:
        _check_blob(key_type, blob)
    except ValueError as e:  # fixed messages only
        raise ServiceError(f"not an OpenSSH public key: {e}") from None
    comment = clean(parts[2] if len(parts) > 2 else "", "comment", 0, MAX_KEY_LINE)
    if not comment.isprintable():  # e.g. U+2028: not a control character, still a line break to some readers
        raise ServiceError("comment must not contain control or separator characters")
    digest = hashlib.md5(blob, usedforsecurity=False).hexdigest()
    return f"{key_type} {encoded}" + (f" {comment}" if comment else ""), ":".join(digest[i:i + 2] for i in range(0, 32, 2))


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
        ident = node.attributes["wire:key"].removeprefix("existingSshKey")
        if not re.fullmatch(r"[0-9]+", ident):
            raise ContractError("ssh-keys: a key tile whose id is not a number")
        out.append({"id": ident, "name": text(name), "fingerprint": text(fingerprint)})
    return out


def _own_select(comp, key_id: str) -> None:
    """The delete button inside the tile of key `key_id` selects exactly that key. cbrm sends the id of the tile
    (`wire:key`); if the tile's own button names another key, the panel's dialog would delete that other one."""
    for node in comp.tree.css(f"[wire\\:key='existingSshKey{key_id}']"):
        selected = {m.group(1) for el in node.css("*") for attr, v in el.attributes.items()
                    if (attr == "wire:click" or attr.startswith("wire:click."))
                    and (m := re.fullmatch(r"selectSshKey\((\d+)\)", (v or "").strip()))}
        if selected != {key_id}:
            raise ContractError(f"ssh-keys: the delete button of key {key_id} selects "
                                f"{', '.join(sorted(selected)) or 'no key'} instead")
        return
    raise ContractError(f"ssh-keys: the tile of key {key_id} is gone from the rendering")


def _check_keys(ctx, vm):
    comp = _component(ctx, vm)
    _keys(comp)
    return comp


def _check_import(ctx, vm):
    comp = _check_keys(ctx, vm).require("showAddSshKeyImportContent")
    for field in ("importSshKeyName", "importSshKeyPublicKey", "addSshKeyContentType"):
        value(comp, field)  # the Livewire state the update will write to; ContractError if it is gone
    return comp


def _check_delete(ctx, vm):
    comp = _check_keys(ctx, vm).require("deleteSshKey")
    keys = _keys(comp)
    if keys:  # only the key tiles offer selectSshKey
        comp.require("selectSshKey")
        for k in keys:
            _own_select(comp, k["id"])
    return comp


@feature("account-ssh-keys", "read", "List the SSH keys stored in the account",
         "SSH keys stored in the panel account: id, name, MD5 fingerprint",
         check=_check_keys)
def _account_ssh_keys(ctx, vm):
    return _keys(_component(ctx, vm))


@tolerant
def _verify_import(ctx, vm, result, name, public_key):
    return settle(lambda: any(k["fingerprint"] == result["fingerprint"] and k["name"] == result["name"]
                              for k in _keys(_component(ctx, vm, fresh=True))))


@feature("account-ssh-key-import", "change", "Store a public SSH key in the account",
         "Store a public SSH key in the panel account; it can then be baked into a reinstall",
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


@feature("account-ssh-key-delete", "change", "Delete a stored SSH key from the account",
         "Delete an SSH key from the panel account; servers already installed keep it",
         (Param("key", "the key's id or name from `account-ssh-keys`"),), verify=_verify_delete, check=_check_delete)
def _account_ssh_key_delete(ctx, vm, key):
    comp = _check_keys(ctx, vm).require("deleteSshKey")
    found = [k for k in _keys(comp) if key in (k["id"], k["name"])]
    if len(found) != 1:
        raise ServiceError(f"{key!r} matches {len(found)} stored keys; use the id from `account-ssh-keys`")
    comp.require("selectSshKey")
    target = found[0]
    _own_select(comp, target["id"])  # the tile's own button must name the key cbrm is about to select

    def go():
        selected = comp.call(("selectSshKey", [int(target["id"])]))  # the panel's delete dialog refers to this key
        # What the panel selected, as the panel reports it: the id AND the name must be those of the tile.
        if (str(value(selected, "selectedKeyId")) != target["id"]
                or " ".join(str(value(selected, "selectedKeyName")).split()) != target["name"]):
            raise ContractError("ssh-keys: selectSshKey did not select the key shown in its tile; nothing was deleted")
        selected.require("deleteSshKey")
        done = selected._send({}, [("deleteSshKey", [])])
        return {**target, "messages": done.messages()}
    return ctx.send(f"Livewire account.ssh-keys: selectSshKey({target['id']}), deleteSshKey() "
                    f"[{target['name']}, {target['fingerprint']}]", go)
