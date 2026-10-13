"""cbrm command line: the same operations as the API and the MCP server (see cbrm.config for setup)."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .panel import POWER_ACTIONS, PanelError
from .service import ServiceError


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="cbrm", description="BERO HOST management: panel and VNC console.")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("vms", help="all VMs of the account")
    sub.add_parser("status").add_argument("vm")
    s = sub.add_parser("logs"); s.add_argument("vm"); s.add_argument("-n", type=int, default=20)
    s = sub.add_parser("console", help="screenshot of the VNC console"); s.add_argument("vm"); s.add_argument("out")
    s = sub.add_parser("power", help="changes the VM"); s.add_argument("vm"); s.add_argument("action", choices=POWER_ACTIONS)
    s.add_argument("--confirm", required=True, metavar="VM", help="repeat the target VM")
    s = sub.add_parser("input", help="type text and/or press keys on the console (changes the VM)")
    s.add_argument("vm"); s.add_argument("--text", default=""); s.add_argument("--key", action="append", default=[],
                                                                              help="vncdotool key name, repeatable")
    s.add_argument("--confirm", required=True, metavar="VM", help="repeat the target VM")
    s = sub.add_parser("serve", help="run the HTTP API (needs CBRM_API_TOKEN)")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)

    def out(obj, text: str) -> None:
        print(json.dumps(obj, ensure_ascii=False) if a.json else text)

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
            rows = b.vms()
            out(rows, "\n".join(f"{r['vm']} {r['state']} {r.get('ipv4', '')} {r.get('system', '')}" for r in rows))
        elif a.cmd == "status":
            s = b.status(a.vm); out(s, "\n".join(f"{k}: {v}" for k, v in s.items()))
        elif a.cmd == "logs":
            e = b.logs(a.vm, a.n); out(e, "\n".join(f"{x['date']} {x['action']}" for x in e))
        elif a.cmd == "console":
            with open(a.out, "wb") as f:
                f.write(b.console_png(a.vm))
            out({"file": a.out}, a.out)
        elif a.cmd == "power":
            r = b.power(a.vm, a.action, a.confirm); out(r, r.get("message", json.dumps(r)))
        elif a.cmd == "input":
            out(b.console_input(a.vm, a.text, a.key, a.confirm), "sent")
    except (ServiceError, PanelError) as e:
        sys.exit(f"cbrm: {e}")


if __name__ == "__main__":
    main()
