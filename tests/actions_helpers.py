# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Hilfen der Beenden-Tests: Helferpfade, vertrauenswürdige lstat-Kette, pkexec-Ersatz, Startzeit, Runner."""
import os
import stat
from types import SimpleNamespace

from orbitop import killhelper
from orbitop.procs import parse_stat


HELPER = os.path.abspath(killhelper.__file__)  # die Quelle im Checkout; pkexec startet nur die Kopie des Pakets
INSTALLED = "/usr/lib/orbitop/killhelper"
PKEXEC = "/usr/bin/pkexec"
FILES = {INSTALLED: stat.S_IFREG | 0o755, PKEXEC: stat.S_IFREG | stat.S_ISUID | 0o755}
ELF_HEAD = b"\x7fELF\x02\x01\x01\x00"


def chain_lstat(**over):
    """lstat einer vertrauenswürdigen Kette: alles root, Ordner 0755, der Helfer eine reguläre Datei 0755, pkexec
    setuid 4755; over: Pfad -> (uid, mode)."""
    def lstat(path):
        uid, mode = over.get(path, (0, FILES.get(path, stat.S_IFDIR | 0o755)))
        return SimpleNamespace(st_uid=uid, st_mode=mode)
    return lstat


def opener(data=ELF_HEAD, seen=None):
    """Ersatz für os.open: ein fd, aus dem data kommt (eine Pipe), statt der echten Datei; seen sammelt (Pfad, flags)
    und die fds, damit ein Test prüfen kann, dass sie geschlossen sind."""
    def open_(path, flags):
        r, w = os.pipe()
        os.write(w, data)
        os.close(w)
        if seen is not None:
            seen.append((path, flags, r))
        return r
    return open_


TRUSTED, ELF = chain_lstat(), opener()


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
