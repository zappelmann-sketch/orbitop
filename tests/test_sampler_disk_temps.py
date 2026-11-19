# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Sampler: Laufwerkstemperatur aus nvme- und drivetemp-Chips (Gerätepfad, Rückfall, Composite)."""
import os
from pathlib import Path

from orbitop import sampler as sampler_mod
from orbitop.sampler import Sampler
from tests.roots import AMD
from tests.sampler_helpers import OVERVIEW, NoTools, fake_clock, run, tile


def test_amd_disk_temperatures_by_device_path():
    snap = run(AMD).snapshot(OVERVIEW)
    d = {x["name"]: x["values"][3] for x in tile(snap, "disk")["devices"]["rows"]}
    assert d["nvme0n1"]["v"] is not None and d["sda"]["v"] is not None
    assert d["nvme0n1"]["v"] != d["sda"]["v"]


# 10 / 11: Laufwerkstemperatur
def disk_temps(root):
    rows = tile(run(root).snapshot(OVERVIEW), "disk")["devices"]["rows"]
    return {d["name"]: (d["values"][3] or {}).get("v") for d in rows}


def test_single_nvme_fallback_when_device_link_broken(tree_copy):
    root = tree_copy(AMD)
    want = disk_temps(root)["nvme0n1"]
    (Path(root) / "sys/class/hwmon/hwmon2/device").unlink()
    got = disk_temps(root)
    assert want is not None and got["nvme0n1"] == want and got["sda"] == disk_temps(AMD)["sda"]


def test_no_fallback_with_two_nvme_disks(tree_copy):
    root = tree_copy(AMD)
    (Path(root) / "sys/class/hwmon/hwmon2/device").unlink()
    import shutil
    shutil.copytree(Path(root) / "sys/block/nvme0n1", Path(root) / "sys/block/nvme1n1", symlinks=True)
    line = next(ln for ln in (Path(root) / "proc/diskstats").read_text().splitlines() if "nvme0n1 " in ln)
    with open(Path(root) / "proc/diskstats", "a") as f:
        f.write(line.replace("nvme0n1", "nvme1n1") + "\n")
    got = disk_temps(root)
    assert "nvme1n1" in got and got["nvme0n1"] is None and got["nvme1n1"] is None


def test_disk_temp_survives_hwmon_renumbering(tree_copy):
    root = tree_copy(AMD)
    base = Path(root) / "sys/class/hwmon"
    want = disk_temps(root)
    (base / "hwmon2").rename(base / "hwmon9")
    assert disk_temps(root) == want


# X1: Laufwerkstemperatur ist der erste Sensor (Composite), nicht der letzte
def test_disk_temp_is_composite_not_last_sensor(tree_copy):
    root = tree_copy(AMD)
    h = Path(root) / "sys/class/hwmon/hwmon2"
    for f in h.glob("temp*"):
        f.unlink()
    (h / "temp1_input").write_text("41000\n")
    (h / "temp1_label").write_text("Composite\n")
    (h / "temp2_input").write_text("63000\n")
    (h / "temp2_label").write_text("Sensor 1\n")
    assert disk_temps(root)["nvme0n1"] == 41.0


def test_disk_temps_built_once_per_tick(monkeypatch, tree_copy):
    root = tree_copy(AMD)
    s = Sampler(root, tools=NoTools(), clock=fake_clock(), uid=1000)
    s.tick_system()
    calls = []
    real = os.path.realpath
    monkeypatch.setattr(sampler_mod.os.path, "realpath", lambda p: (calls.append(p), real(p))[1])
    s.tick_system()
    chip_calls = [c for c in calls if "/hwmon/" in c]  # sensors löst nur gehaltene Chips (dell_smm) auf, hier keine
    assert len(chip_calls) == len(set(chip_calls)) == 2  # nvme und drivetemp, je einmal
