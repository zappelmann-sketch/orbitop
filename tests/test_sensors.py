# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import shutil

import pytest

from orbitop import sysfs
from orbitop.sensors import RaplReader, read_battery, read_sensors
from tests.roots import AMD, ARM, INTEL, VM


def _w(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(str(text))


def _hw(root, n, name, files):
    _w(root, f"sys/class/hwmon/hwmon{n}/name", name)
    for k, v in files.items():
        _w(root, f"sys/class/hwmon/hwmon{n}/{k}", v)


def _zone(root, z, energy, name="package-0", mx=262143328850):
    base = f"sys/class/powercap/{z}"
    _w(root, f"{base}/name", name)
    _w(root, f"{base}/max_energy_range_uj", mx)
    if energy is not None:
        _w(root, f"{base}/energy_uj", energy)


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
    _hw(intel_copy, 4, "pch_skylake", {"temp1_input": 150000, "temp2_input": -41000, "temp3_input": 149000})
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


def test_hwmon_power(intel_copy):
    _hw(intel_copy, 9, "foo", {"power1_input": 12_500_000, "power1_label": "PPT"})
    _hw(intel_copy, 10, "amdgpu", {"power1_average": 50_000_000})
    assert read_sensors(intel_copy).hwmon_power == [("PPT", pytest.approx(12.5))]


def test_rapl_watts(intel_copy):
    _zone(intel_copy, "intel-rapl:0", 1_000_000)
    r = RaplReader(intel_copy)
    assert r.read(0) is None
    _zone(intel_copy, "intel-rapl:0", 11_000_000)
    assert r.read(1.0)["package-0"] == pytest.approx(10.0)


def test_rapl_wraparound(intel_copy):
    _zone(intel_copy, "intel-rapl:0", 1000_000_000 - 1_000_000, mx=1000_000_000)
    r = RaplReader(intel_copy)
    r.read(0)
    _zone(intel_copy, "intel-rapl:0", 4_000_000, mx=1000_000_000)
    assert r.read(1.0)["package-0"] == pytest.approx(5.0)


def test_rapl_gap_rules(intel_copy):
    _zone(intel_copy, "intel-rapl:0", 5_000_000)
    r = RaplReader(intel_copy)
    r.read(0)
    _zone(intel_copy, "intel-rapl:0", 6_000_000)
    assert r.read(6.0) is None          # dt > 5
    _zone(intel_copy, "intel-rapl:0", 7_000_000)
    assert r.read(6.0) is None          # dt == 0
    _zone(intel_copy, "intel-rapl:0", 8_000_000)
    assert r.read(7.0)["package-0"] == pytest.approx(1.0)


def test_rapl_unreadable_is_none():
    assert RaplReader(VM).read(0) is None
    assert RaplReader(INTEL).read(0) is None


def test_rapl_unreadable_midrun_and_recovery(intel_copy):
    _zone(intel_copy, "intel-rapl:0", 1_000_000)
    _zone(intel_copy, "intel-rapl:0:0", 1_000_000, name="core")
    r = RaplReader(intel_copy)
    r.read(0)
    _zone(intel_copy, "intel-rapl:0", 2_000_000)
    os.remove(f"{intel_copy}/sys/class/powercap/intel-rapl:0:0/energy_uj")
    out = r.read(1.0)
    assert out == {"package-0": pytest.approx(1.0)}
    _zone(intel_copy, "intel-rapl:0:0", 9_000_000, name="core")
    assert "core" not in r.read(2.0)     # no baseline yet after the gap
    _zone(intel_copy, "intel-rapl:0:0", 10_000_000, name="core")
    assert r.read(3.0)["core"] == pytest.approx(1.0)


def test_rapl_counter_decrease_without_max(intel_copy):
    _zone(intel_copy, "intel-rapl:0", 5_000_000, mx="garbage")
    r = RaplReader(intel_copy)
    r.read(0)
    _zone(intel_copy, "intel-rapl:0", 1_000_000, mx="garbage")
    assert r.read(1.0) is None


def test_rapl_two_packages_and_psys_and_mmio(intel_copy):
    _zone(intel_copy, "intel-rapl:0", 0)
    _zone(intel_copy, "intel-rapl:1", 0, name="package-1")
    _zone(intel_copy, "intel-rapl:2", 0, name="psys")
    _zone(intel_copy, "intel-rapl:0:0", 0, name="core")
    _zone(intel_copy, "intel-rapl:1:0", 0, name="core")
    _zone(intel_copy, "intel-rapl-mmio:0", 0)
    r = RaplReader(intel_copy)
    r.read(0)
    for z, n in (("0", 1), ("1", 2), ("2", 4)):
        _zone(intel_copy, f"intel-rapl:{z}", n * 1_000_000, name=["package-0", "package-1", "psys"][int(z)])
    _zone(intel_copy, "intel-rapl:0:0", 1_000_000, name="core")
    _zone(intel_copy, "intel-rapl:1:0", 2_000_000, name="core")
    _zone(intel_copy, "intel-rapl-mmio:0", 99_000_000)
    out = r.read(1.0)
    assert out["package-0"] == pytest.approx(1.0) and out["package-1"] == pytest.approx(2.0)
    assert out["package"] == pytest.approx(3.0)
    assert out["core"] == pytest.approx(3.0) and out["psys"] == pytest.approx(4.0)


def test_rapl_single_package_has_no_package_key(intel_copy):
    _zone(intel_copy, "intel-rapl:0", 0)
    r = RaplReader(intel_copy)
    r.read(0)
    _zone(intel_copy, "intel-rapl:0", 1_000_000)
    assert "package" not in r.read(1.0)


def test_battery_none_without_battery():
    assert read_battery(AMD) is None and read_battery(VM) is None and read_battery(ARM) is None


def test_battery_intel_not_discharging():
    b = read_battery(INTEL)
    assert b.percent == 80 and b.on_ac is True and b.discharge_w is None


def test_battery_discharge(intel_copy):
    d = f"{intel_copy}/sys/class/power_supply"
    _w(d, "BAT0/status", "Discharging")
    _w(d, "AC/online", 0)
    b = read_battery(intel_copy)
    assert b.on_ac is False
    assert b.discharge_w == pytest.approx(1000 * 8133000 / 1e12)


def test_battery_power_now_preferred(intel_copy):
    d = f"{intel_copy}/sys/class/power_supply"
    _w(d, "BAT0/status", "Discharging")
    _w(d, "BAT0/power_now", 7_500_000)
    assert read_battery(intel_copy).discharge_w == pytest.approx(7.5)


def test_battery_current_without_voltage(intel_copy):
    d = f"{intel_copy}/sys/class/power_supply"
    _w(d, "BAT0/status", "Discharging")
    os.remove(f"{d}/BAT0/voltage_now")
    assert read_battery(intel_copy).discharge_w is None


def test_battery_skips_device_scope(intel_copy):
    d = f"{intel_copy}/sys/class/power_supply"
    _w(d, "AAmouse/type", "Battery")
    _w(d, "AAmouse/scope", "Device")
    _w(d, "AAmouse/capacity", 5)
    assert read_battery(intel_copy).percent == 80
