"""MCP server (stdio), generated from the feature registry: one tool per feature, `bero_<name>`.
Same rules as every other interface; with CBRM_API_URL set it is a client of a remote `cbrm serve`
and never sees the panel credential."""
from __future__ import annotations

import base64
import inspect

import anyio

try:  # mcp >= 2 renamed FastMCP to MCPServer; the API used here is the same
    from mcp.server.mcpserver import Image
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp import Image
    from mcp.server.fastmcp.exceptions import ToolError

from .client import backend
from .errors import ContractError, PanelError, ServiceError
from .features import ACCOUNT_NOTE, FILE_TYPES, REGISTRY, Feature

mcp = _Server("cbrm", instructions=(
    "Operate BERO HOST (bero-host.de) KVM rootservers through the customer panel and the VNC console. "
    "Read first. Every tool states its risk: change tools need confirm=<vm>, destroy tools also "
    "confirm_destroy=<vm>. dry_run=true shows what would be sent. cbrm never spends money. "
    "A 'panel changed' error means BERO altered the panel and the change was not made; report it, do not work around it. "
    "bero_account_* tools act on the whole account (stored SSH keys, credit, tickets, networks, firewalls), not on "
    "one server: the VM allow-list does not limit them. "
    "`system` in bero_status is the last template BERO installed, not necessarily what runs."))
_b = None


def b():
    global _b
    if _b is None:
        _b = backend()
    return _b


def _tool(f: Feature):
    P = inspect.Parameter
    account = f.scope == "account"  # the VM is optional (any allowed VM names the account context)
    params = [P("vm", P.KEYWORD_ONLY, annotation=str | None, default=None) if account else P("vm", P.KEYWORD_ONLY, annotation=str)]
    for p in f.params:
        ann = list[p.type] if p.multiple else p.type
        params.append(P(p.name, P.KEYWORD_ONLY, annotation=ann) if p.required
                      else P(p.name, P.KEYWORD_ONLY, annotation=ann | None, default=None))
    if f.risk != "read":
        params.append(P("confirm", P.KEYWORD_ONLY, annotation=str))
    if f.risk == "destroy":
        params.append(P("confirm_destroy", P.KEYWORD_ONLY, annotation=str))
    if f.risk != "read":
        params.append(P("dry_run", P.KEYWORD_ONLY, annotation=bool, default=False))

    async def tool(**kw):
        vm = kw.pop("vm") or "account"
        opts = {k: kw.pop(k) for k in ("confirm", "confirm_destroy", "dry_run") if k in kw}
        args = {k: v for k, v in kw.items() if v is not None}
        try:  # in a worker thread: panel and console calls block, the server must keep answering
            r = await anyio.to_thread.run_sync(lambda: b().run(f.name, vm, args, **opts))
        except ContractError as e:  # the text reaches the client: say clearly that the change was not made
            raise ToolError(f"the panel changed, so the change was not made: {e}") from e
        except (ServiceError, PanelError) as e:
            raise ToolError(f"refused: {e}" if isinstance(e, ServiceError) else f"panel error: {e}") from e
        if isinstance(r, bytes):
            if f.returns == "png":
                return Image(data=r, format="png")
            # Other files (an invoice PDF): the bytes as base64, for the client to save; MCP has no file type for them
            return {"type": FILE_TYPES[f.returns], "bytes": len(r), "base64": base64.b64encode(r).decode("ascii")}
        return r

    tool.__name__ = "bero_" + f.name.replace("-", "_")
    tool.__doc__ = f"[{f.risk}] {f.help}." + (f" {ACCOUNT_NOTE}" if account else "")
    tool.__signature__ = inspect.Signature(params)
    tool.__annotations__ = {p.name: p.annotation for p in params}
    return tool


for _f in REGISTRY.values():
    mcp.tool()(_tool(_f))


@mcp.tool()
async def bero_vms() -> list[dict]:
    """[read] All KVM rootservers of the account: state, addresses, last installed template."""
    return await anyio.to_thread.run_sync(lambda: b().vms())


@mcp.tool()
async def bero_doctor(vm: str) -> dict:
    """[read] Check that the panel still offers every feature (ok / BROKEN: reason / untested)."""
    return await anyio.to_thread.run_sync(lambda: b().check(vm))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
