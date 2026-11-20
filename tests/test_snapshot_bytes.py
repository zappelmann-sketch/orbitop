# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Wächter des Schnappschuss-Vertrags: das tick-JSON jedes Testbaums bleibt Byte für Byte gleich.

Die Dateien unter tests/fixtures/snapshots/ sind snapshot(Kopie des Baums) vom Stand vor dem Umbau der Kacheln.
Neu geschrieben werden sie nur bei einer gewollten Änderung des Vertrags, mit genau dieser Funktion.
"""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from orbitop.sampler import Sampler
from tests.roots import ROOTS
from tests.sampler_helpers import OVERVIEW, NoTools, fake_clock

TREES = ("intel-laptop", "amd-desktop", "arm-board", "vm")
SNAPSHOTS = Path(__file__).parent / "fixtures" / "snapshots"
TICKS = 5


def statvfs(point):
    return SimpleNamespace(f_blocks=1000, f_bfree=400, f_frsize=4096)


def add(path: Path, step) -> None:
    """step(Felder einer Zeile) -> {Spalte: Zuwachs}; betroffene Zeilen stehen danach mit einfachen Leerzeichen."""
    out = []
    for line in path.read_text().splitlines():
        f = line.split()
        inc = step(f) if f else {}
        out.append(" ".join(str(int(x) + inc[i]) if i in inc else x for i, x in enumerate(f)) if inc else line)
    path.write_text("\n".join(out) + "\n")


def grow(root: str, n: int) -> None:
    """Vor Takt n wachsen die Zähler um n Schritte: Raten, Skalen und Segmente bekommen echte, wechselnde Werte."""
    stat = Path(root, "proc/stat")
    k = len(re.findall(r"^cpu\d", stat.read_text(), re.M))  # die Zeile "cpu" bleibt die Summe der cpuN-Zeilen
    add(stat, lambda f: {1: 3 * n * (k if f[0] == "cpu" else 1), 4: 7 * n * (k if f[0] == "cpu" else 1)}
        if f[0].startswith("cpu") else {})
    add(Path(root, "proc/net/dev"), lambda f: {1: 4000 * n, 9: 1000 * n} if f[0].endswith(":") else {})
    add(Path(root, "proc/diskstats"), lambda f: {5: 64 * n, 9: 16 * n} if len(f) >= 14 else {})
    for e in Path(root, "sys/class/powercap").glob("*/energy_uj"):
        e.write_text(f"{int(e.read_text()) + 5_000_000 * n}\n")


def snapshot(root: str) -> str:
    """Feste Tick-Folge auf einem beschreibbaren Baum, ohne Werkzeuge, Wanduhr oder echte Dateisysteme."""
    s = Sampler(root, tools=NoTools(), statvfs=statvfs, clock=fake_clock(), uid=1000)
    for n in range(TICKS):
        grow(root, n)
        s.tick_system()
        s.tick_procs()
    return s.snapshot_json(OVERVIEW)


@pytest.mark.parametrize("tree", TREES)
def test_snapshot_bytes_unchanged(tree, tree_copy):
    got = snapshot(tree_copy(str(Path(ROOTS, tree))))
    assert got.encode() == (SNAPSHOTS / f"{tree}.json").read_bytes()
