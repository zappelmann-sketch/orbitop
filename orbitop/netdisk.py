# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Netzwerk- und Datenträgerwerte aus /proc und /sys (Raten aus Zählerdifferenz, Belegung der Dateisysteme)."""
import os
import re
from dataclasses import dataclass

from orbitop import sysfs
from orbitop.system import MAX_DT


@dataclass
class NetDev:
    name: str
    rx_bps: float | None
    tx_bps: float | None
    rx_total: int
    tx_total: int
    up: bool
    speed: int | None = None  # Mbit/s laut /sys/class/net/<if>/speed; None bei WLAN, gezogenem Kabel, unlesbar


@dataclass
class Disk:
    name: str
    model: str
    read_bps: float | None
    write_bps: float | None
    used: int | None  # used und size: Summen über die eingehängten Dateisysteme des Laufwerks, nicht dessen Rohkapazität
    size: int | None
    temp_c: float | None  # füllt der Sampler aus den Sensoren


_VIRTUAL_NET = re.compile(r"^(lo|docker|veth|br-|virbr|tun|tap|wg)")
_VIRTUAL_DISK = re.compile(r"^(loop|ram|zram|dm-|md|sr|fd)")


def _rate(prev: int | None, cur: int, dt: float | None) -> float | None:
    """Lücke (None) bei neuem Gerät, ungültigem dt oder kleiner gewordenem Zähler."""
    if prev is None or dt is None or not 0 < dt <= MAX_DT or cur < prev:
        return None
    return (cur - prev) / dt


def _physical(root: str, pattern: str, skip: re.Pattern) -> list[str]:
    return [
        os.path.basename(p)
        for p in sysfs.glob(root, pattern)
        if not skip.match(os.path.basename(p)) and os.path.exists(os.path.join(p, "device"))
    ]


def _parse_net_dev(text: str | None) -> dict[str, tuple[int, int]]:
    """Schnittstelle -> (rx_bytes, tx_bytes). Kopfzeilen und kaputte Zeilen entfallen."""
    out = {}
    for line in (text or "").splitlines():
        name, sep, rest = line.partition(":")
        f = rest.split()
        if not sep or len(f) < 9:
            continue
        try:
            out[name.strip()] = (int(f[0]), int(f[8]))
        except ValueError:
            continue
    return out


def _parse_diskstats(text: str | None) -> dict[str, tuple[int, int]]:
    """Laufwerk -> (gelesene, geschriebene Bytes). Kaputte Zeilen entfallen."""
    out = {}
    for line in (text or "").splitlines():
        f = line.split()
        if len(f) < 10:
            continue
        try:
            out[f[2]] = (int(f[5]) * 512, int(f[9]) * 512)
        except ValueError:
            continue
    return out


class NetReader:
    def __init__(self, root: str):
        self._root = root
        self._prev: dict[str, tuple[int, int]] = {}
        self._prev_now: float | None = None

    def read(self, now: float) -> list[NetDev]:
        cur = _parse_net_dev(sysfs.read_str(sysfs.path(self._root, "/proc/net/dev")))
        dt = None if self._prev_now is None else now - self._prev_now
        prev, self._prev_now = self._prev, now
        names = [n for n in _physical(self._root, "/sys/class/net/*", _VIRTUAL_NET) if n in cur]
        self._prev = {n: cur[n] for n in names}  # verschwundene Geräte beginnen später ohne Altwert
        devs = []
        for name in names:
            rx, tx = cur[name]
            p = prev.get(name, (None, None))
            state = sysfs.read_str(sysfs.path(self._root, "/sys/class/net/", name, "/operstate"))
            speed = sysfs.read_int(sysfs.path(self._root, "/sys/class/net/", name, "/speed"))
            devs.append(NetDev(name, _rate(p[0], rx, dt), _rate(p[1], tx, dt), rx, tx, state == "up",
                               speed if speed and speed > 0 else None))
        return devs


def _unescape_mount(s: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), s)


def _safe(name: str) -> bool:
    """Name aus /proc/mounts oder sysfs, der nur ein einzelnes Verzeichnis unter sys/block benennen darf."""
    return bool(name) and "/" not in name and "\0" not in name and name not in (".", "..")


_MAX_DM_DEPTH = 4


class DiskReader:
    def __init__(self, root: str, statvfs=os.statvfs):
        self._root = root
        self._statvfs = statvfs
        self._prev: dict[str, tuple[int, int]] = {}
        self._prev_now: float | None = None
        self._models: dict[str, str] = {}

    def read(self, now: float) -> list[Disk]:
        cur = _parse_diskstats(sysfs.read_str(sysfs.path(self._root, "/proc/diskstats")))
        dt = None if self._prev_now is None else now - self._prev_now
        prev, self._prev_now = self._prev, now
        names = [n for n in _physical(self._root, "/sys/block/*", _VIRTUAL_DISK) if n in cur]
        self._prev = {n: cur[n] for n in names}
        # Modell ist statisch; nur Geräte der letzten Runde behalten, damit ein neues Laufwerk unter altem Namen neu gelesen wird
        self._models = {n: self._models[n] if n in self._models else self._read_model(n) for n in names}
        usage = self._usage(set(names))
        disks = []
        for name in names:
            sectors = cur[name]
            p = prev.get(name, (None, None))
            used, size = usage.get(name, (None, None))
            disks.append(Disk(
                name, self._models[name],
                _rate(p[0], sectors[0], dt),
                _rate(p[1], sectors[1], dt),
                used, size, None,
            ))
        return disks

    def _read_model(self, name: str) -> str:
        return sysfs.read_str(sysfs.path(self._root, "/sys/block/", name, "/device/model")) or ""

    def _block(self, *parts: str) -> str:
        return sysfs.path(self._root, "/sys/block/" + "/".join(parts))

    def _resolve(self, dev: str, disks: set[str], depth: int = 0) -> str | None:
        """Gerätename (aus /dev) -> physisches Laufwerk. Folgt dm-Geräten über slaves/ (LUKS, LVM)."""
        if dev in disks:
            return dev
        dm = self._dm_node(dev)
        if dm is None:
            if not _safe(dev):
                return None
            return next((d for d in sorted(disks) if os.path.exists(self._block(d, dev))), None)
        if depth >= _MAX_DM_DEPTH:  # begrenzt auch Zyklen
            return None
        # shortcut: LVM über mehrere Platten zählt das ganze Dateisystem beim ersten Laufwerk unter slaves/; aufrüsten
        # (Belegung anteilig oder als eigene Zeile), sobald Rechner mit solchen Volumes unterstützt werden sollen.
        for slave in sysfs.glob(self._root, "/sys/block/" + dm + "/slaves/*"):
            found = self._resolve(os.path.basename(slave), disks, depth + 1)
            if found:
                return found
        return None

    def _dm_node(self, dev: str) -> str | None:
        """/dev/mapper/<name> oder dm-N -> dm-N, sofern es unter sys/block existiert."""
        if dev.startswith("mapper/"):
            name = dev[7:]
            if not _safe(name):
                return None
            for p in sysfs.glob(self._root, "/sys/block/dm-*/dm/name"):
                if sysfs.read_str(p) == name:
                    return os.path.basename(os.path.dirname(os.path.dirname(p)))
            return None
        if dev.startswith("dm-") and _safe(dev) and os.path.isdir(self._block(dev)):
            return dev
        return None

    def _usage(self, disks: set[str]) -> dict[str, tuple[int, int]]:
        """Laufwerk -> (belegt, Größe), Summe über seine eingehängten Dateisysteme."""
        # Dateisystem (dm-Knoten oder Gerätename) -> (Laufwerk, Einhängepunkte); Bind-Mounts bündeln sich hier
        filesystems: dict[str, tuple[str, list[str]]] = {}
        for line in (sysfs.read_str(sysfs.path(self._root, "/proc/mounts")) or "").splitlines():
            f = line.split()
            # fuse und fuse.*: jeder User kann mit fsname=/dev/… einhängen und so die Belegung eines Laufwerks vortäuschen
            if len(f) < 3 or not f[0].startswith("/dev/") or f[2] == "fuse" or f[2].startswith("fuse."):
                continue
            dev = _unescape_mount(f[0])[5:]
            disk = self._resolve(dev, disks)
            if disk is None:
                continue
            key = self._dm_node(dev) or dev
            filesystems.setdefault(key, (disk, []))[1].append(_unescape_mount(f[1]))
        out: dict[str, tuple[int, int]] = {}
        for disk, points in filesystems.values():
            for point in points:  # Bind-Mounts: der erste lesbare Einhängepunkt zählt
                # shortcut: statvfs auf fuseblk (ntfs-3g) blockiert bei hängendem FUSE-Dienst den Kachel-Thread und
                # damit den Schnappschuss; aufrüsten (Belegung außerhalb des Kachel-Threads holen) in Stufe 2.
                try:
                    st = self._statvfs(point)
                except OSError:
                    continue
                used, size = out.get(disk, (0, 0))
                out[disk] = (used + (st.f_blocks - st.f_bfree) * st.f_frsize, size + st.f_blocks * st.f_frsize)
                break
        return out
