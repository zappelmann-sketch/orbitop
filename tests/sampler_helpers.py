# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Hilfen der Sampler-Tests: Ersatz-Werkzeuge, feste Uhr, Takte fahren, Kacheln finden."""
import itertools

from orbitop.sampler import Sampler
from orbitop.sensors import SensorValues
from tests.roots import INTEL

OVERVIEW = {"tab": "overview", "pid": None, "start": None}
PROCS = {"tab": "procs", "pid": None, "start": None}


class NoTools:
    """Ersatz für GpuTools: keine Kindprozesse; pkg_w einstellbar, rechecks zählt recheck()."""
    def __init__(self, pkg_w=None):
        self.pkg_w, self.rechecks = pkg_w, 0

    def intel(self, card):
        return {"pkg_w": self.pkg_w} if self.pkg_w is not None else None

    def nvidia(self, pci):
        return None

    def hints(self):
        return []

    def recheck(self):
        self.rechecks += 1

    def stop(self):
        pass


def run(root, ticks=3, tools=None):
    clock = itertools.count(1000.0)
    s = Sampler(root, tools=tools or NoTools(), clock=lambda: float(next(clock)), uid=1000)
    for _ in range(ticks):
        s.tick_system()
        s.tick_procs()
    return s


def kinds(snap):
    return [t["kind"] for t in snap["tiles"]]


def tile(snap, id):
    return next(t for t in snap["tiles"] if t["id"] == id)


def fake_clock():
    c = itertools.count(1000.0)
    return lambda: float(next(c))


def sens(power=(), fans=(), temps=(), cpu=None):
    return SensorValues(cpu, list(temps), list(fans), list(power))


def power_of(patched, rapl=None, pkg_w=None, batt=None, hw=()):
    s = patched(INTEL, rapl=rapl, read_battery=batt, read_sensors=sens(power=hw), tools=NoTools(pkg_w=pkg_w))
    return tile(s.snapshot(OVERVIEW), "power")
