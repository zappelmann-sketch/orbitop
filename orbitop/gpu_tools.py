# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Hilfsprogramme intel_gpu_top und nvidia-smi: langlebige Kindprozesse, begrenzt geparst."""
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterable, Iterator

MAX_BUF = 1024 * 1024  # größtes Objekt/Zeile, das gepuffert wird
RESTART_S = 30.0
STALE_S = 3.0  # älteren Werten wird nicht mehr getraut
TOOL_PATH = "/usr/local/bin:/usr/bin:/bin"  # fest: kein ~/.local/bin, kein leerer PATH-Eintrag
_CARD = re.compile(r"card[0-9]+")
_NV_FIELDS = ("busy", "vram_used", "vram_total", "temp_c", "power_w", "freq_mhz",
              "freq_max_mhz", "fan_pct")
_NV_QUERY = ("pci.bus_id,name,utilization.gpu,memory.used,memory.total,temperature.gpu,"
             "power.draw,clocks.gr,clocks.max.gr,fan.speed")


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def parse_intel(obj: dict) -> dict:
    engines = obj.get("engines")
    busy = [b for e in (engines.values() if isinstance(engines, dict) else [])
            if isinstance(e, dict) and (b := _num(e.get("busy"))) is not None]
    power, freq = obj.get("power") or {}, obj.get("frequency") or {}
    return {"busy": max(busy, default=None), "freq_mhz": _num(freq.get("actual")),
            "gpu_w": _num(power.get("GPU")), "pkg_w": _num(power.get("Package"))}


def split_json_stream(lines: Iterable[str]) -> Iterator[dict]:
    """Rahmt Objekte über Zeilen genau `{` und `}`/`},`; der `clients`-Block (rohe Prozessnamen) entfällt."""
    buf: list[str] = []
    size = 0
    active = in_clients = False
    for line in lines:
        s = line.rstrip("\r\n")
        if s == "{":  # auch mitten im Objekt: neu aufsetzen
            active, in_clients, buf, size = True, False, [s], len(s)
            continue
        if not active:
            continue
        size += len(s) + 1
        if size > MAX_BUF:
            active, buf = False, []
            continue
        if s in ("}", "},"):
            active = False
            text = "\n".join(buf).rstrip().removesuffix(",") + "\n}"
            buf = []
            try:
                obj = json.loads(text)
            except (ValueError, RecursionError):
                continue
            if isinstance(obj, dict):
                yield obj
        elif in_clients:
            in_clients = s not in ("\t}", "\t},")
        elif s == '\t"clients": {':
            in_clients = True
        else:
            buf.append(s)


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
    d.update({k: _num(v) for k, v in zip(_NV_FIELDS, parts[2:])})  # [N/A] -> None
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
            self._spawn()

    def _spawn(self) -> None:  # Aufrufer hält self._lock
        if self._stopped:
            return
        self._started = time.monotonic()
        try:
            proc = subprocess.Popen(self._cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, errors="replace")
        except OSError:
            self.failed = not self._ever
            return
        self._proc = proc
        self._thread = threading.Thread(target=self._run, args=(proc,), daemon=True)
        self._thread.start()

    def _run(self, proc) -> None:
        try:
            for item in self._split(iter(lambda: proc.stdout.readline(65536), "")):
                try:
                    val = self._parse(item)
                except Exception:  # defekte Zeile/Objekt überspringen
                    continue
                with self._lock:
                    self._values[val.get(self._key) if self._key else None] = (time.monotonic(), val)
                    self._ever = True
        except Exception:  # der Thread darf nie an einem Parsefehler sterben
            pass
        with self._lock:
            if not self._ever:
                self.failed = True

    def latest(self, key: str | None = None) -> dict | None:
        with self._lock:
            if (not self._stopped and not self.failed and self._proc is not None
                    and self._proc.poll() is not None
                    and time.monotonic() - self._started >= RESTART_S):
                self._spawn()
            stamped = self._values.get(key)
            if stamped and time.monotonic() - stamped[0] <= STALE_S:
                return dict(stamped[1])
            return None

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
    # 2 s statt 1 s halbiert die Eigenlast von intel_gpu_top (gemessen 2,2 % -> 1,1 % eines Kerns). Die Grafik-Kachel
    # (und die Leistung aus Package, wenn RAPL nicht lesbar ist) zeigt dann 2-s-Mittel, im Verlauf je zweimal derselbe Wert.
    cmd = [path, "-J", "-s", "2000"]
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
            path = shutil.which("intel_gpu_top", path=TOOL_PATH)
            if not path:
                self._hints.append("hint.igt_missing")
            elif not _has_capability(path):
                self._hints.append("hint.igt_noperm")
            else:
                for c in cards:
                    r = ToolReader(_intel_cmd(path, c if len(cards) > 1 else None), parse_intel)
                    r.start()
                    self._intel[c] = r
        if any(g.driver == "nvidia" for g in gpus):
            path = shutil.which("nvidia-smi", path=TOOL_PATH)
            if not path:
                self._hints.append("hint.nvsmi_missing")
            else:
                self._nvidia = ToolReader(_nvidia_cmd(path), parse_nvidia_line, split_lines, "pci")
                self._nvidia.start()

    def intel(self, card: str) -> dict | None:
        r = self._intel.get(card)
        return r.latest() if r else None

    def nvidia(self, pci: str) -> dict | None:
        return self._nvidia.latest(pci) if self._nvidia else None

    def hints(self) -> list[str]:
        failed = ["hint.igt_failed"] if any(r.failed for r in self._intel.values()) else []
        return self._hints + failed

    def stop(self) -> None:
        for r in [*self._intel.values(), self._nvidia]:
            if r:
                r.stop()
