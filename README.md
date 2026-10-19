# cbrm — manage BERO HOST servers from the terminal, from code, and from AI assistants

[![PyPI](https://img.shields.io/pypi/v/cbrm)](https://pypi.org/project/cbrm/)
[![Python](https://img.shields.io/pypi/pyversions/cbrm)](https://pypi.org/project/cbrm/)
[![License: LGPL-3.0 with linking exception](https://img.shields.io/badge/license-LGPL--3.0%20%2B%20linking%20exception-blue)](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/LICENSE.md)
[![Documentation](https://img.shields.io/badge/docs-wiki-orange)](https://forge.corbet.ch/corbet-infra/cbrm/wiki)

**cbrm** ("BERO management") operates [BERO HOST](https://bero-host.de) KVM rootservers without clicking
through the customer panel: check status, read the panel's logs, look at the VNC console, power a server on or
off, type at its console, reinstall it, manage backups, rDNS, firewalls, internal networks and support tickets.
It is one package with five faces:

| You are | Use | Start with |
|---|---|---|
| a person at a terminal | the CLI `cbrm` | `cbrm vms` |
| a team or a service | the HTTP API `cbrm serve` (OpenAPI, bearer token) | [HTTP API](https://forge.corbet.ch/corbet-infra/cbrm/wiki/HTTP-API) |
| an AI assistant (Claude, …) | the MCP server `cbrm-mcp` and the skill in [`skills/bero/`](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/skills/bero/SKILL.md) | [MCP setup](#mcp) |
| a Python program | `cbrm.service.Service` (or the raw `cbrm.Panel` and `cbrm.Console`) | [Library](https://forge.corbet.ch/corbet-infra/cbrm/wiki/Library) |
| a contributor | Forgejo, see [CONTRIBUTING.md](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/CONTRIBUTING.md) | `nix develop` |

**Documentation: the [wiki](https://forge.corbet.ch/corbet-infra/cbrm/wiki)** — installation, quick start, credentials, the full command reference,
examples per area, the safety model, troubleshooting and FAQ.

BERO HOST is a German provider of prepaid game, root and virtual servers. Its panel is pleasant to use by hand; cbrm
exists for the moments when a script or an assistant should do the same thing. It is an independent community
project, not made or endorsed by BERO HOST, and it only does what a customer can do in the panel with their own
login. **cbrm never spends money**: renewals, upgrades, orders and credit top-ups stay in the panel, by hand.

## What it can do

Every operation is one entry of a registry; the CLI (`cbrm <feature> <vm> …`), the HTTP API
(`POST /vms/{vm}/{feature}`) and the MCP server (`bero_<feature>`) are generated from it, so all three offer the
same features with the same rules. `cbrm features` lists them; `cbrm <feature> --help` explains one.

<!-- features:begin (generated from the registry; tests/test_docs.py keeps it complete) -->
| Feature | Risk | Arguments | What it does |
|---|---|---|---|
| `account-codes` | read | – | The account's share code and transfer code (account-wide): what others enter to share a product or transfer a server to this account; neither reveals the e-mail address, and each share or transfer must be accepted |
| `account-credit` | read | – | The account's credit balance as the panel shows it (account-wide) |
| `account-firewall` | read | `--firewall` | One firewall (account-wide): name, default policy per direction (ACCEPT or DROP), the rules as the panel stores them, and the account's servers with whether each uses this firewall |
| `account-firewalls` | read | – | Firewalls of the account (account-wide): id, name, the servers each is assigned to, how many the account may have, and the templates the panel offers for a new one |
| `account-invoice-download` | read | `--invoice` | One invoice as PDF (account-wide): the panel's download of an invoice number from `account-invoices` |
| `account-invoices` | read | `--search`? `--page`? | Invoices of the account (account-wide): number, amount, date; newest first |
| `account-networks` | read | – | Internal networks of the account (account-wide): id, title, description, subnet (assigned by the panel), servers with their internal address, and how many networks the account may have |
| `account-orders` | read | `--search`? `--page`? | Orders of the account (account-wide): product, type, date, status as the panel shows it |
| `account-ssh-keys` | read | – | SSH keys stored in the panel account (account-wide): id, name, MD5 fingerprint |
| `account-ticket` | read | `--ticket` | One support ticket with its whole thread (account-wide): subject, status open/closed, who handles it, every message with sender (customer/support/system), date and attachment links |
| `account-tickets` | read | `--search`? `--page`? | Support tickets of the account (account-wide): id, subject, date, status (as the panel labels it); newest first, with an optional search and page number |
| `account-transactions` | read | `--search`? `--page`? | Credit transactions of the account (account-wide): description, amount (negative = spent), date, status |
| `activity` | read | `--n`? | Who did what to the server in the panel, and when (the panel's activity list, newest first, panel time): `you`, or the customer the product is shared with |
| `addresses` | read | – | The VM's IPv4/IPv6 addresses with prefix length, gateway and reverse DNS entry |
| `automatic-backup-status` | read | – | Whether the automatic backup is enabled, and its last and next run (panel time) |
| `backups` | read | – | The VM's backups (id, title, size, date in panel time, protected: not replaced by scheduled backups) and how many backup slots are free |
| `boot-order` | read | – | Boot devices in order (scsi0 = disk, ide0/ide2 = CD drives, net0 = network) |
| `console` | read | `--out` | A screenshot of the VNC console (PNG) |
| `drives` | read | – | The VM's CD drives and what is inserted (live state from the hypervisor) |
| `firewall` | read | – | The server's firewall (id and name, or none) and its mail ports (25, 465, 587, 2525): unlocked since when, or locked and whether an unlock can be requested |
| `isos` | read | `--search`? | ISO images the panel can insert (public ones and the account's own), optionally filtered |
| `logs` | read | `--n`? `--search`? `--page`? | The panel's action log, newest first, in panel time (Europe/Berlin): date, action and status (ok, failed); a page of the log, optionally filtered with the panel's own search |
| `renewal` | read | – | Remaining runtime, automatic renewal (runtimes with the prices the panel quotes, payment method), whether the server can be upgraded, and the account credit |
| `rescue` | read | – | Rescue system state and the available rescue images |
| `running-task` | read | – | The task the panel is running on the server right now (for example an installation or a backup), as the panel's progress notice shows it; `running: false` when there is none |
| `ssh-keys` | read | – | SSH keys stored in the panel account: name -> id |
| `stats` | read | – | Current CPU, RAM and disk use, uptime, ping, traffic and running network/disk counters |
| `stats-history` | read | `--timeframe`? `--metric`? | CPU, RAM, disk or network figures over a time frame: min, average, max and last value per series (cpu and ram in percent, disk in MB/s, network in Mbit/s) |
| `status` | read | – | State, hostname, addresses, last backup and last installed template |
| `tasks` | read | – | The VM's scheduled tasks: id, action, repeat interval, next run (panel time) and the e-mail notification (mode none, always or failed_only, and the address if not the account's) |
| `templates` | read | – | Operating systems the panel can install: name -> template id |
| `updates` | read | – | Pending server updates the panel offers to install (`pending` and the list the panel shows; the panel's own words) |
| `root-password` | secret | – | The root password as the panel shows it |
| `account-code-regenerate` | change | `--code` | Replace the account's share or transfer code with a new one (account-wide, not limited by the VM allow-list): the old code stops working at once |
| `account-firewall-create` | change | `--title` `--template`? | Create a firewall from one of the panel's templates (account-wide, not limited by the VM allow-list; free). It applies to no server until one is assigned; the account may have a limited number (see `account-firewalls`) |
| `account-firewall-edit` | change | `--firewall` `--title`? `--policy-in`? `--policy-out`? | Rename a firewall and/or set its default policy per direction (ACCEPT or DROP; account-wide, not limited by the VM allow-list). It applies to every server the firewall is assigned to after about a minute: DROP inbound without a rule for SSH locks you out. The rules stay as they are; what you leave out stays as it is |
| `account-firewall-server-remove` | change | `--firewall` `--server` | Remove a server from a firewall (the editor's 'Entfernen'; account-wide, not limited by the VM allow-list): the firewall's rules stop applying to that server after about a minute |
| `account-network-create` | change | `--title` `--description`? | Create an internal network (account-wide, not limited by the VM allow-list; free). The panel assigns the subnet itself, at most a few networks per account (see `account-networks`) |
| `account-network-edit` | change | `--network` `--title`? `--description`? | Change an internal network's title and/or description (account-wide, not limited by the VM allow-list; what you leave out stays as it is; an empty description clears it) |
| `account-network-server-add` | change | `--network` `--server` | Add a server of the account to an internal network (account-wide, not limited by the VM allow-list; free). Only servers the panel offers for that network can be added |
| `account-network-server-remove` | change | `--network` `--server` | Remove a server from an internal network (account-wide, not limited by the VM allow-list). The server loses its internal address; the panel assigns one again when it is added back |
| `account-ssh-key-delete` | change | `--key` | Delete an SSH key from the panel account (account-wide, not limited by the VM allow-list; servers already installed keep it) |
| `account-ssh-key-import` | change | `--name` `--public-key` | Store a public SSH key in the panel account (account-wide, not limited by the VM allow-list; it can then be baked into a reinstall) |
| `account-ticket-close` | change | `--ticket` | Close a support ticket as solved (the panel's 'Mein Anliegen ist gelöst'; account-wide, not limited by the VM allow-list). A closed ticket CANNOT be reopened: further questions need a new ticket |
| `account-ticket-create` | change | `--subject` `--text` `--product`? `--attach …`? | Open a support ticket (account-wide, not limited by the VM allow-list), optionally linked to a product of the account (a VM number as in `status`) and with attachments (files inside the directory named by CBRM_ATTACH_DIR). BERO staff read it: write it as a person would |
| `account-ticket-reply` | change | `--ticket` `--text` `--attach …`? | Reply to an open support ticket (account-wide, not limited by the VM allow-list), optionally with attachments (files inside the directory named by CBRM_ATTACH_DIR) |
| `backup-create` | change | `--title` | Create a backup now (the panel makes it in the background; needs a free slot, see `backups`) |
| `boot-order-set` | change | `--order …` | Set the boot order: every device key from `boot-order`, first boots first |
| `console-input` | change | `--text`? `--keys …`? `--repeat`? `--interval`? | Type text, then press keys (vncdotool names: enter, ctrl-c, down, f1, ...); repeat the keys to catch a boot menu |
| `drive-add` | change | – | Add a CD drive to the VM (the panel's 'Weiteres Laufwerk'; the panel picks the slot). A VM should have one CD drive: add one only when it has none, see `drives` |
| `drive-delete` | change | `--drive` | Remove a CD drive from the VM (a VM should have one CD drive, the disk and network) |
| `firewall-unassign` | change | – | Remove the firewall from the server (the panel's 'Entfernen' on the server's card): its rules stop applying to this server after about a minute; the firewall itself stays for its other servers |
| `hostname-set` | change | `--hostname` | Set the VM's host name in the panel (lower-cased; letters, digits, hyphens, dots) |
| `iso-add` | change | `--url` `--title` | Add your own ISO to the account from a public download URL (kept at least 6 months) |
| `iso-mount` | change | `--drive` `--iso` | Insert an ISO (id, title or file name from `isos`) into a CD drive |
| `iso-unmount` | change | `--drive` | Remove the ISO from a CD drive |
| `mail-unlock-request` | change | `--purpose` `--hostname` `--accept-terms` | Ask BERO to unlock the mail ports (25, 465, 587, 2525) of the server (the panel's 'Freischaltung beantragen'). BERO staff review it and answer in a support ticket: write the purpose as a person would. Only while the ports are locked and the panel offers the request |
| `network-address-set` | change | `--address` | Change the VM's internal IP in its internal network (any free address of the subnet, not the network or broadcast address). The panel only records it: the guest's NIC is configured by you |
| `network-connect` | change | `--network` | Connect the VM to an internal network (free; the panel assigns the VM's address in the subnet, change it with `network-address-set`). The VM must not be connected yet: disconnect it first to move it. The guest's second NIC appears about a minute later and is not configured by the panel |
| `network-disconnect` | change | – | Disconnect the VM from its internal network. The VM loses its internal address (a new connection gets one assigned again); traffic over the second NIC stops |
| `power` | change | `--action` | Start, stop (hard), shut down (ACPI) or restart the VM |
| `rdns-set` | change | `--address` `--name` | Set the reverse DNS name of one of the VM's IP addresses (see `addresses`) |
| `rename` | change | `--name` | Rename the product in the panel (its display name, not the host name) |
| `rescue-disable` | change | – | Leave the rescue system |
| `rescue-enable` | change | `--image` | Boot the next time into a rescue image (id or title from `rescue`) |
| `set-root-password` | change | `--password`? | Set the root password (generated if omitted); returns it |
| `task-delete` | change | `--task` | Delete a scheduled task (deleting the weekly backup task switches the automatic backup off) |
| `task-notification-set` | change | `--task` `--notification-mode` `--notification-email`? | Set a scheduled task's e-mail notification (the panel's bell on the task): none, always or failed_only, optionally to another address than the account's |
| `updates-install` | change | – | Install the pending server updates (the panel's 'Updates installieren'; read `updates` first: what they do is the panel's, the server may be restarted). Only while the panel lists pending updates |
| `account-network-delete` | destroy | `--network` | Delete an internal network (account-wide, not limited by the VM allow-list). Only a network the panel offers a delete button for (one without servers); the subnet is gone and may be assigned to another network |
| `backup-delete` | destroy | `--backup` | Delete a backup. THE BACKUP IS GONE |
| `backup-restore` | destroy | `--backup` `--live`? | Restore the whole VM from a backup. OVERWRITES THE DISK with the backup's state |
| `network-reset` | destroy | – | Reset the VM's network configuration and software firewall (the panel's 'Netzwerk-Reset'): everything you configured there is lost |
| `reinstall` | destroy | `--template` `--ssh-keys …`? | Reinstall from a template with stored SSH keys baked in. ERASES THE DISK |
| `task-create` | destroy | `--action` `--interval` `--start` `--notification-mode`? `--notification-email`? | Schedule an action for the VM (action dump = backup, start, restart, shutdown, stop; interval daily, 2-days, 3-days, 5-days, weekly, 2-weeks, monthly, yearly). DESTROYING: the task acts later and repeatedly without you until it is deleted (a stop or restart task keeps interrupting the VM, a backup task may rotate or overwrite backups), so it needs both confirmations |
<!-- features:end -->

| Risk | What cbrm requires |
|---|---|
| read | nothing |
| secret | `--confirm <vm>`; audited without the value |
| change | `--confirm <vm>`; audited; checked afterwards where the panel shows the effect (`verified`) |
| destroy | `--confirm <vm>` and `--confirm-destroy <vm>`: erases or overwrites data, or acts later and repeatedly without you (`reinstall`, `backup-delete`, `backup-restore`, `network-reset`, `task-create`, `account-network-delete`) |

`verified` is `true` when cbrm re-read the panel and it shows the effect, `false` when it does not (look again
before repeating the change; the CLI exits with 4), and `null` when cbrm cannot tell: the panel shows no sign of the
change to re-read (`backup-restore`, `network-reset`, `console-input`, …) or could not be read afterwards (then
`verify_error` may say why). `null` never means "failed".

Every changing command takes `--dry-run`: cbrm reads the panel (it may refresh or page through lists, which
changes nothing), checks everything, and shows the exact request it would send — without sending it or any
other request that changes or submits something. A dry run of a `secret` feature reveals nothing.

Features named `account-*` act on the **whole account** (stored SSH keys, credit, support tickets, internal
networks, firewalls, codes, bookkeeping), not on one server, and are **not limited by the VM allow-list**
(`CBRM_VMS`): the allow-list only decides which `<vm>` may *name* the account context. The VM is optional for them:
left out, cbrm uses the first allowed VM (else the lowest VM number) as the context, and the confirmation is
`--confirm account`. Naming a VM still works: it must belong to the account, must be on the allow-list and is
repeated as `--confirm <vm>`. One allowed VM is therefore enough to add or delete a stored key of the whole account,
to open or close support tickets and to change the account's networks and firewalls. If you give a team or an
assistant an allow-list, think of `account-*` as account access.

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
uv tool install cbrm                                              # from PyPI (or: pipx install cbrm / pip install cbrm)
uvx cbrm --help                                                   # run without installing (uv)
nix run git+https://forge.corbet.ch/corbet-infra/cbrm -- --help                    # Nix (flake)
```

Python 3.11 or newer. Dependencies: httpx, selectolax, websockets, vncdotool, Pillow, FastAPI, uvicorn, mcp.

## Configure

| Variable | Meaning |
|---|---|
| `CBRM_USER`, `CBRM_PASSWORD` | the panel login |
| `CBRM_CREDENTIALS_CMD` | instead: a command that prints the user and the password on two lines (`pass`, `sops`, a vault CLI, …) |
| `CBRM_VMS` | allow-list, e.g. `"10001 10002"`: every other server is refused. Unset means every server of the account. It does **not** limit the `account-*` features: they act on the whole account |
| `CBRM_ATTACH_DIR` | the only directory ticket attachments are read from (`--attach <file>` is relative to it). Unset means no attachments: an assistant cannot make cbrm send other files out |
| `CBRM_API_URL`, `CBRM_API_TOKEN` | use a running `cbrm serve` instead of logging in yourself |
| `XDG_STATE_HOME` | where the session cookie and `audit.log` live (`$XDG_STATE_HOME/cbrm`, mode 0700) |

```sh
export CBRM_CREDENTIALS_CMD="pass show hosting/bero-host"
cbrm vms
cbrm logs 10002 --n 5
cbrm console 10002 --out screen.png
cbrm power 10002 --action restart --confirm 10002
```

The password never appears on a command line: cbrm reads it from the environment or from the command's output.
See [Authentication and secrets](https://forge.corbet.ch/corbet-infra/cbrm/wiki/Authentication-and-secrets).

## MCP

For Claude Code, Claude Desktop or any MCP client (stdio):

```json
{ "mcpServers": { "bero": { "command": "uvx", "args": ["--from", "cbrm", "cbrm-mcp"],
    "env": { "CBRM_CREDENTIALS_CMD": "pass show hosting/bero-host", "CBRM_VMS": "10001 10002" } } } }
```

With a shared API the assistant never sees the panel password:
`"env": { "CBRM_API_URL": "https://cbrm.example.internal", "CBRM_API_TOKEN": "…" }`.
The skill [`skills/bero/SKILL.md`](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/skills/bero/SKILL.md) teaches an agent the safe order of work
(read, confirm, act, look again); copy it into your agent's skill directory.

## Recipes

| Goal | Steps |
|---|---|
| Fresh template with your SSH key | `cbrm reinstall <vm> --template "Arch Linux" --ssh-keys <name> --confirm <vm> --confirm-destroy <vm>`, then `ssh root@<ip>` (about 90 s later) |
| Hung server | `cbrm console <vm> --out s.png` → `cbrm power <vm> --action restart --confirm <vm>` → `cbrm console …` |
| What happened to my server? | `cbrm activity <vm>` (who did what in the panel) and `cbrm logs <vm>` (the hypervisor's actions with their status) |
| Is cbrm still in sync with the panel? | `cbrm doctor <vm>` |
| Back up before a risky change | `cbrm backups <vm>` (free slot?) → `cbrm backup-create <vm> --title <t> --confirm <vm>` |
| Repeat something on a schedule | `cbrm tasks <vm>` → `cbrm task-create <vm> --action dump --interval weekly --start "2026-10-20 03:30" --confirm <vm> --confirm-destroy <vm>` (panel time; the task repeats until `cbrm task-delete`) |
| Reverse DNS for a mail server | `cbrm addresses <vm>` → `cbrm rdns-set <vm> --address <ip> --name mail.example.org --confirm <vm>`; `cbrm firewall <vm>` shows whether the mail ports are unlocked, `cbrm mail-unlock-request` asks BERO to unlock them |
| A firewall for web servers | `cbrm account-firewalls` → `cbrm account-firewall-create --title web --template webserver --confirm account` |
| Private network between servers | `cbrm account-network-create --title backend --confirm account` → `cbrm network-connect <vm> --network <id> --confirm <vm>` per server |
| An invoice for the books | `cbrm account-invoices` → `cbrm account-invoice-download --invoice <number> --out invoice.pdf` |
| Server unreachable after a firewall or network change | `cbrm console <vm> --out s.png`, `cbrm firewall <vm>`, then `cbrm network-reset <vm> --confirm <vm> --confirm-destroy <vm>` |

More, per area, in the wiki's [Examples](https://forge.corbet.ch/corbet-infra/cbrm/wiki/Examples).

### Booting your own ISO (for example to install any OS)

1. `cbrm iso-add <vm> --url <public https url> --title <t> --confirm <vm>`. The panel confirms at once but
   **downloads in the background** (a 1.5 GB image took about 30 minutes); until it is done, inserting it
   reports success and inserts nothing — cbrm's `verified: false` tells you.
2. `cbrm isos <vm> --search <t>` → `cbrm iso-mount <vm> --drive ide2 --iso <id> --confirm <vm>`.
   Keep **one** CD drive (`cbrm drive-delete <vm> --drive ide0 …` if a reinstall created a second one,
   `cbrm drive-add` if there is none).
3. **After** mounting: `cbrm boot-order-set <vm> --order ide2 scsi0 net0 --confirm <vm>`.
4. `cbrm power <vm> --action stop …`, then `--action start`. The console becomes reachable about 20 s after
   the start; if your ISO has a boot menu, `cbrm console-input <vm> --keys enter --repeat 3 --interval 0.5 …`
   right away selects its default entry. `cbrm console` shows what is on the screen.

## Status

cbrm is 0.x and used in production by its authors on BERO HOST KVM rootservers. Covered: the server
lifecycle (status, logs, activity, console screenshot and input, power, root password, reinstall with SSH keys,
own ISOs, CD drives, boot order, rescue system, pending updates), IP addresses and reverse DNS, network reset,
the server's firewall and mail ports, internal networks, backups and scheduled tasks with their notifications,
host and product name, statistics, and for the whole account: stored SSH keys, support tickets, internal networks,
firewalls (create, rename, policies, servers), share and transfer codes, credit, invoices (with PDFs), orders and
transactions.

Not covered, on purpose: anything that costs money (renewals and their automation, upgrades, additional
addresses, orders, credit top-ups, donations), handing a server to another account (transfers), and the login's own
security and identity settings (password, e-mail, two-factor authentication, passkeys, sessions, personal data).
Not covered yet, because the panel shows the controls only in states that could not be recorded without changing
something: firewall rules, assigning a firewall to a server, deleting a firewall, sharing a product with another
customer, protecting a backup, and restoring single files from a backup. The wiki's [FAQ](https://forge.corbet.ch/corbet-infra/cbrm/wiki/FAQ) explains
each. Issues and pull requests are welcome on the primary repository.

## How it works

BERO HOST does not publish an API, so cbrm uses what the panel itself uses: its Livewire login, its
server-rendered pages, its Livewire components, the JSON endpoints behind its buttons, and the noVNC console
session it hands out (a Proxmox VNC websocket, bridged to a local port and driven with vncdotool). Details in
[docs/architecture.md](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/docs/architecture.md).

If the panel changes, cbrm fails with a clear error instead of guessing; see
[docs/operations.md](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/docs/operations.md#when-the-panel-changes).

## Where the code lives

| Place | Role |
|---|---|
| [forge.corbet.ch/corbet-infra/cbrm](https://forge.corbet.ch/corbet-infra/cbrm) | **primary**: code, issues, pull requests, releases, [wiki](https://forge.corbet.ch/corbet-infra/cbrm/wiki) |
| [PyPI](https://pypi.org/project/cbrm/) | releases |
| GitHub, GitLab, Bitbucket | read-only mirrors, updated automatically from the primary |

Please open issues and pull requests on the primary; changes pushed to a mirror are overwritten.

## License

**LGPL-3.0-only WITH LGPL-3.0-linking-exception** — use cbrm from any application under any license;
changes to cbrm itself stay open. Details in [LICENSE.md](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/LICENSE.md). Contributions are welcome under
the same terms; see [CONTRIBUTING.md](https://forge.corbet.ch/corbet-infra/cbrm/src/branch/main/CONTRIBUTING.md).
