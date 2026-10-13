# cbrm — manage BERO HOST servers from the terminal, from code, and from AI assistants

**cbrm** ("BERO management") operates [BERO HOST](https://bero-host.de) KVM rootservers without clicking
through the customer panel: check status, read the panel's action log, look at the VNC console, power a
server on or off, type at its console. It is one package with five faces:

| You are | Use | Start with |
|---|---|---|
| a person at a terminal | the CLI `cbrm` | `cbrm vms` |
| a team or a service | the HTTP API `cbrm serve` (OpenAPI, bearer token) | [docs/operations.md](https://git.corbet.ch/corbet-infra/cbrm/src/branch/main/docs/operations.md) |
| an AI assistant (Claude, …) | the MCP server `cbrm-mcp` and the skill in [`skills/bero/`](https://git.corbet.ch/corbet-infra/cbrm/src/branch/main/skills/bero/SKILL.md) | [MCP setup](#mcp) |
| a Python program | `from cbrm import Panel, Console` or `cbrm.service.Service` | [docs/architecture.md](https://git.corbet.ch/corbet-infra/cbrm/src/branch/main/docs/architecture.md) |
| a contributor | Forgejo, see [CONTRIBUTING.md](https://git.corbet.ch/corbet-infra/cbrm/src/branch/main/CONTRIBUTING.md) | `nix develop` |

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
| `account-credit` | read | – | The account's credit balance as the panel shows it (account-wide) |
| `account-ssh-keys` | read | – | SSH keys stored in the panel account (account-wide): id, name, MD5 fingerprint |
| `addresses` | read | – | The VM's IPv4/IPv6 addresses with prefix length, gateway and reverse DNS entry |
| `automatic-backup-status` | read | – | Whether the automatic backup is enabled, and its last and next run (panel time) |
| `backups` | read | – | The VM's backups (id, title, size, date; panel time) and how many backup slots are free |
| `boot-order` | read | – | Boot devices in order (scsi0 = disk, ide0/ide2 = CD drives, net0 = network) |
| `console` | read | `--out` | A screenshot of the VNC console (PNG) |
| `drives` | read | – | The VM's CD drives and what is inserted (live state from the hypervisor) |
| `isos` | read | `--search`? | ISO images the panel can insert (public ones and the account's own), optionally filtered |
| `logs` | read | `--n`? | The panel's action log, newest first, in panel time (Europe/Berlin) |
| `renewal` | read | – | Remaining runtime, automatic renewal (runtimes with the prices the panel quotes, payment method), whether the server can be upgraded, and the account credit |
| `rescue` | read | – | Rescue system state and the available rescue images |
| `ssh-keys` | read | – | SSH keys stored in the panel account: name -> id |
| `stats` | read | – | Current CPU, RAM and disk use, uptime, ping, traffic and running network/disk counters |
| `stats-history` | read | `--timeframe`? `--metric`? | CPU, RAM, disk or network figures over a time frame: min, average, max and last value per series (cpu and ram in percent, disk in MB/s, network in Mbit/s) |
| `status` | read | – | State, hostname, addresses, last backup and last installed template |
| `tasks` | read | – | The VM's scheduled tasks: id, action, repeat interval and next run (panel time) |
| `templates` | read | – | Operating systems the panel can install: name -> template id |
| `root-password` | secret | – | The root password as the panel shows it |
| `account-ssh-key-delete` | change | `--key` | Delete an SSH key from the panel account (account-wide, not limited by the VM allow-list; servers already installed keep it) |
| `account-ssh-key-import` | change | `--name` `--public-key` | Store a public SSH key in the panel account (account-wide, not limited by the VM allow-list; it can then be baked into a reinstall) |
| `backup-create` | change | `--title` | Create a backup now (the panel makes it in the background; needs a free slot, see `backups`) |
| `boot-order-set` | change | `--order …` | Set the boot order: every device key from `boot-order`, first boots first |
| `console-input` | change | `--text`? `--keys …`? `--repeat`? `--interval`? | Type text, then press keys (vncdotool names: enter, ctrl-c, down, f1, ...); repeat the keys to catch a boot menu |
| `drive-delete` | change | `--drive` | Remove a CD drive from the VM (a VM should have one CD drive, the disk and network) |
| `hostname-set` | change | `--hostname` | Set the VM's host name in the panel (lower-cased; letters, digits, hyphens, dots) |
| `iso-add` | change | `--url` `--title` | Add your own ISO to the account from a public download URL (kept at least 6 months) |
| `iso-mount` | change | `--drive` `--iso` | Insert an ISO (id, title or file name from `isos`) into a CD drive |
| `iso-unmount` | change | `--drive` | Remove the ISO from a CD drive |
| `power` | change | `--action` | Start, stop (hard), shut down (ACPI) or restart the VM |
| `rdns-set` | change | `--address` `--name` | Set the reverse DNS name of one of the VM's IP addresses (see `addresses`) |
| `rename` | change | `--name` | Rename the product in the panel (its display name, not the host name) |
| `rescue-disable` | change | – | Leave the rescue system |
| `rescue-enable` | change | `--image` | Boot the next time into a rescue image (id or title from `rescue`) |
| `set-root-password` | change | `--password`? | Set the root password (generated if omitted); returns it |
| `task-delete` | change | `--task` | Delete a scheduled task (deleting the weekly backup task switches the automatic backup off) |
| `backup-delete` | destroy | `--backup` | Delete a backup. THE BACKUP IS GONE |
| `backup-restore` | destroy | `--backup` `--live`? | Restore the whole VM from a backup. OVERWRITES THE DISK with the backup's state |
| `network-reset` | destroy | – | Reset the VM's network configuration and software firewall (the panel's 'Netzwerk-Reset'): everything you configured there is lost |
| `reinstall` | destroy | `--template` `--ssh-keys …`? | Reinstall from a template with stored SSH keys baked in. ERASES THE DISK |
| `task-create` | destroy | `--action` `--interval` `--start` | Schedule an action for the VM (action dump = backup, start, restart, shutdown, stop; interval daily, 2-days, 3-days, 5-days, weekly, 2-weeks, monthly, yearly). DESTROYING: the task acts later and repeatedly without you until it is deleted (a stop or restart task keeps interrupting the VM, a backup task may rotate or overwrite backups), so it needs both confirmations |
<!-- features:end -->

| Risk | What cbrm requires |
|---|---|
| read | nothing |
| secret | `--confirm <vm>`; audited without the value |
| change | `--confirm <vm>`; audited; checked afterwards where the panel shows the effect (`verified`) |
| destroy | `--confirm <vm>` and `--confirm-destroy <vm>`: erases or overwrites data, or acts later and repeatedly without you (`reinstall`, `backup-delete`, `backup-restore`, `network-reset`, `task-create`) |
| cost | `--confirm <vm>` and `--confirm-cost <amount>` (none implemented yet) |

`verified` is `true` when cbrm re-read the panel and it shows the effect, `false` when it does not (look again
before repeating the change), and `null` when cbrm cannot tell: the panel shows no sign of the change to re-read
(`backup-restore`, `network-reset`, `console-input`, …) or could not be read afterwards (then `verify_error`
may say why). `null` never means "failed".

Every changing command takes `--dry-run`: cbrm reads the panel (it may refresh or page through lists, which
changes nothing), checks everything, and shows the exact request it would send — without sending it or any
other request that changes or submits something. A dry run of a `secret` feature reveals nothing.

Features named `account-*` act on the **whole account** (stored SSH keys, credit), not on one server, and are
**not limited by the VM allow-list** (`CBRM_VMS`): the allow-list only decides which `<vm>` may *name* the
account context. They still take `<vm>`: it must belong to the account, must be on the allow-list and is
repeated as `--confirm <vm>` like for every other change. One allowed VM is therefore enough to add or delete
a stored key of the whole account, including keys that a later reinstall of a server outside the allow-list
would bake in. If you give a team or an assistant an allow-list, think of `account-*` as account access.

### When BERO changes the panel

cbrm checks before every change that the panel still offers exactly what the feature relies on (the
Livewire component and method, the form and its field names, the exact endpoint in the page's own script).
If anything differs it stops with "the panel changed, so the change was not made" (HTTP 409, an MCP tool
error) instead of guessing. If a change was sent but cannot be confirmed afterwards, the answer says so
(`verified: null` and `verify_error`) instead of claiming nothing happened.
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
| `CBRM_VMS` | allow-list, e.g. `"10001 10002"`: every other server is refused. Unset means every server of the account. It does **not** limit the `account-*` features (stored SSH keys, credit): they act on the whole account |
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
The skill [`skills/bero/SKILL.md`](https://git.corbet.ch/corbet-infra/cbrm/src/branch/main/skills/bero/SKILL.md) teaches an agent the safe order of work
(read, confirm, act, look again); copy it into your agent's skill directory.

## Recipes

| Goal | Steps |
|---|---|
| Fresh template with your SSH key | `cbrm reinstall <vm> --template "Arch Linux" --ssh-keys <name> --confirm <vm> --confirm-destroy <vm>`, then `ssh root@<ip>` (about 90 s later) |
| Hung server | `cbrm console <vm> --out s.png` → `cbrm power <vm> --action restart --confirm <vm>` → `cbrm console …` |
| What happened to my server? | `cbrm logs <vm>`: reinstalls, restarts and starts as the panel recorded them |
| Is cbrm still in sync with the panel? | `cbrm doctor <vm>` |
| Back up before a risky change | `cbrm backups <vm>` (free slot?) → `cbrm backup-create <vm> --title <t> --confirm <vm>` (`verified: true` once the new backup or the used slot shows; `false` means not visible yet: look at `cbrm backups <vm>` again before repeating) |
| Repeat something on a schedule | `cbrm tasks <vm>` → `cbrm task-create <vm> --action dump --interval weekly --start "2026-10-20 03:30" --confirm <vm> --confirm-destroy <vm>` (start in panel time, not in the past; the task repeats until `cbrm task-delete`) |
| Reverse DNS for a mail server | `cbrm addresses <vm>` → `cbrm rdns-set <vm> --address <ip> --name mail.example.org --confirm <vm>` (`verified: true` once the panel shows it) |
| Server unreachable after a firewall or network change | `cbrm console <vm> --out s.png`, then `cbrm network-reset <vm> --confirm <vm> --confirm-destroy <vm>` — it resets the panel-managed network configuration and the software firewall |

### Booting your own ISO (for example to install any OS)

1. `cbrm iso-add <vm> --url <public https url> --title <t> --confirm <vm>`. The panel confirms at once but
   **downloads in the background** (a 1.5 GB image took about 30 minutes); until it is done, inserting it
   reports success and inserts nothing — cbrm's `verified: false` tells you.
2. `cbrm isos <vm> --search <t>` → `cbrm iso-mount <vm> --drive ide2 --iso <id> --confirm <vm>`.
   Keep **one** CD drive (`cbrm drive-delete <vm> --drive ide0 …` if a reinstall created a second one).
3. **After** mounting: `cbrm boot-order-set <vm> --order ide2 scsi0 net0 --confirm <vm>`.
4. `cbrm power <vm> --action stop …`, then `--action start`. The console becomes reachable about 20 s after
   the start; if your ISO has a boot menu, `cbrm console-input <vm> --keys enter --repeat 3 --interval 0.5 …`
   right away selects its default entry. `cbrm console` shows what is on the screen.

## Status

cbrm is young (0.x) and used in production by its authors on BERO HOST KVM rootservers. Covered today:
the server lifecycle — status, action log, console (screenshot and input), power, root password,
reinstall with SSH keys, own ISOs, CD drives, boot order and rescue system — and, new since 0.3.1, IP
addresses and reverse DNS, network reset, backups (list, create, restore, delete, automatic-backup
status), scheduled tasks, host name and product name, statistics (current and history), the account's SSH
keys, and read-only renewal and credit information (runtime left, the prices the panel quotes, payment
method, upgrade possible or not, balance). Planned: support tickets and — as the `cost` risk class — the
paying actions: renewals, upgrades and credit top-ups. Restoring single files from a backup is not covered.
Issues and pull requests are welcome on the primary repository.

## How it works

BERO HOST does not publish an API, so cbrm uses what the panel itself uses: its login form, its
server-rendered pages, one Livewire request for the action log, the JSON endpoints behind its power
buttons, and the noVNC console session it hands out (a Proxmox VNC websocket, bridged to a local port
and driven with vncdotool). Details in [docs/architecture.md](https://git.corbet.ch/corbet-infra/cbrm/src/branch/main/docs/architecture.md).

If the panel changes, cbrm fails with a clear error instead of guessing; see
[docs/operations.md](https://git.corbet.ch/corbet-infra/cbrm/src/branch/main/docs/operations.md#when-the-panel-changes).

## Where the code lives

| Place | Role |
|---|---|
| [git.corbet.ch/corbet-infra/cbrm](https://git.corbet.ch/corbet-infra/cbrm) | **primary**: issues, pull requests, releases |
| GitHub, GitLab, Bitbucket | read-only mirrors, updated automatically from the primary |

Please open issues and pull requests on the primary; changes pushed to a mirror are overwritten.

## License

**LGPL-3.0-only WITH LGPL-3.0-linking-exception** — use cbrm from any application under any license;
changes to cbrm itself stay open. Details in [LICENSE.md](https://git.corbet.ch/corbet-infra/cbrm/src/branch/main/LICENSE.md). Contributions are welcome under
the same terms; see [CONTRIBUTING.md](https://git.corbet.ch/corbet-infra/cbrm/src/branch/main/CONTRIBUTING.md).
