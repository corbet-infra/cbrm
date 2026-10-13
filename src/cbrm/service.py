"""The operations every interface offers (CLI, HTTP API, MCP), with the rules in one place:
the allow-list, the repeated target for anything that changes a VM, and the audit log."""
from __future__ import annotations

import datetime
import os
import secrets
import string
from pathlib import Path

from .panel import POWER_ACTIONS, Panel


class ServiceError(ValueError):
    """The request is refused (unknown VM, missing confirmation, ...)."""


class Service:
    def __init__(self, panel: Panel, allow: list[str] | None = None, audit: Path | None = None):
        self.panel = panel
        self.allow = allow if allow is not None else os.environ.get("CBRM_VMS", "").split()
        self.audit_path = audit or panel.state_dir / "audit.log"

    def _audit(self, line: str) -> None:
        fd = os.open(self.audit_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(f"{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%M:%SZ} {line}\n")

    def _vm(self, vm: str, confirm: str | None = None, changing: bool = False) -> str:
        if self.allow and vm not in self.allow:
            raise ServiceError(f"VM {vm} is not in the allow-list")
        if changing and confirm != vm:
            raise ServiceError(f"this changes VM {vm}: repeat it as confirm={vm}")
        return vm

    # reading
    def vms(self) -> list[dict]:
        return [self.panel.status(v) for v in sorted(self.panel.products()) if not self.allow or v in self.allow]

    def status(self, vm: str) -> dict:
        return self.panel.status(self._vm(vm))

    def logs(self, vm: str, n: int = 20) -> list[dict]:
        return [e.__dict__ for e in self.panel.logs(self._vm(vm))[:n]]

    def console_png(self, vm: str) -> bytes:
        from .console import Console
        with Console(*self.panel.console_session(self._vm(vm))) as c:
            return c.png()

    # changing
    def power(self, vm: str, action: str, confirm: str) -> dict:
        self._vm(vm, confirm, changing=True)
        if action not in POWER_ACTIONS:
            raise ServiceError(f"action must be one of {', '.join(POWER_ACTIONS)}")
        self._audit(f"power {vm} {action} requested")
        r = self.panel.power(vm, action)
        self._audit(f"power {vm} {action} -> {r}")
        return r

    def templates(self, vm: str) -> dict:
        return self.panel.templates(self._vm(vm))

    def ssh_keys(self, vm: str) -> dict:
        return self.panel.ssh_keys(self._vm(vm))

    def root_password(self, vm: str, confirm: str) -> dict:
        """Reveals a secret: needs the target repeated, and is audited (without the value)."""
        self._vm(vm, confirm, changing=True)
        self._audit(f"root-password {vm} read")
        return {"vm": vm, "root_password": self.panel.root_password(vm)}

    def set_root_password(self, vm: str, confirm: str, password: str | None = None) -> dict:
        self._vm(vm, confirm, changing=True)
        password = password or "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))
        self._audit(f"root-password {vm} set")
        r = self.panel.set_root_password(vm, password)
        self._audit(f"root-password {vm} set -> {r.get('state')}")
        return {**r, "root_password": password}

    def reinstall(self, vm: str, template: str, ssh_keys: list[str], confirm: str, confirm_destroy: str) -> dict:
        """ERASES THE DISK. Needs confirm=<vm> AND confirm_destroy=<vm>. template and ssh_keys are names
        as the panel shows them (see templates() and ssh_keys())."""
        self._vm(vm, confirm, changing=True)
        if confirm_destroy != vm:
            raise ServiceError(f"reinstall erases VM {vm}: also repeat it as confirm_destroy={vm}")
        templates, keys = self.panel.templates(vm), self.panel.ssh_keys(vm)
        if template not in templates:
            raise ServiceError(f"unknown template {template!r}; one of: {', '.join(templates)}")
        missing = [k for k in ssh_keys if k not in keys]
        if missing:
            raise ServiceError(f"unknown SSH key(s) {missing}; stored in the panel: {', '.join(keys)}")
        self._audit(f"reinstall {vm} template={template} ssh_keys={','.join(ssh_keys)} requested")
        r = self.panel.reinstall(vm, templates[template], [keys[k] for k in ssh_keys])
        self._audit(f"reinstall {vm} -> {r}")
        return r

    def console_input(self, vm: str, text: str = "", keys: list[str] | None = None, confirm: str = "") -> dict:
        self._vm(vm, confirm, changing=True)
        self._audit(f"console {vm} text={len(text)} chars keys={' '.join(keys or [])}")
        from .console import Console
        with Console(*self.panel.console_session(vm)) as c:
            c.type(text)
            c.keys(*(keys or []))
        return {"sent": True}
