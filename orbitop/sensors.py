# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Temperaturen, Lüfter, RAPL-Leistung und Akku aus /sys. Alles wird bei jedem Aufruf neu gelesen."""
import os
import re
from dataclasses import dataclass

from orbitop import sysfs
from orbitop.system import MAX_DT

GPU_CHIPS = {"amdgpu", "radeon", "nouveau"}
TEMP_MIN, TEMP_MAX = -40.0, 150.0   # °C, Obergrenze exklusiv
_THERMAL_CPU = re.compile(r"x86_pkg_temp|cpu|soc")


@dataclass
class Temp:
    label: str
    value: float
    chip: str


@dataclass
class Fan:
    label: str
    rpm: float
    max_rpm: float | None


@dataclass
class SensorValues:
    cpu_temp: float | None
    temps: list[Temp]
    fans: list[Fan]
    hwmon_power: list[tuple[str, float]]


@dataclass
class Battery:
    percent: float
    on_ac: bool
    discharge_w: float | None


@dataclass
class _Chip:
    name: str
    dir: str
    temps: list[Temp]


def _index(p: str) -> str:
    return re.search(r"(\d+)_[a-z]+$", p).group(1)


def _chips(root: str) -> list[_Chip]:
    chips = []
    for d in sysfs.glob(root, "/sys/class/hwmon/hwmon*"):
        name = sysfs.read_str(d + "/name")
        if not name:
            continue
        temps = []
        for f in sysfs.glob(d, "/temp*_input"):
            v = sysfs.read_float(f)
            if v is None or not TEMP_MIN <= v / 1000 < TEMP_MAX:
                continue
            n = _index(f)
            label = sysfs.read_str(f"{d}/temp{n}_label") or f"{name} {n}"
            temps.append(Temp(label, v / 1000, name))
        chips.append(_Chip(name, d, temps))
    return chips


def _tmax(chips: list[_Chip], *names: str) -> float | None:
    vals = [t.value for c in chips if c.name in names for t in c.temps]
    return max(vals) if vals else None


def _cpu_temp(root: str, chips: list[_Chip]) -> tuple[float | None, set[str]]:
    """CPU-Temperatur und die Chips, die dafür verbraucht wurden."""
    pkg = [t.value for c in chips if c.name == "coretemp" for t in c.temps if t.label == "Package id 0"]
    v = pkg[0] if pkg else _tmax(chips, "coretemp")
    if v is not None:
        return v, {"coretemp"}
    for chip_name in ("k10temp", "zenpower"):
        ts = [t for c in chips if c.name == chip_name for t in c.temps]
        for want in ("Tctl", "Tdie", f"{chip_name} 1"):
            for t in ts:
                if t.label == want:
                    return t.value, {chip_name}
    v = _tmax(chips, "k8temp", "via_cputemp", "macsmc_hwmon")
    if v is not None:
        return v, {"k8temp", "via_cputemp", "macsmc_hwmon"}
    vals = []
    for z in sysfs.glob(root, "/sys/class/thermal/thermal_zone*"):
        typ = sysfs.read_str(z + "/type")
        t = sysfs.read_float(z + "/temp")
        if typ and _THERMAL_CPU.search(typ) and t is not None and TEMP_MIN <= t / 1000 < TEMP_MAX:
            vals.append(t / 1000)
    return (max(vals) if vals else None), set()


def _temp_rank(t: Temp) -> tuple[int, int]:
    if t.chip == "nvme":
        return (0, 0 if t.label.endswith("Composite") else 1)
    if t.chip == "drivetemp":
        return (1, 0)
    return (2, 0) if t.chip.startswith("pch_") else (3, 0)


def read_sensors(root: str) -> SensorValues:
    chips = _chips(root)
    cpu, used = _cpu_temp(root, chips)
    temps = [t for c in chips if c.name not in used | GPU_CHIPS for t in c.temps]
    temps.sort(key=_temp_rank)  # stabil: hwmon-Reihenfolge bleibt innerhalb der Gruppe
    fans, power = [], []
    for c in chips:
        for f in sysfs.glob(c.dir, "/fan*_input"):
            rpm = sysfs.read_float(f)
            if rpm is None or rpm < 0:
                continue
            n = _index(f)
            fans.append(Fan(sysfs.read_str(f"{c.dir}/fan{n}_label") or f"{c.name} {n}", rpm,
                            sysfs.read_float(f"{c.dir}/fan{n}_max")))
        if c.name in GPU_CHIPS:
            continue  # GPU-Leistung gehört zur GPU-Kachel
        seen = set()
        for f in sysfs.glob(c.dir, "/power*_input") + sysfs.glob(c.dir, "/power*_average"):
            n = _index(f)
            w = sysfs.read_float(f)
            if n in seen or w is None or w < 0:
                continue
            seen.add(n)
            power.append((sysfs.read_str(f"{c.dir}/power{n}_label") or f"{c.name} {n}", w / 1e6))
    return SensorValues(cpu, temps, fans, power)


class RaplReader:
    def __init__(self, root: str):
        self._root = root
        self._t: float | None = None
        self._prev: dict[str, int] = {}

    def read(self, now: float) -> dict[str, float] | None:
        """Domänenname → Watt. Der erste Aufruf liefert nur die Basis (None)."""
        dt = None if self._t is None else now - self._t
        cur: dict[str, int] = {}
        names: dict[str, str] = {}
        for z in sysfs.glob(self._root, "/sys/class/powercap/intel-rapl:*"):
            e = sysfs.read_int(z + "/energy_uj")
            name = sysfs.read_str(z + "/name")
            if e is not None and name:
                cur[z], names[z] = e, name
        prev, self._prev, self._t = self._prev, cur, now
        if dt is None or dt <= 0 or dt > MAX_DT:
            return None
        out: dict[str, float] = {}
        for z, e in cur.items():
            if z not in prev:
                continue
            delta = e - prev[z]
            if delta < 0:
                mx = sysfs.read_int(z + "/max_energy_range_uj")
                if not mx or mx < prev[z]:
                    continue
                delta += mx
            out[names[z]] = out.get(names[z], 0.0) + delta / dt / 1e6
        if not out:
            return None
        pkgs = [w for n, w in out.items() if re.fullmatch(r"package-\d+", n)]
        if len(pkgs) > 1:
            out["package"] = sum(pkgs)
        return out


def read_battery(root: str) -> Battery | None:
    supplies = sysfs.glob(root, "/sys/class/power_supply/*")
    on_ac = any(sysfs.read_str(s + "/type") == "Mains" and sysfs.read_int(s + "/online") == 1
                for s in supplies)
    for s in supplies:
        if sysfs.read_str(s + "/type") != "Battery" or sysfs.read_str(s + "/scope") == "Device":
            continue
        pct = sysfs.read_float(s + "/capacity")
        if pct is None:
            continue
        w = None
        if sysfs.read_str(s + "/status") == "Discharging":
            p = sysfs.read_float(s + "/power_now")
            if p:
                w = abs(p) / 1e6
            else:
                i, v = sysfs.read_float(s + "/current_now"), sysfs.read_float(s + "/voltage_now")
                if i is not None and v is not None:
                    w = abs(i) * v / 1e12
        return Battery(pct, on_ac, w)
    return None
