# Architecture

```
cbrm.panel     Panel     the customer panel over HTTP: login, pages, Livewire, power endpoints
cbrm.console   Console   the VNC console: Proxmox noVNC websocket ⇄ local TCP ⇄ vncdotool
      ▼
cbrm.service   Service   the rules, in one place: allow-list, confirm=<vm>, audit log
      ▼
cbrm.api       HTTP API  FastAPI over Service; bearer token; OpenAPI at /openapi.json
cbrm.client    Client    the Service interface over the HTTP API
cbrm.cli       cbrm      Service in-process, or Client when CBRM_API_URL is set
cbrm.mcp       cbrm-mcp  the same choice, exposed as MCP tools
```

Every interface goes through `Service`, so a rule added there holds for the CLI, the API and MCP alike.
`Client` and `Service` have the same methods; `cbrm.client.backend()` picks one from the environment.

## The panel (cbrm.panel)

| Need | What the panel does | What cbrm does |
|---|---|---|
| Login | form with a CSRF `_token`, session cookie | GET `/login`, POST the form, keep the cookies (`cookies.json`, 0600) and log in again when a page redirects to `/login` |
| Products | links `/customer/products/<id>` on `/customer`; titles `KVM Server: #<vm> (KVM Rootserver #<id>)` | map VM id → product id |
| Status | server-rendered product page | read the labelled values after `KVM Rootserver #<id>` |
| Action log | a lazy Livewire component (`…logs-table`) | replay its `__lazyLoad` call with its own snapshot, parse the rendered rows |
| Power | `GET /customer/rootserver/<vm>/{start,stop,shutdown,restart}` → JSON | the same request, `X-Requested-With: XMLHttpRequest` |
| Console | `/customer/rootserver/<vm>/vnc` embeds noVNC with `host`, `port` and a one-time `password` (a Proxmox VNC ticket) | read those three values |

The panel shows times in Europe/Berlin; cbrm passes them through unchanged. `system` in the status is
the last template the panel installed, not necessarily the operating system running now.

## The console (cbrm.console)

The noVNC session is a websocket (`wss://<host>:<port>/websockify`, subprotocol `binary`) carrying
plain RFB with VNC authentication. `Console` opens a local TCP port, bridges each connection to the
websocket (asyncio, in a background thread) and connects vncdotool to it. vncdotool runs one Twisted
reactor per process and cannot restart it, so cbrm stops it only at exit; long-running servers can
open any number of console sessions.
