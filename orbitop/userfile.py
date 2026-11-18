# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Dateien im Konfigurationsordner des Benutzers: XDG-Basis, sicheres Lesen, atomares Schreiben. Ohne GTK."""
import contextlib
import os
import stat
import tempfile
from collections.abc import Mapping


def config_home(env: Mapping[str, str]) -> str | None:
    """$XDG_CONFIG_HOME, wenn absolut (XDG: relative Werte ignorieren), sonst ~/.config; None, wenn auch das relativ
    ist, denn sonst landete alles unter dem Arbeitsverzeichnis."""
    base = env.get("XDG_CONFIG_HOME", "")
    if not os.path.isabs(base):
        base = os.path.join(os.path.expanduser("~"), ".config")
    return base if os.path.isabs(base) else None


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


def write_atomic(path: str, data: str) -> bool:
    """data über eine tmp-Datei im selben Ordner und os.replace; ein Symlink am Ziel wird selbst ersetzt, nie sein
    Ziel. False bei einem Fehler, dann bleibt keine tmp-Datei zurück."""
    tmp = None
    try:
        d = os.path.dirname(path)
        os.makedirs(d, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, path)
        return True
    except OSError:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        return False
