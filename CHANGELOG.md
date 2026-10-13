# Changelog

## 0.3.0 — 2026-10-13

- Architecture: a feature registry with risk classes (read, secret, change, destroy, cost); CLI, HTTP
  API and MCP tools are generated from it. Every changing feature takes `--dry-run`.
- Breaking safely: a generic Livewire layer checks components, methods, fields and endpoints before
  every change (`ContractError`, HTTP 409); changes are verified by re-reading the panel; `cbrm doctor`.
- New: CD drives, ISO list, insert/remove ISO, own ISO by URL, boot order, rescue system.
- CLI is now `cbrm <feature> <vm> --arg …` (e.g. `cbrm power <vm> --action restart --confirm <vm>`).

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
