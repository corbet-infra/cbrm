"""A process that used the console must exit: vncdotool's reactor thread is non-daemon and has to be
stopped before the interpreter joins threads (plain atexit runs too late and the process hangs)."""
import os
import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).parents[1] / "src")


def test_process_exits_after_the_vnc_reactor_started():
    code = ("import cbrm.console\n"
            "from vncdotool import api\n"
            "try:\n    api.connect('127.0.0.1::1', timeout=2)\n"
            "except Exception:\n    pass\n"
            "print('done')\n")
    # the child finds cbrm in the source tree too (pytest's `pythonpath` does not reach a subprocess)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (SRC, os.environ.get("PYTHONPATH"))))}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, env=env, check=False)
    assert "done" in r.stdout, r.stderr[-2000:]
