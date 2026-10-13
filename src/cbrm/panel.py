"""The BERO HOST customer panel (bero-host.de) has no API. This module speaks the panel's own HTTP:
a form login, server-rendered pages, one Livewire request for the action log, and the JSON endpoints
its power buttons call. Only reading and power exist here; everything else stays in the panel."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

BASE = "https://bero-host.de"
POWER_ACTIONS = ("start", "stop", "shutdown", "restart")


from .errors import ContractError, PanelError


@dataclass
class LogEntry:
    date: str    # panel time (Europe/Berlin), as the panel shows it: "11.10.2026 00:02"
    action: str  # e.g. "Rootserver installieren", "Neustarten"


def _lines(html: str) -> list[str]:
    tree = HTMLParser(html)
    for node in tree.css("script, style"):
        node.decompose()
    root = tree.body or tree.root
    return [l.strip() for l in root.text(separator="\n").splitlines() if l.strip()]


class Panel:
    """A logged-in panel session. Cookies persist in `state_dir` (mode 0600) between runs."""

    def __init__(self, user: str, password: str, state_dir: Path | None = None):
        self._user, self._password = user, password
        self.state_dir = state_dir or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "cbrm"
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._cookies = self.state_dir / "cookies.json"
        jar = httpx.Cookies()
        try:
            for name, value in json.loads(self._cookies.read_text()).items():
                jar.set(name, value, domain="bero-host.de")
        except (OSError, ValueError, AttributeError):
            pass  # no or unreadable session file: log in afresh
        self._lock = threading.RLock()  # `cbrm serve` handles requests in threads: one login, one product scan
        self.http = httpx.Client(base_url=BASE, cookies=jar, timeout=60,
                                 headers={"User-Agent": "cbrm (+https://git.corbet.ch/corbet-infra/cbrm)"})
        self._products: dict[str, str] | None = None

    # -- session -----------------------------------------------------------------------------
    def _save(self) -> None:
        """Atomically: a temp file (0600 from the start) renamed over the old one."""
        fd, tmp = tempfile.mkstemp(dir=self.state_dir, prefix=".cookies-")
        with os.fdopen(fd, "w") as f:
            json.dump({c.name: c.value for c in self.http.cookies.jar}, f)
        os.replace(tmp, self._cookies)

    def _login(self) -> None:
        self.http.cookies.clear()  # a stale session cookie would shadow the new one
        form = HTMLParser(self.http.get("/login").text).css_first("form[action$='/login'] input[name=_token]")
        if form is None:
            raise PanelError("login form not found")
        r = self.http.post("/login", data={"_token": form.attributes["value"], "email": self._user,
                                            "password": self._password})
        if r.status_code != 302 or "/login" in r.headers.get("location", ""):
            raise PanelError("login failed")
        self._save()

    def _get(self, path: str, **kw) -> httpx.Response:
        try:
            r = self.http.get(path, **kw)
            if r.status_code == 302 and "/login" in r.headers.get("location", ""):
                with self._lock:
                    self._login()
                r = self.http.get(path, **kw)
            r.raise_for_status()
            return r
        except httpx.HTTPError as e:
            raise PanelError(f"GET {path}: {type(e).__name__}: {e}") from e

    def page(self, path: str) -> str:
        """GET a panel page, logging in again when the session has expired."""
        return self._get(path).text

    # -- reading -----------------------------------------------------------------------------
    def products(self) -> dict[str, str]:
        """VM id -> product id, for every KVM rootserver in the account."""
        with self._lock:
            if self._products is None:
                found = {}
                for pid in sorted(set(re.findall(r"/customer/products/(\d+)", self.page("/customer")))):
                    title = HTMLParser(self.page(f"/customer/products/{pid}")).css_first("title")
                    m = re.search(r"#(\d+) \(KVM Rootserver #%s\)" % pid, title.text() if title else "")
                    if m:
                        found[m.group(1)] = pid
                self._products = found  # published only when complete
            return self._products

    def _product_page(self, vm: str) -> str:
        pid = self.products().get(vm)
        if pid is None:
            raise PanelError(f"VM {vm} is not in this account")
        return self.page(f"/customer/products/{pid}")

    def status(self, vm: str) -> dict[str, str]:
        """Overview fields. `system` is the last template BERO installed, not what is running now."""
        lines = _lines(self._product_page(vm))
        i = next((k for k, l in enumerate(lines) if l.startswith("KVM Rootserver #")), None)
        if i is None or i + 1 >= len(lines):
            raise ContractError(f"product page of {vm}: no overview")
        out = {"vm": vm, "state": lines[i + 1]}
        names = {"Hostname": "hostname", "Installiertes System": "system", "Haupt IP-Adressen": "ipv4"}
        for k in range(i, min(len(lines) - 2, i + 80)):
            if lines[k] in names:
                out[names[lines[k]]] = lines[k + 1]
            if lines[k] == "Haupt IP-Adressen":
                out["ipv6"] = lines[k + 2]
            if lines[k].startswith("Letztes Backup"):
                out["last_backup"] = lines[k].split(":", 1)[1].strip() or lines[k + 1]
                break
        return out

    def logs(self, vm: str) -> list[LogEntry]:
        """The panel's action log, newest first. It is a lazy Livewire component: replay its
        __lazyLoad call with the component's own snapshot."""
        html = self._product_page(vm)
        tree = HTMLParser(html)
        csrf = tree.css_first("meta[name=csrf-token]").attributes["content"]
        uri = tree.css_first("[data-update-uri]").attributes["data-update-uri"]
        for node in tree.css("[wire\\:snapshot][x-intersect]"):
            snapshot = node.attributes["wire:snapshot"]
            if json.loads(snapshot)["memo"]["name"].endswith(".logs-table"):
                param = re.search(r"__lazyLoad\('([^']+)'\)", node.attributes["x-intersect"]).group(1)
                break
        else:
            raise PanelError("log component not found")
        r = self.http.post(uri, headers={"X-Livewire": "true", "X-CSRF-TOKEN": csrf}, json={
            "_token": csrf, "components": [{"snapshot": snapshot, "updates": {},
                                            "calls": [{"path": "", "method": "__lazyLoad", "params": [param]}]}]})
        r.raise_for_status()
        # Rows read "Datum : 11.10.2026 | 00:02 Uhr  Aktion: Starten"; line breaks vary with the parser.
        lines = _lines(r.json()["components"][0]["effects"]["html"])
        entries, date = [], None
        for k, line in enumerate(lines):
            if m := re.search(r"(\d{2}\.\d{2}\.\d{4}) \| (\d{2}:\d{2})", line):
                date = f"{m.group(1)} {m.group(2)}"
            elif line.startswith("Aktion:") and date and k + 1 < len(lines):
                entries.append(LogEntry(date, line[len("Aktion:"):].strip() or lines[k + 1]))
                date = None
        return entries

    def console_session(self, vm: str) -> tuple[str, int, str]:
        """(host, port, password) of a fresh noVNC session. The password is a Proxmox VNC ticket."""
        iframe = HTMLParser(self.page(f"/customer/rootserver/{vm}/vnc")).css_first("iframe")
        if iframe is None or not iframe.attributes.get("src"):
            raise ContractError(f"console page of {vm}: no noVNC frame")
        src = iframe.attributes["src"]
        q = httpx.URL(src).params
        if not (q.get("host") and q.get("port") and q.get("password")):
            raise PanelError(f"no console session offered for {vm}")
        try:
            port = int(q["port"])
        except ValueError:
            raise ContractError(f"console page of {vm}: the noVNC frame offers a port that is not a number") from None
        return q["host"], port, q["password"]

    def _form_token(self, html: str) -> str:
        return HTMLParser(html).css_first("meta[name=csrf-token]").attributes["content"]

    def templates(self, vm: str) -> dict[str, str]:
        """Installable operating systems: name -> template id (from the reinstall form)."""
        sel = HTMLParser(self._product_page(vm)).css_first("select#rootserverTemplate")
        return {o.text().strip(): o.attributes["value"] for o in sel.css("option")}

    def ssh_keys(self, vm: str) -> dict[str, str]:
        """SSH keys stored in the panel account: name -> key id (selectable on reinstall)."""
        nodes = HTMLParser(self._product_page(vm)).css("[id^=ssh_key_][data-id]")
        # The tile shows the name, then the key's fingerprint: the name is the first line.
        return {next(l.strip() for l in n.text().splitlines() if l.strip()): n.attributes["data-id"] for n in nodes}

    def root_password(self, vm: str) -> str:
        """The root password the panel shows for the VM (set at the last install or change)."""
        node = HTMLParser(self._product_page(vm)).css_first("#password[data-password]")
        if node is None:
            raise PanelError(f"no root password shown for {vm}")
        return node.attributes["data-password"]

    # -- changing ----------------------------------------------------------------------------
    def _post_json(self, vm: str, action: str, data: dict) -> dict:
        data = {"_token": self._form_token(self._product_page(vm)), **data}
        try:
            r = self.http.post(f"/customer/rootserver/{vm}/{action}", data=data,
                               headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise PanelError(f"POST {action}: {type(e).__name__}: {e}") from e

    def set_root_password(self, vm: str, password: str) -> dict:
        return self._post_json(vm, "setrootpassword", {"password": password, "password_confirmation": password})

    def reinstall(self, vm: str, template_id: str, ssh_key_ids: list[str]) -> dict:
        """Reinstalls the VM from a template: ERASES ITS DISK. The panel generates a new root password."""
        return self._post_json(vm, "reinstall", {"template": template_id, "ssh_keys[]": list(ssh_key_ids)})

    def get_json(self, path: str, params: dict | None = None) -> dict:
        """A panel endpoint the page's JavaScript calls with $.getJSON."""
        r = self._get(path, params=params, headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
        try:
            return r.json()
        except ValueError as e:
            raise PanelError(f"GET {path}: not JSON") from e

    def power(self, vm: str, action: str) -> dict:
        if action not in POWER_ACTIONS:
            raise PanelError(f"power action must be one of {POWER_ACTIONS}")
        self._product_page(vm)  # also proves the VM belongs to this account
        return self.get_json(f"/customer/rootserver/{vm}/{action}")
