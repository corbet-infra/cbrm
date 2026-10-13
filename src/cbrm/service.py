"""The one place where cbrm's rules are applied, for every feature and every interface:
the allow-list, the confirmations each risk class needs, dry runs, the audit log and verification."""
from __future__ import annotations

import datetime
import os
from pathlib import Path

from .errors import ServiceError
from .features import REGISTRY, Ctx, Feature
from .panel import Panel


class Service:
    """Use this, not `Panel`, from code: Panel is the raw transport and applies none of the rules.
    An empty allow-list (CBRM_VMS unset) means every VM of the account. The allow-list names the VMs a caller may
    act on; it does not scope the account-wide features (`account-*`): those act on the whole account, whichever
    allowed VM names the context."""

    def __init__(self, panel: Panel, allow: list[str] | None = None, audit: Path | None = None):
        self.panel = panel
        self.allow = allow if allow is not None else os.environ.get("CBRM_VMS", "").split()
        self.audit_path = audit or panel.state_dir / "audit.log"

    def _audit(self, line: str) -> None:
        fd = os.open(self.audit_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(f"{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%M:%SZ} {line}\n")

    def features(self) -> list[dict]:
        return [{"name": f.name, "risk": f.risk, "help": f.help, "returns": f.returns,
                 "params": [{"name": p.name, "help": p.help, "type": p.type.__name__, "required": p.required,
                             "multiple": p.multiple, "choices": list(p.choices), "secret": p.secret} for p in f.params]}
                for f in REGISTRY.values()]

    def vms(self) -> list[dict]:
        return [self.panel.status(v) for v in sorted(self.panel.products()) if not self.allow or v in self.allow]

    def _feature(self, name: str) -> Feature:
        if name not in REGISTRY:
            raise ServiceError(f"unknown feature {name!r}")
        return REGISTRY[name]

    def _args(self, f: Feature, args: dict) -> dict:
        known = {p.name: p for p in f.params}
        unknown = set(args) - set(known)
        if unknown:
            raise ServiceError(f"{f.name}: unknown argument(s) {sorted(unknown)}")
        out = {}
        for p in f.params:
            v = args.get(p.name, p.default)
            if v is None or v == "" or v == ():
                if p.required:
                    raise ServiceError(f"{f.name}: {p.name} is required")
                out[p.name] = p.default
                continue
            if p.multiple:
                v = [v] if isinstance(v, str) else list(v)
                v = [p.type(x) for x in v]
            else:
                v = p.type(v)
            if p.choices and any(x not in p.choices for x in (v if p.multiple else [v])):
                raise ServiceError(f"{f.name}: {p.name} must be one of {list(p.choices)}")
            out[p.name] = v
        return out

    def _gate(self, f: Feature, vm: str, confirm, confirm_destroy, confirm_cost) -> None:
        if self.allow and vm not in self.allow:
            raise ServiceError(f"VM {vm} is not in the allow-list")
        if f.risk in ("secret", "change", "destroy", "cost") and confirm != vm:
            raise ServiceError(f"{f.name} ({f.risk}) acts on VM {vm}: repeat it as confirm={vm}")
        if f.risk == "destroy" and confirm_destroy != vm:
            raise ServiceError(f"{f.name} destroys data on VM {vm}: also repeat it as confirm_destroy={vm}")
        if f.risk == "cost" and not confirm_cost:
            raise ServiceError(f"{f.name} costs money: confirm_cost must repeat the exact amount the panel quotes")

    def run(self, name: str, vm: str, args: dict | None = None, *, confirm: str | None = None,
            confirm_destroy: str | None = None, confirm_cost: str | None = None, dry_run: bool = False):
        """Run a feature. Returns its result (bytes for PNG features). Changing features return a dict with
        `result` and `verified`:

          True   the re-read panel shows the effect
          False  the re-read panel does not show the effect (look again before retrying)
          None   unknown: the feature has no verification, its verification could not tell (it returned None,
                 e.g. the panel hiccuped while re-reading), or it raised; then `verify_error` says why

        None is never turned into False: "could not tell" and "does not show it" are different answers.
        A dry run makes only reading requests and returns {"dry_run": True, "would": ...}."""
        f = self._feature(name)
        a = self._args(f, args or {})
        if self.allow and vm not in self.allow:
            raise ServiceError(f"VM {vm} is not in the allow-list")
        if dry_run and f.risk != "read":
            if f.risk == "secret":  # never reveal anything in a dry run
                return {"dry_run": True, "would": f"reveal {f.name} of VM {vm} (needs confirm={vm})"}
            result = f.run(Ctx(self.panel, dry_run=True), vm, **a)
            if not (isinstance(result, dict) and result.get("dry_run")):
                raise ServiceError(f"{f.name} has no dry run")  # safety net: a dry run never returns real results
            return result
        self._gate(f, vm, confirm, confirm_destroy, confirm_cost)
        ctx = Ctx(self.panel)
        if f.risk == "read":
            return f.run(ctx, vm, **a)
        secret = {p.name for p in f.params if p.secret}
        shown = {k: ("<given>" if k in secret and v else v) for k, v in a.items()}
        self._audit(f"{f.name} {vm} {shown} requested")
        result = f.run(ctx, vm, **a)
        if f.risk == "secret":
            self._audit(f"{f.name} {vm} revealed")
            return result
        logged = sorted(result) if f.secret_result and isinstance(result, dict) else result
        self._audit(f"{f.name} {vm} -> {logged}")
        out = {"result": result, "verified": None}
        if f.verify:
            try:
                v = f.verify(ctx, vm, result, **a)
                out["verified"] = None if v is None else bool(v)  # None stays "unknown"
            except Exception as e:  # the change was sent: never report a verification problem as "not sent"
                out["verify_error"] = f"{type(e).__name__}: {e}"
            self._audit(f"{f.name} {vm} verified={out['verified']}" + (f" ({out['verify_error']})" if "verify_error" in out else ""))
        return out

    def check(self, vm: str) -> dict[str, str]:
        """`cbrm doctor`: for every feature, read-only proof that the panel still offers what it needs.
        One Ctx serves all checks, so the product page, the account page and each lazy component are loaded once
        and every check looks at the same rendering. The checks only read: a check that needs state fresher than
        that (one that re-reads after a change) calls `ctx.fresh(vm)` itself, none does today."""
        if self.allow and vm not in self.allow:
            raise ServiceError(f"VM {vm} is not in the allow-list")
        out = {}
        ctx = Ctx(self.panel)
        for f in REGISTRY.values():
            try:
                if f.check:
                    f.check(ctx, vm)
                elif f.risk == "read" and f.returns == "json" and not any(p.required for p in f.params):
                    f.run(ctx, vm)
                else:
                    out[f.name] = "untested"
                    continue
                out[f.name] = "ok"
            except Exception as e:  # doctor reports, it never crashes: that is when the panel changed
                out[f.name] = f"BROKEN: {type(e).__name__}: {e}"
        return out
