"""The operations every interface offers (CLI, HTTP API, MCP), with the rules in one place:
the allow-list, the repeated target for anything that changes a VM, and the audit log."""
from __future__ import annotations

import datetime
import os
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

    def console_input(self, vm: str, text: str = "", keys: list[str] | None = None, confirm: str = "") -> dict:
        self._vm(vm, confirm, changing=True)
        self._audit(f"console {vm} text={len(text)} chars keys={' '.join(keys or [])}")
        from .console import Console
        with Console(*self.panel.console_session(vm)) as c:
            c.type(text)
            c.keys(*(keys or []))
        return {"sent": True}
