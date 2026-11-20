# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Layout der Prozesstabelle: Prüfung, Reparatur alter Dateien, Pfad und atomares Speichern. Ohne GTK."""
import contextlib
import json
import os
from collections.abc import Mapping

from orbitop.userfile import config_home, read_regular, write_atomic

COLUMNS = ("pid", "process", "user", "cpu", "last60", "ram", "io", "state", "pri", "nice", "virt", "shr", "s",
           "mem", "time")  # Grundreihenfolge; ui/js/procs/columns.js hat dieselbe Liste (Test)
DEFAULT_HIDDEN = ("pri", "nice", "virt", "shr", "s", "mem", "time")
WIDTH_MIN, WIDTH_MAX = 40, 1200
SPLIT_MIN, SPLIT_MAX = 0.2, 0.8
MAX_BYTES = 4096
KEYS = ("order", "hidden", "widths", "split")


def _ids(v) -> bool:
    return isinstance(v, list) and all(isinstance(c, str) and c in COLUMNS for c in v)


def validate(obj) -> dict | None:
    """Streng laut Vertrag; eine neue Kopie ohne Zusatzschlüssel oder None."""
    if not isinstance(obj, dict) or any(k not in obj for k in KEYS):
        return None
    order, hidden, widths, split = (obj[k] for k in KEYS)
    if not (_ids(order) and len(order) == len(COLUMNS) and set(order) == set(COLUMNS)):
        return None
    if not (_ids(hidden) and len(set(hidden)) == len(hidden) and "process" not in hidden):
        return None
    if not (isinstance(widths, dict) and all(
            k in COLUMNS and type(v) is int and WIDTH_MIN <= v <= WIDTH_MAX for k, v in widths.items())):
        return None
    if type(split) not in (int, float) or not SPLIT_MIN <= split <= SPLIT_MAX:  # NaN und inf fallen hier durch
        return None
    return {"order": list(order), "hidden": list(hidden), "widths": dict(widths), "split": split}


def repair(obj) -> dict | None:
    """Für die Datei: unbekannte ids fallen weg, fehlende kommen an ihren Standardplatz, dann streng prüfen."""
    if not isinstance(obj, dict) or any(k not in obj for k in KEYS):
        return None
    order, hidden, widths = obj["order"], obj["hidden"], obj["widths"]
    if not (isinstance(order, list) and isinstance(hidden, list) and isinstance(widths, dict)):
        return None
    known = [c for c in order if isinstance(c, str) and c in COLUMNS]
    hid = [c for c in hidden if isinstance(c, str) and c in COLUMNS]
    for i, c in enumerate(COLUMNS):
        if c in known:
            continue
        before = [p for p in COLUMNS[:i] if p in known]
        known.insert(known.index(before[-1]) + 1 if before else 0, c)
        if c in DEFAULT_HIDDEN and c not in hid:
            hid.append(c)
    return validate({**obj, "order": known, "hidden": hid, "widths": {k: v for k, v in widths.items() if k in COLUMNS}})


def config_path(env: Mapping[str, str]) -> str | None:
    home = config_home(env)
    return os.path.join(home, "orbitop", "layout.json") if home else None


class LayoutFile:
    """path None (kein absoluter Konfigurationsordner): nichts lesen, nichts schreiben, nur current im Speicher."""

    def __init__(self, path: str | None):
        self.path, self.current = path, None

    def load(self) -> dict | None:
        self.current = None
        data = read_regular(self.path, MAX_BYTES) if self.path else None
        if data is not None:
            with contextlib.suppress(ValueError, RecursionError):  # current bleibt None
                self.current = repair(json.loads(data))
        return self.current

    def save(self, layout: dict) -> bool:
        if layout == self.current:
            return False
        self.current = layout
        return bool(self.path) and write_atomic(self.path, json.dumps(layout), "layout")
