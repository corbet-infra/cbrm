"""MCP server (stdio) for AI clients. Same operations and rules as the CLI and the API; with
CBRM_API_URL set it is a client of a remote `cbrm serve` and never sees the panel credential."""
from __future__ import annotations

try:  # mcp >= 2 renamed FastMCP to MCPServer; the API cbrm uses is the same
    from mcp.server.mcpserver import Image, MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server, Image

from .client import backend

mcp = _Server("cbrm", instructions=(
    "Manage BERO HOST (bero-host.de) KVM rootservers through the customer panel and the VNC console. "
    "Read first (bero_vms, bero_status, bero_logs, bero_console). Changing tools need confirm=<vm>. "
    "`system` in the status is the last template BERO installed, not necessarily what runs. "
    "Reinstall, backups, root password, network reset and billing are deliberately not available."))
_b = None


def b():
    global _b
    if _b is None:
        _b = backend()
    return _b


@mcp.tool()
def bero_vms() -> list[dict]:
    """All KVM rootservers of the account: state, addresses, last installed template."""
    return b().vms()


@mcp.tool()
def bero_status(vm: str) -> dict:
    """Overview of one VM (state, hostname, addresses, last backup)."""
    return b().status(vm)


@mcp.tool()
def bero_logs(vm: str, n: int = 20) -> list[dict]:
    """The panel's action log of a VM, newest first, in panel time (Europe/Berlin)."""
    return b().logs(vm, n)


@mcp.tool()
def bero_console(vm: str) -> Image:
    """A screenshot of the VM's VNC console (what a monitor would show)."""
    return Image(data=b().console_png(vm), format="png")


@mcp.tool()
def bero_power(vm: str, action: str, confirm: str) -> dict:
    """Power action on a VM: start, stop, shutdown or restart. confirm must repeat the VM id."""
    return b().power(vm, action, confirm)


@mcp.tool()
def bero_console_input(vm: str, confirm: str, text: str = "", keys: list[str] | None = None) -> dict:
    """Type text, then press keys (vncdotool names: enter, ctrl-c, f1, ...) on the VNC console.
    confirm must repeat the VM id. Look at bero_console before and after."""
    return b().console_input(vm, text, keys, confirm)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
