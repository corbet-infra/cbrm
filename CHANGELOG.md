# Changelog

## 0.3.2 — 2026-10-13

Fixes from an independent review before the public announcement:

- A dry run of `root-password` revealed the password without confirmation; secret features now never run
  in a dry run, and a dry run returns only a description.
- `console-input` text and other secret arguments never reach the audit log; secret results are logged
  as their keys only.
- `iso-add` in a dry run no longer opens the form or sends the URL; its contract (form fields, method) is
  checked before anything is submitted.
- An error while verifying a change that was sent is reported as `verified: null` + `verify_error`, not as
  "nothing was sent"; the wording is now "the panel changed, so the change was not made".
- `doctor` respects the allow-list and reports instead of crashing.
- HTTP API: the framework's docs routes (which bypassed the token) are off; `/openapi.json` needs the
  token; a non-ASCII token is a 401, not a 500.
- Exact endpoint checks (`/stop` no longer matches `/stop-hard`); reinstall and set-root-password check the
  form fields they submit; drive and boot-order reads fail closed when the refresh is missing.
- Every HTTP error maps to `PanelError` (419 on an expired Livewire session included); the session's login
  and product scan are locked for the threaded API; the cookie file is written atomically and a damaged
  one is ignored.
- MCP tools run in a worker thread; the client reports a timeout as "may still be running".
- `console-input`: repeat x interval at most 120 s; the console cleans up when opening fails.

## 0.3.1 — 2026-10-13

- Fix: every command that used the console hung when the process exited (vncdotool's reactor thread
  was stopped too late). A regression test runs a process through it.
- Console: hard deadline per operation; the panel's noVNC proxy is retried while it starts;
  `console-input --repeat/--interval` to catch a boot menu.
- `drives` and `boot-order` read the hypervisor's live state (the panel caches both); `iso-mount` is
  verified only when exactly that file is in the drive (the panel reports success for an own ISO that is
  still downloading).
- New: `drive-delete`.
- README: absolute links (they work on PyPI), the ISO boot recipe, a status and roadmap section.

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
