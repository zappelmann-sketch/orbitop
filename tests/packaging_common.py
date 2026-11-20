# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsames der Paket-Tests (test_packaging_*.py, test_changelog.py, test_build_packages.py)."""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
APT_SOURCE = PKG / "apt-source"
APP = "io.github.zappelmann_sketch.orbitop"
METAINFO = ROOT / "data" / f"{APP}.metainfo.xml"
NOREPLY = "235797375+zappelmann-sketch@users.noreply.github.com"
KEY_FILE = PKG / "keys" / "orbitop-archive-keyring.asc"  # der öffentliche Archivschlüssel (Plan 2026-11-18, Task 9)


def pulls_orbitop(relations):
    """K3: ob ein Feld mit Abhängigkeiten (deb oder RPM) ein Paket orbitop* nennt, auch als Alternative
    (a | b, (a or b)), in einer Bedingung, mit Version oder Architektur; %{name} und %name einer Spec zählen als
    orbitop (beide Specs heißen orbitop*)."""
    relations = re.sub(r"%\{name\}|%name\b", "orbitop", relations)
    return any(word.startswith("orbitop") for word in re.findall(r"[\w.+-]+", relations))


def load_changelog():  # über den Pfad: "packaging" ist auch der Name einer PyPI-Bibliothek, die pytest lädt
    spec = importlib.util.spec_from_file_location("orbitop_changelog", PKG / "changelog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def deb822(path):
    """Absätze einer deb822-Datei als dicts (ohne Kommentare, Folgezeilen angehängt)."""
    paras, cur, key = [], {}, None
    for line in path.read_text(encoding="utf-8").splitlines() + [""]:
        if line.startswith("#"):
            continue
        if not line.strip():
            if cur:
                paras.append(cur)
            cur, key = {}, None
        elif line[0] in " \t":
            cur[key] += "\n" + line.strip()
        else:
            key, _, value = line.partition(":")
            cur[key] = value.strip()
    return paras
