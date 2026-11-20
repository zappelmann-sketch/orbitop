# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""read_sensors: CPU-Temperatur, Temperaturliste und Lüfter aus hwmon und thermal_zone."""
import os
import shutil

import pytest

from orbitop import sysfs
from orbitop.sensors import read_sensors
from tests.roots import AMD, ARM, INTEL, VM
from tests.sensors_helpers import hwmon, write


def test_cpu_temp_intel_package():
    assert read_sensors(INTEL).cpu_temp == pytest.approx(98.0)


def test_cpu_temp_amd_tctl():
    v = read_sensors(AMD)
    assert v.cpu_temp == pytest.approx(
        sysfs.read_float(f"{AMD}/sys/class/hwmon/hwmon0/temp1_input") / 1000)


def test_cpu_temp_arm_thermal_zone():
    assert read_sensors(ARM).cpu_temp == pytest.approx(52.0)


def test_vm_has_nothing():
    v = read_sensors(VM)
    assert v.cpu_temp is None and v.temps == [] and v.fans == [] and v.hwmon_power == []


def test_temps_order_nvme_composite_first():
    t = read_sensors(INTEL).temps
    assert t[0].label.endswith("Composite") and t[0].chip == "nvme"
    assert [x.chip for x in t if x.chip == "nvme"] == ["nvme"] * 3
    assert all(x.chip != "coretemp" for x in t)


def test_unlabeled_sensor_named_chip_n():
    assert "dell_smm 1" in [t.label for t in read_sensors(INTEL).temps]


def test_gpu_chips_not_in_temps_or_power():
    v = read_sensors(AMD)
    assert all(t.chip != "amdgpu" for t in v.temps)
    assert v.hwmon_power == []


def test_fans_amd_three():
    assert len(read_sensors(AMD).fans) == 3


def test_fan_max():
    f = read_sensors(INTEL).fans
    assert len(f) == 1 and f[0].max_rpm is not None


def test_out_of_range_temps_dropped(intel_copy):
    hwmon(intel_copy, 4, "pch_skylake", {"temp1_input": 150000, "temp2_input": -41000, "temp3_input": 149000})
    pch = [t for t in read_sensors(intel_copy).temps if t.chip == "pch_skylake"]
    assert [t.value for t in pch] == [149.0]


def test_hwmon_renumbered_no_crash(intel_copy):
    os.rename(f"{intel_copy}/sys/class/hwmon/hwmon3", f"{intel_copy}/sys/class/hwmon/hwmon9")
    shutil.rmtree(f"{intel_copy}/sys/class/hwmon/hwmon7")
    after = read_sensors(intel_copy)
    assert any(t.chip == "nvme" for t in after.temps)


def test_unreadable_temp_file(intel_copy):
    os.remove(f"{intel_copy}/sys/class/hwmon/hwmon7/temp1_input")
    os.remove(f"{intel_copy}/sys/class/hwmon/hwmon7/temp2_input")
    os.mkdir(f"{intel_copy}/sys/class/hwmon/hwmon7/temp2_input")
    v = read_sensors(intel_copy)
    assert v.cpu_temp is not None


def test_coretemp_without_package_label_uses_max(intel_copy):
    os.remove(f"{intel_copy}/sys/class/hwmon/hwmon7/temp1_label")
    assert read_sensors(intel_copy).cpu_temp == pytest.approx(98.0)


def _zone_t(root, n, typ, temp):
    write(root, f"sys/class/thermal/thermal_zone{n}/type", typ)
    write(root, f"sys/class/thermal/thermal_zone{n}/temp", temp)


def test_coretemp_package_not_max(intel_copy):
    hwmon(intel_copy, 7, "coretemp", {"temp1_input": 60000, "temp1_label": "Package id 0",
                                    "temp2_input": 99000, "temp2_label": "Core 0"})
    assert read_sensors(intel_copy).cpu_temp == pytest.approx(60.0)


def _cpu(tmp_path, chip, files):
    root = str(tmp_path)
    hwmon(root, 0, chip, files)
    return read_sensors(root)


@pytest.mark.parametrize("chip", ["k10temp", "zenpower"])
def test_amd_cpu_labels(tmp_path, chip):
    v = _cpu(tmp_path, chip, {"temp1_input": 40000, "temp1_label": "Tdie", "temp2_input": 70000,
                              "temp2_label": "Tctl", "temp3_input": 90000, "temp3_label": "Tccd1"})
    assert v.cpu_temp == pytest.approx(70.0) and v.temps == []


@pytest.mark.parametrize("chip", ["k10temp", "zenpower"])
def test_amd_tdie_without_tctl(tmp_path, chip):
    v = _cpu(tmp_path, chip, {"temp1_input": 40000, "temp1_label": "Tccd1", "temp2_input": 55000,
                              "temp2_label": "Tdie"})
    assert v.cpu_temp == pytest.approx(55.0)


@pytest.mark.parametrize("label_files", [{}, {"temp1_label": "Whatever"}])
def test_amd_temp1_fallback(tmp_path, label_files):
    v = _cpu(tmp_path, "k10temp", {"temp1_input": 41000, "temp2_input": 80000,
                                   "temp2_label": "Tccd1", **label_files})
    assert v.cpu_temp == pytest.approx(41.0)


@pytest.mark.parametrize("chip", ["k8temp", "via_cputemp", "macsmc_hwmon"])
def test_max_chips(tmp_path, chip):
    v = _cpu(tmp_path, chip, {"temp1_input": 41000, "temp2_input": 66000})
    assert v.cpu_temp == pytest.approx(66.0) and v.temps == []


def test_thermal_zone_type_match_not_max(tmp_path):
    root = str(tmp_path)
    _zone_t(root, 0, "gpu-thermal", 90000)
    _zone_t(root, 1, "cpu-thermal", 50000)
    _zone_t(root, 2, "x86_pkg_temp", 55000)
    _zone_t(root, 3, "acpitz", 99000)
    assert read_sensors(root).cpu_temp == pytest.approx(55.0)


def test_temps_composite_not_first_index(tmp_path):
    root = str(tmp_path)
    hwmon(root, 0, "nvme", {"temp1_input": 30000, "temp1_label": "Sensor 1", "temp2_input": 31000,
                          "temp2_label": "Sensor 2", "temp3_input": 40000, "temp3_label": "Composite"})
    assert [t.label for t in read_sensors(root).temps] == ["Composite", "Sensor 1", "Sensor 2"]


def test_temps_chip_order_amd():
    chips = [t.chip for t in read_sensors(AMD).temps]
    assert "k10temp" not in chips
    firsts = list(dict.fromkeys(chips))
    assert firsts[:2] == ["nvme", "drivetemp"]
    assert firsts[2:] and "amdgpu" not in firsts


def test_temps_chip_order_pch_before_drivetemp(tmp_path):
    root = str(tmp_path)
    hwmon(root, 0, "zzz", {"temp1_input": 41000})
    hwmon(root, 1, "pch_cannonlake", {"temp1_input": 40000})
    hwmon(root, 2, "drivetemp", {"temp1_input": 42000})
    hwmon(root, 3, "nvme", {"temp1_input": 43000})
    assert [t.chip for t in read_sensors(root).temps] == ["nvme", "drivetemp", "pch_cannonlake", "zzz"]


def test_renumbered_coretemp_gone_falls_back_to_zone(intel_copy):
    shutil.rmtree(f"{intel_copy}/sys/class/hwmon/hwmon7")
    shutil.rmtree(f"{intel_copy}/sys/class/thermal", ignore_errors=True)
    _zone_t(intel_copy, 0, "x86_pkg_temp", 61000)
    _zone_t(intel_copy, 1, "gpu-thermal", 99000)
    assert read_sensors(intel_copy).cpu_temp == pytest.approx(61.0)


def test_stray_hwmon_files_ignored(intel_copy):
    d = f"{intel_copy}/sys/class/hwmon/hwmon5"
    for n in ("temp_input", "fan_input", "power_input", "tempX_input"):
        write(d, n, 1000)
    v = read_sensors(intel_copy)
    assert len(v.fans) == 1 and v.hwmon_power == []


def test_temps_only_first_nvme_sensor_ranks_first(tmp_path):
    root = str(tmp_path)
    hwmon(root, 0, "nvme", {"temp1_input": 40000, "temp1_label": "Composite", "temp2_input": 41000,
                          "temp2_label": "Sensor 1"})
    hwmon(root, 1, "drivetemp", {"temp1_input": 42000})
    hwmon(root, 2, "pch_cannonlake", {"temp1_input": 43000})
    hwmon(root, 3, "zzz", {"temp1_input": 44000})
    assert [(t.chip, t.label) for t in read_sensors(root).temps] == [
        ("nvme", "Composite"), ("drivetemp", "drivetemp 1"), ("pch_cannonlake", "pch_cannonlake 1"),
        ("nvme", "Sensor 1"), ("zzz", "zzz 1")]
