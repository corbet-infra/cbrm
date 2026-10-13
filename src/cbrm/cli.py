"""cbrm command line, generated from the feature registry: `cbrm <feature> <vm> [--arg …]`.
Setup: see cbrm.config. `cbrm features` lists everything with its risk class."""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

from .errors import ContractError, PanelError, ServiceError
from .features import REGISTRY


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cbrm", description="BERO HOST management: the panel and the VNC console.")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("vms", help="all VMs of the account")
    sub.add_parser("features", help="every operation with its risk class and arguments")
    sub.add_parser("doctor", help="check read-only that the panel still offers every feature").add_argument("vm")
    s = sub.add_parser("serve", help="run the HTTP API (needs CBRM_API_TOKEN)")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765)
    for f in REGISTRY.values():
        s = sub.add_parser(f.name, help=f"[{f.risk}] {f.help}".replace("%", "%%"))  # argparse formats help
        s.add_argument("vm")
        for prm in f.params:
            opt = "--" + prm.name.replace("_", "-")
            kw = {"help": prm.help.replace("%", "%%"), "dest": prm.name, "type": prm.type}
            if prm.multiple:
                kw.update(nargs="+", default=None)
            if prm.choices:
                kw["choices"] = prm.choices
            s.add_argument(opt, required=prm.required, **kw)
        if f.returns == "png":
            s.add_argument("--out", required=True, help="PNG file to write")
        if f.risk != "read":
            s.add_argument("--confirm", required=True, metavar="VM", help="repeat the target VM")
            s.add_argument("--dry-run", action="store_true", help="read and check everything, change nothing, show the request")
        if f.risk == "destroy":
            s.add_argument("--confirm-destroy", required=True, metavar="VM", help="repeat the target VM again: data is erased")
        if f.risk == "cost":
            s.add_argument("--confirm-cost", required=True, metavar="AMOUNT", help="the exact amount the panel quotes")
    return p


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

    from .client import backend
    b = backend()
    try:
        if a.cmd == "vms":
            out(b.vms())
        elif a.cmd == "features":
            fs = b.features()
            if a.json:
                out(fs)
            else:
                for f in fs:
                    args = " ".join(("--" + p["name"].replace("_", "-")) + ("" if p["required"] else "?") for p in f["params"])
                    print(f"{f['risk']:8} {f['name']:18} {args:30} {f['help']}")
        elif a.cmd == "doctor":
            res = b.check(a.vm)
            out(res)
            if any(v.startswith("BROKEN") for v in res.values()):
                sys.exit(3)
        else:
            f = REGISTRY[a.cmd]
            args = {p.name: getattr(a, p.name) for p in f.params if getattr(a, p.name) is not None}
            r = b.run(f.name, a.vm, args, confirm=getattr(a, "confirm", None),
                      confirm_destroy=getattr(a, "confirm_destroy", None), confirm_cost=getattr(a, "confirm_cost", None),
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
