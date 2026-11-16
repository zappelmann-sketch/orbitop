# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Prozess-Erhebung aus /proc: Rohwerte, CPU-Raten, Verlauf und Einstufung."""
import os
import pwd
import re
from collections import deque
from dataclasses import dataclass, field

from orbitop import sysfs
from orbitop.classify import ProcState, classify, is_busy_sample
from orbitop.system import MAX_DT

HISTORY = 150
SPARK = 30
CMDLINE_MAX = 4096
ARGS_MAX = 120
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


@dataclass
class RawProc:
    pid: int
    start: int
    ppid: int
    name: str
    cmdline: str
    uid: int
    state: str
    ticks: int
    rss: int  # Bytes
    threads: int
    vctx: int
    nvctx: int
    io: int | None  # rchar + wchar, None wenn nicht lesbar


def _read(p: str) -> str | None:
    """Schlanker als sysfs.read_str (kein TextIOWrapper), das hier läuft je Prozess und Tick."""
    try:
        fd = os.open(p, os.O_RDONLY)
    except OSError:
        return None
    try:
        return os.read(fd, 16384).decode("utf-8", errors="replace")
    except OSError:
        return None
    finally:
        os.close(fd)


def parse_stat(text: str) -> dict:
    """Felder nach proc(5). comm reicht bis zur letzten ')'. Wirft ValueError/IndexError bei Müll."""
    end = text.rindex(")")
    f = text[end + 2:].split()
    return {"name": text[text.index("(") + 1:end], "state": f[0], "ppid": int(f[1]),
            "ticks": int(f[11]) + int(f[12]), "threads": int(f[17]), "start": int(f[19]),
            "rss": int(f[21])}


def _field(text: str, key: str) -> int:
    i = text.index("\n" + key + ":") + len(key) + 2  # ValueError wenn Feld fehlt
    return int(text[i:i + 24].split()[0])


def _parse_status(text: str) -> tuple[int, int, int]:
    text = "\n" + text
    return _field(text, "Uid"), _field(text, "voluntary_ctxt_switches"), _field(text, "nonvoluntary_ctxt_switches")


def _parse_io(text: str | None) -> int | None:
    if text is None:
        return None
    got = dict(line.partition(":")[::2] for line in text.splitlines())
    try:
        return int(got["rchar"]) + int(got["wchar"])
    except (KeyError, ValueError):
        return None


def _read_cmdline(p: str) -> str:
    try:
        with open(p, "rb") as f:
            raw = f.read(CMDLINE_MAX * 4)
    except OSError:
        return ""
    text = raw.decode("utf-8", errors="replace").rstrip("\0").replace("\0", " ")
    return _CONTROL.sub("?", text)[:CMDLINE_MAX]


def scan(root: str, cmdlines: dict | None = None,
         page_size: int = os.sysconf("SC_PAGE_SIZE")) -> dict[tuple[int, int], RawProc]:
    """Liest alle Prozesse. `cmdlines` (Schlüssel -> Text) wird nur für neue Schlüssel gefüllt."""
    cmdlines = {} if cmdlines is None else cmdlines
    out = {}
    try:
        names = os.listdir(sysfs.path(root, "/proc"))
    except OSError:
        return out
    for n in names:
        if not (n.isascii() and n.isdecimal()):  # nie Pfade aus anderem Inhalt bauen
            continue
        base = sysfs.path(root, "/proc/" + n)
        stat, status = _read(base + "/stat"), _read(base + "/status")
        if stat is None or status is None:
            continue
        try:
            s = parse_stat(stat)
            uid, vctx, nvctx = _parse_status(status)
        except (ValueError, IndexError):
            continue
        key = (int(n), s["start"])
        if key not in cmdlines:
            cmdlines[key] = _read_cmdline(base + "/cmdline")
        cmd = cmdlines[key]
        out[key] = RawProc(int(n), s["start"], s["ppid"], s["name"] if cmd else f"[{s['name']}]", cmd,
                           uid, s["state"], s["ticks"], s["rss"] * page_size, s["threads"], vctx, nvctx,
                           _parse_io(_read(base + "/io")))
    return out


@dataclass
class _Entry:
    raw: RawProc
    user: str
    state: ProcState
    t: float | None = None
    cpu: float = 0.0
    io_rate: float | None = None
    vctx_rate: float = 0.0
    nvctx_rate: float = 0.0
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY))


class ProcTable:
    def __init__(self, clk_tck: int = os.sysconf("SC_CLK_TCK"), uid: int | None = None, root: str = "/"):
        self.clk_tck = clk_tck
        self.uid = os.getuid() if uid is None else uid
        self.cmdlines: dict[tuple[int, int], str] = {}  # Eingabe für scan(), wird in update() bereinigt
        self._entries: dict[tuple[int, int], _Entry] = {}
        self._users: dict[int, str] = {}
        btime = re.search(r"^btime (\d+)", sysfs.read_str(sysfs.path(root, "/proc/stat")) or "", re.M)
        self._btime = int(btime.group(1)) if btime else 0

    def _user(self, uid: int) -> str:
        if uid not in self._users:
            try:
                self._users[uid] = pwd.getpwuid(uid).pw_name
            except KeyError:
                self._users[uid] = str(uid)
        return self._users[uid]

    def update(self, raw: dict[tuple[int, int], RawProc], now: float) -> None:
        old = self._entries
        self._entries = {}
        for key, r in raw.items():
            e = old.get(key) or _Entry(r, self._user(r.uid), ProcState(r.state, None, None, True, 0.0, None))
            prev, e.raw = e.raw, r
            dt = None if e.t is None else now - e.t
            valid = dt is not None and 0 < dt <= MAX_DT
            e.cpu = e.vctx_rate = e.nvctx_rate = 0.0
            io_delta = None
            if valid and r.ticks >= prev.ticks:
                e.cpu = (r.ticks - prev.ticks) / self.clk_tck / dt * 100
            if valid and r.vctx >= prev.vctx and r.nvctx >= prev.nvctx:
                e.vctx_rate, e.nvctx_rate = (r.vctx - prev.vctx) / dt, (r.nvctx - prev.nvctx) / dt
            if valid and r.io is not None and prev.io is not None and r.io >= prev.io:
                io_delta = r.io - prev.io
            e.io_rate = None if io_delta is None else io_delta / dt
            e.t = now
            e.history.append(e.cpu)
            s = e.state
            s.state, s.io_known, s.last_cpu, s.last_io_delta = r.state, r.io is not None, e.cpu, io_delta
            s.d_since = (s.d_since if s.d_since is not None else now) if r.state == "D" else None
            busy = valid and r.ticks >= prev.ticks and is_busy_sample(e.cpu, e.vctx_rate, io_delta)
            s.busy_since = (s.busy_since if s.busy_since is not None else now) if busy else None
            self._entries[key] = e
        self.cmdlines = {k: v for k, v in self.cmdlines.items() if k in self._entries}

    def _row(self, e: _Entry, now: float) -> dict:
        r = e.raw
        state, since = classify(e.state, now)
        args = r.cmdline.partition(" ")[2]
        return {"pid": r.pid, "start": r.start, "name": r.name,
                "args": args if len(args) <= ARGS_MAX else args[:ARGS_MAX - 1] + "…",
                "user": e.user, "own": r.uid == self.uid, "cpu": e.cpu,
                "spark": list(e.history)[-SPARK:], "rss": r.rss, "io": e.io_rate,
                "state": state, "since": since}

    def rows(self, now: float) -> list[dict]:
        return [self._row(e, now) for e in self._entries.values()]

    def detail(self, pid: int, start: int, now: float) -> dict | None:
        e = self._entries.get((pid, start))
        if e is None:
            return None
        r = e.raw
        parent = next((p.raw.name for k, p in self._entries.items() if k[0] == r.ppid), "")
        return {**self._row(e, now), "cmdline": r.cmdline, "ppid": r.ppid, "parent": parent,
                "threads": r.threads, "vctx": e.vctx_rate, "nvctx": e.nvctx_rate,
                "started": int(self._btime + r.start / self.clk_tck), "history": list(e.history)}

    def _brief(self, e: _Entry) -> dict:
        r = e.raw
        return {"pid": r.pid, "start": r.start, "name": r.name, "cpu": e.cpu, "rss": r.rss}

    def top_cpu(self, n: int = 3) -> list[dict]:
        busy = sorted((e for e in self._entries.values() if e.cpu > 0), key=lambda e: -e.cpu)
        return [self._brief(e) for e in busy[:n]]

    def top_mem(self) -> dict | None:
        e = max(self._entries.values(), key=lambda e: e.raw.rss, default=None)
        return None if e is None else self._brief(e)

    def counts(self) -> tuple[int, int]:
        return len(self._entries), sum(e.raw.threads for e in self._entries.values())
