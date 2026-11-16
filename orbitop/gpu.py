# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Grafik über sysfs, /proc-fdinfo und optionale Werkzeuge (Task 7). Startet nie Prozesse."""
import os
import re
from dataclasses import dataclass

from . import sysfs
from .system import MAX_DT

_VENDOR_IDS = {"0x8086": "intel", "0x1002": "amd", "0x10de": "nvidia"}
_DRIVER_VENDORS = {"i915": "intel", "xe": "intel", "amdgpu": "amd", "radeon": "amd",
                   "nvidia": "nvidia", "nouveau": "nvidia"}
_ARM_DRIVERS = {"panfrost", "panthor", "lima", "msm", "v3d", "vc4", "asahi", "etnaviv", "powervr"}
_VENDOR_LABELS = {"intel": "Intel Graphics", "amd": "AMD Radeon", "nvidia": "NVIDIA"}
_CARD = re.compile(r"card\d+")
_PCI = re.compile(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]")
_SCLK_LINE = re.compile(r"(\d+(?:\.\d+)?)\s*mhz(\s*\*)?", re.IGNORECASE)
FDINFO_INTERVAL = 2.0


@dataclass(frozen=True)
class GpuInfo:
    card: str
    driver: str
    vendor: str
    name: str
    pci: str | None


@dataclass(frozen=True)
class GpuSample:
    busy: float | None = None
    busy_scope: str | None = None  # "global" | "own"
    freq_mhz: float | None = None
    freq_max_mhz: float | None = None
    power_w: float | None = None
    temp_c: float | None = None
    vram_used: int | None = None
    vram_total: int | None = None


def _card_dir(root: str, card: str) -> str:
    return sysfs.path(root, "/sys/class/drm/", card)


def discover_gpus(root: str) -> list[GpuInfo]:
    gpus = []
    for d in sysfs.glob(root, "/sys/class/drm/card*"):
        card = os.path.basename(d)
        if not _CARD.fullmatch(card):  # schließt Anschlüsse wie card0-DP-1 aus
            continue
        dev = d + "/device"
        driver = sysfs.link_name(dev + "/driver") or ""
        vendor = _VENDOR_IDS.get((sysfs.read_str(dev + "/vendor") or "").lower())
        vendor = vendor or _DRIVER_VENDORS.get(driver) or ("arm" if driver in _ARM_DRIVERS else "other")
        base = _VENDOR_LABELS.get(vendor) or driver or card
        name = sysfs.read_str(dev + "/product_name") or (f"{base} ({driver})" if driver else base)
        pci = os.path.basename(os.path.realpath(dev))
        gpus.append(GpuInfo(card, driver, vendor, name, pci if _PCI.fullmatch(pci) else None))
    return gpus


def _real_uid(status: str | None) -> int | None:
    for line in (status or "").splitlines():
        if line.startswith("Uid:"):
            try:
                return int(line.split()[1])  # erste Zahl = reale UID
            except (IndexError, ValueError):
                return None
    return None


def _parse_fdinfo(text: str) -> dict[str, str]:
    kv = {}
    for line in text.splitlines():
        k, sep, v = line.partition(":")
        if sep:
            kv[k.strip()] = v.strip()
    return kv


class FdinfoScanner:
    """Ein Scan für alle Treiber: DRM-fdinfo eigener Prozesse.

    Die fd-Verzeichnisse werden höchstens alle FULL_INTERVAL s komplett neu aufgelistet, dazwischen nur
    neue PIDs. Gelesen wird fdinfo ausschließlich für die gemerkten DRM-fds.
    shortcut: ein neuer DRM-fd eines schon bekannten Prozesses wird erst beim nächsten Voll-Scan
    gesehen (<= 10 s); PID-Wiederverwendung ebenso, upgrade nur bei Bedarf an engerer Erkennung.
    """
    FULL_INTERVAL = 10.0

    def __init__(self, root: str, uid: int):
        self._proc = sysfs.path(root, "/proc")
        self._uid = uid
        self._fds: dict[str, list[str]] = {}
        self._full_t: float | None = None
        self._t: float | None = None
        self._snap: dict[str, dict[str, dict[str, int]]] = {}
        self.pdev: dict[tuple[str, str], str] = {}  # (Treiber, client-id) -> drm-pdev

    def _scan_pid(self, pid: str) -> list[str]:
        base = f"{self._proc}/{pid}"
        if _real_uid(sysfs.read_str(base + "/status")) != self._uid:
            return []
        try:
            names = os.listdir(base + "/fd")
        except OSError:
            return []
        out = []
        for n in names:
            try:
                if os.readlink(f"{base}/fd/{n}").startswith("/dev/dri/"):
                    out.append(f"{base}/fdinfo/{n}")
            except OSError:
                pass
        return out

    def snapshot(self, now: float) -> dict[str, dict[str, dict[str, int]]]:
        """Treiber -> client-id -> Engine -> ns (jede client-id einmal)."""
        if now == self._t:
            return self._snap
        try:
            pids = [p for p in os.listdir(self._proc) if p.isdecimal()]
        except OSError:
            pids = []
        if self._full_t is None or not 0 <= now - self._full_t < self.FULL_INTERVAL:
            self._fds, self._full_t = {p: self._scan_pid(p) for p in pids}, now
        else:
            self._fds = {p: self._fds[p] if p in self._fds else self._scan_pid(p) for p in pids}
        snap: dict[str, dict[str, dict[str, int]]] = {}
        self.pdev = {}
        for paths in self._fds.values():
            for path in paths:
                text = sysfs.read_str(path)
                if not text:
                    continue
                kv = _parse_fdinfo(text)
                drv, cid = kv.get("drm-driver"), kv.get("drm-client-id")
                if drv is None or cid is None or cid in snap.get(drv, {}):
                    continue
                engines = {}
                for k, v in kv.items():
                    num, _, unit = v.partition(" ")
                    if (k.startswith("drm-engine-") and unit.strip() == "ns"
                            and num.isdecimal() and len(num) <= 20):
                        engines[k[len("drm-engine-"):].lower()] = int(num)
                snap.setdefault(drv, {})[cid] = engines
                if "drm-pdev" in kv:
                    self.pdev[(drv, cid)] = kv["drm-pdev"]
        self._t, self._snap = now, snap
        return snap


def _scaled(v: float | None, div: float) -> float | None:
    return None if v is None else v / div


def _hwmon(dev: str) -> tuple[float | None, float | None]:
    """(Leistung in W, Temperatur in °C) des ersten hwmon-Chips der Karte."""
    for h in sysfs.glob(dev, "/hwmon/hwmon*")[:1]:
        power = sysfs.read_float(h + "/power1_average")
        if power is None:
            power = sysfs.read_float(h + "/power1_input")
        return _scaled(power, 1e6), _scaled(sysfs.read_float(h + "/temp1_input"), 1000)
    return None, None


def _sclk(dev: str) -> tuple[float | None, float | None]:
    """(aktueller, maximaler Takt in MHz) aus pp_dpm_sclk; aktuell = Zeile mit '*'."""
    cur, top = None, None
    for line in (sysfs.read_str(dev + "/pp_dpm_sclk") or "").splitlines():
        m = _SCLK_LINE.search(line)
        if m:
            mhz = float(m.group(1))
            top = max(top or 0.0, mhz)
            if m.group(2):
                cur = mhz
    return cur, top


class GpuReader:
    def __init__(self, root: str, info: GpuInfo, tools=None, scanner: FdinfoScanner | None = None):
        self._root, self.info, self._tools = root, info, tools
        self._scanner = scanner or FdinfoScanner(root, os.getuid())
        self.name = info.name
        self._fd_t: float | None = None
        self._fd_prev: dict[str, dict[str, int]] | None = None
        self._fd_busy: float | None = None

    def read(self, now: float) -> GpuSample:
        drv = self.info.driver
        card = _card_dir(self._root, self.info.card)
        dev = card + "/device"
        if drv == "amdgpu":
            return self._amd(dev)
        if drv in ("i915", "xe"):
            return self._intel(card, dev, now)
        if drv == "nvidia":
            return self._nvidia()
        if drv in ("nouveau", "radeon"):
            return GpuSample(temp_c=_hwmon(dev)[1])
        return self._devfreq(dev, now)

    def _amd(self, dev: str) -> GpuSample:
        busy = sysfs.read_float(dev + "/gpu_busy_percent")
        power, temp = _hwmon(dev)
        cur, top = _sclk(dev)
        return GpuSample(busy, None if busy is None else "global", cur, top, power, temp,
                         sysfs.read_int(dev + "/mem_info_vram_used"),
                         sysfs.read_int(dev + "/mem_info_vram_total"))

    def _intel(self, card: str, dev: str, now: float) -> GpuSample:
        if self.info.driver == "xe":
            freq = sysfs.read_float(dev + "/tile0/gt0/freq0/act_freq")
            top = sysfs.read_float(dev + "/tile0/gt0/freq0/max_freq")
        else:
            freq = sysfs.read_float(card + "/gt_act_freq_mhz")
            top = sysfs.read_float(card + "/gt_max_freq_mhz")
        busy, scope, power = None, None, None
        t = self._tools.intel(self.info.card) if self._tools else None
        if t:
            busy, power = t.get("busy"), t.get("gpu_w")
            scope = None if busy is None else "global"
            if t.get("freq_mhz") is not None:
                freq = t["freq_mhz"]
        if busy is None:
            busy = self._own_busy(now)
            scope = None if busy is None else "own"
        return GpuSample(busy, scope, freq, top, power)

    def _nvidia(self) -> GpuSample:
        t = self._tools.nvidia(self.info.pci) if self._tools and self.info.pci else None
        if not t:
            return GpuSample()
        if t.get("name"):
            self.name = t["name"]
        busy = t.get("busy")
        # vram_used/vram_total liefert das Werkzeug in MiB (wie nvidia-smi)
        used, total = t.get("vram_used"), t.get("vram_total")
        return GpuSample(busy, None if busy is None else "global", t.get("freq_mhz"),
                         t.get("freq_max_mhz"), t.get("power_w"), t.get("temp_c"),
                         None if used is None else int(used * 1024 ** 2),
                         None if total is None else int(total * 1024 ** 2))

    def _devfreq(self, dev: str, now: float) -> GpuSample:
        mine = os.path.realpath(dev)
        dirs = sysfs.glob(dev, "/devfreq/*") + [
            d for d in sysfs.glob(self._root, "/sys/class/devfreq/*")
            if os.path.realpath(d + "/device") == mine]
        freq = top = None
        for d in dirs:
            freq = _scaled(sysfs.read_float(d + "/cur_freq"), 1e6)
            top = _scaled(sysfs.read_float(d + "/max_freq"), 1e6)
            if freq is not None:
                break
        busy = self._own_busy(now)
        return GpuSample(busy, None if busy is None else "own", freq, top)

    def _clients(self, now: float) -> dict[str, dict[str, int]]:
        """Eigene Clients dieser Karte: client-id -> Engine -> ns (Treiber und drm-pdev passend)."""
        snap = self._scanner.snapshot(now)
        pdev = self._scanner.pdev
        drv, pci = self.info.driver, self.info.pci
        return {cid: eng for cid, eng in snap.get(drv, {}).items()
                if not (pci and (drv, cid) in pdev and pdev[(drv, cid)] != pci)}

    def _own_busy(self, now: float) -> float | None:
        """Auslastung eigener DRM-Clients, höchstens alle FDINFO_INTERVAL s neu berechnet.

        Nur Clients, die in beiden Schnappschüssen vorkommen; Engine-Summe über Clients, Maximum über Engines.
        """
        if self._fd_t is not None and 0 <= now - self._fd_t < FDINFO_INTERVAL:
            return self._fd_busy
        cur = self._clients(now)
        prev, dt = self._fd_prev, None if self._fd_t is None else now - self._fd_t
        self._fd_prev, self._fd_t, self._fd_busy = cur, now, None
        if prev is None or dt is None or not 0 < dt <= MAX_DT:
            return None
        per_engine: dict[str, int] = {}
        for cid, engines in cur.items():
            for e, ns in engines.items():
                if cid in prev and e in prev[cid]:
                    if ns < prev[cid][e]:
                        return None  # Zähler gefallen
                    per_engine[e] = per_engine.get(e, 0) + ns - prev[cid][e]
        if per_engine:
            self._fd_busy = min(100.0, max(per_engine.values()) / (dt * 1e9) * 100)
        return self._fd_busy
