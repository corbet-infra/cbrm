"""Livewire 3, the protocol behind the panel's interactive parts, spoken directly.

A page carries components (`wire:snapshot`); some render lazily (`x-intersect="$wire.__lazyLoad(...)"`).
A call posts the component's snapshot plus model updates and method calls to the page's update URI and
gets the new snapshot and HTML back. Before anything is sent, `require` checks that the rendered
component really offers the methods and models the caller relies on: if BERO changed the panel, cbrm
raises `ContractError` and sends nothing, instead of calling something that now means something else.
"""
from __future__ import annotations

import json
import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from .errors import ContractError

_LAZY = re.compile(r"__lazyLoad\('([^']+)'\)")


class Page:
    def __init__(self, panel, path: str):
        self.panel, self.path = panel, path
        self.html = panel.page(path)
        self.tree = HTMLParser(self.html)
        meta, update = self.tree.css_first("meta[name=csrf-token]"), self.tree.css_first("[data-update-uri]")
        if meta is None or update is None:
            raise ContractError(f"{path}: no Livewire on this page (CSRF token or update URI missing)")
        self.csrf, self.update_uri = meta.attributes["content"], update.attributes["data-update-uri"]

    def component(self, suffix: str) -> "Component":
        """The component whose name is `suffix` or ends in `.suffix`, rendered (lazy ones are loaded)."""
        for node in self.tree.css("[wire\\:snapshot]"):
            snapshot = node.attributes["wire:snapshot"]
            name = json.loads(snapshot)["memo"]["name"]
            if name == suffix or name.endswith("." + suffix):
                c = Component(self, name, snapshot, node.html)
                lazy = _LAZY.search(node.attributes.get("x-intersect") or "")
                return c._send({}, [("__lazyLoad", [lazy.group(1)])]) if lazy else c
        raise ContractError(f"{self.path}: component '{suffix}' not found")

    def require_endpoint(self, path_prefix: str) -> None:
        """The page's own JavaScript still calls this endpoint (e.g. `/customer/rootserver/1/boot_order`)."""
        if path_prefix not in self.html:
            raise ContractError(f"{self.path}: the panel no longer calls {path_prefix}")


class Component:
    def __init__(self, page: Page, name: str, snapshot: str, html: str, effects: dict | None = None):
        self.page, self.name, self.snapshot, self.html = page, name, snapshot, html
        self.effects = effects or {}

    @property
    def data(self) -> dict:
        return json.loads(self.snapshot)["data"]

    @property
    def tree(self) -> HTMLParser:
        return HTMLParser(self.html)

    def offers(self, method: str) -> bool:
        return re.search(r'wire:(?:click|submit)[\w.]*="' + re.escape(method) + r"\b", self.html) is not None

    def require(self, *methods: str, models: tuple[str, ...] = ()) -> "Component":
        missing = [f"method {m}" for m in methods if not self.offers(m)]
        missing += [f"field {m}" for m in models
                    if not re.search(r'wire:model[\w.]*="' + re.escape(m) + '"', self.html)]
        if missing:
            raise ContractError(f"{self.name}: the panel no longer offers {', '.join(missing)}")
        return self

    def set(self, **updates) -> "Component":
        self.require(models=tuple(updates))
        return self._send(updates, [])

    def call(self, *calls: tuple[str, list], updates: dict | None = None) -> "Component":
        """One request with model updates and method calls, e.g. call(("setCurrentDrive", ["ide0"]), ("unmountIso", []))."""
        self.require(*(m for m, _ in calls), models=tuple(updates or ()))
        return self._send(updates or {}, list(calls))

    def _send(self, updates: dict, calls: list[tuple[str, list]]) -> "Component":
        p = self.page
        r = p.panel.http.post(p.update_uri, headers={"X-Livewire": "true", "X-CSRF-TOKEN": p.csrf}, json={
            "_token": p.csrf,
            "components": [{"snapshot": self.snapshot, "updates": updates,
                            "calls": [{"path": "", "method": m, "params": a} for m, a in calls]}]})
        r.raise_for_status()
        out = r.json()["components"][0]
        effects = out.get("effects", {})
        return Component(p, self.name, out["snapshot"], effects.get("html", self.html), effects)

    def messages(self) -> list[str]:
        """Toast texts the component dispatched (success or error notices), if any."""
        found = []
        for d in self.effects.get("dispatches", []):
            params = d.get("params")
            values = params.values() if isinstance(params, dict) else (params or [])
            found += [str(v) for v in values if isinstance(v, str)]
        return found
