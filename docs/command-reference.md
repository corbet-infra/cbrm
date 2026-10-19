# Command reference

Generated from the registry and the CLI's own `--help` of cbrm 0.6.1 (`python scripts/command_reference.py`).

`cbrm [--json] <command> [<vm>] [--argument …]`; `--json` before the command prints machine-readable output. The HTTP API (`/vms/{vm}/<command>`) and the MCP server (`bero_<command>`, `-` written as `_`) offer the same commands with the same arguments and rules. `?` marks an optional argument, `…` one that takes several values.

| Risk | Meaning |
|---|---|
| read | Reads only; nothing to confirm. |
| secret | Reveals a secret: needs --confirm; audited without the value. |
| change | Changes something: needs --confirm; audited, and checked afterwards where the panel shows the effect; --dry-run shows the request without sending it. |
| destroy | Erases or overwrites data, or acts later and repeatedly without you: needs --confirm and --confirm-destroy; audited; --dry-run shows the request without sending it. |

Scope: `vm` commands act on one VM, and the allow-list `CBRM_VMS` applies. `account` commands (named `account-*`) act on the whole account and are not limited by the VM allow-list; the VM is optional, and the confirmation can be `account`.

## Contents

- [Server: state and logs](#server-state-and-logs)
- [Server: console and power](#server-console-and-power)
- [Server: installation, ISOs, drives, boot, rescue](#server-installation-isos-drives-boot-rescue)
- [Server: names, addresses, network, firewall](#server-names-addresses-network-firewall)
- [Server: backups and scheduled tasks](#server-backups-and-scheduled-tasks)
- [Server: runtime and SSH keys (read only)](#server-runtime-and-ssh-keys-read-only)
- [Account: SSH keys and codes](#account-ssh-keys-and-codes)
- [Account: internal networks](#account-internal-networks)
- [Account: firewalls](#account-firewalls)
- [Account: support tickets](#account-support-tickets)
- [Account: credit and bookkeeping (read only)](#account-credit-and-bookkeeping-read-only)
- [General](#general)

## Server: state and logs

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`status`](#status) | read | vm | – | Show state, host name, addresses and last backup |
| [`logs`](#logs) | read | vm | `--n`? `--search`? `--page`? | Show the panel's action log, newest first |
| [`activity`](#activity) | read | vm | `--n`? | Show who did what to the server in the panel |
| [`running-task`](#running-task) | read | vm | – | Show the task the panel is running right now |
| [`stats`](#stats) | read | vm | – | Show current CPU, RAM, disk and network use |
| [`stats-history`](#stats-history) | read | vm | `--timeframe`? `--metric`? | Show CPU, RAM, disk or network figures over time |
| [`updates`](#updates) | read | vm | – | Show the pending server updates |

### status

```
usage: cbrm status [-h] vm

[read] State, hostname, addresses, last backup and last installed template.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### logs

```
usage: cbrm logs [-h] [--n N] [--search SEARCH] [--page PAGE] vm

[read] The panel's action log, newest first, in panel time (Europe/Berlin): date, action and status (ok,
failed); a page of the log, optionally filtered with the panel's own search.

positional arguments:
  vm               the VM number, as `cbrm vms` lists it

options:
  -h, --help       show this help message and exit
  --n N            how many entries of the page
  --search SEARCH  only entries matching this text (the panel's own search)
  --page PAGE      page number, 1 is the newest
```

### activity

```
usage: cbrm activity [-h] [--n N] vm

[read] Who did what to the server in the panel, and when (the panel's activity list, newest first, panel
time): `you`, or the customer the product is shared with.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
  --n N       how many entries (1..200)
```

### running-task

```
usage: cbrm running-task [-h] vm

[read] The task the panel is running on the server right now (for example an installation or a backup), as
the panel's progress notice shows it; `running: false` when there is none.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### stats

```
usage: cbrm stats [-h] vm

[read] Current CPU, RAM and disk use, uptime, ping, traffic and running network/disk counters.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### stats-history

```
usage: cbrm stats-history [-h] [--timeframe {hour,day,week,month,year}] [--metric {cpu,ram,disk,network}] vm

[read] CPU, RAM, disk or network figures over a time frame: min, average, max and last value per series (cpu
and ram in percent, disk in MB/s, network in Mbit/s).

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --timeframe {hour,day,week,month,year}
                        how far back
  --metric {cpu,ram,disk,network}
                        what to show
```

### updates

```
usage: cbrm updates [-h] vm

[read] Pending server updates the panel offers to install (`pending` and the list the panel shows; the
panel's own words).

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

## Server: console and power

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`console`](#console) | read | vm | `--out` | Take a screenshot of the VNC console |
| [`console-input`](#console-input) | change | vm | `--text`? `--keys …`? `--repeat`? `--interval`? | Type text and press keys at the console |
| [`power`](#power) | change | vm | `--action` | Start, stop, shut down or restart the VM |
| [`updates-install`](#updates-install) | change | vm | – | Install the pending server updates |

### console

```
usage: cbrm console [-h] --out OUT vm

[read] A screenshot of the VNC console (PNG).

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
  --out OUT   PNG file to write
```

### console-input

```
usage: cbrm console-input [-h] [--text TEXT] [--keys KEYS [KEYS ...]] [--repeat REPEAT]
                          [--interval INTERVAL] --confirm VM [--dry-run]
                          vm

[change] Type text, then press keys (vncdotool names: enter, ctrl-c, down, f1, ...); repeat the keys to
catch a boot menu. Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --text TEXT           text to type (kept out of the audit log)
  --keys KEYS [KEYS ...]
                        keys to press after the text
  --repeat REPEAT       press the keys this many times (max 120)
  --interval INTERVAL   seconds between repeats
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
```

### power

```
usage: cbrm power [-h] --action {start,stop,shutdown,restart} --confirm VM [--dry-run] vm

[change] Start, stop (hard), shut down (ACPI) or restart the VM. Audited, and checked afterwards where the
panel shows the effect.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --action {start,stop,shutdown,restart}
                        what to do
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
```

### updates-install

```
usage: cbrm updates-install [-h] --confirm VM [--dry-run] vm

[change] Install the pending server updates (the panel's 'Updates installieren'; read `updates` first: what
they do is the panel's, the server may be restarted). Only while the panel lists pending updates. Audited,
and checked afterwards where the panel shows the effect.

positional arguments:
  vm            the VM number, as `cbrm vms` lists it

options:
  -h, --help    show this help message and exit
  --confirm VM  repeat the target VM
  --dry-run     read and check everything, change nothing, show the request
```

## Server: installation, ISOs, drives, boot, rescue

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`templates`](#templates) | read | vm | – | List the operating systems the panel can install |
| [`reinstall`](#reinstall) | destroy | vm | `--template` `--ssh-keys …`? | Reinstall from a template, erasing the disk |
| [`root-password`](#root-password) | secret | vm | – | Show the root password |
| [`set-root-password`](#set-root-password) | change | vm | `--password`? | Set or generate the root password |
| [`isos`](#isos) | read | vm | `--search`? | List the ISO images the panel can insert |
| [`iso-add`](#iso-add) | change | vm | `--url` `--title` | Add your own ISO from a public URL |
| [`iso-mount`](#iso-mount) | change | vm | `--drive` `--iso` | Insert an ISO into a CD drive |
| [`iso-unmount`](#iso-unmount) | change | vm | `--drive` | Remove the ISO from a CD drive |
| [`drives`](#drives) | read | vm | – | List the CD drives and what is inserted |
| [`drive-add`](#drive-add) | change | vm | – | Add a CD drive |
| [`drive-delete`](#drive-delete) | change | vm | `--drive` | Remove a CD drive |
| [`boot-order`](#boot-order) | read | vm | – | Show the boot order |
| [`boot-order-set`](#boot-order-set) | change | vm | `--order …` | Set the boot order |
| [`rescue`](#rescue) | read | vm | – | Show the rescue system state and images |
| [`rescue-enable`](#rescue-enable) | change | vm | `--image` | Boot into a rescue image next time |
| [`rescue-disable`](#rescue-disable) | change | vm | – | Leave the rescue system |

### templates

```
usage: cbrm templates [-h] vm

[read] Operating systems the panel can install: name -> template id.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### reinstall

```
usage: cbrm reinstall [-h] --template TEMPLATE [--ssh-keys SSH_KEYS [SSH_KEYS ...]] --confirm VM [--dry-run]
                      --confirm-destroy VM
                      vm

[destroy] Reinstall from a template with stored SSH keys baked in. ERASES THE DISK. Erases or overwrites
data, or acts later and repeatedly without you; audited.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --template TEMPLATE   name from `templates`
  --ssh-keys SSH_KEYS [SSH_KEYS ...]
                        names from `ssh-keys`
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
  --confirm-destroy VM  repeat the target VM again: data is erased
```

### root-password

```
usage: cbrm root-password [-h] --confirm VM [--dry-run] vm

[secret] The root password as the panel shows it. Audited without the value.

positional arguments:
  vm            the VM number, as `cbrm vms` lists it

options:
  -h, --help    show this help message and exit
  --confirm VM  repeat the target VM
  --dry-run     read and check everything, change nothing, show the request
```

### set-root-password

```
usage: cbrm set-root-password [-h] [--password PASSWORD] --confirm VM [--dry-run] vm

[change] Set the root password (generated if omitted); returns it. Audited, and checked afterwards where the
panel shows the effect.

positional arguments:
  vm                   the VM number, as `cbrm vms` lists it

options:
  -h, --help           show this help message and exit
  --password PASSWORD  the new password
  --confirm VM         repeat the target VM
  --dry-run            read and check everything, change nothing, show the request
```

### isos

```
usage: cbrm isos [-h] [--search SEARCH] vm

[read] ISO images the panel can insert (public ones and the account's own), optionally filtered.

positional arguments:
  vm               the VM number, as `cbrm vms` lists it

options:
  -h, --help       show this help message and exit
  --search SEARCH  filter by title or file name
```

### iso-add

```
usage: cbrm iso-add [-h] --url URL --title TITLE --confirm VM [--dry-run] vm

[change] Add your own ISO to the account from a public download URL (kept at least 6 months). Audited, and
checked afterwards where the panel shows the effect.

positional arguments:
  vm             the VM number, as `cbrm vms` lists it

options:
  -h, --help     show this help message and exit
  --url URL      HTTP(S) URL of the ISO file
  --title TITLE  title shown in the panel
  --confirm VM   repeat the target VM
  --dry-run      read and check everything, change nothing, show the request
```

### iso-mount

```
usage: cbrm iso-mount [-h] --drive DRIVE --iso ISO --confirm VM [--dry-run] vm

[change] Insert an ISO (id, title or file name from `isos`) into a CD drive. Audited, and checked afterwards
where the panel shows the effect.

positional arguments:
  vm             the VM number, as `cbrm vms` lists it

options:
  -h, --help     show this help message and exit
  --drive DRIVE  the drive, e.g. ide0
  --iso ISO      id, title or file name
  --confirm VM   repeat the target VM
  --dry-run      read and check everything, change nothing, show the request
```

### iso-unmount

```
usage: cbrm iso-unmount [-h] --drive DRIVE --confirm VM [--dry-run] vm

[change] Remove the ISO from a CD drive. Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm             the VM number, as `cbrm vms` lists it

options:
  -h, --help     show this help message and exit
  --drive DRIVE  the drive, e.g. ide0
  --confirm VM   repeat the target VM
  --dry-run      read and check everything, change nothing, show the request
```

### drives

```
usage: cbrm drives [-h] vm

[read] The VM's CD drives and what is inserted (live state from the hypervisor).

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### drive-add

```
usage: cbrm drive-add [-h] --confirm VM [--dry-run] vm

[change] Add a CD drive to the VM (the panel's 'Weiteres Laufwerk'; the panel picks the slot). A VM should
have one CD drive: add one only when it has none, see `drives`. Audited, and checked afterwards where the
panel shows the effect.

positional arguments:
  vm            the VM number, as `cbrm vms` lists it

options:
  -h, --help    show this help message and exit
  --confirm VM  repeat the target VM
  --dry-run     read and check everything, change nothing, show the request
```

### drive-delete

```
usage: cbrm drive-delete [-h] --drive DRIVE --confirm VM [--dry-run] vm

[change] Remove a CD drive from the VM (a VM should have one CD drive, the disk and network). Audited, and
checked afterwards where the panel shows the effect.

positional arguments:
  vm             the VM number, as `cbrm vms` lists it

options:
  -h, --help     show this help message and exit
  --drive DRIVE  the drive, e.g. ide0
  --confirm VM   repeat the target VM
  --dry-run      read and check everything, change nothing, show the request
```

### boot-order

```
usage: cbrm boot-order [-h] vm

[read] Boot devices in order (scsi0 = disk, ide0/ide2 = CD drives, net0 = network).

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### boot-order-set

```
usage: cbrm boot-order-set [-h] --order ORDER [ORDER ...] --confirm VM [--dry-run] vm

[change] Set the boot order: every device key from `boot-order`, first boots first. Audited, and checked
afterwards where the panel shows the effect.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --order ORDER [ORDER ...]
                        device keys in the new order, e.g. ide0 scsi0 net0 ide2
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
```

### rescue

```
usage: cbrm rescue [-h] vm

[read] Rescue system state and the available rescue images.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### rescue-enable

```
usage: cbrm rescue-enable [-h] --image IMAGE --confirm VM [--dry-run] vm

[change] Boot the next time into a rescue image (id or title from `rescue`). Audited, and checked afterwards
where the panel shows the effect.

positional arguments:
  vm             the VM number, as `cbrm vms` lists it

options:
  -h, --help     show this help message and exit
  --image IMAGE  id, title or file name
  --confirm VM   repeat the target VM
  --dry-run      read and check everything, change nothing, show the request
```

### rescue-disable

```
usage: cbrm rescue-disable [-h] --confirm VM [--dry-run] vm

[change] Leave the rescue system. Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm            the VM number, as `cbrm vms` lists it

options:
  -h, --help    show this help message and exit
  --confirm VM  repeat the target VM
  --dry-run     read and check everything, change nothing, show the request
```

## Server: names, addresses, network, firewall

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`hostname-set`](#hostname-set) | change | vm | `--hostname` | Set the VM's host name |
| [`rename`](#rename) | change | vm | `--name` | Rename the product in the panel |
| [`addresses`](#addresses) | read | vm | – | List IP addresses with gateway and reverse DNS |
| [`rdns-set`](#rdns-set) | change | vm | `--address` `--name` | Set the reverse DNS name of an address |
| [`network-reset`](#network-reset) | destroy | vm | – | Reset the network configuration and software firewall |
| [`network-connect`](#network-connect) | change | vm | `--network` | Connect the VM to an internal network |
| [`network-disconnect`](#network-disconnect) | change | vm | – | Disconnect the VM from its internal network |
| [`network-address-set`](#network-address-set) | change | vm | `--address` | Change the VM's internal IP address |
| [`firewall`](#firewall) | read | vm | – | Show the server's firewall and mail-port state |
| [`firewall-unassign`](#firewall-unassign) | change | vm | – | Remove the firewall from the server |
| [`mail-unlock-request`](#mail-unlock-request) | change | vm | `--purpose` `--hostname` `--accept-terms` | Ask BERO to unlock the mail ports |

### hostname-set

```
usage: cbrm hostname-set [-h] --hostname HOSTNAME --confirm VM [--dry-run] vm

[change] Set the VM's host name in the panel (lower-cased; letters, digits, hyphens, dots). Audited, and
checked afterwards where the panel shows the effect.

positional arguments:
  vm                   the VM number, as `cbrm vms` lists it

options:
  -h, --help           show this help message and exit
  --hostname HOSTNAME  the new host name, e.g. web1.example.org
  --confirm VM         repeat the target VM
  --dry-run            read and check everything, change nothing, show the request
```

### rename

```
usage: cbrm rename [-h] --name NAME --confirm VM [--dry-run] vm

[change] Rename the product in the panel (its display name, not the host name). Audited, and checked
afterwards where the panel shows the effect.

positional arguments:
  vm            the VM number, as `cbrm vms` lists it

options:
  -h, --help    show this help message and exit
  --name NAME   the new display name
  --confirm VM  repeat the target VM
  --dry-run     read and check everything, change nothing, show the request
```

### addresses

```
usage: cbrm addresses [-h] vm

[read] The VM's IPv4/IPv6 addresses with prefix length, gateway and reverse DNS entry.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### rdns-set

```
usage: cbrm rdns-set [-h] --address ADDRESS --name NAME --confirm VM [--dry-run] vm

[change] Set the reverse DNS name of one of the VM's IP addresses (see `addresses`). Audited, and checked
afterwards where the panel shows the effect.

positional arguments:
  vm                 the VM number, as `cbrm vms` lists it

options:
  -h, --help         show this help message and exit
  --address ADDRESS  the IP address, as `addresses` lists it
  --name NAME        the host name the address should resolve to, e.g. mail.example.org
  --confirm VM       repeat the target VM
  --dry-run          read and check everything, change nothing, show the request
```

### network-reset

```
usage: cbrm network-reset [-h] --confirm VM [--dry-run] --confirm-destroy VM vm

[destroy] Reset the VM's network configuration and software firewall (the panel's 'Netzwerk-Reset'):
everything you configured there is lost. Erases or overwrites data, or acts later and repeatedly without
you; audited.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
  --confirm-destroy VM  repeat the target VM again: data is erased
```

### network-connect

```
usage: cbrm network-connect [-h] --network NETWORK --confirm VM [--dry-run] vm

[change] Connect the VM to an internal network (free; the panel assigns the VM's address in the subnet,
change it with `network-address-set`). The VM must not be connected yet: disconnect it first to move it. The
guest's second NIC appears about a minute later and is not configured by the panel. Audited, and checked
afterwards where the panel shows the effect.

positional arguments:
  vm                 the VM number, as `cbrm vms` lists it

options:
  -h, --help         show this help message and exit
  --network NETWORK  the network's id from `account-networks`
  --confirm VM       repeat the target VM
  --dry-run          read and check everything, change nothing, show the request
```

### network-disconnect

```
usage: cbrm network-disconnect [-h] --confirm VM [--dry-run] vm

[change] Disconnect the VM from its internal network. The VM loses its internal address (a new connection
gets one assigned again); traffic over the second NIC stops. Audited, and checked afterwards where the panel
shows the effect.

positional arguments:
  vm            the VM number, as `cbrm vms` lists it

options:
  -h, --help    show this help message and exit
  --confirm VM  repeat the target VM
  --dry-run     read and check everything, change nothing, show the request
```

### network-address-set

```
usage: cbrm network-address-set [-h] --address ADDRESS --confirm VM [--dry-run] vm

[change] Change the VM's internal IP in its internal network (any free address of the subnet, not the
network or broadcast address). The panel only records it: the guest's NIC is configured by you. Audited, and
checked afterwards where the panel shows the effect.

positional arguments:
  vm                 the VM number, as `cbrm vms` lists it

options:
  -h, --help         show this help message and exit
  --address ADDRESS  the new IPv4 address, inside the network's subnet
  --confirm VM       repeat the target VM
  --dry-run          read and check everything, change nothing, show the request
```

### firewall

```
usage: cbrm firewall [-h] vm

[read] The server's firewall (id and name, or none) and its mail ports (25, 465, 587, 2525): unlocked since
when, or locked and whether an unlock can be requested.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### firewall-unassign

```
usage: cbrm firewall-unassign [-h] --confirm VM [--dry-run] vm

[change] Remove the firewall from the server (the panel's 'Entfernen' on the server's card): its rules stop
applying to this server after about a minute; the firewall itself stays for its other servers. Audited, and
checked afterwards where the panel shows the effect.

positional arguments:
  vm            the VM number, as `cbrm vms` lists it

options:
  -h, --help    show this help message and exit
  --confirm VM  repeat the target VM
  --dry-run     read and check everything, change nothing, show the request
```

### mail-unlock-request

```
usage: cbrm mail-unlock-request [-h] --purpose PURPOSE --hostname HOSTNAME --accept-terms {yes} --confirm VM
                                [--dry-run]
                                vm

[change] Ask BERO to unlock the mail ports (25, 465, 587, 2525) of the server (the panel's 'Freischaltung
beantragen'). BERO staff review it and answer in a support ticket: write the purpose as a person would. Only
while the ports are locked and the panel offers the request. Audited, and checked afterwards where the panel
shows the effect.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --purpose PURPOSE     what the mail ports are for, at most 2000 characters (BERO staff read it)
  --hostname HOSTNAME   the mail server's host name, e.g. mail.example.org
  --accept-terms {yes}  yes: you confirm that you send no spam or unsolicited bulk mail and keep BERO's
                        terms (the panel's checkbox)
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
```

## Server: backups and scheduled tasks

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`backups`](#backups) | read | vm | – | List backups and free backup slots |
| [`automatic-backup-status`](#automatic-backup-status) | read | vm | – | Show the automatic backup's state and schedule |
| [`backup-create`](#backup-create) | change | vm | `--title` | Create a backup now |
| [`backup-restore`](#backup-restore) | destroy | vm | `--backup` `--live`? | Restore the whole VM from a backup |
| [`backup-delete`](#backup-delete) | destroy | vm | `--backup` | Delete a backup |
| [`tasks`](#tasks) | read | vm | – | List the scheduled tasks |
| [`task-create`](#task-create) | destroy | vm | `--action` `--interval` `--start` `--notification-mode`? `--notification-email`? | Schedule a repeating action such as a backup |
| [`task-delete`](#task-delete) | change | vm | `--task` | Delete a scheduled task |
| [`task-notification-set`](#task-notification-set) | change | vm | `--task` `--notification-mode` `--notification-email`? | Set a scheduled task's e-mail notification |

### backups

```
usage: cbrm backups [-h] vm

[read] The VM's backups (id, title, size, date in panel time, protected: not replaced by scheduled backups)
and how many backup slots are free.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### automatic-backup-status

```
usage: cbrm automatic-backup-status [-h] vm

[read] Whether the automatic backup is enabled, and its last and next run (panel time).

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### backup-create

```
usage: cbrm backup-create [-h] --title TITLE --confirm VM [--dry-run] vm

[change] Create a backup now (the panel makes it in the background; needs a free slot, see `backups`).
Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm             the VM number, as `cbrm vms` lists it

options:
  -h, --help     show this help message and exit
  --title TITLE  the backup's name
  --confirm VM   repeat the target VM
  --dry-run      read and check everything, change nothing, show the request
```

### backup-restore

```
usage: cbrm backup-restore [-h] --backup BACKUP [--live {yes,no}] --confirm VM [--dry-run]
                           --confirm-destroy VM
                           vm

[destroy] Restore the whole VM from a backup. OVERWRITES THE DISK with the backup's state. Erases or
overwrites data, or acts later and repeatedly without you; audited.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --backup BACKUP       the backup's id from `backups`
  --live {yes,no}       yes: the VM starts at once while the data is restored in the background (the panel's
                        default); no: it is restored first
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
  --confirm-destroy VM  repeat the target VM again: data is erased
```

### backup-delete

```
usage: cbrm backup-delete [-h] --backup BACKUP --confirm VM [--dry-run] --confirm-destroy VM vm

[destroy] Delete a backup. THE BACKUP IS GONE. Erases or overwrites data, or acts later and repeatedly
without you; audited.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --backup BACKUP       the backup's id from `backups`
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
  --confirm-destroy VM  repeat the target VM again: data is erased
```

### tasks

```
usage: cbrm tasks [-h] vm

[read] The VM's scheduled tasks: id, action, repeat interval, next run (panel time) and the e-mail
notification (mode none, always or failed_only, and the address if not the account's).

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### task-create

```
usage: cbrm task-create [-h] --action ACTION --interval INTERVAL --start START
                        [--notification-mode NOTIFICATION_MODE] [--notification-email NOTIFICATION_EMAIL]
                        --confirm VM [--dry-run] --confirm-destroy VM
                        vm

[destroy] Schedule an action for the VM (action dump = backup, start, restart, shutdown, stop; interval
daily, 2-days, 3-days, 5-days, weekly, 2-weeks, monthly, yearly). DESTROYING: the task acts later and
repeatedly without you until it is deleted (a stop or restart task keeps interrupting the VM, a backup task
may rotate or overwrite backups), so it needs both confirmations. Erases or overwrites data, or acts later
and repeatedly without you; audited.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --action ACTION       what to run: the panel's own choices (dump, start, restart, shutdown, stop)
  --interval INTERVAL   how often: the panel's own choices (daily, 2-days, 3-days, 5-days, weekly, 2-weeks,
                        monthly, yearly)
  --start START         first run in panel time (Europe/Berlin), YYYY-MM-DD HH:MM, not in the past
  --notification-mode NOTIFICATION_MODE
                        optional e-mail notification: the panel's own choices (always, failed_only);
                        default: none (the panel's 'Keine E-Mail')
  --notification-email NOTIFICATION_EMAIL
                        optional: send the notification to this address instead of the account's (needs
                        notification_mode); default: the account's own address
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
  --confirm-destroy VM  repeat the target VM again: data is erased
```

### task-delete

```
usage: cbrm task-delete [-h] --task TASK --confirm VM [--dry-run] vm

[change] Delete a scheduled task (deleting the weekly backup task switches the automatic backup off).
Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm            the VM number, as `cbrm vms` lists it

options:
  -h, --help    show this help message and exit
  --task TASK   the task's id from `tasks`
  --confirm VM  repeat the target VM
  --dry-run     read and check everything, change nothing, show the request
```

### task-notification-set

```
usage: cbrm task-notification-set [-h] --task TASK --notification-mode NOTIFICATION_MODE
                                  [--notification-email NOTIFICATION_EMAIL] --confirm VM [--dry-run]
                                  vm

[change] Set a scheduled task's e-mail notification (the panel's bell on the task): none, always or
failed_only, optionally to another address than the account's. Audited, and checked afterwards where the
panel shows the effect.

positional arguments:
  vm                    the VM number, as `cbrm vms` lists it

options:
  -h, --help            show this help message and exit
  --task TASK           the task's id from `tasks`
  --notification-mode NOTIFICATION_MODE
                        none, or the panel's own choices (always, failed_only)
  --notification-email NOTIFICATION_EMAIL
                        optional: send it to this address instead of the account's (needs a mode other than
                        none)
  --confirm VM          repeat the target VM
  --dry-run             read and check everything, change nothing, show the request
```

## Server: runtime and SSH keys (read only)

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`renewal`](#renewal) | read | vm | – | Show remaining runtime, renewal options and credit |
| [`ssh-keys`](#ssh-keys) | read | vm | – | List the stored SSH keys by name |

### renewal

```
usage: cbrm renewal [-h] vm

[read] Remaining runtime, automatic renewal (runtimes with the prices the panel quotes, payment method),
whether the server can be upgraded, and the account credit.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### ssh-keys

```
usage: cbrm ssh-keys [-h] vm

[read] SSH keys stored in the panel account: name -> id.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

## Account: SSH keys and codes

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`account-ssh-keys`](#account-ssh-keys) | read | account | – | List the SSH keys stored in the account |
| [`account-ssh-key-import`](#account-ssh-key-import) | change | account | `--name` `--public-key` | Store a public SSH key in the account |
| [`account-ssh-key-delete`](#account-ssh-key-delete) | change | account | `--key` | Delete a stored SSH key from the account |
| [`account-codes`](#account-codes) | read | account | – | Show the account's share and transfer codes |
| [`account-code-regenerate`](#account-code-regenerate) | change | account | `--code` | Replace the share or transfer code with a new one |

### account-ssh-keys

```
usage: cbrm account-ssh-keys [-h] [vm]

[read, account-wide] SSH keys stored in the panel account: id, name, MD5 fingerprint.

positional arguments:
  vm          Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the VM
              is optional. Default: the first allowed VM

options:
  -h, --help  show this help message and exit
```

### account-ssh-key-import

```
usage: cbrm account-ssh-key-import [-h] --name NAME --public-key PUBLIC_KEY --confirm VM [--dry-run] [vm]

[change, account-wide] Store a public SSH key in the panel account; it can then be baked into a reinstall.
Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm                    Account-wide: acts on the whole account, not limited by the VM allow-list
                        (CBRM_VMS); the VM is optional. Default: the first allowed VM

options:
  -h, --help            show this help message and exit
  --name NAME           the key's name
  --public-key PUBLIC_KEY
                        one OpenSSH public key line (never a private key)
  --confirm VM          repeat the target VM (or `account`)
  --dry-run             read and check everything, change nothing, show the request
```

### account-ssh-key-delete

```
usage: cbrm account-ssh-key-delete [-h] --key KEY --confirm VM [--dry-run] [vm]

[change, account-wide] Delete an SSH key from the panel account; servers already installed keep it. Audited,
and checked afterwards where the panel shows the effect.

positional arguments:
  vm            Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the VM
                is optional. Default: the first allowed VM

options:
  -h, --help    show this help message and exit
  --key KEY     the key's id or name from `account-ssh-keys`
  --confirm VM  repeat the target VM (or `account`)
  --dry-run     read and check everything, change nothing, show the request
```

### account-codes

```
usage: cbrm account-codes [-h] [vm]

[read, account-wide] The account's share code and transfer code: what others enter to share a product or
transfer a server to this account; neither reveals the e-mail address, and each share or transfer must be
accepted.

positional arguments:
  vm          Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the VM
              is optional. Default: the first allowed VM

options:
  -h, --help  show this help message and exit
```

### account-code-regenerate

```
usage: cbrm account-code-regenerate [-h] --code {share,transfer} --confirm VM [--dry-run] [vm]

[change, account-wide] Replace the account's share or transfer code with a new one: the old code stops
working at once. Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm                    Account-wide: acts on the whole account, not limited by the VM allow-list
                        (CBRM_VMS); the VM is optional. Default: the first allowed VM

options:
  -h, --help            show this help message and exit
  --code {share,transfer}
                        which code
  --confirm VM          repeat the target VM (or `account`)
  --dry-run             read and check everything, change nothing, show the request
```

## Account: internal networks

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`account-networks`](#account-networks) | read | account | – | List internal networks with subnets and servers |
| [`account-network-create`](#account-network-create) | change | account | `--title` `--description`? | Create an internal network |
| [`account-network-edit`](#account-network-edit) | change | account | `--network` `--title`? `--description`? | Change an internal network's title or description |
| [`account-network-server-add`](#account-network-server-add) | change | account | `--network` `--server` | Add a server to an internal network |
| [`account-network-server-remove`](#account-network-server-remove) | change | account | `--network` `--server` | Remove a server from an internal network |
| [`account-network-delete`](#account-network-delete) | destroy | account | `--network` | Delete an internal network without servers |

### account-networks

```
usage: cbrm account-networks [-h] [vm]

[read, account-wide] Internal networks of the account: id, title, description, subnet (assigned by the
panel), servers with their internal address, and how many networks the account may have.

positional arguments:
  vm          Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the VM
              is optional. Default: the first allowed VM

options:
  -h, --help  show this help message and exit
```

### account-network-create

```
usage: cbrm account-network-create [-h] --title TITLE [--description DESCRIPTION] --confirm VM [--dry-run]
                                   [vm]

[change, account-wide] Create an internal network (free). The panel assigns the subnet itself, at most a few
networks per account (see `account-networks`). Audited, and checked afterwards where the panel shows the
effect.

positional arguments:
  vm                    Account-wide: acts on the whole account, not limited by the VM allow-list
                        (CBRM_VMS); the VM is optional. Default: the first allowed VM

options:
  -h, --help            show this help message and exit
  --title TITLE         the network's name, at most 255 characters
  --description DESCRIPTION
                        a description, at most 2000 characters
  --confirm VM          repeat the target VM (or `account`)
  --dry-run             read and check everything, change nothing, show the request
```

### account-network-edit

```
usage: cbrm account-network-edit [-h] --network NETWORK [--title TITLE] [--description DESCRIPTION]
                                 --confirm VM [--dry-run]
                                 [vm]

[change, account-wide] Change an internal network's title and/or description; what you leave out stays as it
is, an empty description clears it. Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm                    Account-wide: acts on the whole account, not limited by the VM allow-list
                        (CBRM_VMS); the VM is optional. Default: the first allowed VM

options:
  -h, --help            show this help message and exit
  --network NETWORK     the network's id from `account-networks`
  --title TITLE         the new title, at most 255 characters
  --description DESCRIPTION
                        the new description, at most 2000 characters; empty ("") clears it
  --confirm VM          repeat the target VM (or `account`)
  --dry-run             read and check everything, change nothing, show the request
```

### account-network-server-add

```
usage: cbrm account-network-server-add [-h] --network NETWORK --server SERVER --confirm VM [--dry-run] [vm]

[change, account-wide] Add a server of the account to an internal network (free). Only servers the panel
offers for that network can be added. Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm                 Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS);
                     the VM is optional. Default: the first allowed VM

options:
  -h, --help         show this help message and exit
  --network NETWORK  the network's id from `account-networks`
  --server SERVER    the server's VM number, as `status` shows it
  --confirm VM       repeat the target VM (or `account`)
  --dry-run          read and check everything, change nothing, show the request
```

### account-network-server-remove

```
usage: cbrm account-network-server-remove [-h] --network NETWORK --server SERVER --confirm VM [--dry-run]
                                          [vm]

[change, account-wide] Remove a server from an internal network. The server loses its internal address; the
panel assigns one again when it is added back. Audited, and checked afterwards where the panel shows the
effect.

positional arguments:
  vm                 Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS);
                     the VM is optional. Default: the first allowed VM

options:
  -h, --help         show this help message and exit
  --network NETWORK  the network's id from `account-networks`
  --server SERVER    the server's VM number, as `status` shows it
  --confirm VM       repeat the target VM (or `account`)
  --dry-run          read and check everything, change nothing, show the request
```

### account-network-delete

```
usage: cbrm account-network-delete [-h] --network NETWORK --confirm VM [--dry-run] --confirm-destroy VM [vm]

[destroy, account-wide] Delete an internal network. Only a network the panel offers a delete button for (one
without servers); the subnet is gone and may be assigned to another network. Erases or overwrites data, or
acts later and repeatedly without you; audited.

positional arguments:
  vm                    Account-wide: acts on the whole account, not limited by the VM allow-list
                        (CBRM_VMS); the VM is optional. Default: the first allowed VM

options:
  -h, --help            show this help message and exit
  --network NETWORK     the network's id from `account-networks`
  --confirm VM          repeat the target VM (or `account`)
  --dry-run             read and check everything, change nothing, show the request
  --confirm-destroy VM  repeat the target VM again: data is erased (or `account`)
```

## Account: firewalls

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`account-firewalls`](#account-firewalls) | read | account | – | List firewalls, their servers and the templates |
| [`account-firewall`](#account-firewall) | read | account | `--firewall` | Show one firewall's policies, rules and servers |
| [`account-firewall-create`](#account-firewall-create) | change | account | `--title` `--template`? | Create a firewall from a template |
| [`account-firewall-edit`](#account-firewall-edit) | change | account | `--firewall` `--title`? `--policy-in`? `--policy-out`? | Rename a firewall or set its default policies |
| [`account-firewall-server-remove`](#account-firewall-server-remove) | change | account | `--firewall` `--server` | Remove a server from a firewall |

### account-firewalls

```
usage: cbrm account-firewalls [-h] [vm]

[read, account-wide] Firewalls of the account: id, name, the servers each is assigned to, how many the
account may have, and the templates the panel offers for a new one.

positional arguments:
  vm          Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the VM
              is optional. Default: the first allowed VM

options:
  -h, --help  show this help message and exit
```

### account-firewall

```
usage: cbrm account-firewall [-h] --firewall FIREWALL [vm]

[read, account-wide] One firewall: name, default policy per direction (ACCEPT or DROP), the rules as the
panel stores them, and the account's servers with whether each uses this firewall.

positional arguments:
  vm                   Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS);
                       the VM is optional. Default: the first allowed VM

options:
  -h, --help           show this help message and exit
  --firewall FIREWALL  the firewall's id from `account-firewalls`
```

### account-firewall-create

```
usage: cbrm account-firewall-create [-h] --title TITLE [--template TEMPLATE] --confirm VM [--dry-run] [vm]

[change, account-wide] Create a firewall from one of the panel's templates (free). It applies to no server
until one is assigned; the account may have a limited number (see `account-firewalls`). Audited, and checked
afterwards where the panel shows the effect.

positional arguments:
  vm                   Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS);
                       the VM is optional. Default: the first allowed VM

options:
  -h, --help           show this help message and exit
  --title TITLE        the firewall's name, at most 100 characters
  --template TEMPLATE  a template id from `account-firewalls` (empty, linux, windows, webserver, ...);
                       default: the panel's preselected one
  --confirm VM         repeat the target VM (or `account`)
  --dry-run            read and check everything, change nothing, show the request
```

### account-firewall-edit

```
usage: cbrm account-firewall-edit [-h] --firewall FIREWALL [--title TITLE] [--policy-in {ACCEPT,DROP}]
                                  [--policy-out {ACCEPT,DROP}] --confirm VM [--dry-run]
                                  [vm]

[change, account-wide] Rename a firewall and/or set its default policy per direction (ACCEPT or DROP). It
applies to every server the firewall is assigned to after about a minute: DROP inbound without a rule for
SSH locks you out. The rules stay as they are; what you leave out stays as it is. Audited, and checked
afterwards where the panel shows the effect.

positional arguments:
  vm                    Account-wide: acts on the whole account, not limited by the VM allow-list
                        (CBRM_VMS); the VM is optional. Default: the first allowed VM

options:
  -h, --help            show this help message and exit
  --firewall FIREWALL   the firewall's id from `account-firewalls`
  --title TITLE         the new name, at most 100 characters
  --policy-in {ACCEPT,DROP}
                        default for incoming traffic
  --policy-out {ACCEPT,DROP}
                        default for outgoing traffic
  --confirm VM          repeat the target VM (or `account`)
  --dry-run             read and check everything, change nothing, show the request
```

### account-firewall-server-remove

```
usage: cbrm account-firewall-server-remove [-h] --firewall FIREWALL --server SERVER --confirm VM [--dry-run]
                                           [vm]

[change, account-wide] Remove a server from a firewall (the editor's 'Entfernen'): the firewall's rules stop
applying to that server after about a minute. Audited, and checked afterwards where the panel shows the
effect.

positional arguments:
  vm                   Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS);
                       the VM is optional. Default: the first allowed VM

options:
  -h, --help           show this help message and exit
  --firewall FIREWALL  the firewall's id from `account-firewalls`
  --server SERVER      the server's VM number, as `account-firewall` lists it
  --confirm VM         repeat the target VM (or `account`)
  --dry-run            read and check everything, change nothing, show the request
```

## Account: support tickets

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`account-tickets`](#account-tickets) | read | account | `--search`? `--page`? | List support tickets, newest first |
| [`account-ticket`](#account-ticket) | read | account | `--ticket` | Show one support ticket with its whole thread |
| [`account-ticket-create`](#account-ticket-create) | change | account | `--subject` `--text` `--product`? `--attach …`? | Open a support ticket |
| [`account-ticket-reply`](#account-ticket-reply) | change | account | `--ticket` `--text` `--attach …`? | Reply to an open support ticket |
| [`account-ticket-close`](#account-ticket-close) | change | account | `--ticket` | Close a support ticket; it cannot be reopened |

### account-tickets

```
usage: cbrm account-tickets [-h] [--search SEARCH] [--page PAGE] [vm]

[read, account-wide] Support tickets of the account: id, subject, date, status (as the panel labels it);
newest first, with an optional search and page number.

positional arguments:
  vm               Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the
                   VM is optional. Default: the first allowed VM

options:
  -h, --help       show this help message and exit
  --search SEARCH  only tickets matching this text (the panel's own search)
  --page PAGE      page number, 1 is the newest
```

### account-ticket

```
usage: cbrm account-ticket [-h] --ticket TICKET [vm]

[read, account-wide] One support ticket with its whole thread: subject, status open/closed, who handles it,
every message with sender (customer/support/system), date and attachment links.

positional arguments:
  vm               Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the
                   VM is optional. Default: the first allowed VM

options:
  -h, --help       show this help message and exit
  --ticket TICKET  the ticket's id from `account-tickets`
```

### account-ticket-create

```
usage: cbrm account-ticket-create [-h] --subject SUBJECT --text TEXT [--product PRODUCT]
                                  [--attach ATTACH [ATTACH ...]] --confirm VM [--dry-run]
                                  [vm]

[change, account-wide] Open a support ticket, optionally linked to a product of the account (a VM number as
in `status`) and with attachments (files inside the directory named by CBRM_ATTACH_DIR). BERO staff read it:
write it as a person would. Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm                    Account-wide: acts on the whole account, not limited by the VM allow-list
                        (CBRM_VMS); the VM is optional. Default: the first allowed VM

options:
  -h, --help            show this help message and exit
  --subject SUBJECT     subject, 5..255 characters
  --text TEXT           the message, at least 10 characters
  --product PRODUCT     link a product: a VM number of the account; omit for none
  --attach ATTACH [ATTACH ...]
                        a file to attach (relative to CBRM_ATTACH_DIR, at most 5, 10 MiB each)
  --confirm VM          repeat the target VM (or `account`)
  --dry-run             read and check everything, change nothing, show the request
```

### account-ticket-reply

```
usage: cbrm account-ticket-reply [-h] --ticket TICKET --text TEXT [--attach ATTACH [ATTACH ...]]
                                 --confirm VM [--dry-run]
                                 [vm]

[change, account-wide] Reply to an open support ticket, optionally with attachments (files inside the
directory named by CBRM_ATTACH_DIR). Audited, and checked afterwards where the panel shows the effect.

positional arguments:
  vm                    Account-wide: acts on the whole account, not limited by the VM allow-list
                        (CBRM_VMS); the VM is optional. Default: the first allowed VM

options:
  -h, --help            show this help message and exit
  --ticket TICKET       the ticket's id from `account-tickets`
  --text TEXT           the message, at least 10 characters
  --attach ATTACH [ATTACH ...]
                        a file to attach (relative to CBRM_ATTACH_DIR, at most 5, 10 MiB each)
  --confirm VM          repeat the target VM (or `account`)
  --dry-run             read and check everything, change nothing, show the request
```

### account-ticket-close

```
usage: cbrm account-ticket-close [-h] --ticket TICKET --confirm VM [--dry-run] [vm]

[change, account-wide] Close a support ticket as solved (the panel's 'Mein Anliegen ist gelöst'). A closed
ticket CANNOT be reopened: further questions need a new ticket. Audited, and checked afterwards where the
panel shows the effect.

positional arguments:
  vm               Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the
                   VM is optional. Default: the first allowed VM

options:
  -h, --help       show this help message and exit
  --ticket TICKET  the ticket's id from `account-tickets`
  --confirm VM     repeat the target VM (or `account`)
  --dry-run        read and check everything, change nothing, show the request
```

## Account: credit and bookkeeping (read only)

| Command | Risk | Scope | Arguments | Summary |
|---|---|---|---|---|
| [`account-credit`](#account-credit) | read | account | – | Show the account's credit balance |
| [`account-invoices`](#account-invoices) | read | account | `--search`? `--page`? | List the account's invoices, newest first |
| [`account-invoice-download`](#account-invoice-download) | read | account | `--invoice` `--out` | Download one invoice as PDF |
| [`account-orders`](#account-orders) | read | account | `--search`? `--page`? | List the account's orders |
| [`account-transactions`](#account-transactions) | read | account | `--search`? `--page`? | List the account's credit transactions |

### account-credit

```
usage: cbrm account-credit [-h] [vm]

[read, account-wide] The account's credit balance as the panel shows it.

positional arguments:
  vm          Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the VM
              is optional. Default: the first allowed VM

options:
  -h, --help  show this help message and exit
```

### account-invoices

```
usage: cbrm account-invoices [-h] [--search SEARCH] [--page PAGE] [vm]

[read, account-wide] Invoices of the account: number, amount, date; newest first.

positional arguments:
  vm               Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the
                   VM is optional. Default: the first allowed VM

options:
  -h, --help       show this help message and exit
  --search SEARCH  only rows matching this text (the panel's own search)
  --page PAGE      page number, 1 is the newest
```

### account-invoice-download

```
usage: cbrm account-invoice-download [-h] --invoice INVOICE --out OUT [vm]

[read, account-wide] One invoice as PDF: the panel's download of an invoice number from `account-invoices`.

positional arguments:
  vm                 Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS);
                     the VM is optional. Default: the first allowed VM

options:
  -h, --help         show this help message and exit
  --invoice INVOICE  the invoice number from `account-invoices`
  --out OUT          PDF file to write
```

### account-orders

```
usage: cbrm account-orders [-h] [--search SEARCH] [--page PAGE] [vm]

[read, account-wide] Orders of the account: product, type, date, status as the panel shows it.

positional arguments:
  vm               Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the
                   VM is optional. Default: the first allowed VM

options:
  -h, --help       show this help message and exit
  --search SEARCH  only rows matching this text (the panel's own search)
  --page PAGE      page number, 1 is the newest
```

### account-transactions

```
usage: cbrm account-transactions [-h] [--search SEARCH] [--page PAGE] [vm]

[read, account-wide] Credit transactions of the account: description, amount (negative = spent), date,
status.

positional arguments:
  vm               Account-wide: acts on the whole account, not limited by the VM allow-list (CBRM_VMS); the
                   VM is optional. Default: the first allowed VM

options:
  -h, --help       show this help message and exit
  --search SEARCH  only rows matching this text (the panel's own search)
  --page PAGE      page number, 1 is the newest
```

## General

### vms

```
usage: cbrm vms [-h]

List the account's VMs (within CBRM_VMS): state, host name, addresses, last backup and last installed
template.

options:
  -h, --help  show this help message and exit
```

### features

```
usage: cbrm features [-h]

List every operation with its risk class, scope and summary; with --json also the full help and the
parameters. Needs no login.

options:
  -h, --help  show this help message and exit
```

### doctor

```
usage: cbrm doctor [-h] vm

Check read-only, for every feature, that the panel still offers what it relies on: ok, BROKEN: reason, or
untested. Exits with 3 if a feature is broken.

positional arguments:
  vm          the VM number, as `cbrm vms` lists it

options:
  -h, --help  show this help message and exit
```

### serve

```
usage: cbrm serve [-h] [--host HOST] [--port PORT]

Run the HTTP API with the same features and rules; every route needs the bearer token in CBRM_API_TOKEN. The
OpenAPI schema is at /openapi.json.

options:
  -h, --help   show this help message and exit
  --host HOST  address to listen on (default: loopback)
  --port PORT  port to listen on (default: 8765)
```
