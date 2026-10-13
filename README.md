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

Every operation is one entry of a registry; the CLI (`cbrm <feature> <vm> …`), the HTTP API
(`POST /vms/{vm}/{feature}`) and the MCP server (`bero_<feature>`) are generated from it, so all
three offer the same features with the same rules. `cbrm features` lists them.

<!-- features:begin (generated from the registry; tests/test_docs.py keeps it complete) -->
| Feature | Risk | Arguments | What it does |
|---|---|---|---|
| `boot-order` | read | – | Boot devices in order (scsi0 = disk, ide0/ide2 = CD drives, net0 = network) |
| `console` | read | `--out` | A screenshot of the VNC console (PNG) |
| `drives` | read | – | The VM's CD drives and what is inserted |
| `isos` | read | `--search`? | ISO images the panel can insert (public ones and the account's own), optionally filtered |
| `logs` | read | `--n`? | The panel's action log, newest first, in panel time (Europe/Berlin) |
| `rescue` | read | – | Rescue system state and the available rescue images |
| `ssh-keys` | read | – | SSH keys stored in the panel account: name -> id |
| `status` | read | – | State, hostname, addresses, last backup and last installed template |
| `templates` | read | – | Operating systems the panel can install: name -> template id |
| `root-password` | secret | – | The root password as the panel shows it |
| `boot-order-set` | change | `--order …` | Set the boot order: every device key from `boot-order`, first boots first |
| `console-input` | change | `--text`? `--keys …`? | Type text, then press keys (vncdotool names: enter, ctrl-c, down, f1, ...) |
| `iso-add` | change | `--url` `--title` | Add your own ISO to the account from a public download URL (kept at least 6 months) |
| `iso-mount` | change | `--drive` `--iso` | Insert an ISO (id, title or file name from `isos`) into a CD drive |
| `iso-unmount` | change | `--drive` | Remove the ISO from a CD drive |
| `power` | change | `--action` | Start, stop (hard), shut down (ACPI) or restart the VM |
| `rescue-disable` | change | – | Leave the rescue system |
| `rescue-enable` | change | `--image` | Boot the next time into a rescue image (id or title from `rescue`) |
| `set-root-password` | change | `--password`? | Set the root password (generated if omitted); returns it |
| `reinstall` | destroy | `--template` `--ssh-keys …`? | Reinstall from a template with stored SSH keys baked in. ERASES THE DISK |
<!-- features:end -->

| Risk | What cbrm requires |
|---|---|
| read | nothing |
| secret | `--confirm <vm>`; audited without the value |
| change | `--confirm <vm>`; audited; checked afterwards where the panel shows the effect (`verified`) |
| destroy | `--confirm <vm>` and `--confirm-destroy <vm>` |
| cost | `--confirm <vm>` and `--confirm-cost <amount>` (none implemented yet) |

Every changing command takes `--dry-run`: cbrm reads the panel, checks everything, and shows the exact
request it would send — without sending it.

### When BERO changes the panel

cbrm checks before every change that the panel still offers exactly what the feature relies on (the
Livewire component and method, the form, the endpoint in the page's own script). If anything differs it
stops with "the panel changed, nothing was sent" (HTTP 409, an MCP tool error) instead of guessing.
`cbrm doctor <vm>` runs these checks for every feature, read-only — run it on a schedule to learn about
a panel change before you need the feature.

## Install

```sh
pipx install cbrm                                                 # from PyPI (or: pip install cbrm)
uvx cbrm vms                                                      # run without installing (uv)
nix run git+https://git.corbet.ch/corbet-infra/cbrm -- vms        # Nix (flake)
```

Python 3.11 or newer. Dependencies: httpx, selectolax, websockets, vncdotool, Pillow, FastAPI, uvicorn, mcp.

## Configure

| Variable | Meaning |
|---|---|
| `CBRM_USER`, `CBRM_PASSWORD` | the panel login |
| `CBRM_CREDENTIALS_CMD` | instead: a command that prints the user and the password on two lines (`pass`, `sops`, a vault CLI, …) |
| `CBRM_VMS` | optional allow-list, e.g. `"10001 10002"`: every other server is refused |
| `CBRM_API_URL`, `CBRM_API_TOKEN` | use a running `cbrm serve` instead of logging in yourself |
| `XDG_STATE_HOME` | where the session cookie and `audit.log` live (`$XDG_STATE_HOME/cbrm`, mode 0700) |

```sh
export CBRM_CREDENTIALS_CMD="pass show hosting/bero-host"
cbrm vms
cbrm logs 10002 --n 5
cbrm console 10002 --out screen.png
cbrm power 10002 --action restart --confirm 10002
```

## MCP

For Claude Code, Claude Desktop or any MCP client (stdio):

```json
{ "mcpServers": { "bero": { "command": "uvx", "args": ["--from", "cbrm", "cbrm-mcp"],
    "env": { "CBRM_CREDENTIALS_CMD": "pass show hosting/bero-host", "CBRM_VMS": "10001 10002" } } } }
```

With a shared API the assistant never sees the panel password:
`"env": { "CBRM_API_URL": "https://cbrm.example.internal", "CBRM_API_TOKEN": "…" }`.
The skill [`skills/bero/SKILL.md`](skills/bero/SKILL.md) teaches an agent the safe order of work
(read, confirm, act, look again); copy it into your agent's skill directory.

## Recipes

| Goal | Steps |
|---|---|
| Fresh template with your SSH key | `cbrm reinstall <vm> --template "Arch Linux" --ssh-keys <name> --confirm <vm> --confirm-destroy <vm>`, then `ssh root@<ip>` |
| Boot your own ISO | `cbrm iso-add <vm> --url <https url> --title <t> --confirm <vm>` → `cbrm isos <vm> --search <t>` → `cbrm iso-mount <vm> --drive ide0 --iso <id> --confirm <vm>` → `cbrm boot-order-set <vm> --order ide0 scsi0 net0 ide2 --confirm <vm>` → `cbrm power <vm> --action restart --confirm <vm>` → `cbrm console <vm> --out s.png` |
| Hung server | `cbrm console` → `cbrm power --action restart` → `cbrm console` |

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

**LGPL-3.0-only WITH LGPL-3.0-linking-exception** — use cbrm from any application under any license;
changes to cbrm itself stay open. Details in [LICENSE.md](LICENSE.md). Contributions are welcome under
the same terms; see [CONTRIBUTING.md](CONTRIBUTING.md).
