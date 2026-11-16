# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Hilfsprogramme intel_gpu_top und nvidia-smi: langlebige Kindprozesse, begrenzt geparst."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterable, Iterator

MAX_BUF = 1024 * 1024  # größtes Objekt/Zeile, das gepuffert wird
RESTART_S = 30.0
_CARD = re.compile(r"card[0-9]+")
_NV_FIELDS = ("name", "busy", "vram_used", "vram_total", "temp_c", "power_w", "freq_mhz",
              "freq_max_mhz", "fan_pct")
_NV_QUERY = ("pci.bus_id,name,utilization.gpu,memory.used,memory.total,temperature.gpu,"
             "power.draw,clocks.gr,clocks.max.gr,fan.speed")


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_intel(obj: dict) -> dict:
    engines = obj.get("engines")
    busy = [b for e in (engines.values() if isinstance(engines, dict) else [])
            if isinstance(e, dict) and (b := _num(e.get("busy"))) is not None]
    power, freq = obj.get("power") or {}, obj.get("frequency") or {}
    return {"busy": max(busy, default=None), "freq_mhz": _num(freq.get("actual")),
            "gpu_w": _num(power.get("GPU")), "pkg_w": _num(power.get("Package"))}


def split_json_stream(chunks: Iterable[str]) -> Iterator[dict]:
    """Zerlegt `[ {..}, {..}` über die Klammertiefe; kaputte oder zu große Objekte entfallen."""
    buf: list[str] = []
    size = depth = 0
    in_str = esc = False
    for chunk in chunks:
        for ch in chunk:
            if depth == 0:
                if ch == "{":
                    depth, buf, size, in_str, esc = 1, ["{"], 1, False, False
                continue
            buf.append(ch)
            size += 1
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads("".join(buf))
                    except ValueError:
                        continue
                    if isinstance(obj, dict):
                        yield obj
                    continue
            if size > MAX_BUF:
                depth, buf, size = 0, [], 0


def split_lines(chunks: Iterable[str]) -> Iterator[str]:
    buf = ""
    for chunk in chunks:
        buf += chunk
        *lines, buf = buf.split("\n")
        yield from (ln for ln in lines if ln.strip())
        buf = buf[-MAX_BUF:]


def parse_nvidia_line(line: str) -> dict:
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != 10:
        raise ValueError("unerwartete Spaltenzahl")
    d = {"pci": parts[0].lower()[-12:], "name": parts[1]}
    d.update({k: _num(v) for k, v in zip(_NV_FIELDS[1:], parts[2:])})  # [N/A] -> None
    return d


class ToolReader:
    """Startet ein Werkzeug, liest seine Ausgabe in einem Daemon-Thread, startet es höchstens alle 30 s neu."""

    def __init__(self, cmd: list[str], parse: Callable[[dict], dict], split=split_json_stream,
                 key: str | None = None):
        self._cmd, self._parse, self._split, self._key = cmd, parse, split, key
        self._lock = threading.Lock()
        self._values: dict = {}
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._started = 0.0
        self._stopped = False
        self._ever = False  # je einen Wert geliefert
        self.failed = False

    def start(self) -> None:
        with self._lock:
            if self._stopped:
                return
            try:
                proc = subprocess.Popen(self._cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, errors="replace")
            except OSError:
                self._started = time.monotonic()
                self.failed = not self._ever
                return
            self._proc, self._started = proc, time.monotonic()
            self._thread = threading.Thread(target=self._run, args=(proc,), daemon=True)
            self._thread.start()

    def _run(self, proc) -> None:
        try:
            for item in self._split(iter(lambda: proc.stdout.readline(65536), "")):  # readline: kehrt pro Zeile zurück
                try:
                    val = self._parse(item)
                except Exception:  # defekte Zeile/Objekt überspringen
                    continue
                with self._lock:
                    self._values[val.get(self._key) if self._key else None] = val
                    self._ever = True
        except (OSError, ValueError):
            pass
        with self._lock:
            if not self._ever:
                self.failed = True

    def latest(self, key: str | None = None) -> dict | None:
        with self._lock:
            val = self._values.get(key)
            restart = (not self._stopped and not self.failed and self._proc is not None
                       and self._proc.poll() is not None
                       and time.monotonic() - self._started >= RESTART_S)
            val = dict(val) if val else None
        if restart:
            self.start()
        return val

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            proc, thread = self._proc, self._thread
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if thread:
            thread.join(2)
        proc.stdout.close()


def _intel_cmd(path: str, card: str | None) -> list[str]:
    cmd = [path, "-J", "-s", "1000"]
    return cmd + ["-d", f"drm:/dev/dri/{card}"] if card else cmd


def _nvidia_cmd(path: str) -> list[str]:
    return [path, f"--query-gpu={_NV_QUERY}", "--format=csv,noheader,nounits", "-lms", "1000"]


def _has_capability(path: str) -> bool:
    if os.geteuid() == 0:
        return True
    try:
        os.getxattr(path, "security.capability")
        return True
    except OSError:
        return False


class GpuTools:
    def __init__(self, gpus):
        self._hints: list[str] = []
        self._intel: dict[str, ToolReader] = {}
        self._nvidia: ToolReader | None = None
        cards = [g.card for g in gpus if g.vendor == "intel" and _CARD.fullmatch(g.card)]
        if cards:
            path = shutil.which("intel_gpu_top")
            if not path:
                self._hints.append("hint.igt_missing")
            elif not _has_capability(path):
                self._hints.append("hint.igt_noperm")
            else:
                for c in cards:
                    r = ToolReader(_intel_cmd(path, c if len(cards) > 1 else None), parse_intel)
                    r.start()
                    self._intel[c] = r
        if any(g.vendor == "nvidia" for g in gpus):
            path = shutil.which("nvidia-smi")
            if not path:
                self._hints.append("hint.nvsmi_missing")
            else:
                self._nvidia = ToolReader(_nvidia_cmd(path), parse_nvidia_line, split_lines, "pci")
                self._nvidia.start()

    def intel(self, card: str) -> dict | None:
        r = self._intel.get(card)
        return r.latest() if r else None

    def nvidia(self, pci: str) -> dict | None:
        return self._nvidia.latest(pci.lower()[-12:]) if self._nvidia else None

    def hints(self) -> list[str]:
        failed = ["hint.igt_failed"] if any(r.failed for r in self._intel.values()) else []
        return self._hints + failed

    def stop(self) -> None:
        for r in [*self._intel.values(), self._nvidia]:
            if r:
                r.stop()
