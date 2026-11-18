# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Prozesse beenden: eigene direkt, fremde über pkexec + die root-eigene Kopie von killhelper.py aus dem Paket."""
import os
import stat
import subprocess

from orbitop import killhelper
from orbitop.procs import is_kernel, parse_stat

# Installiert vom orbitop-Paket; nie die Datei im Checkout, die User-Code austauschen könnte (F-1).
# pkexec startet ihn direkt (Shebang python3 -I), damit die polkit-Action mit exec.path genau ihn trifft.
_HELPER = "/usr/lib/orbitop/killhelper"
# Absolute Pfade: kein PATH- oder venv-Einfluss auf das, was als root läuft.
PKEXEC = "/usr/bin/pkexec"
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


def _trusted(path: str, lstat=os.lstat) -> bool:
    """True, wenn path eine ausführbare reguläre Datei und kein Symlink ist und jedes Glied von ihr bis / root gehört
    und für Gruppe und andere nicht beschreibbar ist. Sonst könnte ein Prozess des Users austauschen, was pkexec als
    root startet; ohne x-Bit scheiterte pkexec erst nach dem Passwort."""
    try:
        st = lstat(path)
        if not stat.S_ISREG(st.st_mode) or not st.st_mode & stat.S_IXUSR:
            return False
        while st.st_uid == 0 and not st.st_mode & 0o022:  # ein Symlink weiter oben hat 0777 und fällt hier heraus
            if path == "/":
                return True
            path = os.path.dirname(path)
            st = lstat(path)
    except OSError:
        pass
    return False


def terminate(pid: int, start: int, force: bool, root="/", run=subprocess.run, lstat=os.lstat) -> str:
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
    if not _trusted(_HELPER, lstat):  # Helfer fehlt oder ist austauschbar: kein pkexec
        return "nohelper"
    try:
        r = run([PKEXEC, _HELPER, str(pid), str(start), sig], timeout=120)
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
        cmdline = b""
        if s["ppid"] in (0, 2):  # wie killhelper.send: nur dort zählt sie; ein hängendes Lesen sperrte das Beenden
            with open(f"{root}/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read(1)
        if is_kernel(pid, s["ppid"], cmdline):  # dieselbe Regel wie killhelper.send
            return "kernel"
    except (OSError, ValueError, IndexError):
        return "gone"
    return None


def is_alive(pid: int, start: int, root="/") -> bool:
    return _precheck(pid, start, root) in (None, "kernel")
