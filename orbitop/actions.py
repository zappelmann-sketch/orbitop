# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Aufrufe mit root-Rechten: Prozesse beenden (eigene direkt, fremde über pkexec und killhelper) und die Zähler
freigeben oder sperren (pkexec und counterhelper). Beide Helfer sind die root-eigenen Kopien aus dem Paket."""
import os
import stat
import subprocess

from orbitop import killhelper
from orbitop.counters import state as counter_state
from orbitop.procs import is_kernel, parse_stat

# Installiert vom orbitop-Paket; nie die Datei im Checkout, die User-Code austauschen könnte (F-1).
# pkexec startet ihn direkt (Shebang python3 -IS), damit die polkit-Action mit exec.path genau ihn trifft.
_HELPER = "/usr/lib/orbitop/killhelper"
_COUNTERHELPER = "/usr/lib/orbitop/counterhelper"  # je Wort eine eigene polkit-Action (exec.argv1, B2.1)
# Absolute Pfade: kein PATH- oder venv-Einfluss auf das, was als root läuft.
PKEXEC = "/usr/bin/pkexec"
_RESULT = {0: "sent", 3: "mismatch", 4: "gone", 5: "zombie", 6: "kernel", 126: "denied", 127: "denied"}
# Je Exit-Code der Freigabe ein festes Wort (B2.1; 3 = Ort oder Umgebung unsicher, 4 = nur teilweise); was wirkt,
# zeigt der frisch gelesene Zustand. Als Ablehnung zählen nur 126 und 127 (jobs._outcome)
_COUNTERS = {0: "ok", 1: "error", 2: "error", 3: "unsafe", 4: "partial", 126: "cancelled", 127: "denied"}


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


def trusted(path: str, lstat=os.lstat) -> bool:
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


def real_pkexec(lstat=os.lstat, opener=os.open) -> bool:
    """True, wenn PKEXEC das setuid-ELF von polkit sein kann: trusted, root-eigen mit S_ISUID, beginnt mit \\x7fELF.
    run0-wrappers (openSUSE) legt dort ein bash-Skript um run0 ab, das die polkit-Action von orbitop umgeht (I-3).
    Vor jedem Aufruf von PKEXEC; gelesen mit O_NOFOLLOW aus einem fd, ein Symlink scheitert also auch hier."""
    try:
        if not trusted(PKEXEC, lstat) or not lstat(PKEXEC).st_mode & stat.S_ISUID:
            return False
        fd = opener(PKEXEC, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            return os.read(fd, 4) == b"\x7fELF"
        finally:
            os.close(fd)
    except OSError:
        return False


def counters_usable(lstat=os.lstat, opener=os.open) -> str:
    """yes, wenn der Schalter den Helfer über pkexec starten kann; nohelper ohne vertrauenswürdigen Helfer (etwa ein
    Start aus dem Checkout ohne Paket), nopkexec ohne das pkexec von polkit (E5)."""
    if not trusted(_COUNTERHELPER, lstat):
        return "nohelper"
    return "yes" if real_pkexec(lstat, opener) else "nopkexec"


def counters(on: bool, root="/", run=subprocess.run, lstat=os.lstat, opener=os.open) -> str:
    """Zähler freigeben (on) oder sperren über pkexec und counterhelper (B2.1, B2.7); ein Wort aus Klärung Q2.
    ok ohne Dialog, wenn die Merkdatei schon so steht; nohelper ohne vertrauenswürdigen Helfer oder pkexec von
    polkit. Was wirkt, zeigt danach der frisch gelesene Zustand (B2.5)."""
    if type(on) is not bool:
        return "error"
    if counter_state(root, lstat=lstat)["marker"] == ("on" if on else "off"):
        return "ok"
    if counters_usable(lstat, opener) != "yes":
        return "nohelper"
    try:
        r = run([PKEXEC, _COUNTERHELPER, "on" if on else "off"], timeout=120)
    except subprocess.TimeoutExpired:  # Dialog offen gelassen: pkexec ist beendet, das zählt wie ein Abbruch (R9)
        return "cancelled"
    except (OSError, subprocess.SubprocessError):  # auch PermissionError: kill() am Helfer, der schon als root läuft
        return "error"
    return _COUNTERS.get(r.returncode, "error")  # auch der Tod durch ein Signal: scheitert geschlossen


def terminate(pid: int, start: int, force: bool, root="/", run=subprocess.run, lstat=os.lstat, opener=os.open) -> str:
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
    if not (trusted(_HELPER, lstat) and real_pkexec(lstat, opener)):  # Helfer austauschbar, pkexec fremd: kein pkexec
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
