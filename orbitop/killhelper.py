#!/usr/bin/python3 -IS
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Signal-Kern und Root-Hilfsprogramm: killhelper.py <pid> <start> TERM|KILL (Aufruf über pkexec).

Läuft mit `python -IS`, ohne PYTHONPATH, Skriptverzeichnis und site-packages: nur Standardbibliothek, nie `orbitop.*`.
Deshalb ist das Stat-Parsen hier (bis zur letzten ')') bewusst doppelt zu procs.parse_stat.
Exit-Codes: 0 gesendet, 2 ungültig, 3 mismatch, 4 gone, 5 zombie, 6 Kernel/verweigert."""
import errno
import os
import signal
import sys

SENT, INVALID, MISMATCH, GONE, ZOMBIE, KERNEL = 0, 2, 3, 4, 5, 6


def _stat(pid: int, root: str) -> tuple[str, int, int]:
    """(state, ppid, start). FileNotFoundError/ProcessLookupError heißt: Prozess weg."""
    with open(f"{root}/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
        text = f.read()
    f = text[text.rindex(")") + 2:].split()
    return f[0], int(f[1]), int(f[19])


def send(pid: int, start: int, sig: str, root: str = "/") -> int:
    """Prüft und signalisiert race-frei über ein pidfd, das VOR der Prüfung geöffnet wird.
    Wirft PermissionError, wenn das Signal nicht erlaubt ist."""
    # Kopie von orbitop.procs.is_kernel (PID 1 oder Kernel-Thread): der Helfer läuft unter -I ohne das Paket
    if pid == 1:
        return KERNEL
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return GONE
    except OSError as e:
        if e.errno != errno.ENOSYS:
            raise
        fd = None  # shortcut: ohne pidfd (Kernel < 5.3) bleibt ein kleines PID-Wiederverwendungsfenster
    try:
        try:
            state, ppid, started = _stat(pid, root)
            if started != start:
                return MISMATCH
            if state in "ZX":
                return ZOMBIE
            if ppid in (0, 2):
                with open(f"{root}/proc/{pid}/cmdline", "rb") as f:
                    if not f.read(1):
                        return KERNEL
        except (FileNotFoundError, ProcessLookupError):
            return GONE
        signals = [{"TERM": signal.SIGTERM, "KILL": signal.SIGKILL}[sig]]
        if sig == "TERM" and state in "Tt":
            signals.append(signal.SIGCONT)  # angehaltener Prozess muss TERM verarbeiten können
        for s in signals:
            if fd is None:
                os.kill(pid, s)
            else:
                signal.pidfd_send_signal(fd, s)
        return SENT
    except ProcessLookupError:
        return GONE
    finally:
        if fd is not None:
            os.close(fd)


def _num(s: str, digits: int) -> int | None:
    return int(s) if s.isascii() and s.isdecimal() and len(s) <= digits else None


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[2] not in ("TERM", "KILL"):
        return INVALID
    try:
        with open("/proc/sys/kernel/pid_max") as f:
            pid_max = int(f.read())
    except (OSError, ValueError):
        pid_max = 4194304
    pid, start = _num(argv[0], 10), _num(argv[1], 20)
    if pid is None or start is None or not 1 <= pid <= pid_max:
        return INVALID
    try:
        return send(pid, start, argv[2])
    except OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
