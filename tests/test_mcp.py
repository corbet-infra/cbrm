"""The MCP server registers one tool per feature (plus vms and doctor) with mcp 1.x or 2.x."""
import asyncio

from cbrm.features import REGISTRY


def test_tools_registered():
    from cbrm.mcp import mcp
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert set(tools) == {"bero_" + n.replace("-", "_") for n in REGISTRY} | {"bero_vms", "bero_doctor"}
    tool = tools["bero_reinstall"]
    schema = getattr(tool, "input_schema", None) or tool.inputSchema  # mcp 2.x / 1.x
    assert {"vm", "template", "confirm", "confirm_destroy"} <= set(schema["required"])
