"""HTTP API (FastAPI; OpenAPI at /openapi.json, docs at /docs). It holds the panel credential, so CLIs
and MCP servers elsewhere only need the API URL and its token. Every route needs the bearer token."""
from __future__ import annotations

import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from . import __version__
from .panel import PanelError
from .service import Service, ServiceError

_bearer = HTTPBearer()


def _auth(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> None:
    token = os.environ.get("CBRM_API_TOKEN", "")
    if not token or not secrets.compare_digest(cred.credentials, token):
        raise HTTPException(401, "bad token")


class PowerRequest(BaseModel):
    action: str
    confirm: str


class Confirm(BaseModel):
    confirm: str


class RootPassword(BaseModel):
    confirm: str
    password: str | None = None


class Reinstall(BaseModel):
    template: str
    ssh_keys: list[str] = []
    confirm: str
    confirm_destroy: str


class ConsoleInput(BaseModel):
    text: str = ""
    keys: list[str] = []
    confirm: str


def create_app(service: Service) -> FastAPI:
    app = FastAPI(title="cbrm", version=__version__, dependencies=[Depends(_auth)],
                  description="BERO HOST management: panel and VNC console.")

    @app.exception_handler(ServiceError)
    async def refused(_: Request, e: ServiceError):
        return JSONResponse({"detail": str(e)}, status_code=403)

    @app.exception_handler(PanelError)
    async def panel(_: Request, e: PanelError):
        return JSONResponse({"detail": str(e)}, status_code=502)

    @app.get("/vms")
    def vms() -> list[dict]:
        return service.vms()

    @app.get("/vms/{vm}")
    def status(vm: str) -> dict:
        return service.status(vm)

    @app.get("/vms/{vm}/logs")
    def logs(vm: str, n: int = 20) -> list[dict]:
        return service.logs(vm, n)

    @app.get("/vms/{vm}/console.png", response_class=Response)
    def console(vm: str) -> Response:
        return Response(service.console_png(vm), media_type="image/png")

    @app.post("/vms/{vm}/power")
    def power(vm: str, body: PowerRequest) -> dict:
        return service.power(vm, body.action, body.confirm)

    @app.post("/vms/{vm}/console/input")
    def console_input(vm: str, body: ConsoleInput) -> dict:
        return service.console_input(vm, body.text, body.keys, body.confirm)

    @app.get("/vms/{vm}/templates")
    def templates(vm: str) -> dict:
        return service.templates(vm)

    @app.get("/vms/{vm}/ssh-keys")
    def ssh_keys(vm: str) -> dict:
        return service.ssh_keys(vm)

    @app.post("/vms/{vm}/root-password/reveal")
    def root_password(vm: str, body: Confirm) -> dict:
        return service.root_password(vm, body.confirm)

    @app.post("/vms/{vm}/root-password")
    def set_root_password(vm: str, body: RootPassword) -> dict:
        return service.set_root_password(vm, body.confirm, body.password)

    @app.post("/vms/{vm}/reinstall")
    def reinstall(vm: str, body: Reinstall) -> dict:
        return service.reinstall(vm, body.template, body.ssh_keys, body.confirm, body.confirm_destroy)

    return app
