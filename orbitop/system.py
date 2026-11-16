# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""CPU- und Speicherwerte aus /proc und /sys."""
from dataclasses import dataclass

from orbitop import sysfs

MAX_DT = 5.0


@dataclass
class CpuSample:
    total: float | None
    threads: list[float | None]
    freq_ghz: float | None
    model: str


@dataclass
class Mem:
    total: int
    available: int
    used: int
    swap_total: int
    swap_used: int


def _parse_stat(text: str | None) -> dict[str, tuple[int, int]]:
    """Zeilenname ("cpu", "cpu0", ...) -> (busy, gesamt) in Ticks. Kaputte Zeilen entfallen."""
    out = {}
    for line in (text or "").splitlines():
        f = line.split()
        if not f or not f[0].startswith("cpu"):
            continue
        try:
            v = [int(x) for x in f[1:9]]  # guest steckt schon in user/nice
        except ValueError:
            continue
        if len(v) < 5:
            continue
        idle = v[3] + v[4]
        total = sum(v)
        out[f[0]] = (total - idle, total)
    return out


def _percent(prev: tuple[int, int] | None, cur: tuple[int, int]) -> float | None:
    if prev is None:
        return None
    busy, total = cur[0] - prev[0], cur[1] - prev[1]
    if busy < 0 or total <= 0:
        return None
    return min(100.0, 100.0 * busy / total)


def _read_model(root: str) -> str:
    found = {}
    for line in (sysfs.read_str(sysfs.path(root, "/proc/cpuinfo")) or "").splitlines():
        key, sep, val = line.partition(":")
        if sep:
            found.setdefault(key.strip(), val.strip())
    for key in ("model name", "Model", "Hardware"):
        if found.get(key):
            return found[key]
    return ""


class CpuReader:
    def __init__(self, root: str):
        self._root = root
        self._model = _read_model(root)
        self._prev: dict[str, tuple[int, int]] = {}
        self._prev_now: float | None = None

    def read(self, now: float) -> CpuSample:
        cur = _parse_stat(sysfs.read_str(sysfs.path(self._root, "/proc/stat")))
        dt = None if self._prev_now is None else now - self._prev_now
        prev = self._prev if dt is not None and 0 < dt <= MAX_DT else {}
        self._prev, self._prev_now = cur, now
        names = [n for n in cur if n != "cpu"]
        return CpuSample(
            total=_percent(prev.get("cpu"), cur["cpu"]) if "cpu" in cur else None,
            threads=[_percent(prev.get(n), cur[n]) for n in names],
            freq_ghz=self._freq_ghz(),
            model=self._model,
        )

    def _freq_ghz(self) -> float | None:
        pattern = "/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"
        khz = [v for p in sysfs.glob(self._root, pattern) if (v := sysfs.read_float(p)) is not None]
        return sum(khz) / len(khz) / 1e6 if khz else None


def read_memory(root: str) -> Mem:
    kb = {}
    for line in (sysfs.read_str(sysfs.path(root, "/proc/meminfo")) or "").splitlines():
        key, _, rest = line.partition(":")
        try:
            kb[key] = int(rest.split()[0]) * 1024
        except (ValueError, IndexError):
            continue
    total = kb.get("MemTotal", 0)
    available = kb.get("MemAvailable", kb.get("MemFree", 0))
    swap_total = kb.get("SwapTotal", 0)
    return Mem(
        total=total,
        available=available,
        used=max(0, total - available),
        swap_total=swap_total,
        swap_used=max(0, swap_total - kb.get("SwapFree", swap_total)),
    )
