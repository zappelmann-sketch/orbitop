# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Sampler: Ringpuffer (5 min) und die tick-Nachricht des Schnappschuss-Vertrags."""
import math
import os
import time
from collections import deque

from orbitop import procs, sysfs
from orbitop.gpu import FdinfoScanner, GpuReader, discover_gpus
from orbitop.gpu_tools import GpuTools
from orbitop.procs import ProcTable
from orbitop.sensors import TEMP_MAX, TEMP_MIN, RaplReader, read_battery, read_sensors
from orbitop.system import CpuReader, DiskReader, NetReader, read_memory

POINTS, THREAD_POINTS = 300, 60
DISK_CHIPS = {"nvme", "drivetemp"}
CPU_CHIPS = {"coretemp", "k10temp", "zenpower", "k8temp", "via_cputemp", "macsmc_hwmon"}
CHIP_REFRESH = 60.0  # s: Zuordnung Laufwerk <-> hwmon-Chip neu suchen (USB-Hotplug)
KINDS = ("cpu", "gpu", "mem", "power", "temp", "fan", "net", "disk")


def _num(v, u):
    return {"v": v, "u": u}


def _kv(k, v):
    return {"k": k, "v": v}


def _sum(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _pct(part, whole):
    return 100.0 * part / whole if whole else None


def _nice(v: float) -> float:
    """1, 2 oder 5 x 10^n, mindestens 1."""
    if v <= 1:
        return 1.0
    e = 10 ** math.floor(math.log10(v))
    return float(next(m * e for m in (1, 2, 5, 10) if v <= m * e))


def _seg(v, ref) -> float:
    if v is None or not ref or ref <= 0:
        return 0.0
    return min(100.0, max(0.0, 100.0 * v / ref))


def _unique(labels):
    seen: dict[str, int] = {}
    out = []
    for lb in labels:
        seen[lb] = seen.get(lb, 0) + 1
        out.append(lb if seen[lb] == 1 else f"{lb} {seen[lb]}")
    return out


def _clean(o):
    """Nur endliche Zahlen (höchstens 2 Nachkommastellen) oder None: JSON-sicher und klein."""
    if isinstance(o, float):
        return round(o, 2) if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def _crit(root: str) -> float | None:
    vals = []
    for d in sysfs.glob(root, "/sys/class/hwmon/hwmon*"):
        if sysfs.read_str(d + "/name") in CPU_CHIPS:
            vals += [v / 1000 for f in sysfs.glob(d, "/temp*_crit") if (v := sysfs.read_float(f))]
    return min((v for v in vals if 30 <= v < TEMP_MAX), default=None)


def _safe(fn, *args, default=None):
    """Ein Leser darf den Sampler nie zu Fall bringen: Fehler heißt keine Werte."""
    try:
        return fn(*args)
    except Exception:
        return default


class Sampler:
    def __init__(self, root="/", tools=None, statvfs=os.statvfs, clock=time.monotonic, uid=None):
        uid = os.getuid() if uid is None else uid
        self._root, self._clock = root, clock
        self._cpu, self._net = CpuReader(root), NetReader(root)
        self._disk, self._rapl = DiskReader(root, statvfs), RaplReader(root)
        scanner = FdinfoScanner(root, uid)
        gpus = discover_gpus(root)
        self._own_tools = tools is None
        self._tools = GpuTools(gpus) if tools is None else tools
        self._gpus = [GpuReader(root, g, self._tools, scanner) for g in gpus]
        zones = sysfs.glob(root, "/sys/class/powercap/intel-rapl:*")
        self._rapl_noperm = bool(zones) and all(sysfs.read_int(z + "/energy_uj") is None for z in zones)
        self._crit = _crit(root)
        self._table = ProcTable(uid=uid, root=root)
        self._now_procs = clock()
        self._bufs: dict[str, deque] = {}
        self._pushed: set[str] = set()
        self._n = 0
        self._chips: list[tuple[str, str, str]] | None = None  # (Verzeichnis, Name, realpath(device))
        self._chips_t = 0.0
        self._s: dict = {}  # letzte Messwerte je Quelle

    # ---- Puffer ----
    def _push(self, key: str, v, size=POINTS) -> None:
        buf = self._bufs.get(key)
        if buf is None:  # neue Kurve: bisherige Takte sind Lücken, damit alle gleich lang bleiben
            buf = self._bufs[key] = deque([None] * min(self._n, size), maxlen=size)
        buf.append(v)
        self._pushed.add(key)

    def _end_tick(self) -> None:
        for key in [k for k in self._bufs if k not in self._pushed]:
            self._bufs[key].append(None)
            if not any(v is not None for v in self._bufs[key]):  # verschwundene Quelle
                del self._bufs[key]
        self._pushed.clear()
        self._n += 1

    # ---- Tick ----
    def tick_system(self) -> None:
        now = self._clock()
        s = self._s = {}
        cpu = s["cpu"] = _safe(self._cpu.read, now)
        mem = s["mem"] = _safe(read_memory, self._root)
        sens = s["sens"] = _safe(read_sensors, self._root)
        rapl = _safe(self._rapl.read, now) or {}
        batt = s["batt"] = _safe(read_battery, self._root)
        s["nets"] = _safe(self._net.read, now, default=[])
        s["disks"] = _safe(self._disk.read, now, default=[])
        self._push("cpu", cpu and cpu.total)
        for i, t in enumerate(cpu.threads if cpu else []):
            self._push(f"t{i}", t, THREAD_POINTS)
        self._push("mem", mem and _pct(mem.used, mem.total))
        self._push("swap", mem and _pct(mem.swap_used, mem.swap_total))
        s["gpus"] = []
        pkg_tool = None
        for g in self._gpus:
            smp = _safe(g.read, now)
            s["gpus"].append((g, smp))
            if smp is not None:
                v = smp.busy if smp.busy is not None else (
                    _pct(smp.freq_mhz, smp.freq_max_mhz) if smp.freq_mhz is not None else None)
                self._push("gpu:" + g.info.card, v)
            if g.info.vendor == "intel" and pkg_tool is None:
                pkg_tool = (_safe(self._tools.intel, g.info.card) or {}).get("pkg_w")
        pkg = rapl.get("package", rapl.get("package-0"))
        pkg = pkg_tool if pkg is None else pkg
        s["pkg"], s["rapl"] = pkg, rapl
        main = next((v for v in (pkg, batt and batt.discharge_w,
                                 sens.hwmon_power[0][1] if sens and sens.hwmon_power else None)
                     if v is not None), None)
        s["pwr"] = main
        self._push("power", main)
        temps = [("series.cpu_package", sens.cpu_temp)] if sens and sens.cpu_temp is not None else []
        if sens:
            temps += [("series.chipset" if t.chip.startswith("pch_") else t.label, t.value)
                      for t in sens.temps]
        s["temps"] = list(zip(_unique([k for k, _ in temps]), [v for _, v in temps]))
        s["fans"] = list(zip(_unique([f.label for f in sens.fans]), sens.fans)) if sens else []
        for k, v in s["temps"]:
            self._push("temp:" + k, v)
        for k, f in s["fans"]:
            self._push("fan:" + k, f.rpm)
        self._push("rx", _sum(d.rx_bps for d in s["nets"]))
        self._push("tx", _sum(d.tx_bps for d in s["nets"]))
        self._push("read", _sum(d.read_bps for d in s["disks"]))
        self._push("write", _sum(d.write_bps for d in s["disks"]))
        self._disk_temps(s["disks"], now)
        self._end_tick()

    def _disk_temps(self, disks, now: float) -> None:
        """Disk.temp_c: Chip nvme/drivetemp mit passendem device-Pfad, sonst bei genau einem NVMe-Laufwerk dessen Chip."""
        if self._chips is None or now - self._chips_t >= CHIP_REFRESH:
            self._chips_t = now
            self._chips = [
                (d, n, os.path.realpath(d + "/device"))
                for d in sysfs.glob(self._root, "/sys/class/hwmon/hwmon*")
                if (n := sysfs.read_str(d + "/name")) in DISK_CHIPS]
        nvme_chips = [c for c in self._chips if c[1] == "nvme"]
        nvme_disks = [d for d in disks if d.name.startswith("nvme")]
        for d in disks:
            real = os.path.realpath(sysfs.path(self._root, "/sys/block/", d.name, "/device"))
            chip = next((c for c in self._chips if c[2] == real), None)
            if chip is None and len(nvme_disks) == 1 and len(nvme_chips) == 1 and d is nvme_disks[0]:
                chip = nvme_chips[0]
            t = chip and sysfs.read_float(chip[0] + "/temp1_input")
            d.temp_c = t / 1000 if t is not None and TEMP_MIN <= t / 1000 < TEMP_MAX else None

    def tick_procs(self) -> None:
        now = self._now_procs = self._clock()
        try:
            self._table.update(procs.scan(self._root, self._table.cmdlines), now)
        except Exception:
            pass

    def close(self) -> None:
        if self._own_tools:
            self._tools.stop()

    # ---- Kacheln ----
    def _plot(self, unit, *specs):
        """specs: (Schlüssel, Puffer, gefüllt). Alle Kurven einer Kachel teilen eine Skala."""
        vals = [list(self._bufs.get(buf, ())) for _, buf, _ in specs]
        wmax = max((v for s in vals for v in s if v is not None), default=0.0)
        top = 100.0 if unit == "%" else max(100.0, 1.1 * wmax) if unit == "°C" else _nice(wmax)
        return [{"key": k, "fill": f, "max": top, "u": unit, "values": v}
                for (k, _, f), v in zip(specs, vals)], wmax

    @staticmethod
    def _tile(kind, id, name, main, aside, seg, series, kv, devices=None, threads=None):
        return {"id": id, "kind": kind, "name": name, "main": main, "aside": aside, "seg": seg,
                "series": series, "threads": threads, "kv": kv, "devices": devices}

    def _cpu_tile(self):
        c = self._s["cpu"]
        if c is None:
            return None
        series, _ = self._plot("%", ("total", "cpu", True))
        temp = self._s["sens"].cpu_temp if self._s["sens"] else None
        kv = [_kv("kv.temperature", _num(temp, "°C"))] if temp is not None else []
        n_proc, n_thr = self._table.counts()
        if n_proc:
            kv.append(_kv("kv.procs_threads", f"{n_proc} / {n_thr}"))
        return self._tile("cpu", "cpu", c.model, _num(c.total, "%"), _num(c.freq_ghz, "GHz"),
                          _seg(c.total, 100), series, kv,
                          threads=[list(self._bufs.get(f"t{i}", ())) for i in range(len(c.threads))])

    def _gpu_tile(self, g, smp):
        card = "gpu:" + g.info.card
        if not any(v is not None for v in (smp.busy, smp.freq_mhz, smp.freq_max_mhz, smp.power_w,
                                            smp.temp_c, smp.vram_used, smp.vram_total)):
            return None
        by_freq = smp.busy is None and smp.freq_mhz is not None and smp.freq_max_mhz
        series, _ = self._plot("%", ("kv.clock" if by_freq else "busy", card, True))
        main = smp.busy if smp.busy is not None else _pct(smp.freq_mhz, smp.freq_max_mhz) if by_freq else None
        kv = [_kv("kv.clock", _num(smp.freq_mhz, "MHz"))] if smp.freq_mhz is not None else []
        if smp.power_w is not None:
            kv.append(_kv("kv.power", _num(smp.power_w, "W")))
        if smp.temp_c is not None:
            kv.append(_kv("kv.temperature", _num(smp.temp_c, "°C")))
        if smp.vram_used is not None:
            kv.append(_kv("kv.memory", _num(smp.vram_used, "B")))
        elif g.info.vendor == "intel":
            kv.append(_kv("kv.memory", "kv.shared_with_ram"))
        return self._tile("gpu", "gpu", g.name, _num(main, "%"), _num(smp.freq_mhz, "MHz"),
                          _seg(main, 100), series, kv)

    def _mem_tile(self):
        m = self._s["mem"]
        if m is None or not m.total:
            return None
        specs = [("series.used", "mem", True)] + ([("series.swap", "swap", False)] if m.swap_total else [])
        series, _ = self._plot("%", *specs)
        used = _pct(m.used, m.total)
        kv = [_kv("kv.memory", _num(m.total, "B")), _kv("kv.available", _num(m.available, "B"))]
        if m.swap_total:
            kv.append(_kv("kv.swap", _num(m.swap_used, "B")))
        return self._tile("mem", "mem", "", _num(used, "%"), _num(m.used, "B"), _seg(used, 100), series, kv)

    def _power_tile(self):
        s = self._s
        batt, gpu_w = s["batt"], _sum(smp.power_w for _, smp in s["gpus"] if smp)
        if s["pwr"] is None and batt is None and gpu_w is None:
            return None
        series, wmax = self._plot("W", ("series.cpu_package", "power", True))
        kv = []
        core = s["rapl"].get("core")
        if core is not None:
            kv.append(_kv("kv.cpu_cores", _num(core, "W")))
        if gpu_w is not None:
            kv.append(_kv("kv.gpu", _num(gpu_w, "W")))
        if batt is not None:
            kv.append(_kv("kv.battery_ac" if batt.on_ac else "kv.battery_discharging", _num(batt.percent, "%")))
        return self._tile("power", "power", "", _num(s["pwr"], "W"), _num(s["pkg"], "W"),
                          _seg(s["pwr"], wmax), series, kv)

    def _temp_tile(self):
        temps = self._s["temps"]
        if not temps:
            return None
        series, _ = self._plot("°C", *[(k, "temp:" + k, i == 0) for i, (k, _) in enumerate(temps[:3])])
        hottest = max(v for _, v in temps)
        ref = self._crit if temps[0][0] == "series.cpu_package" else None
        return self._tile("temp", "temp", "", _num(temps[0][1], "°C"), _num(hottest, "°C"),
                          _seg(temps[0][1], ref or 100), series,
                          [_kv(k, _num(v, "°C")) for k, v in temps[3:]])

    def _fan_tile(self):
        fans = self._s["fans"]
        if not fans:
            return None
        series, wmax = self._plot("rpm", *[(k, "fan:" + k, i == 0) for i, (k, _) in enumerate(fans[:3])])
        first = [v for v in self._bufs["fan:" + fans[0][0]] if v is not None]
        kv = [_kv("kv.fan_min", _num(min(first), "rpm")), _kv("kv.fan_max", _num(max(first), "rpm"))]
        return self._tile("fan", "fan", fans[0][0], _num(fans[0][1].rpm, "rpm"), None,
                          _seg(fans[0][1].rpm, fans[0][1].max_rpm or wmax), series, kv)

    def _net_tile(self):
        devs = self._s["nets"]
        if not devs:
            return None
        series, wmax = self._plot("B/s", ("series.rx", "rx", True), ("series.tx", "tx", False))
        rx, tx = _sum(d.rx_bps for d in devs), _sum(d.tx_bps for d in devs)
        up = [d.name for d in devs if d.up]
        kv = [_kv("kv.interface", up[0])] if len(up) == 1 else []
        kv += [_kv("kv.since_boot", _num(sum(d.rx_total for d in devs), "B")),
               _kv("kv.since_boot", _num(sum(d.tx_total for d in devs), "B"))]
        return self._tile("net", "net", up[0] if len(up) == 1 else "", _num(rx, "B/s"), _num(tx, "B/s"),
                          _seg(rx, wmax), series, kv,
                          [{"name": d.name, "values": [_num(d.rx_bps, "B/s"), _num(d.tx_bps, "B/s")]} for d in devs])

    def _disk_tile(self):
        disks = self._s["disks"]
        if not disks:
            return None
        series, wmax = self._plot("B/s", ("series.read", "read", True), ("series.write", "write", False))
        rd, wr = _sum(d.read_bps for d in disks), _sum(d.write_bps for d in disks)
        kv = [_kv("kv.write", _num(wr, "B/s"))]
        used, size = _sum(d.used for d in disks), _sum(d.size for d in disks)
        if used is not None:
            kv += [_kv("kv.mounted_used", _num(used, "B")), _kv("kv.mounted_size", _num(size, "B"))]
        temp = max((d.temp_c for d in disks if d.temp_c is not None), default=None)
        if temp is not None:
            kv.append(_kv("kv.temperature", _num(temp, "°C")))
        one = disks[0] if len(disks) == 1 else None
        return self._tile("disk", "disk", (one.model or one.name) if one else "", _num(rd, "B/s"), None,
                          _seg(rd, wmax), series, kv,
                          [{"name": d.name, "values": [_num(d.read_bps, "B/s"), _num(d.write_bps, "B/s"),
                                                       _num(d.used, "B"), _num(d.size, "B"),
                                                       _num(d.temp_c, "°C")]} for d in disks])

    def _tiles(self) -> list[dict]:
        out = [_safe(self._cpu_tile)]
        gpu = [_safe(self._gpu_tile, g, smp) for g, smp in self._s.get("gpus", []) if smp]
        gpu = [t for t in gpu if t]
        for i, t in enumerate(gpu):  # Nummern zählen nur Grafikchips mit Kachel
            t["id"] = f"gpu{i}"
        out += gpu
        out += [_safe(getattr(self, f"_{k}_tile")) for k in ("mem", "power", "temp", "fan", "net", "disk")]
        return [t for t in out if t]

    def snapshot(self, view: dict) -> dict:
        tiles = _safe(self._tiles, default=[]) if self._s else []
        kinds = {t["kind"] for t in tiles}
        hints = _safe(self._tools.hints, default=[]) or []
        hints = list(hints)
        if self._rapl_noperm and self._s and self._s["pkg"] is None:
            hints.append("hint.rapl_noperm")
        procs_rows = detail = None
        if view.get("tab") == "procs":
            procs_rows = _safe(self._table.rows, self._now_procs, default=[])
            pid, start = view.get("pid"), view.get("start")
            if all(isinstance(x, int) and not isinstance(x, bool) for x in (pid, start)):
                detail = _safe(self._table.detail, pid, start, self._now_procs)
        top = {"cpu": _safe(self._table.top_cpu, 3, default=[]), "mem": _safe(self._table.top_mem)}
        return _clean({"type": "tick", "tiles": tiles, "missing": [k for k in KINDS if k not in kinds],
                       "hints": hints, "top": top, "procs": procs_rows, "detail": detail})
