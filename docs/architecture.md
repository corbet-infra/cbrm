# Architecture

```
cbrm.panel      Panel      login/session, server-rendered pages, panel JSON endpoints
cbrm.livewire   Page/Component  Livewire calls with contract checks (require methods/fields/endpoints)
cbrm.console    Console    the VNC console: Proxmox noVNC websocket ⇄ local TCP ⇄ vncdotool
      ▼
cbrm.features   REGISTRY   every operation: name, risk class, parameters, run, verify, check
      ▼
cbrm.service    Service    the rules for every feature: allow-list, confirmations per risk class,
                           dry run, audit log, verification; `check` = doctor
      ▼
cbrm.api / cbrm.cli / cbrm.mcp   generated from the registry; CLI and MCP use the API when CBRM_API_URL is set
```

Adding a feature is one decorated function in `cbrm/features/`; every interface picks it up with the
right guards. A feature reads and checks first and passes its single changing request to `ctx.send`,
which a dry run turns into a description.

## Breaking safely

| Layer | What happens when BERO changes the panel |
|---|---|
| `Component.require` | a Livewire method or field a feature needs is gone → `ContractError`, nothing sent |
| `Page.require_endpoint` | the page's script no longer calls an endpoint → `ContractError` |
| `common.require_post` | the page's own `$.post` to an endpoint no longer sends exactly the fields cbrm sends → `ContractError` |
| parsers | an expected element is missing → `ContractError` instead of an empty answer |
| `verify` | after a change, the panel does not show the effect → `verified: false` (CLI exit 4) |
| `cbrm doctor` | runs every feature's check read-only → `ok` / `BROKEN: reason` |

Account-wide features (`account-*`) read `/customer/account` instead of a product page. The VM argument
still names the account context, so the allow-list and the confirmations of `Service` apply to them unchanged.

Interfaces report a contract error distinctly: CLI "the panel changed, nothing was sent", HTTP 409,
an MCP tool error with the same text.

## The panel (cbrm.panel)

| Need | What the panel does | What cbrm does |
|---|---|---|
| Login | form with a CSRF `_token`, session cookie | GET `/login`, POST the form, keep the cookies (`cookies.json`, 0600) and log in again when a page redirects to `/login` |
| Products | links `/customer/products/<id>` on `/customer`; titles `KVM Server: #<vm> (KVM Rootserver #<id>)` | map VM id → product id |
| Status | server-rendered product page | read the labelled values after `KVM Rootserver #<id>` |
| Action log | a lazy Livewire component (`…logs-table`) | replay its `__lazyLoad` call with its own snapshot, parse the rendered rows |
| Power | `GET /customer/rootserver/<vm>/{start,stop,shutdown,restart}` → JSON | the same request, `X-Requested-With: XMLHttpRequest` |
| Root password | shown on the product page (`#password[data-password]`); set with `POST …/setrootpassword` | read the attribute; the same POST with the CSRF token |
| Reinstall | `POST /customer/rootserver/<vm>/reinstall` with `template=<id>` and `ssh_keys[]=<id>` (ids from the reinstall form) | names → ids from the form, then the same POST |
| Console | `/customer/rootserver/<vm>/vnc` embeds noVNC with `host`, `port` and a one-time `password` (a Proxmox VNC ticket) | read those three values |

The panel shows times in Europe/Berlin; cbrm passes them through unchanged. `system` in the status is
the last template the panel installed, not necessarily the operating system running now.

## The console (cbrm.console)

The noVNC session is a websocket (`wss://<host>:<port>/websockify`, subprotocol `binary`) carrying
plain RFB with VNC authentication. `Console` opens a local TCP port, bridges each connection to the
websocket (asyncio, in a background thread) and connects vncdotool to it. vncdotool runs one Twisted
reactor per process and cannot restart it, so cbrm stops it only at exit; long-running servers can
open any number of console sessions.
