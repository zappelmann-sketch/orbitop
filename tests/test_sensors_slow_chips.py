# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""read_sensors mit langsamen Chips: dell_smm höchstens alle 5 s, gehaltene Werte je Gerät."""
import os
import time

import pytest

from orbitop import sensors
from orbitop.sensors import read_sensors
from tests.sensors_helpers import hwmon, write


# ---- Langsame Chips (Task 17): dell_smm (SLOW_CHIPS) höchstens alle 5 s ----
def _smm(v):
    return [t.value for t in v.temps if t.chip == "dell_smm"] + [f.rpm for f in v.fans]


def test_dell_smm_read_at_most_every_5_s(intel_copy):
    held = {}
    first = read_sensors(intel_copy, held, 100.0)
    hwmon(intel_copy, 5, "dell_smm", {"temp1_input": 77000, "fan1_input": 3333})
    hwmon(intel_copy, 7, "coretemp", {"temp1_input": 55000})
    mid = read_sensors(intel_copy, held, 104.9)
    assert _smm(mid) == _smm(first)  # der letzte Wert bleibt stehen
    assert mid.cpu_temp == pytest.approx(55.0)  # schnelle Chips jeden Takt
    late = read_sensors(intel_copy, held, 105.0)
    assert 77.0 in _smm(late) and 3333.0 in _smm(late)


def test_held_chip_not_reused_after_hwmon_renumbering(intel_copy):
    held = {}
    read_sensors(intel_copy, held, 0.0)
    base = f"{intel_copy}/sys/class/hwmon"
    os.rename(f"{base}/hwmon5", f"{base}/hwmon10")  # dell_smm wandert, nvme bekommt seine alte Nummer
    os.rename(f"{base}/hwmon3", f"{base}/hwmon5")
    v = read_sensors(intel_copy, held, 1.0)
    assert [t.chip for t in v.temps].count("dell_smm") == 4 and any(t.chip == "nvme" for t in v.temps)


def test_only_known_slow_chips_are_held(intel_copy, monkeypatch):
    """Ein einmal langsames Lesen (Last, GC-Pause) macht keinen schnellen Chip für 5 s starr."""
    real = sensors._read_chip

    def slow(d, name):
        if name == "nvme":
            time.sleep(0.015)  # langsamer als die frühere 10-ms-Schwelle
        return real(d, name)
    monkeypatch.setattr(sensors, "_read_chip", slow)
    held = {}
    read_sensors(intel_copy, held, 0.0)
    hwmon(intel_copy, 3, "nvme", {"temp1_input": 66000})
    assert 66.0 in [t.value for t in read_sensors(intel_copy, held, 1.0).temps if t.chip == "nvme"]


def _dev_hwmon(root, n, dev, temp):
    """Wie im echten sysfs: /sys/class/hwmon/hwmonN ist ein Symlink auf das hwmon-Verzeichnis des Geräts."""
    rel = f"sys/devices/{dev}/hwmon/hwmon{n}"
    write(root, rel + "/name", "dell_smm")
    write(root, rel + "/temp1_input", temp)
    link = f"{root}/sys/class/hwmon/hwmon{n}"
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.lexists(link):
        os.unlink(link)
    os.symlink(f"{root}/{rel}", link)


def test_held_value_stays_with_its_device_when_same_chips_swap_numbers(tmp_path):
    """Zwei gleichnamige Chips tauschen ihre hwmon-Nummer (Aufwachen, Hot-Swap): kein Wert beim anderen Gerät."""
    root = str(tmp_path)
    _dev_hwmon(root, 1, "devA", 30000)
    _dev_hwmon(root, 2, "devB", 45000)
    held = {}
    read_sensors(root, held, 0.0)
    _dev_hwmon(root, 1, "devB", 46000)
    _dev_hwmon(root, 2, "devA", 31000)
    v = read_sensors(root, held, 2.0)
    assert {os.path.realpath(t.hwmon).split("/")[-3]: t.value for t in v.temps} == {"devA": 31.0, "devB": 46.0}


def test_chip_that_vanished_is_read_fresh_when_it_returns(tmp_path):
    root = str(tmp_path)
    _dev_hwmon(root, 1, "devA", 30000)
    held = {}
    read_sensors(root, held, 0.0)
    os.unlink(f"{root}/sys/class/hwmon/hwmon1")
    read_sensors(root, held, 1.0)
    _dev_hwmon(root, 1, "devA", 33000)
    assert [t.value for t in read_sensors(root, held, 2.0).temps] == [33.0]
