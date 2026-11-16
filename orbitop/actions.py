# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Prozesse beenden: eigene direkt, fremde über pkexec + killhelper.py (als root)."""
import os
import subprocess
import sys

from orbitop import killhelper
from orbitop.procs import parse_stat

_HELPER = os.path.abspath(killhelper.__file__)
_RESULT = {0: "sent", 3: "mismatch", 4: "gone", 5: "zombie", 6: "kernel", 126: "denied", 127: "denied"}
_CODES = {killhelper.SENT: "sent", killhelper.MISMATCH: "mismatch", killhelper.GONE: "gone",
          killhelper.ZOMBIE: "zombie", killhelper.KERNEL: "kernel"}


def _own(pid: int, root: str) -> bool | None:
    """True, wenn die reale UID der eigenen entspricht; None, wenn der Prozess nicht mehr lesbar ist."""
    try:
        with open(f"{root}/proc/{pid}/status", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Uid:"):
                    return int(line.split()[1]) == os.getuid()
    except (OSError, ValueError, IndexError):
        pass
    return None


def terminate(pid: int, start: int, force: bool, root="/", run=subprocess.run) -> str:
    sig = "KILL" if force else "TERM"
    own = _own(pid, root)
    if own is None:
        return "gone"
    if own:
        try:
            return _CODES[killhelper.send(pid, start, sig, root)]
        except PermissionError:
            return "denied"
    try:
        r = run(["pkexec", sys.executable, "-I", _HELPER, str(pid), str(start), sig], timeout=120)
    except (OSError, subprocess.SubprocessError):
        return "error"
    return _RESULT.get(r.returncode, "error")


def is_alive(pid: int, start: int, root="/") -> bool:
    try:
        with open(f"{root}/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            s = parse_stat(f.read())
    except (OSError, ValueError, IndexError):
        return False
    return s["start"] == start and s["state"] not in "ZX"
