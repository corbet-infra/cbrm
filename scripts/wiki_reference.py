"""Write the wiki's Command reference from the CLI's own help: `python scripts/wiki_reference.py <out.md>`.
Every command, grouped by area, with its risk class and the exact `--help` text."""
import os
import sys
from pathlib import Path

os.environ["COLUMNS"] = "110"  # argparse wraps to the terminal width: make the reference reproducible
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from cbrm import __version__
from cbrm.cli import RISK_NOTES, _parser
from cbrm.features import REGISTRY

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


def main(out: str) -> None:
    listed = [n for _, names in AREAS for n in names]
    missing = sorted(set(REGISTRY) - set(listed))
    unknown = sorted(set(listed) - set(REGISTRY))
    if missing or unknown:
        raise SystemExit(f"update AREAS: missing {missing}, unknown {unknown}")
    parser = _parser()
    sub = next(a for a in parser._actions if a.dest == "cmd")
    lines = [f"Generated from `cbrm --help` of cbrm {__version__} (`python scripts/wiki_reference.py`). "
             "Every command also takes the global `--json` (before the command) for machine-readable output.", "",
             "| Risk | Meaning |", "|---|---|", *(f"| {r} | {n} |" for r, n in RISK_NOTES.items()), "",
             "## Contents", ""]
    for title, names in AREAS:
        lines.append(f"- **{title}**: " + ", ".join(f"[`{n}`](#{n})" for n in names))
    lines += ["- **General**: [`vms`](#vms), [`features`](#features), [`doctor`](#doctor), [`serve`](#serve)", "",
              "## cbrm", "", "```", parser.format_help().rstrip(), "```", ""]
    for title, names in [*AREAS, ("General", ("vms", "features", "doctor", "serve"))]:
        lines += [f"## {title}", ""]
        for n in names:
            risk = f" ({REGISTRY[n].risk})" if n in REGISTRY else ""
            lines += [f"### {n}", "", f"`cbrm {n}`{risk}", "", "```", sub.choices[n].format_help().rstrip(), "```", ""]
    Path(out).write_text("\n".join(lines))
    print(f"{len(listed)} features written to {out}")


if __name__ == "__main__":
    main(sys.argv[1])
