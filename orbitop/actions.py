# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Prozesse beenden: eigene direkt, fremde über pkexec + killhelper.py (als root)."""
import os
import subprocess

from orbitop import killhelper
from orbitop.procs import parse_stat

_HELPER = os.path.abspath(killhelper.__file__)
# Absolute Pfade: kein PATH- oder venv-Einfluss auf das, was als root läuft.
PKEXEC = "/usr/bin/pkexec"
PYTHON = "/usr/bin/python3"
_RESULT = {0: "sent", 3: "mismatch", 4: "gone", 5: "zombie", 6: "kernel", 126: "denied", 127: "denied"}


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
    if type(pid) is not int or type(start) is not int:
        return "error"
    sig = "KILL" if force else "TERM"
    own = _own(pid, root)
    if own is None:
        return "gone"
    if own:
        try:
            return _RESULT[killhelper.send(pid, start, sig, root)]
        except PermissionError:
            return "denied"
        except OSError:  # z. B. Thread-ID als pid (ENOENT) oder EMFILE
            return "error"
    refused = _precheck(pid, start, root)
    if refused:  # veraltete Startzeit oder verweigertes Ziel: kein Passwortdialog
        return refused
    try:
        r = run([PKEXEC, PYTHON, "-I", _HELPER, str(pid), str(start), sig], timeout=120)
    except (OSError, subprocess.SubprocessError):
        return "error"
    return _RESULT.get(r.returncode, "error")


def _precheck(pid: int, start: int, root: str) -> str | None:
    """Ergebnis ohne Passwortdialog: gone, mismatch oder zombie, wenn (pid, start) nicht mehr lebt; kernel für pid 1
    und Kernel-Threads, die killhelper ohnehin verweigert. None: der Prozess lebt und darf gefragt werden."""
    try:
        with open(f"{root}/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            s = parse_stat(f.read())
        if s["start"] != start:
            return "mismatch"
        if s["state"] in "ZX":
            return "zombie"
        if pid == 1:
            return "kernel"
        if s["ppid"] in (0, 2):  # dieselbe Regel wie killhelper.send
            with open(f"{root}/proc/{pid}/cmdline", "rb") as f:
                if not f.read(1):
                    return "kernel"
    except (OSError, ValueError, IndexError):
        return "gone"
    return None


def is_alive(pid: int, start: int, root="/") -> bool:
    return _precheck(pid, start, root) in (None, "kernel")
