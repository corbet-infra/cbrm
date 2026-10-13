"""Configuration from the environment.
CBRM_USER + CBRM_PASSWORD, or CBRM_CREDENTIALS_CMD (prints user and password on two lines): the panel login.
CBRM_VMS: space-separated allow-list. CBRM_API_URL + CBRM_API_TOKEN: use a remote `cbrm serve` instead."""
from __future__ import annotations

import os
import shlex
import subprocess


def credentials() -> tuple[str, str]:
    if os.environ.get("CBRM_USER") and os.environ.get("CBRM_PASSWORD"):
        return os.environ["CBRM_USER"], os.environ["CBRM_PASSWORD"]
    cmd = os.environ.get("CBRM_CREDENTIALS_CMD")
    if not cmd:
        raise SystemExit("cbrm: set CBRM_USER/CBRM_PASSWORD, CBRM_CREDENTIALS_CMD, or CBRM_API_URL")
    lines = subprocess.run(shlex.split(cmd), capture_output=True, text=True, check=True).stdout.splitlines()
    if len(lines) < 2:
        raise SystemExit("cbrm: CBRM_CREDENTIALS_CMD must print the user and the password on two lines")
    return lines[0], lines[1]
