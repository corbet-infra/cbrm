# cbrm — manage BERO HOST servers (CLI, library, MCP server, agent skill)

**cbrm** ("BERO management") operates [BERO HOST](https://bero-host.de) KVM rootservers from a script,
a terminal or an AI assistant. BERO HOST offers no public API, only its customer panel; cbrm speaks that
panel's HTTP and its VNC console, so you do not have to click.

| You are | Use |
|---|---|
| a person or a script | the CLI: `cbrm vms`, `cbrm status <vm>`, `cbrm logs <vm>`, `cbrm console <vm> out.png`, `cbrm power <vm> restart --confirm <vm>`, `cbrm serve` |
| an AI client (Claude, …) | the MCP server `cbrm-mcp` (stdio) and the skill in `skills/bero/` |
| a service or a team | the HTTP API: `cbrm serve` (OpenAPI at `/openapi.json`, bearer token) |
| a Python program | `from cbrm import Panel, Console` (or `cbrm.service.Service`) |

## What it can do

| Area | Commands / tools | Changes the VM |
|---|---|---|
| Inventory | `vms` / `bero_vms` | no |
| Status | `status` / `bero_status`: state, hostname, IPv4/IPv6, last backup, last installed template | no |
| Action log | `logs` / `bero_logs`: reinstalls, restarts, starts, as the panel records them | no |
| Console | `console` / `bero_console`: a screenshot of the VNC console | no |
| Power | `power start\|stop\|shutdown\|restart` / `bero_power` | **yes**, needs `--confirm <vm>` |
| Console input | `input --text … --key enter` / `bero_console_input` | **yes**, needs `--confirm <vm>` |

Deliberately **not** included: reinstall, backups and restore, root password, network reset, ISO and
boot order, renewals, upgrades, credit. Those can destroy a server or cost money; use the panel.

## Install

```sh
nix run git+https://git.corbet.ch/corbet-infra/cbrm -- vms     # Nix
pipx install git+https://git.corbet.ch/corbet-infra/cbrm      # pip/pipx
```

Credentials: `CBRM_USER` and `CBRM_PASSWORD`, or `CBRM_CREDENTIALS_CMD` — a command that prints the user
and the password on two lines (for example a call to `pass`, `sops` or a vault). The session cookie is
kept in `$XDG_STATE_HOME/cbrm` (mode 0600); changing commands are appended to `audit.log` there.
`CBRM_VMS="10001 10002"` restricts every command to those VMs.

### MCP (Claude Code, Claude Desktop, other MCP clients)

```json
{ "mcpServers": { "bero": { "command": "cbrm-mcp",
    "env": { "CBRM_CREDENTIALS_CMD": "pass show bero-host", "CBRM_VMS": "10001 10002" } } } }
```

## Architecture

```
cbrm.panel / cbrm.console   speak to BERO: panel HTTP, Livewire, the Proxmox noVNC console
        ▼
cbrm.service                the rules, once: allow-list, confirm=<vm> for changes, audit log
        ▼
├── HTTP API  cbrm serve    holds the credential; OpenAPI; bearer token (CBRM_API_TOKEN)
├── MCP       cbrm-mcp      in-process, or a client of the API when CBRM_API_URL is set
└── CLI       cbrm          the same
```

Run `cbrm serve` where the credential lives and point every CLI and MCP server at it with
`CBRM_API_URL` and `CBRM_API_TOKEN`: the panel password then exists in one place only.

## How it works

| Panel feature | How cbrm reaches it |
|---|---|
| Login | the panel's login form (CSRF token + session cookie) |
| Status | the server-rendered product page |
| Action log | one Livewire request (the log is a lazy component) |
| Power | the JSON endpoints the panel's buttons call |
| Console | the Proxmox noVNC session the panel hands out, bridged to a local port and driven with vncdotool |

The panel is BERO's own software and can change without notice; cbrm then fails loudly instead of
guessing. Not affiliated with BERO HOST.
