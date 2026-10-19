"""The registry of everything cbrm can do on a VM. Every interface (CLI, HTTP API, MCP) is generated
from it, and `cbrm.service.Service.run` applies the same rules to every entry:

  risk     read     no confirmation
           secret   reveals a secret: confirm=<vm>, audited without the value
           change   confirm=<vm>, audited, verified afterwards where possible
           destroy  erases data: confirm=<vm> and confirm_destroy=<vm>

There is no risk class for spending money: cbrm never extends, upgrades or tops up anything (Julian's
decision, 2026-10-13), and `feature()` refuses any risk not listed here.

A feature's `run(ctx, vm, **args)` does all its reading and contract checks first and hands the one
request that changes something to `ctx.send(description, fn)`: in a dry run that returns the
description instead of sending. `verify(ctx, vm, result, **args)` re-reads the panel afterwards.
`check(ctx, vm)` proves read-only that the panel still offers what the feature needs (`cbrm doctor`).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..errors import ServiceError
from ..livewire import Page
from ..panel import Panel

RISKS = ("read", "secret", "change", "destroy")
FILE_TYPES = {"png": "image/png", "pdf": "application/pdf"}  # features that return bytes, by `returns`


@dataclass(frozen=True)
class Param:
    name: str
    help: str
    type: type = str
    required: bool = True
    choices: tuple[str, ...] = ()
    multiple: bool = False
    secret: bool = False
    default: Any = None
    allow_empty: bool = False  # an empty string is a real value (e.g. clearing a description), not 'not given'


@dataclass(frozen=True)
class Feature:
    name: str
    risk: str
    help: str
    run: Callable
    params: tuple[Param, ...] = ()
    verify: Callable | None = None
    check: Callable | None = None
    returns: str = "json"  # or a file type: "png", "pdf" (bytes; the CLI writes them to --out)
    secret_result: bool = False


REGISTRY: dict[str, Feature] = {}


def feature(name: str, risk: str, help: str, params: tuple[Param, ...] = (), returns: str = "json",
            secret_result: bool = False, verify: Callable | None = None, check: Callable | None = None):
    if risk not in RISKS:  # not an assert: python -O must not let a paying or unknown class through
        raise ValueError(f"{name}: unknown risk class {risk!r}")
    if returns != "json" and returns not in FILE_TYPES:
        raise ValueError(f"{name}: unknown result type {returns!r}")

    def register(fn: Callable) -> Callable:
        REGISTRY[name] = Feature(name, risk, help, fn, params, verify, check, returns, secret_result)
        return fn
    return register


@dataclass
class Ctx:
    panel: Panel
    dry_run: bool = False
    _pages: dict = field(default_factory=dict)

    def product_page(self, vm: str) -> Page:
        if vm not in self._pages:
            pid = self.panel.products().get(vm)
            if pid is None:
                raise ServiceError(f"VM {vm} is not in this account")
            self._pages[vm] = Page(self.panel, f"/customer/products/{pid}")
        return self._pages[vm]

    def fresh(self, vm: str) -> Page:
        self._pages.pop(vm, None)
        return self.product_page(vm)

    def send(self, description: str, fn: Callable[[], Any]) -> Any:
        if self.dry_run:
            return {"dry_run": True, "would": description}
        return fn()


