---
name: bero
description: Operate BERO HOST (bero-host.de) KVM rootservers — status, the panel's action log, VNC console (screenshot, typing), power, root password, reinstall with an SSH key baked in, own ISOs, CD drives, boot order, rescue system. Use when the user asks to check, restart, reinstall or boot a BERO HOST server, or to see its console. Uses the cbrm tool (MCP server `cbrm-mcp` or CLI `cbrm`). Use when the user asks to check, restart or operate a BERO HOST server, or to see its console. Uses the cbrm tool (MCP server `cbrm-mcp` or CLI `cbrm`).
---

# BERO HOST with cbrm

BERO HOST has no public API; `cbrm` speaks its customer panel and the panel's VNC console (Proxmox
noVNC). Prefer the MCP tools (`bero_*`, one per feature); the CLI `cbrm <feature> <vm>` has the same features.

## Rules

1. **Read before you act.** `bero_status`, `bero_logs`, `bero_console`, `bero_drives`, `bero_boot_order`; say what you see.
2. **Changing tools repeat the target**: `confirm=<vm>`; destroying ones also `confirm_destroy=<vm>`. Never act on a
   VM the user did not name. Use `dry_run=true` first when unsure: it shows the exact request.
3. **"panel changed" means stop.** BERO altered its panel; nothing was sent. Report it (and run `bero_doctor`);
   never try to reach the same effect another way.
4. **One VM at a time** in a cluster: check the others are healthy before stopping or restarting one.
5. **`system` in the status is the last template BERO installed**, not proof of what runs. The console and
   the action log tell the truth ("Rootserver installieren" = it was reinstalled).
6. **Reinstall erases the disk**: only when the user asked for this VM to be wiped. Bake an SSH key in.
7. Root passwords are secrets: reveal or set them only for the task, never repeat them in chat or files.
8. Console: screenshot, act, screenshot again. `verified=false` on a change means the panel did not show
   the effect yet: look again before retrying.

## Recipes

| Need | Steps |
|---|---|
| Is the server up? | `bero_status` → `bero_console` (login prompt? kernel panic? waiting for a disk key?) |
| What happened to it? | `bero_logs`: reinstalls, restarts, starts (panel time, Europe/Berlin) |
| Hung server | `bero_console` → `bero_power(action="restart", confirm=vm)` → `bero_console` |
| Fresh OS with your key | `bero_templates`, `bero_ssh_keys` → `bero_reinstall(template, ssh_keys=[name], confirm=vm, confirm_destroy=vm)` → SSH |
| Boot your own ISO | `bero_iso_add(url, title, confirm=vm)` → `bero_isos(search=title)` → `bero_iso_mount(drive="ide0", iso=id, confirm=vm)` → `bero_boot_order_set(order=["ide0", ...], confirm=vm)` → `bero_power(action="restart", confirm=vm)` → `bero_console` |
| Act at the console | `bero_console` → `bero_console_input(text=..., keys=["enter"], confirm=vm)` → `bero_console` |
| Is cbrm still in sync with the panel? | `bero_doctor(vm)` |

## Setup

`CBRM_USER` / `CBRM_PASSWORD`, or `CBRM_CREDENTIALS_CMD` (prints user and password on two lines, e.g.
from a secret store), or `CBRM_API_URL` + `CBRM_API_TOKEN` to use a shared `cbrm serve`.
Optional `CBRM_VMS="10001 10002"` limits everything to those VMs.
