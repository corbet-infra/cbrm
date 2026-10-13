"""The MCP server imports and registers its tools with the installed mcp version (1.x or 2.x)."""
import asyncio


def test_tools_registered():
    from cbrm.mcp import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {"bero_vms", "bero_status", "bero_logs", "bero_console", "bero_power", "bero_console_input"}
