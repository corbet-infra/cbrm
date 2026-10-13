# Changelog

## 0.2.0 — 2026-10-13

- Reinstall from a template with stored SSH keys baked in (`reinstall`, double confirmation).
- Show, set or generate the root password (audited without the value).
- List installable templates and the account's stored SSH keys.
- Fix: an expired session made the next login fail (stale cookie shadowed the new one).

## 0.1.1 — 2026-10-13

- MCP server works with mcp 2.x (`MCPServer`) as well as 1.x (`FastMCP`); 0.1.0 failed to start with mcp 2.x.
- Test that the MCP server registers its tools.

## 0.1.0 — 2026-10-13

First version: status, action log, console screenshot and input, power — as a Python library, CLI,
HTTP API and MCP server, with an agent skill.
