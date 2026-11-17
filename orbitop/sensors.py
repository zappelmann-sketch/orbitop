# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Temperaturen, Lüfter, RAPL-Leistung und Akku aus /sys. Alles wird bei jedem Aufruf neu gelesen, außer langsamen
hwmon-Chips (read_sensors mit held)."""
import os
import re
from dataclasses import dataclass

from orbitop import sysfs
from orbitop.system import MAX_DT

GPU_CHIPS = {"amdgpu", "radeon", "nouveau"}
TEMP_MIN, TEMP_MAX = -40.0, 150.0   # °C, Obergrenze exklusiv
SLOW_CHIPS = {"dell_smm"}  # jeder Lesezugriff ist ein BIOS-SMM-Aufruf (gemessen: 3,7 ms CPU, 58 ms Wartezeit)
SLOW_EVERY_S = 5.0  # langsame Chips höchstens so oft lesen
_THERMAL_CPU = re.compile(r"x86_pkg_temp|cpu|soc")


@dataclass
class Temp:
    label: str
    value: float
    chip: str
    hwmon: str = ""  # Verzeichnis des hwmon-Chips


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
    temps: list[Temp]
    first: Temp | None  # temp1, unabhängig vom Label
    fans: list[Fan]
    power: list[tuple[str, float]]


def _files(d: str, kind: str, suffix: str):
    """(Index, Pfad) für <kind><n>_<suffix>; Dateien ohne Zahl werden übersprungen."""
    for f in sysfs.glob(d, f"/{kind}*_{suffix}"):
        m = re.fullmatch(rf"{kind}(\d+)_{suffix}", os.path.basename(f))
        if m:
            yield m.group(1), f


def _temp_ok(c: float) -> bool:
    return TEMP_MIN <= c < TEMP_MAX


def _read_chip(d: str, name: str) -> _Chip:
    temps, first = [], None
    for n, f in _files(d, "temp", "input"):
        v = sysfs.read_float(f)
        if v is None or not _temp_ok(v / 1000):
            continue
        label = sysfs.read_str(f"{d}/temp{n}_label") or f"{name} {n}"
        temps.append(Temp(label, v / 1000, name, d))
        if n == "1":
            first = temps[-1]
    fans, power = [], []
    for n, f in _files(d, "fan", "input"):
        rpm = sysfs.read_float(f)
        if rpm is None or rpm < 0:
            continue
        fans.append(Fan(sysfs.read_str(f"{d}/fan{n}_label") or f"{name} {n}", rpm, sysfs.read_float(f"{d}/fan{n}_max")))
    if name not in GPU_CHIPS:  # GPU-Leistung gehört zur GPU-Kachel
        seen = set()
        for n, f in [*_files(d, "power", "input"), *_files(d, "power", "average")]:
            w = sysfs.read_float(f)
            if n in seen or w is None or w < 0:
                continue
            seen.add(n)
            power.append((sysfs.read_str(f"{d}/power{n}_label") or f"{name} {n}", w / 1e6))
    return _Chip(name, temps, first, fans, power)


def _chips(root: str, held: dict, now: float) -> list[_Chip]:
    """Alle Chips; SLOW_CHIPS aus held (Verzeichnis -> (Zeit, Gerätepfad, Chip)), solange ihr Wert jünger als
    SLOW_EVERY_S ist und das Verzeichnis noch auf dasselbe Gerät zeigt (nach dem Aufwachen ggf. ein anderes)."""
    chips, keep = [], {}
    for d in sysfs.glob(root, "/sys/class/hwmon/hwmon*"):
        name = sysfs.read_str(d + "/name")
        if not name:
            continue
        real, old = os.path.realpath(d), held.get(d)  # der Klassen-Symlink zeigt in den Gerätebaum: kein SMM-Aufruf
        if old and old[1] == real and old[2].name == name and 0 <= now - old[0] < SLOW_EVERY_S:
            keep[d] = old
            chips.append(old[2])
            continue
        chip = _read_chip(d, name)
        if name in SLOW_CHIPS:
            keep[d] = (now, real, chip)
        chips.append(chip)
    held.clear()
    held.update(keep)  # verschwundene Verzeichnisse fallen heraus
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
        cs = [c for c in chips if c.name == chip_name]
        ts = [t for c in cs for t in c.temps]
        for want in ("Tctl", "Tdie"):
            for t in ts:
                if t.label == want:
                    return t.value, {chip_name}
        for c in cs:
            if c.first:
                return c.first.value, {chip_name}
    v = _tmax(chips, "k8temp", "via_cputemp", "macsmc_hwmon")
    if v is not None:
        return v, {"k8temp", "via_cputemp", "macsmc_hwmon"}
    vals = []
    for z in sysfs.glob(root, "/sys/class/thermal/thermal_zone*"):
        typ = sysfs.read_str(z + "/type")
        t = sysfs.read_float(z + "/temp")
        if typ and _THERMAL_CPU.search(typ) and t is not None and _temp_ok(t / 1000):
            vals.append(t / 1000)
    return (max(vals) if vals else None), set()


def _temp_rank(t: Temp, primary: set[int]) -> int:
    """Gruppen: erster Sensor je nvme-Chip, drivetemp, pch_*, alles übrige (auch die weiteren nvme-Sensoren)."""
    if t.chip == "nvme" and id(t) in primary:
        return 0
    if t.chip == "drivetemp":
        return 1
    return 2 if t.chip.startswith("pch_") else 3


def read_sensors(root: str, held: dict | None = None, now: float = 0.0) -> SensorValues:
    """held behält der Aufrufer über die Takte: Darin bleiben langsame Chips (SLOW_CHIPS) bis zu SLOW_EVERY_S stehen.
    Der Verlauf zeigt dann so lange denselben Wert."""
    chips = _chips(root, {} if held is None else held, now)
    cpu, used = _cpu_temp(root, chips)
    temps = [t for c in chips if c.name not in used | GPU_CHIPS for t in c.temps]
    primary = {id(next((t for t in c.temps if t.label.endswith("Composite")), c.temps[0]))
               for c in chips if c.name == "nvme" and c.temps}
    temps.sort(key=lambda t: _temp_rank(t, primary))  # stabil: hwmon-Reihenfolge bleibt innerhalb der Gruppe
    return SensorValues(cpu, temps, [f for c in chips for f in c.fans], [w for c in chips for w in c.power])


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
                delta += mx or 0
                # shortcut: a reset landing in the first half of the range after a wrap is
                # indistinguishable from a wrap; upgrade if real wraps get dropped
                if not mx or delta >= mx / 2:  # Zähler-Reset statt Überlauf
                    continue
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
