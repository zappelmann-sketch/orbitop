# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Sampler: Ringpuffer (5 min) und die tick-Nachricht des Schnappschuss-Vertrags."""
import json
import math
import os
import threading
import time
from collections import deque

from orbitop import procs, sysfs
from orbitop.app import encode
from orbitop.gpu import FdinfoScanner, GpuReader, discover_gpus
from orbitop.gpu_tools import GpuTools
from orbitop.procs import ProcTable
from orbitop.sensors import TEMP_MAX, RaplReader, Temp, read_battery, read_sensors
from orbitop.system import CpuReader, DiskReader, NetReader, read_memory

POINTS, THREAD_POINTS = 300, 60
DISK_CHIPS = {"nvme", "drivetemp"}
CPU_CHIPS = {"coretemp", "k10temp", "zenpower", "k8temp", "via_cputemp", "macsmc_hwmon"}
CPU_KEY, CHIPSET_KEY = "series.cpu_package", "series.chipset"
KINDS = ("cpu", "gpu", "mem", "power", "temp", "fan", "net", "disk")
_PROCS = object()  # Platzhalter für die Prozessliste im Schnappschuss, eingesetzt von snapshot / snapshot_json
_SLOT = json.dumps("\0procs\0")  # ihr Platz im JSON; echte Texte enthalten nie NUL (_clean, sysfs.printable)


def _num(v, u, of=None, p=None):
    n = {"v": v, "u": u}
    if of is not None:
        n["of"] = of
    if p:
        n["p"] = p
    return n


def _opt(v, u, of=None):
    """Zelle der Geräte-Tabelle: fehlender Wert ist null („–“), kein Num mit v=None."""
    return None if v is None else _num(v, u, of)


def _kv(k, v):
    return {"k": k, "v": v}


def _kl(label, v):
    return {"l": label, "v": v}


def _tk(key):
    return {"k": key}


def _tl(label):
    return {"l": label}


def _sum(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _pct(part, whole):
    return 100.0 * part / whole if part is not None and whole else None


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
    """Nur endliche Zahlen (höchstens 2 Nachkommastellen) oder None, nur druckbare Texte: JSON-sicher und klein."""
    if isinstance(o, float):
        return round(o, 2) if math.isfinite(o) else None
    if isinstance(o, str):
        return sysfs.printable(o)
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
        self._held: dict = {}  # langsame hwmon-Chips für read_sensors
        self._table = ProcTable(uid=uid, root=root)
        self._now_procs = clock()
        # Prozess-Takt (eigener Thread) und Schnappschuss teilen _table und _now_procs: update und jedes Lesen unter
        # dieser Sperre. procs.scan läuft ohne Sperre, liest aber nur _table.cmdlines (nur dieser Thread) und über
        # wants_status die Einträge und selected (einfache Attribut-Zugriffe).
        self._procs_lock = threading.Lock()
        self._procs_n, self._rows_json = 0, (-1, "")  # Prozess-Takte; JSON der Zeilen und sein Takt
        self._bufs: dict[str, deque] = {}
        self._pushed: set[str] = set()
        self._n = 0
        # Busy-Kurve oder Takt-Kurve wird je GPU einmal entschieden, damit die Kurve nie zwei Größen mischt
        self._busy_gpu = {g.info.card: self._has_busy(g.info, scanner, clock()) for g in self._gpus}
        self._s: dict = {}  # letzte Messwerte je Quelle

    def _has_busy(self, info, scanner, now) -> bool:
        # shortcut: ein beim Start ohne Busy-Quelle entschiedener GPU bleibt bei der Takt-Kurve; sauber wäre, beim ersten
        # Busy-Wert einmal auf Busy zu wechseln und diesen Puffer zurückzusetzen.
        if info.driver in ("i915", "xe", "nvidia"):
            return True  # Werkzeug oder DRM-fdinfo
        if info.driver == "amdgpu":
            return os.path.exists(sysfs.path(self._root, "/sys/class/drm/", info.card, "/device/gpu_busy_percent"))
        if info.driver in ("nouveau", "radeon"):
            return False
        return bool(_safe(scanner.snapshot, now, default={}).get(info.driver))  # devfreq-Treiber: nur mit fdinfo-Clients

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
        """Jeder Abschnitt läuft für sich: ein Fehler in einem lässt die anderen und den Puffer-Takt unberührt."""
        now = self._clock()
        self._s = {"cpu": None, "mem": None, "sens": None, "batt": None, "nets": [], "disks": [], "gpus": [],
                   "pkg": None, "rapl": {}, "pwr": None, "pwr_name": ("key", CPU_KEY), "temps": [], "fans": []}
        for section in (self._tick_sensors, self._tick_cpu, self._tick_mem, self._tick_gpus, self._tick_power,
                        self._tick_temps,
                        self._tick_fans, self._tick_net, self._tick_disks):
            _safe(section, now)
        self._end_tick()

    def _tick_sensors(self, now) -> None:
        self._s["sens"] = _safe(read_sensors, self._root, self._held, now)
        self._s["batt"] = _safe(read_battery, self._root)

    def _tick_cpu(self, now) -> None:
        cpu = self._s["cpu"] = _safe(self._cpu.read, now)
        self._push("cpu", cpu and cpu.total)
        for i, t in enumerate(cpu.threads if cpu else []):
            self._push(f"t{i}", t, THREAD_POINTS)

    def _tick_mem(self, now) -> None:
        mem = self._s["mem"] = _safe(read_memory, self._root)
        self._push("mem", mem and _pct(mem.used, mem.total))
        self._push("swap", mem and _pct(mem.swap_used, mem.swap_total))

    def _tick_gpus(self, now) -> None:
        for g in self._gpus:
            smp = _safe(g.read, now)
            self._s["gpus"].append((g, smp))
            if smp is not None:
                v = smp.busy if self._busy_gpu[g.info.card] else _pct(smp.freq_mhz, smp.freq_max_mhz)
                self._push("gpu:" + g.info.card, v)

    def _tick_power(self, now) -> None:
        s = self._s
        sens, batt = s["sens"], s["batt"]
        rapl = s["rapl"] = _safe(self._rapl.read, now) or {}
        pkg_tool = next((_safe(self._tools.intel, g.info.card) or {} for g, _ in s["gpus"]
                         if g.info.vendor == "intel"), {}).get("pkg_w")
        pkg = rapl.get("package", rapl.get("package-0"))
        pkg = s["pkg"] = pkg_tool if pkg is None else pkg
        # Quelle der Hauptleistung: (Wert, Name der Kurve); Reihenfolge ist Vertrag
        hw = sens.hwmon_power[0] if sens and sens.hwmon_power else (None, None)
        s["pwr"], s["pwr_name"] = next(
            ((v, n) for v, n in ((pkg, ("key", CPU_KEY)), (batt and batt.discharge_w, ("key", "kv.battery")),
                                 (hw[1], ("label", hw[0]))) if v is not None),
            (None, ("key", "kv.battery") if batt else ("key", CPU_KEY)))
        self._push("power", s["pwr"])

    def _tick_temps(self, now) -> None:
        sens = self._s["sens"]
        # (Puffer, Name der Kurve, Wert); der Puffer folgt der eindeutigen Beschriftung, nicht der Listenposition
        temps = [("temp:#cpu", ("key", CPU_KEY), sens.cpu_temp)] if sens and sens.cpu_temp is not None else []
        if sens:
            temps += [(f"temp:{lb}", ("key", CHIPSET_KEY) if t.chip.startswith("pch_") else ("label", lb), t.value)
                      for t, lb in zip(sens.temps, _unique([t.label for t in sens.temps]))]
        self._s["temps"] = temps
        for buf, _, v in temps:
            self._push(buf, v)

    def _tick_fans(self, now) -> None:
        sens = self._s["sens"]
        self._s["fans"] = list(zip(_unique([f.label for f in sens.fans]), sens.fans)) if sens else []
        for k, f in self._s["fans"]:
            self._push("fan:" + k, f.rpm)

    def _tick_net(self, now) -> None:
        nets = self._s["nets"] = _safe(self._net.read, now, default=[])
        self._push("rx", _sum(d.rx_bps for d in nets))
        self._push("tx", _sum(d.tx_bps for d in nets))

    def _tick_disks(self, now) -> None:
        disks = self._s["disks"] = _safe(self._disk.read, now, default=[])
        self._push("read", _sum(d.read_bps for d in disks))
        self._push("write", _sum(d.write_bps for d in disks))
        self._disk_temps(disks, self._s["sens"])

    def _disk_temps(self, disks, sens) -> None:
        """Disk.temp_c: Chip nvme/drivetemp, dessen device-Pfad zum Laufwerk gehört (Werte des selben Ticks aus read_sensors).

        Sonst bei genau einem NVMe-Laufwerk und einem nvme-Chip dessen Temperatur.
        """
        chips: dict[str, Temp] = {}  # Chip-Verzeichnis -> erste Temperatur (temp1)
        for t in sens.temps if sens else []:
            if t.chip in DISK_CHIPS:
                chips.setdefault(t.hwmon, t)
        nvme = [t for t in chips.values() if t.chip == "nvme"]
        nvme_disks = [d for d in disks if d.name.startswith("nvme")]
        by_device = {os.path.realpath(h + "/device"): t for h, t in chips.items()}
        for d in disks:
            real = os.path.realpath(sysfs.path(self._root, "/sys/block/", d.name, "/device"))
            t = by_device.get(real)
            if t is None and len(nvme_disks) == 1 and len(nvme) == 1 and d is nvme_disks[0]:
                t = nvme[0]
            d.temp_c = t.value if t else None

    def tick_procs(self) -> None:
        """Im eigenen Thread (app.Worker). Fehler gehen an den Aufrufer, der jeden einmal meldet."""
        now = self._clock()
        raw = procs.scan(self._root, self._table.cmdlines, want_status=self._table.wants_status(now))  # kann blockieren
        with self._procs_lock:
            self._table.update(raw, now)
            self._now_procs = now
            self._procs_n += 1

    def close(self) -> None:
        if self._own_tools:
            self._tools.stop()

    # ---- Kacheln ----
    def _plot(self, unit, *specs):
        """specs: ((\"key\"|\"label\", Name), Puffer, gefüllt). Alle Kurven einer Kachel teilen eine Skala."""
        vals = [list(self._bufs.get(buf, ())) for _, buf, _ in specs]
        wmax = max((v for s in vals for v in s if v is not None), default=0.0)
        top = 100.0 if unit == "%" else max(100.0, 1.1 * wmax) if unit == "°C" else _nice(wmax)
        return [{name[0]: name[1], "fill": f, "max": top, "u": unit, "values": v}
                for (name, _, f), v in zip(specs, vals)]

    @staticmethod
    def _tile(kind, id, name, main, aside, seg, series, kv, warn, devices=None, threads=None):
        """warn: seg hat eine absolute Obergrenze, Bernstein ab 80 % ist dann eine echte Warnung."""
        return {"id": id, "kind": kind, "name": name, "main": main, "aside": aside, "seg": seg,
                "series": series, "threads": threads, "kv": kv, "devices": devices, "warn": warn}

    def _cpu_tile(self):
        c = self._s["cpu"]
        if c is None:
            return None
        series = self._plot("%", (("key", "series.used"), "cpu", True))
        temp = self._s["sens"].cpu_temp if self._s["sens"] else None
        kv = [_kv("kv.temperature", _num(temp, "°C"))] if temp is not None else []
        n_proc, n_thr = self._table.counts()
        if n_proc:
            kv.append(_kv("kv.procs_threads", _num(n_proc, "", n_thr)))
        return self._tile("cpu", "cpu", c.model, _num(c.total, "%"), _num(c.freq_ghz, "GHz"),
                          _seg(c.total, 100), series, kv, True,
                          threads=[list(self._bufs.get(f"t{i}", ())) for i in range(len(c.threads))])

    def _gpu_tile(self, g, smp):
        card = "gpu:" + g.info.card
        if not any(v is not None for v in (smp.busy, smp.freq_mhz, smp.freq_max_mhz, smp.power_w,
                                            smp.temp_c, smp.vram_used, smp.vram_total)):
            return None
        busy = self._busy_gpu[g.info.card]
        series = self._plot("%", (("key", "series.used" if busy else "kv.clock"), card, True))
        main = smp.busy if busy else _pct(smp.freq_mhz, smp.freq_max_mhz)
        kv = [_kv("kv.clock", _num(smp.freq_mhz, "MHz"))] if smp.freq_mhz is not None else []
        if smp.power_w is not None:
            kv.append(_kv("kv.power", _num(smp.power_w, "W")))
        if smp.temp_c is not None:
            kv.append(_kv("kv.temperature", _num(smp.temp_c, "°C")))
        if smp.vram_used is not None:
            kv.append(_kv("kv.memory", _num(smp.vram_used, "B", smp.vram_total)))
        elif g.info.vendor == "intel":
            kv.append(_kv("kv.memory", _tk("kv.shared_with_ram")))
        return self._tile("gpu", "gpu", g.name, _num(main, "%"), _num(smp.freq_mhz, "MHz", smp.freq_max_mhz),
                          _seg(main, 100), series, kv, True)

    def _mem_tile(self):
        m = self._s["mem"]
        if m is None or not m.total:
            return None
        specs = [(("key", "series.used"), "mem", True)] + (
            [(("key", "series.swap"), "swap", False)] if m.swap_total else [])
        series = self._plot("%", *specs)
        used = _pct(m.used, m.total)
        kv = [_kv("kv.available", _num(m.available, "B"))]
        if m.swap_total:
            kv.append(_kv("kv.swap", _num(m.swap_used, "B", m.swap_total)))
        return self._tile("mem", "mem", "", _num(used, "%"), _num(m.used, "B", m.total), _seg(used, 100), series, kv,
                          True)

    def _power_tile(self):
        s = self._s
        batt, gpu_w = s["batt"], _sum(smp.power_w for _, smp in s["gpus"] if smp)
        if s["pwr"] is None and batt is None and gpu_w is None:
            return None
        name = s["pwr_name"]
        series = self._plot("W", (name, "power", True))
        kv = []
        core = s["rapl"].get("core")
        if core is not None:
            kv.append(_kv("kv.cpu_cores", _num(core, "W")))
        if gpu_w is not None:
            kv.append(_kv("kv.gpu", _num(gpu_w, "W")))
        if batt is not None:
            state = _tk("kv.on_ac") if batt.on_ac else _num(batt.discharge_w, "W") if batt.discharge_w is not None else None
            kv.append(_kv("kv.battery", [_num(batt.percent, "%")] + ([state] if state else [])))
        return self._tile("power", "power", "", _num(s["pwr"], "W"), _tk(name[1]) if name[0] == "key" else _tl(name[1]),
                          _seg(s["pwr"], series[0]["max"]), series, kv, False)

    def _temp_tile(self):
        temps = self._s["temps"]
        if not temps:
            return None
        series = self._plot("°C", *[(name, buf, i == 0) for i, (buf, name, _) in enumerate(temps[:3])])
        hottest = max(v for _, _, v in temps)
        return self._tile("temp", "temp", "", _num(hottest, "°C"), _tk("tile.temp_aside"),
                          _seg(hottest, self._crit or 100), series,
                          [(_kv if name[0] == "key" else _kl)(name[1], _num(v, "°C")) for _, name, v in temps[3:]],
                          True)

    def _fan_tile(self):
        fans = self._s["fans"]
        if not fans:
            return None
        series = self._plot("rpm", *[(("label", k), "fan:" + k, i == 0) for i, (k, _) in enumerate(fans[:3])])
        first = [v for v in self._bufs["fan:" + fans[0][0]] if v is not None]
        kv = [_kv("kv.fan_min", _num(min(first), "rpm")), _kv("kv.fan_max", _num(max(first), "rpm"))]
        return self._tile("fan", "fan", "", _num(fans[0][1].rpm, "rpm"), _tl(fans[0][0]),
                          _seg(fans[0][1].rpm, fans[0][1].max_rpm or series[0]["max"]), series, kv,
                          bool(fans[0][1].max_rpm))

    def _net_tile(self):
        devs = self._s["nets"]
        if not devs:
            return None
        series = self._plot("B/s", (("key", "series.rx"), "rx", True), (("key", "series.tx"), "tx", False))
        rx, tx = _sum(d.rx_bps for d in devs), _sum(d.tx_bps for d in devs)
        up = [d.name for d in devs if d.up]
        kv = [_kv("kv.interface", _tl(up[0]))] if len(up) == 1 else []
        kv.append(_kv("kv.since_boot", [_num(sum(d.rx_total for d in devs), "B", p="↓"),
                                        _num(sum(d.tx_total for d in devs), "B", p="↑")]))
        # Absolut nur, wenn jedes aktive Gerät seine Link-Geschwindigkeit kennt (Mbit/s -> B/s), sonst relativ zur Skala
        link = sum(d.speed for d in devs if d.up) * 125000 if up and all(d.speed for d in devs if d.up) else None
        return self._tile("net", "net", up[0] if len(up) == 1 else "", _num(rx, "B/s", p="↓"),
                          _num(tx, "B/s", p="↑"), _seg(rx, link or series[0]["max"]), series, kv, link is not None,
                          {"cols": ["series.rx", "series.tx"],
                           "rows": [{"name": d.name, "values": [_opt(d.rx_bps, "B/s"), _opt(d.tx_bps, "B/s")]}
                                    for d in devs]})

    def _disk_tile(self):
        disks = self._s["disks"]
        if not disks:
            return None
        series = self._plot("B/s", (("key", "series.read"), "read", True), (("key", "series.write"), "write", False))
        rd, wr = _sum(d.read_bps for d in disks), _sum(d.write_bps for d in disks)
        kv = [_kv("kv.write", _num(wr, "B/s"))]
        used, size = _sum(d.used for d in disks), _sum(d.size for d in disks)
        if used is not None:  # Summe über die eingehängten Dateisysteme, nicht die Rohkapazität
            kv.append(_kv("kv.used", _num(used, "B", size)))
        temp = max((d.temp_c for d in disks if d.temp_c is not None), default=None)
        if temp is not None:
            kv.append(_kv("kv.temperature", _num(temp, "°C")))
        one = disks[0] if len(disks) == 1 else None
        return self._tile("disk", "disk", (one.model or one.name) if one else "", _num(rd, "B/s"),
                          _tk("series.read"), _seg(rd, series[0]["max"]), series, kv, False,
                          {"cols": ["series.read", "series.write", "kv.used", "kv.temperature"],
                           "rows": [{"name": d.name, "values": [_opt(d.read_bps, "B/s"), _opt(d.write_bps, "B/s"),
                                                                _opt(d.used, "B", d.size), _opt(d.temp_c, "°C")]}
                                    for d in disks]})

    def _tiles(self) -> list[dict]:
        out = [_safe(self._cpu_tile)]
        gpu = [_safe(self._gpu_tile, g, smp) for g, smp in self._s.get("gpus", []) if smp]
        gpu = [t for t in gpu if t]
        for i, t in enumerate(gpu):  # Nummern zählen nur Grafikchips mit Kachel
            t["id"] = f"gpu{i}"
        out += gpu
        out += [_safe(getattr(self, f"_{k}_tile")) for k in ("mem", "power", "temp", "fan", "net", "disk")]
        return [t for t in out if t]

    def _rows(self) -> list:
        return _clean(_safe(self._table.rows, self._now_procs, default=[]))

    def snapshot(self, view: dict) -> dict:
        with self._procs_lock:  # _tiles (CPU-Kachel) und der Rest lesen die Prozesstabelle
            snap = self._snapshot(view)
            if snap["procs"] is _PROCS:
                snap["procs"] = self._rows()
            return snap

    def snapshot_json(self, view: dict) -> str:
        """Gleich encode(snapshot(view)), Byte für Byte. Die Prozessliste ändert sich nur je Prozess-Takt (2 s): ihre
        Zeilen werden dann einmal gebaut und kodiert und in den 1-s-Schnappschüssen dazwischen nur eingesetzt."""
        with self._procs_lock:
            snap = self._snapshot(view)
            if snap["procs"] is not _PROCS:
                return encode(snap)
            if self._rows_json[0] != self._procs_n:
                self._rows_json = (self._procs_n, encode(self._rows()))
            snap["procs"] = json.loads(_SLOT)
            return encode(snap).replace(_SLOT, self._rows_json[1], 1)

    def _snapshot(self, view: dict) -> dict:
        view = view if isinstance(view, dict) else {}
        tiles = _safe(self._tiles, default=[]) if self._s else []
        kinds = {t["kind"] for t in tiles}
        hints = list(_safe(self._tools.hints, default=None) or [])
        # erst nach ein paar Takten: intel_gpu_top liefert pkg_w nicht sofort
        if self._rapl_noperm and self._n > 3 and self._s["pkg"] is None:
            hints.append("hint.rapl_noperm")
        procs_rows = detail = self._table.selected = None
        if view.get("tab") == "procs":
            procs_rows = _PROCS  # setzt snapshot oder snapshot_json ein
            pid, start = view.get("pid"), view.get("start")
            if all(isinstance(x, int) and not isinstance(x, bool) for x in (pid, start)):
                detail = _safe(self._table.detail, pid, start, self._now_procs)
                self._table.selected = (pid, start)  # der nächste Prozess-Takt liest dessen status
        top = {"cpu": _safe(self._table.top_cpu, 3, default=[]), "mem": _safe(self._table.top_mem)}
        return _clean({"type": "tick", "tiles": tiles, "missing": [k for k in KINDS if k not in kinds],
                       "hints": hints, "top": top, "procs": procs_rows, "detail": detail})
