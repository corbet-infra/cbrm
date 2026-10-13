"""The Service interface over the HTTP API, so the CLI and the MCP server work the same whether they
run next to the credential (in-process Service) or against a remote `cbrm serve` (CBRM_API_URL)."""
from __future__ import annotations

import httpx

from .service import ServiceError


class Client:
    def __init__(self, url: str, token: str):
        self.http = httpx.Client(base_url=url.rstrip("/"), headers={"Authorization": f"Bearer {token}"},
                                 timeout=120)

    def _do(self, method: str, path: str, **kw):
        r = self.http.request(method, path, **kw)
        if r.status_code == 403:
            raise ServiceError(r.json().get("detail", "refused"))
        r.raise_for_status()
        return r

    def vms(self): return self._do("GET", "/vms").json()
    def status(self, vm): return self._do("GET", f"/vms/{vm}").json()
    def logs(self, vm, n=20): return self._do("GET", f"/vms/{vm}/logs", params={"n": n}).json()
    def console_png(self, vm): return self._do("GET", f"/vms/{vm}/console.png").content
    def power(self, vm, action, confirm):
        return self._do("POST", f"/vms/{vm}/power", json={"action": action, "confirm": confirm}).json()
    def console_input(self, vm, text="", keys=None, confirm=""):
        return self._do("POST", f"/vms/{vm}/console/input",
                        json={"text": text, "keys": keys or [], "confirm": confirm}).json()


def backend():
    """CBRM_API_URL (+ CBRM_API_TOKEN) -> remote API client; otherwise the in-process Service."""
    import os
    if os.environ.get("CBRM_API_URL"):
        return Client(os.environ["CBRM_API_URL"], os.environ.get("CBRM_API_TOKEN", ""))
    from .config import credentials
    from .panel import Panel
    from .service import Service
    return Service(Panel(*credentials()))
