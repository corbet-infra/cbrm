---
name: bero
description: Manage BERO HOST (bero-host.de) KVM rootservers — list VMs, read status and the panel's action log, look at the VNC console, power start/stop/restart, type into the console, show or set the root password, reinstall from a template with an SSH key baked in. Use when the user asks to check, restart or operate a BERO HOST server, or to see its console. Uses the cbrm tool (MCP server `cbrm-mcp` or CLI `cbrm`).
---

# BERO HOST with cbrm

BERO HOST has no public API; `cbrm` speaks its customer panel and the panel's VNC console (Proxmox
noVNC). Prefer the MCP tools (`bero_*`); the CLI `cbrm` has the same commands.

## Rules

1. **Read before you act.** `bero_status`, `bero_logs` and `bero_console` first; say what you see.
2. **Changing tools repeat the target**: `confirm=<vm>`. Never change a VM the user did not name.
3. **One VM at a time** in a cluster: check the others are healthy before stopping or restarting one.
4. **`system` in the status is the last template BERO installed**, not proof of what runs. The
   console and the action log tell the truth (e.g. "Rootserver installieren" = it was reinstalled).
5. Typing into the console: screenshot, type, screenshot again; never type secrets you were not given
   for that purpose.
6. **Reinstall erases the disk**: only when the user asked for this VM to be wiped; it needs
   `confirm=<vm>` and `confirm_destroy=<vm>`. Bake an SSH key in (`bero_ssh_keys`) so you can log in after.
7. Root passwords are secrets: reveal or set them only for the task at hand, never repeat them in chat
   or files. Not available: backups/restore, network reset, ISO/boot order, renewals, upgrades, credit.

## Recipes

| Need | Steps |
|---|---|
| Is the server up? | `bero_status` → `bero_console` (login prompt? kernel panic? initrd waiting for a disk key?) |
| What happened to it? | `bero_logs` (panel time, Europe/Berlin): reinstalls, restarts, starts |
| Hung server | `bero_console` → `bero_power(action="restart", confirm=vm)` → `bero_console` |
| Fresh OS with your key | `bero_templates`, `bero_ssh_keys` → `bero_reinstall(template, ssh_keys=[name], confirm=vm, confirm_destroy=vm)` → SSH with that key |
| Act at the console | `bero_console` → `bero_console_input(text=..., keys=["enter"], confirm=vm)` → `bero_console` |

## Setup

`CBRM_USER` / `CBRM_PASSWORD`, or `CBRM_CREDENTIALS_CMD` (prints user and password on two lines, e.g.
from a secret store), or `CBRM_API_URL` + `CBRM_API_TOKEN` to use a shared `cbrm serve`.
Optional `CBRM_VMS="10001 10002"` limits everything to those VMs.
