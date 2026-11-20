# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Hilfen der Beenden-Tests: Helferpfade, vertrauenswürdige lstat-Kette, Startzeit, Ersatz-Runner."""
import os
import stat
from types import SimpleNamespace

from orbitop import killhelper
from orbitop.procs import parse_stat


HELPER = os.path.abspath(killhelper.__file__)  # die Quelle im Checkout; pkexec startet nur die Kopie des Pakets
INSTALLED = "/usr/lib/orbitop/killhelper"


def chain_lstat(**over):
    """lstat einer vertrauenswürdigen Kette (alles root, 0755, der Helfer eine reguläre Datei); over: Pfad -> (uid, mode)."""
    def lstat(path):
        uid, mode = over.get(path, (0, (stat.S_IFREG if path == INSTALLED else stat.S_IFDIR) | 0o755))
        return SimpleNamespace(st_uid=uid, st_mode=mode)
    return lstat


TRUSTED = chain_lstat()


def start_of(pid):
    with open(f"/proc/{pid}/stat") as f:
        return parse_stat(f.read())["start"]


def fake(calls, rc=0, exc=None):
    def run(argv, **kw):
        calls.append((argv, kw))
        if exc:
            raise exc
        return SimpleNamespace(returncode=rc)
    return run


def foreign_proc(root, pid, start, state, ppid=1, cmdline=b"x\0"):
    """Fremder Prozess (Uid 0) in einem Testbaum; state None: stat fehlt, cmdline None: cmdline fehlt."""
    d = root / "proc" / str(pid)
    d.mkdir(parents=True)
    (d / "status").write_text("Name:\tx\nUid:\t0\t0\t0\t0\n")
    if state:
        (d / "stat").write_text(f"{pid} (x y) {state} {ppid} " + "0 " * 17 + f"{start} 0 0\n")
    if cmdline is not None:
        (d / "cmdline").write_bytes(cmdline)
