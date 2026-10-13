# cbrm — manage BERO HOST servers from the terminal, from code, and from AI assistants

**cbrm** ("BERO management") operates [BERO HOST](https://bero-host.de) KVM rootservers without clicking
through the customer panel: check status, read the panel's action log, look at the VNC console, power a
server on or off, type at its console. It is one package with five faces:

| You are | Use | Start with |
|---|---|---|
| a person at a terminal | the CLI `cbrm` | `cbrm vms` |
| a team or a service | the HTTP API `cbrm serve` (OpenAPI, bearer token) | [docs/operations.md](docs/operations.md) |
| an AI assistant (Claude, …) | the MCP server `cbrm-mcp` and the skill in [`skills/bero/`](skills/bero/SKILL.md) | [MCP setup](#mcp) |
| a Python program | `from cbrm import Panel, Console` or `cbrm.service.Service` | [docs/architecture.md](docs/architecture.md) |
| a contributor | Forgejo, see [CONTRIBUTING.md](CONTRIBUTING.md) | `nix develop` |

BERO HOST is a German provider of prepaid game, root and virtual servers. Its panel is pleasant to use
by hand; cbrm exists for the moments when a script or an assistant should do the same thing. It is an
independent community project, not made or endorsed by BERO HOST, and it only does what a customer can
do in the panel with their own login.

## What it can do

| Area | CLI | API | MCP tool | Changes the server |
|---|---|---|---|---|
| All servers of the account | `cbrm vms` | `GET /vms` | `bero_vms` | no |
| Status: state, hostname, IPv4/IPv6, last backup, last installed template | `cbrm status <vm>` | `GET /vms/{vm}` | `bero_status` | no |
| Action log (installs, restarts, starts) | `cbrm logs <vm>` | `GET /vms/{vm}/logs` | `bero_logs` | no |
| Console screenshot | `cbrm console <vm> out.png` | `GET /vms/{vm}/console.png` | `bero_console` | no |
| Power: start, stop, shutdown, restart | `cbrm power <vm> <action> --confirm <vm>` | `POST /vms/{vm}/power` | `bero_power` | **yes** |
| Console input: text and keys | `cbrm input <vm> --text … --key enter --confirm <vm>` | `POST /vms/{vm}/console/input` | `bero_console_input` | **yes** |

Every changing operation repeats its target (`--confirm <vm>` / `confirm`) and is written to an audit
log. **Not included on purpose**: reinstall, backups and restore, root password, network reset, ISO and
boot order, renewals, upgrades and credit — they can destroy a server or cost money, so they stay in the
panel where a person sees what they click.

## Install

```sh
nix run git+https://git.corbet.ch/corbet-infra/cbrm -- vms        # Nix (flake)
pipx install git+https://git.corbet.ch/corbet-infra/cbrm         # pipx / pip
```

Python 3.11 or newer. Dependencies: httpx, selectolax, websockets, vncdotool, Pillow, FastAPI, uvicorn, mcp.

## Configure

| Variable | Meaning |
|---|---|
| `CBRM_USER`, `CBRM_PASSWORD` | the panel login |
| `CBRM_CREDENTIALS_CMD` | instead: a command that prints the user and the password on two lines (`pass`, `sops`, a vault CLI, …) |
| `CBRM_VMS` | optional allow-list, e.g. `"17761 17762"`: every other server is refused |
| `CBRM_API_URL`, `CBRM_API_TOKEN` | use a running `cbrm serve` instead of logging in yourself |
| `XDG_STATE_HOME` | where the session cookie and `audit.log` live (`$XDG_STATE_HOME/cbrm`, mode 0700) |

```sh
export CBRM_CREDENTIALS_CMD="pass show hosting/bero-host"
cbrm vms
cbrm logs 17762 -n 5
cbrm console 17762 screen.png
cbrm power 17762 restart --confirm 17762
```

## MCP

For Claude Code, Claude Desktop or any MCP client (stdio):

```json
{ "mcpServers": { "bero": { "command": "cbrm-mcp",
    "env": { "CBRM_CREDENTIALS_CMD": "pass show hosting/bero-host", "CBRM_VMS": "17761 17762" } } } }
```

With a shared API the assistant never sees the panel password:
`"env": { "CBRM_API_URL": "https://cbrm.example.internal", "CBRM_API_TOKEN": "…" }`.
The skill [`skills/bero/SKILL.md`](skills/bero/SKILL.md) teaches an agent the safe order of work
(read, confirm, act, look again); copy it into your agent's skill directory.

## How it works

BERO HOST does not publish an API, so cbrm uses what the panel itself uses: its login form, its
server-rendered pages, one Livewire request for the action log, the JSON endpoints behind its power
buttons, and the noVNC console session it hands out (a Proxmox VNC websocket, bridged to a local port
and driven with vncdotool). Details in [docs/architecture.md](docs/architecture.md).

If the panel changes, cbrm fails with a clear error instead of guessing; see
[docs/operations.md](docs/operations.md#when-the-panel-changes).

## Where the code lives

| Place | Role |
|---|---|
| [git.corbet.ch/corbet-infra/cbrm](https://git.corbet.ch/corbet-infra/cbrm) | **primary**: issues, pull requests, releases |
| GitHub, GitLab, Bitbucket | read-only mirrors, updated automatically from the primary |

Please open issues and pull requests on the primary; changes pushed to a mirror are overwritten.

## License

See [LICENSE](LICENSE). Contributions are welcome under the same terms; see [CONTRIBUTING.md](CONTRIBUTING.md).
