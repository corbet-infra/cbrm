"""HTTP API, generated from the feature registry (OpenAPI at /openapi.json, docs at /docs).
It holds the panel credential, so CLIs and MCP servers elsewhere only need its URL and token."""
from __future__ import annotations

import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from . import __version__
from .errors import ContractError, PanelError, ServiceError
from .features import REGISTRY
from .service import Service

_bearer = HTTPBearer()


def _auth(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> None:
    token = os.environ.get("CBRM_API_TOKEN", "")
    if not token or not secrets.compare_digest(cred.credentials.encode(), token.encode()):
        raise HTTPException(401, "bad token")


class RunRequest(BaseModel):
    args: dict = {}
    confirm: str | None = None
    confirm_destroy: str | None = None
    dry_run: bool = False


def create_app(service: Service) -> FastAPI:
    # FastAPI's own docs routes would bypass the app-level token: switch them off and serve the schema
    # through an authenticated route instead.
    app = FastAPI(title="cbrm", version=__version__, dependencies=[Depends(_auth)], docs_url=None, redoc_url=None,
                  openapi_url=None, description="BERO HOST management. GET /features lists every operation with its risk class.")

    @app.get("/openapi.json", include_in_schema=False)
    def openapi() -> dict:
        return app.openapi()

    @app.exception_handler(ServiceError)
    async def refused(_: Request, e: ServiceError):
        return JSONResponse({"detail": str(e), "kind": "refused"}, status_code=403)

    @app.exception_handler(ContractError)
    async def contract(_: Request, e: ContractError):
        return JSONResponse({"detail": f"the panel changed, so the change was not made: {e}", "kind": "panel-changed"},
                            status_code=409)

    @app.exception_handler(PanelError)
    async def panel(_: Request, e: PanelError):
        return JSONResponse({"detail": str(e), "kind": "panel-error"}, status_code=502)

    def respond(result):
        return Response(result, media_type="image/png") if isinstance(result, bytes) else result

    @app.get("/features")
    def features() -> list[dict]:
        return service.features()

    @app.get("/vms")
    def vms() -> list[dict]:
        return service.vms()

    @app.get("/vms/{vm}/doctor")
    def doctor(vm: str) -> dict:
        return service.check(vm)

    @app.get("/vms/{vm}/{feature}")
    def read(vm: str, feature: str, request: Request):
        """Read-only features with their arguments as query parameters."""
        f = REGISTRY.get(feature)
        if f is None or f.risk != "read":
            raise ServiceError(f"GET serves read features only; use POST for {feature!r}")
        q = request.query_params
        args = {p.name: (q.getlist(p.name) if p.multiple else q[p.name]) for p in f.params if p.name in q}
        return respond(service.run(feature, vm, args))

    @app.post("/vms/{vm}/{feature}")
    def run(vm: str, feature: str, body: RunRequest):
        return respond(service.run(feature, vm, body.args, confirm=body.confirm, confirm_destroy=body.confirm_destroy,
                                   dry_run=body.dry_run))

    return app
