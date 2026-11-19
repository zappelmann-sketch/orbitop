# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Sampler: Leser, Raten, Ringpuffer (5 min) und die tick-Nachricht des Schnappschuss-Vertrags (Kacheln: tiles)."""
import json
import os
import threading
import time
from collections import deque

from orbitop import procs, sysfs, tiles
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
_SLOT = json.dumps("\0procs\0")  # ihr Platz im JSON; echte Texte enthalten nie NUL (tiles.clean, sysfs.printable)


def _crit(root: str) -> float | None:
    vals = []
    for d in sysfs.glob(root, "/sys/class/hwmon/hwmon*"):
        if sysfs.read_str(d + "/name") in CPU_CHIPS:
            vals += [v / 1000 for f in sysfs.glob(d, "/temp*_crit") if (v := sysfs.read_float(f))]
    return min((v for v in vals if 30 <= v < TEMP_MAX), default=None)


def _boottime() -> float:
    """Zeitbasis der Raten. Anders als monotonic zählt sie den Ruhezustand mit: nach dem Aufwachen ist dt groß und
    der Punkt eine Lücke (RAPL zählt im s2idle weiter). Die Takt-Kadenz des Workers bleibt monoton."""
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def _safe(fn, *args, default=None):
    """Ein Leser darf den Sampler nie zu Fall bringen: Fehler heißt keine Werte."""
    try:
        return fn(*args)
    except Exception:
        return default


class Sampler:
    def __init__(self, root="/", tools=None, statvfs=os.statvfs, clock=_boottime, uid=None):
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
        self._push("mem", mem and tiles.pct(mem.used, mem.total))
        self._push("swap", mem and tiles.pct(mem.swap_used, mem.swap_total))

    def _tick_gpus(self, now) -> None:
        for g in self._gpus:
            smp = _safe(g.read, now)
            self._s["gpus"].append((g, smp))
            if smp is not None:
                v = smp.busy if self._busy_gpu[g.info.card] else tiles.pct(smp.freq_mhz, smp.freq_max_mhz)
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
        self._push("power:" + s["pwr_name"][1], s["pwr"])  # je Quelle: ein Wechsel ist eine Lücke, keine Mischkurve

    def _tick_temps(self, now) -> None:
        sens = self._s["sens"]
        # (Puffer, Name der Kurve, Wert); der Puffer folgt der eindeutigen Beschriftung, nicht der Listenposition
        temps = [("temp:#cpu", ("key", CPU_KEY), sens.cpu_temp)] if sens and sens.cpu_temp is not None else []
        if sens:
            temps += [(f"temp:{lb}", ("key", CHIPSET_KEY) if t.chip.startswith("pch_") else ("label", lb), t.value)
                      for t, lb in zip(sens.temps, tiles.unique([t.label for t in sens.temps]))]
        self._s["temps"] = temps
        for buf, _, v in temps:
            self._push(buf, v)

    def _tick_fans(self, now) -> None:
        sens = self._s["sens"]
        self._s["fans"] = list(zip(tiles.unique([f.label for f in sens.fans]), sens.fans)) if sens else []
        for k, f in self._s["fans"]:
            self._push("fan:" + k, f.rpm)

    def _tick_net(self, now) -> None:
        nets = self._s["nets"] = _safe(self._net.read, now, default=[])
        self._push("rx", tiles.total(d.rx_bps for d in nets))
        self._push("tx", tiles.total(d.tx_bps for d in nets))

    def _tick_disks(self, now) -> None:
        disks = self._s["disks"] = _safe(self._disk.read, now, default=[])
        self._push("read", tiles.total(d.read_bps for d in disks))
        self._push("write", tiles.total(d.write_bps for d in disks))
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

    def tick_procs(self, shr: bool = False) -> None:
        """Im eigenen Thread (app.Worker). Fehler gehen an den Aufrufer, der jeden einmal meldet."""
        now = self._clock()
        raw = procs.scan(self._root, self._table.cmdlines, want_status=self._table.wants_status(now),
                        want_shr=shr)  # kann blockieren
        with self._procs_lock:
            self._table.update(raw, now)
            self._now_procs = now
            self._procs_n += 1

    def close(self) -> None:
        if self._own_tools:
            self._tools.stop()

    # ---- Kacheln (Bau in tiles.py) ----
    def _tiles(self) -> list[dict]:
        """Jede Kachel für sich: ein Fehler beim Bau einer Kachel lässt nur diese weg."""
        s, bufs = self._s, self._bufs
        out = [_safe(lambda: tiles.cpu_tile(s["cpu"], s["sens"], self._table.counts(), bufs))]
        gpu = [_safe(lambda g=g, smp=smp: tiles.gpu_tile(g.info, g.name, smp, self._busy_gpu[g.info.card], bufs))
               for g, smp in s.get("gpus", []) if smp]
        gpu = [t for t in gpu if t]
        for i, t in enumerate(gpu):  # Nummern zählen nur Grafikchips mit Kachel
            t["id"] = f"gpu{i}"
        out += gpu
        out += [_safe(lambda: tiles.mem_tile(s["mem"], bufs)),
                _safe(lambda: tiles.power_tile(s["pwr"], s["pwr_name"], s["rapl"], s["batt"],
                                               [smp for _, smp in s["gpus"]], bufs)),
                _safe(lambda: tiles.temp_tile(s["temps"], self._crit, bufs)),
                _safe(lambda: tiles.fan_tile(s["fans"], bufs)),
                _safe(lambda: tiles.net_tile(s["nets"], bufs)),
                _safe(lambda: tiles.disk_tile(s["disks"], bufs))]
        return [t for t in out if t]

    def _rows(self) -> list:
        return tiles.clean(_safe(self._table.rows, self._now_procs, default=[]))

    def snapshot(self, view: dict) -> dict:
        with self._procs_lock:  # _tiles (CPU-Kachel) und der Rest lesen die Prozesstabelle
            snap = self._snapshot(view)
            if snap["procs"] is _PROCS:
                snap["procs"] = self._rows()
            return snap

    def snapshot_json(self, view: dict, resend: bool = True) -> str:
        """Mit resend gleich encode(snapshot(view)), Byte für Byte. Die Prozessliste ändert sich nur je Prozess-Takt
        (2 s): ihre Zeilen werden dann einmal gebaut und kodiert und in den 1-s-Schnappschüssen dazwischen nur
        eingesetzt. Ohne resend steht im Prozess-Reiter statt einer schon gelieferten Liste "procs": null,
        "procs_same": true; die Seite behält dann ihre."""
        with self._procs_lock:
            snap = self._snapshot(view)
            if snap["procs"] is not _PROCS:
                return encode(snap)
            if not resend and self._rows_json[0] == self._procs_n:  # _rows_json entsteht nur mit einer gelieferten Liste
                snap["procs"], snap["procs_same"] = None, True
                return encode(snap)
            if self._rows_json[0] != self._procs_n:
                self._rows_json = (self._procs_n, encode(self._rows()))
            snap["procs"] = json.loads(_SLOT)
            return encode(snap).replace(_SLOT, self._rows_json[1], 1)

    def _snapshot(self, view: dict) -> dict:
        view = view if isinstance(view, dict) else {}
        tab, pid, start = view.get("tab"), view.get("pid"), view.get("start")
        valid = tab == "procs" and all(isinstance(x, int) and not isinstance(x, bool) for x in (pid, start))
        # genau einmal zuweisen, vor jedem Lesen der Tabelle: der Prozess-Thread liest selected ohne Sperre
        self._table.selected = (pid, start) if valid else None
        built = _safe(self._tiles, default=[]) if self._s else []
        kinds = {t["kind"] for t in built}
        hints = list(_safe(self._tools.hints, default=None) or [])
        # erst nach ein paar Takten: intel_gpu_top liefert pkg_w nicht sofort
        if self._rapl_noperm and self._n > 3 and self._s["pkg"] is None:
            hints.append("hint.rapl_noperm")
        procs_rows = _PROCS if tab == "procs" else None  # setzt snapshot oder snapshot_json ein
        detail = _safe(self._table.detail, pid, start, self._now_procs) if valid else None
        top = {"cpu": _safe(self._table.top_cpu, 3, default=[]), "mem": _safe(self._table.top_mem)}
        return tiles.clean({"type": "tick", "tiles": built, "missing": [k for k in KINDS if k not in kinds],
                            "hints": hints, "top": top, "procs": procs_rows, "detail": detail})
