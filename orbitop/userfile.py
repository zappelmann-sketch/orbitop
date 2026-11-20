# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Dateien im Konfigurationsordner des Benutzers: XDG-Basis, sicheres Lesen, atomares Schreiben. Ohne GTK."""
import contextlib
import errno
import os
import stat
import sys
import tempfile
from collections.abc import Mapping

_reported: set[tuple[str, str]] = set()  # (Datei, Fehlerart), die in diesem Programmlauf schon auf stderr standen


def config_home(env: Mapping[str, str]) -> str | None:
    """XDG_CONFIG_HOME, wenn absolut (XDG: relative Werte ignorieren), sonst $HOME/.config, wenn HOME absolut ist;
    sonst None, denn sonst landete alles unter dem Arbeitsverzeichnis. Beides nur aus env, nie aus os.environ."""
    xdg, home = env.get("XDG_CONFIG_HOME", ""), env.get("HOME", "")
    if os.path.isabs(xdg):
        return xdg
    return os.path.join(home, ".config") if os.path.isabs(home) else None


def report_write_error(name: str, err: OSError) -> None:
    """Meldet einen Schreibfehler der Datei name ("layout", "autostart") auf stderr, je Art einmal je Programmlauf.
    Nur die Fehlerart, nie der Pfad: der enthielte das Home und damit den Benutzernamen."""
    kind = errno.errorcode.get(err.errno) or type(err).__name__
    if (name, kind) not in _reported:
        _reported.add((name, kind))
        with contextlib.suppress(OSError, ValueError):  # kaputtes stderr (EPIPE, ENOSPC, geschlossen): nur nicht melden
            print(f"orbitop: could not save {name} ({kind})", file=sys.stderr)


def read_regular(path: str, limit: int) -> bytes | None:
    """Inhalt einer regulären Datei mit höchstens limit Bytes; alles andere (FIFO, Gerät, Ordner, zu groß,
    unlesbar) ergibt None."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)  # nie auf eine FIFO warten, nie ein Terminal
        with os.fdopen(fd, "rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                return None
            data = f.read(limit + 1)
    except OSError:
        return None
    return data if len(data) <= limit else None


def _makedirs_private(d: str) -> None:
    """Wie os.makedirs(d, exist_ok=True), nur bekommt jede neue Ebene 0700; os.makedirs gibt mode nur der letzten."""
    missing = []
    while d and not os.path.isdir(d):
        missing.append(d)
        d = os.path.dirname(d)
    for m in reversed(missing):
        with contextlib.suppress(FileExistsError):  # gleichzeitig angelegt; liegt dort eine Datei, scheitert mkstemp
            os.mkdir(m, 0o700)


def write_atomic(path: str, data: str, name: str) -> bool:
    """data über eine tmp-Datei im selben Ordner und os.replace; ein Symlink am Ziel wird selbst ersetzt, nie sein
    Ziel. False bei einem Fehler, dann bleibt keine tmp-Datei zurück und report_write_error meldet ihn als name."""
    tmp = None
    try:
        d = os.path.dirname(path)
        _makedirs_private(d)
        fd, tmp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, path)
        return True
    except OSError as e:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        report_write_error(name, e)
        return False
