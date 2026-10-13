---
name: bero
description: Operate BERO HOST (bero-host.de) KVM rootservers — status, the panel's action log, VNC console (screenshot, typing), power, root password, reinstall with an SSH key baked in, own ISOs, CD drives, boot order, rescue system, IP addresses and reverse DNS, backups, scheduled tasks, host and product name, statistics, the account's SSH keys, renewal and credit information. Use when the user asks to check, restart, reinstall or boot a BERO HOST server, to see its console, or to manage its backups, rDNS or SSH keys. Uses the cbrm tool (MCP server `cbrm-mcp` or CLI `cbrm`). Use when the user asks to check, restart or operate a BERO HOST server, or to see its console. Uses the cbrm tool (MCP server `cbrm-mcp` or CLI `cbrm`).
---

# BERO HOST with cbrm

BERO HOST has no public API; `cbrm` speaks its customer panel and the panel's VNC console (Proxmox
noVNC). Prefer the MCP tools (`bero_*`, one per feature); the CLI `cbrm <feature> <vm>` has the same features.

## Rules

1. **Read before you act.** `bero_status`, `bero_logs`, `bero_console`, `bero_drives`, `bero_boot_order`; say what you see.
2. **Changing tools repeat the target**: `confirm=<vm>`; destroying ones also `confirm_destroy=<vm>`. Never act on a
   VM the user did not name. Use `dry_run=true` first when unsure: it shows the exact request. Destroying includes
   what acts later and repeatedly: `bero_task_create` (a scheduled stop, restart or backup repeats until
   `bero_task_delete`; the start must not be in the past, panel time).
3. **"panel changed" means stop.** BERO altered its panel; nothing was sent. Report it (and run `bero_doctor`);
   never try to reach the same effect another way.
4. **One VM at a time** in a cluster: check the others are healthy before stopping or restarting one.
5. **`system` in the status is the last template BERO installed**, not proof of what runs. The console and
   the action log tell the truth ("Rootserver installieren" = it was reinstalled).
6. **Reinstall erases the disk**: only when the user asked for this VM to be wiped. Bake an SSH key in.
7. Root passwords are secrets: reveal or set them only for the task, never repeat them in chat or files.
8. Console: screenshot, act, screenshot again. `verified=false` on a change means the panel did not show
   the effect yet: look again before retrying. `verified=null` means cbrm cannot tell (the panel shows no sign
   of that change, or could not be read): look yourself, never read it as failure or as success.
9. **`bero_account_*` tools act on the whole account** (stored SSH keys, credit), not on one server, and are
   **not limited by the VM allow-list**: the `vm` argument only names the account context. Delete or import
   keys only when the user asked for exactly that; a stored key can be baked into any server's reinstall.

## Recipes

| Need | Steps |
|---|---|
| Is the server up? | `bero_status` → `bero_console` (login prompt? kernel panic? waiting for a disk key?) |
| What happened to it? | `bero_logs`: reinstalls, restarts, starts (panel time, Europe/Berlin) |
| Hung server | `bero_console` → `bero_power(action="restart", confirm=vm)` → `bero_console` |
| Fresh OS with your key | `bero_templates`, `bero_ssh_keys` → `bero_reinstall(template, ssh_keys=[name], confirm=vm, confirm_destroy=vm)` → SSH |
| Boot your own ISO | `bero_iso_add(url, title, confirm=vm)` (the panel downloads in the background; wait) → `bero_isos(search=title)` → `bero_iso_mount(drive="ide2", iso=id, confirm=vm)` (must be `verified: true`) → keep one CD drive (`bero_drive_delete`) → **then** `bero_boot_order_set(order=["ide2","scsi0","net0"], confirm=vm)` → `bero_power(stop)`, `bero_power(start)` → right away `bero_console_input(keys=["enter"], repeat=3, interval=0.5, confirm=vm)` to pick the ISO menu's default → `bero_console` |
| Act at the console | `bero_console` → `bero_console_input(text=..., keys=["enter"], confirm=vm)` → `bero_console` |
| Backup before a risky change | `bero_backups` (free slot?) → `bero_backup_create(title, confirm=vm)` (`verified: true` once the backup or the used slot shows; if not, `bero_backups` again) ; restoring (`bero_backup_restore`) and deleting (`bero_backup_delete`) overwrite or destroy: only when the user asked, with `confirm` and `confirm_destroy` |
| Reverse DNS | `bero_addresses` → `bero_rdns_set(address, name, confirm=vm)` (`verified: true`) |
| Resource use | `bero_stats` (now) or `bero_stats_history(timeframe, metric)` |
| Stored SSH keys | `bero_account_ssh_keys`; `bero_account_ssh_key_import(name, public_key, confirm=vm)` takes **public** keys only; account-wide and not limited by the allow-list, `vm` only names the account context |
| Runtime, prices, credit | `bero_renewal`, `bero_account_credit` (read only; paying is not part of cbrm) |
| Is cbrm still in sync with the panel? | `bero_doctor(vm)` |

## Setup

`CBRM_USER` / `CBRM_PASSWORD`, or `CBRM_CREDENTIALS_CMD` (prints user and password on two lines, e.g.
from a secret store), or `CBRM_API_URL` + `CBRM_API_TOKEN` to use a shared `cbrm serve`.
Optional `CBRM_VMS="10001 10002"` limits everything to those VMs.
