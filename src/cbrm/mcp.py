"""MCP server (stdio), generated from the feature registry: one tool per feature, `bero_<name>`.
Same rules as every other interface; with CBRM_API_URL set it is a client of a remote `cbrm serve`
and never sees the panel credential."""
from __future__ import annotations

import inspect

try:  # mcp >= 2 renamed FastMCP to MCPServer; the API used here is the same
    from mcp.server.mcpserver import Image, MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server, Image
    from mcp.server.fastmcp.exceptions import ToolError

from .client import backend
from .errors import ContractError, PanelError, ServiceError
from .features import REGISTRY, Feature

mcp = _Server("cbrm", instructions=(
    "Operate BERO HOST (bero-host.de) KVM rootservers through the customer panel and the VNC console. "
    "Read first. Every tool states its risk: change tools need confirm=<vm>, destroy tools also "
    "confirm_destroy=<vm>, cost tools confirm_cost=<amount>. dry_run=true shows what would be sent. "
    "A 'panel changed' error means BERO altered the panel: nothing was sent; report it, do not work around it. "
    "`system` in bero_status is the last template BERO installed, not necessarily what runs."))
_b = None


def b():
    global _b
    if _b is None:
        _b = backend()
    return _b


def _tool(f: Feature):
    P = inspect.Parameter
    params = [P("vm", P.KEYWORD_ONLY, annotation=str)]
    for p in f.params:
        ann = list[p.type] if p.multiple else p.type
        params.append(P(p.name, P.KEYWORD_ONLY, annotation=ann) if p.required
                      else P(p.name, P.KEYWORD_ONLY, annotation=ann | None, default=None))
    if f.risk != "read":
        params.append(P("confirm", P.KEYWORD_ONLY, annotation=str))
    if f.risk == "destroy":
        params.append(P("confirm_destroy", P.KEYWORD_ONLY, annotation=str))
    if f.risk == "cost":
        params.append(P("confirm_cost", P.KEYWORD_ONLY, annotation=str))
    if f.risk != "read":
        params.append(P("dry_run", P.KEYWORD_ONLY, annotation=bool, default=False))

    def tool(**kw):
        vm = kw.pop("vm")
        opts = {k: kw.pop(k) for k in ("confirm", "confirm_destroy", "confirm_cost", "dry_run") if k in kw}
        try:
            r = b().run(f.name, vm, {k: v for k, v in kw.items() if v is not None}, **opts)
        except ContractError as e:  # the text reaches the client: say clearly that nothing was sent
            raise ToolError(f"panel changed, nothing was sent: {e}") from e
        except (ServiceError, PanelError) as e:
            raise ToolError(f"refused: {e}" if isinstance(e, ServiceError) else f"panel error: {e}") from e
        return Image(data=r, format="png") if isinstance(r, bytes) else r

    tool.__name__ = "bero_" + f.name.replace("-", "_")
    tool.__doc__ = f"[{f.risk}] {f.help}."
    tool.__signature__ = inspect.Signature(params)
    tool.__annotations__ = {p.name: p.annotation for p in params}
    return tool


for _f in REGISTRY.values():
    mcp.tool()(_tool(_f))


@mcp.tool()
def bero_vms() -> list[dict]:
    """[read] All KVM rootservers of the account: state, addresses, last installed template."""
    return b().vms()


@mcp.tool()
def bero_doctor(vm: str) -> dict:
    """[read] Check that the panel still offers every feature (ok / BROKEN: reason / untested)."""
    return b().check(vm)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
