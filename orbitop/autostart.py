# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Autostart je Benutzer nach der freedesktop-Spezifikation „Desktop Application Autostart“. Ohne GTK.

Eine Benutzerdatei gleichen Namens geht allen Systemdateien vor, unter diesen gilt nur die im wichtigsten Ordner."""
import contextlib
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping

from orbitop import APP_ID

FILE = APP_ID + ".desktop"
TEMPLATE = """\
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
[Desktop Entry]
Type=Application
Name=orbitop
Exec=orbitop --hidden
TryExec=orbitop
Icon=io.github.zappelmann_sketch.orbitop
X-GNOME-Autostart-enabled=true
NoDisplay=true
"""  # byte-gleich data/autostart.desktop (Test)
OVERRIDE = "[Desktop Entry]\nType=Application\nName=orbitop\nHidden=true\n"
MAX_BYTES = 65536


def user_path(env: Mapping[str, str]) -> str:
    base = env.get("XDG_CONFIG_HOME", "")
    if not os.path.isabs(base):  # XDG: relative Werte ignorieren
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "autostart", FILE)


def system_paths(env: Mapping[str, str]) -> list[str]:
    dirs = env.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    return [os.path.join(d, "autostart", FILE) for d in dirs.split(":") if os.path.isabs(d)]


def _read(path: str) -> str | None:
    """Inhalt einer regulären Datei bis MAX_BYTES; alles andere gilt als nicht vorhanden."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)  # nie auf eine FIFO warten
        with os.fdopen(fd, "rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                return None
            data = f.read(MAX_BYTES + 1)
        return data.decode("utf-8") if len(data) <= MAX_BYTES else None
    except (OSError, ValueError):
        return None


def _on(text: str) -> bool:
    group, keys = None, {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            group = line
        elif group == "[Desktop Entry]" and "=" in line:
            key, _, value = line.partition("=")
            keys[key.strip()] = value.strip()
    return keys.get("Hidden") not in ("true", "1") and keys.get("X-GNOME-Autostart-enabled") not in ("false", "0")


def _entries(env: Mapping[str, str]) -> list[str]:
    """Lesbare Systemeinträge, der wichtigste zuerst."""
    return [t for t in map(_read, system_paths(env)) if t is not None]


def state(env: Mapping[str, str], which=shutil.which) -> bool | None:
    """None, wenn orbitop nicht als Befehl installiert ist (Checkout ohne Paket)."""
    if which("orbitop") is None:
        return None
    text = _read(user_path(env))
    if text is None:
        text = next(iter(_entries(env)), None)
    return text is not None and _on(text)


def _write(path: str, text: str) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)  # ersetzt auch einen Symlink selbst, nie sein Ziel
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def set_enabled(on: bool, env: Mapping[str, str], which=shutil.which) -> bool | None:
    """Schaltet den Autostart des Benutzers und gibt den Stand danach zurück; ohne Befehl schreibt es nichts."""
    if which("orbitop") is None:
        return None
    path, entries = user_path(env), _entries(env)
    try:
        if on:
            # lexists: liegt dort etwas Unlesbares oder Seltsames, wird es ersetzt, damit sicher TEMPLATE gilt
            if not (entries and _on(entries[0]) and not os.path.lexists(path)):
                _write(path, TEMPLATE)
        elif entries:
            _write(path, OVERRIDE)
        else:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(path)
    except OSError:
        pass  # der Stand bleibt; die Antwort nennt ihn
    return state(env, which)
