"""A process that used the console must exit: vncdotool's reactor thread is non-daemon and has to be
stopped before the interpreter joins threads (plain atexit runs too late and the process hangs)."""
import subprocess
import sys


def test_process_exits_after_the_vnc_reactor_started():
    code = ("import cbrm.console\n"
            "from vncdotool import api\n"
            "try:\n    api.connect('127.0.0.1::1', timeout=2)\n"
            "except Exception:\n    pass\n"
            "print('done')\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert "done" in r.stdout
