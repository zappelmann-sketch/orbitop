# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Layout der Prozesstabelle: Prüfung, Reparatur alter Dateien, Pfad und atomares Speichern. Ohne GTK."""
import contextlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping

COLUMNS = ("pid", "process", "user", "cpu", "last60", "ram", "io", "state", "pri", "nice", "virt", "shr", "s",
           "mem", "time")  # Grundreihenfolge; app.js hat dieselbe Liste (Test)
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


def config_path(env: Mapping[str, str]) -> str:
    base = env.get("XDG_CONFIG_HOME", "")
    if not os.path.isabs(base):  # XDG: relative Werte ignorieren
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "orbitop", "layout.json")


class LayoutFile:
    def __init__(self, path: str):
        self.path, self.current = path, None

    def load(self) -> dict | None:
        self.current = None
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)  # nie auf eine FIFO warten
            with os.fdopen(fd, "rb") as f:
                if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                    return None
                data = f.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                return None
            self.current = repair(json.loads(data))
        except (OSError, ValueError, RecursionError):
            pass  # current ist schon None
        return self.current

    def save(self, layout: dict) -> bool:
        if layout == self.current:
            return False
        self.current = layout
        tmp = None
        try:
            d = os.path.dirname(self.path)
            os.makedirs(d, mode=0o700, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=d)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(layout, f)
            os.replace(tmp, self.path)
            return True
        except OSError:
            if tmp:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
            return False
