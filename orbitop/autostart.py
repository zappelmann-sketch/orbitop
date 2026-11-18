# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Autostart je Benutzer nach der freedesktop-Spezifikation „Desktop Application Autostart“. Ohne GTK.

Eine Benutzerdatei gleichen Namens geht allen Systemdateien vor, unter diesen gilt nur die im wichtigsten Ordner."""
import contextlib
import os
import shutil
from collections.abc import Mapping

from orbitop import APP_ID
from orbitop.userfile import config_home, read_regular, write_atomic

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


def user_path(env: Mapping[str, str]) -> str | None:
    """None ohne absoluten Konfigurationsordner (relatives HOME): dann gibt es keinen Autostart des Benutzers."""
    home = config_home(env)
    return os.path.join(home, "autostart", FILE) if home else None


def system_paths(env: Mapping[str, str]) -> list[str]:
    dirs = env.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    return [os.path.join(d, "autostart", FILE) for d in dirs.split(":") if os.path.isabs(d)]


def _read(path: str) -> str | None:
    data = read_regular(path, MAX_BYTES)
    try:
        return None if data is None else data.decode("utf-8")
    except ValueError:  # kein UTF-8: wie nicht vorhanden
        return None


def _on(text: str) -> bool:
    """An nur mit Gruppe [Desktop Entry] und ohne Hidden=true oder X-GNOME-Autostart-enabled=false darin."""
    lines = [line.strip() for line in text.splitlines()]
    group, keys = None, {}
    for line in lines:
        if line.startswith("["):
            group = line
        elif group == "[Desktop Entry]" and "=" in line:
            key, _, value = line.partition("=")
            keys[key.strip()] = value.strip()
    return ("[Desktop Entry]" in lines and keys.get("Hidden") not in ("true", "1")
            and keys.get("X-GNOME-Autostart-enabled") not in ("false", "0"))


def _entries(env: Mapping[str, str]) -> list[str]:
    """Lesbare Systemeinträge, der wichtigste zuerst."""
    return [t for t in map(_read, system_paths(env)) if t is not None]


def state(env: Mapping[str, str], which=shutil.which) -> bool | None:
    """None, wenn orbitop nicht als Befehl installiert ist (Checkout ohne Paket) oder der Benutzerpfad fehlt."""
    path = user_path(env)
    if path is None or which("orbitop") is None:
        return None
    text = _read(path)
    if text is None:
        text = next(iter(_entries(env)), None)
    return text is not None and _on(text)


def set_enabled(on: bool, env: Mapping[str, str], which=shutil.which) -> bool | None:
    """Schaltet den Autostart des Benutzers und gibt den Stand danach zurück; wo state None ist, schreibt es nichts.
    Schreibfehler bleiben still wie bei LayoutFile.save: der Stand danach nennt sie."""
    path = user_path(env)
    if path is None or which("orbitop") is None:
        return None
    entries = _entries(env)
    if on:
        # lexists: liegt dort etwas Unlesbares oder Seltsames, wird es ersetzt, damit sicher TEMPLATE gilt
        if not (entries and _on(entries[0]) and not os.path.lexists(path)):
            write_atomic(path, TEMPLATE)
    elif entries:
        write_atomic(path, OVERRIDE)
    else:
        with contextlib.suppress(OSError):  # fehlt sie, ist das kein Fehler
            os.unlink(path)
    return state(env, which)
