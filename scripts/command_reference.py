"""Write the command reference from the registry and the CLI's own help: `python scripts/command_reference.py [out.md]`
(default `docs/command-reference.md`; the wiki's Command reference page is a copy of it). Every command, grouped
by area: a table with risk, scope, arguments and summary, then its exact `--help` text."""
import os
import sys
from pathlib import Path

os.environ["COLUMNS"] = "110"  # argparse wraps to the terminal width: make the reference reproducible
os.environ["NO_COLOR"] = "1"   # and colours its help on a terminal (Python 3.14)
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from cbrm import __version__
from cbrm.cli import RISK_NOTES, _parser
from cbrm.features import REGISTRY

ROOT = Path(__file__).parents[1]

AREAS = [
    ("Server: state and logs", ("status", "logs", "activity", "running-task", "stats", "stats-history", "updates")),
    ("Server: console and power", ("console", "console-input", "power", "updates-install")),
    ("Server: installation, ISOs, drives, boot, rescue",
     ("templates", "reinstall", "root-password", "set-root-password", "isos", "iso-add", "iso-mount", "iso-unmount",
      "drives", "drive-add", "drive-delete", "boot-order", "boot-order-set", "rescue", "rescue-enable", "rescue-disable")),
    ("Server: names, addresses, network, firewall",
     ("hostname-set", "rename", "addresses", "rdns-set", "network-reset", "network-connect", "network-disconnect",
      "network-address-set", "firewall", "firewall-unassign", "mail-unlock-request")),
    ("Server: backups and scheduled tasks",
     ("backups", "automatic-backup-status", "backup-create", "backup-restore", "backup-delete", "tasks", "task-create",
      "task-delete", "task-notification-set")),
    ("Server: runtime and SSH keys (read only)", ("renewal", "ssh-keys")),
    ("Account: SSH keys and codes", ("account-ssh-keys", "account-ssh-key-import", "account-ssh-key-delete",
                                     "account-codes", "account-code-regenerate")),
    ("Account: internal networks", ("account-networks", "account-network-create", "account-network-edit",
                                    "account-network-server-add", "account-network-server-remove", "account-network-delete")),
    ("Account: firewalls", ("account-firewalls", "account-firewall", "account-firewall-create", "account-firewall-edit",
                            "account-firewall-server-remove")),
    ("Account: support tickets", ("account-tickets", "account-ticket", "account-ticket-create", "account-ticket-reply",
                                  "account-ticket-close")),
    ("Account: credit and bookkeeping (read only)", ("account-credit", "account-invoices", "account-invoice-download",
                                                     "account-orders", "account-transactions")),
]
GENERAL = ("vms", "features", "doctor", "serve")


def anchor(title: str) -> str:
    return "".join(c for c in title.lower().replace(" ", "-") if c.isalnum() or c == "-")


def arguments(f) -> str:
    args = [f"`--{p.name.replace('_', '-')}{' …' if p.multiple else ''}`" + ("" if p.required else "?") for p in f.params]
    if f.returns != "json":
        args.append("`--out`")
    return " ".join(args) or "–"


def main(out: str) -> None:
    listed = [n for _, names in AREAS for n in names]
    missing = sorted(set(REGISTRY) - set(listed))
    unknown = sorted(set(listed) - set(REGISTRY))
    if missing or unknown:
        raise SystemExit(f"update AREAS: missing {missing}, unknown {unknown}")
    sub = next(a for a in _parser()._actions if a.dest == "cmd")
    lines = ["# Command reference", "",
             f"Generated from the registry and the CLI's own `--help` of cbrm {__version__} "
             "(`python scripts/command_reference.py`).", "",
             "`cbrm [--json] <command> [<vm>] [--argument …]`; `--json` before the command prints machine-readable "
             "output. The HTTP API (`/vms/{vm}/<command>`) and the MCP server (`bero_<command>`, `-` written as `_`) "
             "offer the same commands with the same arguments and rules. `?` marks an optional argument, `…` one "
             "that takes several values.", "",
             "| Risk | Meaning |", "|---|---|", *(f"| {r} | {n} |" for r, n in RISK_NOTES.items()), "",
             "Scope: `vm` commands act on one VM, and the allow-list `CBRM_VMS` applies. `account` commands (named "
             "`account-*`) act on the whole account and are not limited by the VM allow-list; the VM is optional, "
             "and the confirmation can be `account`.", "",
             "## Contents", ""]
    lines += [f"- [{title}](#{anchor(title)})" for title, _ in [*AREAS, ("General", ())]]
    lines.append("")
    for title, names in AREAS:
        lines += [f"## {title}", "", "| Command | Risk | Scope | Arguments | Summary |", "|---|---|---|---|---|"]
        for n in names:
            f = REGISTRY[n]
            lines.append(f"| [`{n}`](#{n}) | {f.risk} | {f.scope} | {arguments(f)} | {f.summary} |")
        lines.append("")
        for n in names:
            lines += [f"### {n}", "", "```", sub.choices[n].format_help().rstrip(), "```", ""]
    lines += ["## General", ""]
    for n in GENERAL:
        lines += [f"### {n}", "", "```", sub.choices[n].format_help().rstrip(), "```", ""]
    Path(out).write_text("\n".join(lines))
    print(f"{len(listed)} features written to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "docs" / "command-reference.md"))
