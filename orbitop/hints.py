# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Ausgeblendete Hinweise der Fußzeile (Klärung Q1, Q2): eine JSON-Liste von Schlüsseln in
$XDG_CONFIG_HOME/orbitop/hints.json, atomar über userfile. Nur bekannte Schlüssel; eine kaputte Datei gilt als leer.
Ohne GTK."""
import json
import os
from collections.abc import Mapping

from orbitop.userfile import config_home, read_regular, write_atomic

KEYS = ("hint.igt_failed", "hint.igt_missing", "hint.igt_noperm", "hint.nvsmi_missing", "hint.rapl_noperm")
MAX_BYTES = 4096


def _path(env: Mapping[str, str]) -> str | None:
    home = config_home(env)
    return os.path.join(home, "orbitop", "hints.json") if home else None


def load(env: Mapping[str, str]) -> list[str]:
    """Die ausgeblendeten Schlüssel in der Reihenfolge von KEYS; ohne Datei oder bei einer kaputten []."""
    path = _path(env)
    data = read_regular(path, MAX_BYTES) if path else None
    try:
        saved = json.loads(data) if data is not None else []
    except (ValueError, RecursionError):  # auch kein UTF-8
        return []
    return [k for k in KEYS if k in saved] if isinstance(saved, list) else []


def _save(keys: list[str], env: Mapping[str, str]) -> list[str]:
    """Schreibt keys und gibt wie LayoutFile.save an die Seite nur den Stand danach: ohne Konfigurationsordner oder
    nach einem Schreibfehler (auf stderr gemeldet) den alten."""
    path = _path(env)
    if path:
        write_atomic(path, json.dumps(keys), "hints")
    return load(env)


def hide(key: str, env: Mapping[str, str]) -> list[str]:
    hidden = load(env)
    if key not in KEYS or key in hidden:
        return hidden
    return _save([k for k in KEYS if k in hidden or k == key], env)


def show_all(env: Mapping[str, str]) -> list[str]:
    return _save([], env)
