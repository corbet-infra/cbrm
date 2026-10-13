"""The Service interface over the HTTP API, so the CLI and the MCP server behave the same whether they
run next to the credential (in-process Service) or against a remote `cbrm serve` (CBRM_API_URL)."""
from __future__ import annotations

import os

import httpx

from .errors import ContractError, PanelError, ServiceError


class Client:
    def __init__(self, url: str, token: str):
        self.http = httpx.Client(base_url=url.rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=300)

    def _do(self, method: str, path: str, **kw):
        try:
            r = self.http.request(method, path, **kw)
        except httpx.TimeoutException as e:
            raise PanelError(f"{method} {path}: no answer from the cbrm API in time; the request may still be "
                             "running there: check with a read feature before repeating it") from e
        except httpx.HTTPError as e:
            raise PanelError(f"{method} {path}: {type(e).__name__}: {e}") from e
        if r.status_code in (403, 409, 502):
            detail = r.json().get("detail", r.text)
            raise {403: ServiceError, 409: ContractError, 502: PanelError}[r.status_code](detail)
        if r.status_code == 401:
            raise ServiceError("the cbrm API refused the token (CBRM_API_TOKEN)")
        r.raise_for_status()
        return r

    def features(self): return self._do("GET", "/features").json()
    def vms(self): return self._do("GET", "/vms").json()
    def check(self, vm): return self._do("GET", f"/vms/{vm}/doctor").json()

    def run(self, name, vm, args=None, *, confirm=None, confirm_destroy=None, confirm_cost=None, dry_run=False):
        r = self._do("POST", f"/vms/{vm}/{name}", json={"args": args or {}, "confirm": confirm, "confirm_destroy":
                     confirm_destroy, "confirm_cost": confirm_cost, "dry_run": dry_run})
        return r.content if r.headers.get("content-type", "").startswith("image/") else r.json()


def backend():
    """CBRM_API_URL (+ CBRM_API_TOKEN) -> remote API client; otherwise the in-process Service."""
    if os.environ.get("CBRM_API_URL"):
        return Client(os.environ["CBRM_API_URL"], os.environ.get("CBRM_API_TOKEN", ""))
    from .config import credentials
    from .panel import Panel
    from .service import Service
    return Service(Panel(*credentials()))
