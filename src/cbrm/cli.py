"""cbrm command line, generated from the feature registry: `cbrm <feature> <vm> [--arg …]`.
Setup: see cbrm.config. `cbrm features` lists everything with its risk class."""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

from . import __version__
from .errors import ContractError, PanelError, ServiceError
from .features import ACCOUNT_NOTE, FILE_TYPES, REGISTRY

RISK_NOTES = {  # what each class means and requires (the command reference's table)
    "read": "Reads only; nothing to confirm.",
    "secret": "Reveals a secret: needs --confirm; audited without the value.",
    "change": "Changes something: needs --confirm; audited, and checked afterwards where the panel shows the effect; "
              "--dry-run shows the request without sending it.",
    "destroy": "Erases or overwrites data, or acts later and repeatedly without you: needs --confirm and "
               "--confirm-destroy; audited; --dry-run shows the request without sending it.",
}
RISK_HELP = {  # what a command's --help adds to its options (which already show --confirm and --dry-run)
    "read": "",
    "secret": " Audited without the value.",
    "change": " Audited, and checked afterwards where the panel shows the effect.",
    "destroy": " Erases or overwrites data, or acts later and repeatedly without you; audited.",
}


def marker(f) -> str:
    """The risk class, and the scope when it is the whole account: `[change]`, `[change, account-wide]`."""
    return f"[{f.risk}, account-wide]" if f.scope == "account" else f"[{f.risk}]"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cbrm", description="CLI for the BERO HOST customer panel and its VNC console. "
                                "`cbrm <command> --help` explains a command.",
                                epilog="Documentation: https://forge.corbet.ch/corbet-infra/cbrm/wiki")
    p.add_argument("--version", action="version", version=f"cbrm {__version__}")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>", title="commands")
    sub.add_parser("vms", help="List the account's VMs", description="List the account's VMs (within CBRM_VMS): "
                   "state, host name, addresses, last backup and last installed template.")
    sub.add_parser("features", help="List every operation with its risk and scope",
                   description="List every operation with its risk class, scope and summary; with --json also the "
                   "full help and the parameters. Needs no login.")
    sub.add_parser("doctor", help="Check read-only that the panel still offers every feature",
                   description="Check read-only, for every feature, that the panel still offers what it relies on: "
                   "ok, BROKEN: reason, or untested. Exits with 3 if a feature is broken.").add_argument(
                   "vm", help="the VM number, as `cbrm vms` lists it")
    s = sub.add_parser("plan", help="Show what makes the panel match a desired-state file",
                       description="Read every VM the desired-state files list and show the steps that make the panel "
                       "match it (task-create, task-notification-set, task-delete), or `no change`. Reads only. The "
                       "file format is in the docstring of cbrm.desired and in docs/operations.md.")
    s.add_argument("file", nargs="+", help="the desired-state file(s) (TOML; several files form one state)")
    s = sub.add_parser("apply", help="Make the panel match a desired-state file",
                       description="Plan afresh, show the steps, then run them through the features, each with its "
                       "checks, audit and verification. Changes nothing unless every VM the plan changes is repeated "
                       "in --confirm and, where it creates a task, in --confirm-destroy too.")
    s.add_argument("file", nargs="+", help="the desired-state file(s) (TOML; several files form one state)")
    s.add_argument("--confirm", nargs="+", default=[], metavar="VM", help="repeat every VM the plan changes")
    s.add_argument("--confirm-destroy", nargs="+", default=[], metavar="VM",
                   help="repeat every VM the plan creates a task on (a task acts later and repeatedly)")
    s = sub.add_parser("serve", help="Run the HTTP API (needs CBRM_API_TOKEN)",
                       description="Run the HTTP API with the same features and rules; every route needs the bearer "
                       "token in CBRM_API_TOKEN. The OpenAPI schema is at /openapi.json.")
    s.add_argument("--host", default="127.0.0.1", help="address to listen on (default: loopback)")
    s.add_argument("--port", type=int, default=8765, help="port to listen on (default: 8765)")
    for f in REGISTRY.values():
        s = sub.add_parser(f.name, help=f"[{f.risk}] {f.summary}".replace("%", "%%"),  # argparse formats help
                           description=f"{marker(f)} {f.help}.{RISK_HELP[f.risk]}".replace("%", "%%"))
        if f.scope == "account":  # no VM needed (a VM still works, as before)
            s.add_argument("vm", nargs="?", default="account", help=f"{ACCOUNT_NOTE} Default: the first allowed VM")
        else:
            s.add_argument("vm", help="the VM number, as `cbrm vms` lists it")
        for prm in f.params:
            opt = "--" + prm.name.replace("_", "-")
            kw = {"help": prm.help.replace("%", "%%"), "dest": prm.name, "type": prm.type}
            if prm.multiple:
                kw.update(nargs="+", default=None)
            if prm.choices:
                kw["choices"] = prm.choices
            s.add_argument(opt, required=prm.required, **kw)
        if f.returns in FILE_TYPES:
            s.add_argument("--out", required=True, help=f"{f.returns.upper()} file to write")
        if f.risk != "read":
            s.add_argument("--confirm", required=True, metavar="VM", help="repeat the target VM" + (" (or `account`)" if f.scope == "account" else ""))
            s.add_argument("--dry-run", action="store_true", help="read and check everything, change nothing, show the request")
        if f.risk == "destroy":
            s.add_argument("--confirm-destroy", required=True, metavar="VM", help="repeat the target VM again: data is erased" + (" (or `account`)" if f.scope == "account" else ""))
    return p


def _features(a, fs: list[dict], out) -> None:
    if a.json:
        out(fs)
        return
    width = max((len(f["name"]) for f in fs), default=18)
    print(f"{'RISK':8} {'SCOPE':8} {'COMMAND':{width}} SUMMARY")
    for f in fs:  # an older `cbrm serve` sends no summary and no scope
        scope = f.get("scope") or ("account" if f["name"].startswith("account-") else "vm")
        print(f"{f['risk']:8} {scope:8} {f['name']:{width}} {f.get('summary') or f['help']}")


def main(argv: list[str] | None = None) -> None:
    a = _parser().parse_args(argv)

    def out(obj) -> None:
        if a.json or not isinstance(obj, (dict, list)):
            print(json.dumps(obj, ensure_ascii=False, indent=None if a.json else 2, default=str))
        elif isinstance(obj, dict):
            print("\n".join(f"{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}" for k, v in obj.items()))
        else:
            print("\n".join(json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x) for x in obj))

    if a.cmd == "serve":
        import uvicorn

        from .api import create_app
        from .config import credentials
        from .panel import Panel
        from .service import Service
        if not os.environ.get("CBRM_API_TOKEN"):
            sys.exit("cbrm: serve needs CBRM_API_TOKEN")
        uvicorn.run(create_app(Service(Panel(*credentials()))), host=a.host, port=a.port)
        return

    if a.cmd == "features" and not os.environ.get("CBRM_API_URL"):  # the local registry: no login needed
        from .service import feature_list
        _features(a, feature_list(), out)
        return
    from .client import backend
    b = backend()
    try:
        if a.cmd == "vms":
            out(b.vms())
        elif a.cmd == "features":
            _features(a, b.features(), out)
        elif a.cmd in ("plan", "apply"):
            from . import desired
            wanted = desired.load_all(a.file)
            if a.cmd == "plan":
                steps = desired.plan(b, wanted)
                out({"steps": steps, "changes": len(steps)} if a.json else (steps or ["no change"]))
            else:
                res = desired.apply(b, wanted, a.confirm, a.confirm_destroy)
                out(res if a.json else (res["steps"] or ["no change"]))
                if not res["complete"]:
                    sys.exit(4)
        elif a.cmd == "doctor":
            res = b.check(a.vm)
            out(res)
            if any(v.startswith("BROKEN") for v in res.values()):
                sys.exit(3)
        else:
            f = REGISTRY[a.cmd]
            args = {p.name: getattr(a, p.name) for p in f.params if getattr(a, p.name) is not None}
            r = b.run(f.name, a.vm, args, confirm=getattr(a, "confirm", None),
                      confirm_destroy=getattr(a, "confirm_destroy", None),
                      dry_run=getattr(a, "dry_run", False))
            if isinstance(r, bytes):
                with open(a.out, "wb") as fh:
                    fh.write(r)
                print(a.out)
            else:
                out(r)
                if isinstance(r, dict) and r.get("verified") is False:
                    sys.exit(4)
    except ContractError as e:
        sys.exit(f"cbrm: the panel changed, so the change was not made: {e}")
    except (ServiceError, PanelError) as e:
        sys.exit(f"cbrm: {e}")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, httpx.HTTPError) as e:
        # Something the panel (or the cbrm API) sent that no check caught: one line, never a traceback.
        # CBRM_DEBUG=1 re-raises, for finding the check that is missing.
        if os.environ.get("CBRM_DEBUG"):
            raise
        sys.exit(f"cbrm: unexpected content from the panel or the cbrm API ({type(e).__name__}: {e}); if this was a "
                 "change, look at the panel or run a read feature to see whether it was made")


if __name__ == "__main__":
    main()
