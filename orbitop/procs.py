# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Prozess-Erhebung aus /proc: Rohwerte, CPU-Raten, Verlauf und Einstufung."""
import os
import pwd
import re
from collections import deque
from dataclasses import dataclass, field

from orbitop import sysfs
from orbitop.classify import BUSY_CPU, ProcState, classify, is_busy_sample
from orbitop.system import MAX_DT

HISTORY = 150
SPARK = 30
CMDLINE_MAX = 4096
_CHUNK = 65536
ARGS_MAX = 120
STATUS_EVERY_S = 10.0  # status (uid, Kontextwechsel) sonst nur bei Bedarf, siehe ProcTable.wants_status


@dataclass
class RawProc:
    pid: int
    start: int
    ppid: int
    name: str
    cmdline: str
    uid: int | None  # uid, vctx, nvctx: None, wenn status in diesem Takt nicht gelesen wurde
    state: str
    ticks: int
    rss: int  # Bytes
    threads: int
    vctx: int | None
    nvctx: int | None
    io: int | None  # rchar + wchar, None wenn nicht lesbar
    args: str


def is_kernel_thread(ppid: int, cmdline) -> bool:
    """Kernel-Thread: Kind von 0 oder kthreadd (2) ohne Befehlszeile."""
    return not cmdline and ppid in (0, 2)


def is_kernel(pid: int, ppid: int, cmdline) -> bool:
    """Nicht beendbar: PID 1 oder Kernel-Thread. Einzige Quelle der Regel; killhelper.send hält eine eigene Kopie,
    weil er unter python3 -I ohne Paket läuft. cmdline als str oder bytes (es zählt nur, ob sie leer ist)."""
    return pid == 1 or is_kernel_thread(ppid, cmdline)


def _read(p: str) -> str | None:
    """Schlanker als sysfs.read_str (kein TextIOWrapper), das hier läuft je Prozess und Tick."""
    try:
        fd = os.open(p, os.O_RDONLY)
    except OSError:
        return None
    try:
        chunks = []
        while True:  # status kann bei vielen Gruppen > 64 KiB werden; weiterlesen nur nach vollem Block
            chunk = os.read(fd, _CHUNK)
            chunks.append(chunk)
            if len(chunk) < _CHUNK:
                return b"".join(chunks).decode("utf-8", errors="replace")
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


# Die Kontextwechsel stammen aus status und zählen nur den Hauptthread; die Dauerlast-Heuristik ist darauf begrenzt.
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


def _read_cmdline(p: str) -> tuple[str, str]:
    """(cmdline, args). args: alles nach der ersten NUL; ohne NUL (setproctitle-Titel) nach dem ersten Leerzeichen.
    shortcut: ein einzelnes argv mit Leerzeichen und ohne NUL (Wine "C:\\Program Files\\x.exe") wird wie ein
    Titel geteilt; sauber erst, wenn /proc/<pid>/exe oder comm zum Unterscheiden herangezogen wird."""
    try:
        with open(p, "rb") as f:
            raw = f.read(CMDLINE_MAX * 4)
    except OSError:
        return "", ""
    raw = raw.rstrip(b"\0")
    text = raw.decode("utf-8", errors="replace").replace("\0", " ")
    if b"\0" in raw:
        args = raw.partition(b"\0")[2].decode("utf-8", errors="replace").replace("\0", " ")
    else:
        args = text.partition(" ")[2]
    return sysfs.printable(text)[:CMDLINE_MAX], sysfs.printable(args)[:CMDLINE_MAX]


def scan(root: str, cmdlines: dict | None = None,
         page_size: int = os.sysconf("SC_PAGE_SIZE"), want_status=None) -> dict[tuple[int, int], RawProc]:
    """Liest alle Prozesse. `cmdlines` (Schlüssel -> (comm, cmdline, args)) wird nur für neue Schlüssel
    und nach einem comm-Wechsel (exec) neu gelesen. `want_status(key, ticks)` entscheidet, ob status gelesen wird
    (ohne: immer); sonst bleiben uid, vctx und nvctx None."""
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
        stat = _read(base + "/stat")
        if stat is None:  # verschwunden
            continue
        try:
            s = parse_stat(stat)
        except (ValueError, IndexError):
            continue
        key = (int(n), s["start"])
        uid = vctx = nvctx = None
        if want_status is None or want_status(key, s["ticks"]):
            status = _read(base + "/status")
            if status is None:
                continue
            try:
                uid, vctx, nvctx = _parse_status(status)
            except (ValueError, IndexError):
                continue
        # shortcut: ein exec auf ein Programm mit gleichem comm behält die alte cmdline (comm ist das einzige
        # Exec-Signal); sauber erst, wenn zusätzlich /proc/<pid>/exe verglichen wird.
        c = cmdlines.get(key)
        if c is None or c[0] != s["name"]:
            c = cmdlines[key] = (s["name"], *_read_cmdline(base + "/cmdline"))
        name = sysfs.printable(s["name"])
        if is_kernel_thread(s["ppid"], c[1]):  # Klammern nur für Kernel-Threads, nicht für PID 1
            name = f"[{name}]"
        out[key] = RawProc(int(n), s["start"], s["ppid"], name, c[1], uid, s["state"], s["ticks"],
                           s["rss"] * page_size, s["threads"], vctx, nvctx, _parse_io(_read(base + "/io")),
                           c[2])
    return out


@dataclass
class _Entry:
    raw: RawProc
    state: ProcState
    t: float | None = None
    cpu: float = 0.0
    io_rate: float | None = None
    vctx_rate: float = 0.0
    nvctx_rate: float = 0.0
    status_t: float | None = None  # Zeit des letzten status-Lesens
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY))


class ProcTable:
    def __init__(self, clk_tck: int = os.sysconf("SC_CLK_TCK"), uid: int | None = None, root: str = "/"):
        self.clk_tck = clk_tck
        self.uid = os.getuid() if uid is None else uid
        self.cmdlines: dict[tuple[int, int], tuple[str, str, str]] = {}  # Eingabe für scan(), wird in update() bereinigt
        self.selected: tuple[int, int] | None = None  # Prozess im Detail: status bei jedem Takt
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

    def wants_status(self, now: float):
        """Für scan: status (uid, Kontextwechsel) nur für neue Schlüssel, die Auswahl, Kandidaten der Dauerlast
        (CPU ≥ BUSY_CPU in diesem Takt, die Regel braucht die Kontextwechsel) und sonst alle STATUS_EVERY_S."""
        def due(key: tuple[int, int], ticks: int) -> bool:
            e = self._entries.get(key)
            if e is None or key == self.selected or e.status_t is None or not 0 <= now - e.status_t < STATUS_EVERY_S:
                return True
            dt = now - e.t
            return 0 < dt <= MAX_DT and (ticks - e.raw.ticks) / self.clk_tck / dt * 100 >= BUSY_CPU
        return due

    def update(self, raw: dict[tuple[int, int], RawProc], now: float) -> None:
        old = self._entries
        self._entries = {}
        for key, r in raw.items():
            e = old.get(key) or _Entry(r, ProcState(r.state, None, None, True, 0.0, None))
            prev, e.raw = e.raw, r
            fresh = r.vctx is not None
            if not fresh:  # status nicht gelesen: uid und Zähler vom letzten Lesen, die Raten bleiben stehen
                r.uid, r.vctx, r.nvctx = prev.uid, prev.vctx, prev.nvctx
            dt = None if e.t is None else now - e.t
            valid = dt is not None and 0 < dt <= MAX_DT
            e.cpu = 0.0
            io_delta = None
            if valid and r.ticks >= prev.ticks:
                e.cpu = (r.ticks - prev.ticks) / self.clk_tck / dt * 100
            ctx_ok = False  # Kontextwechsel in diesem Takt gelesen; angezeigt wird die Rate über das dt seit dem letzten Lesen
            if fresh:
                sdt = None if e.status_t is None else now - e.status_t
                ctx_ok = sdt is not None and 0 < sdt <= STATUS_EVERY_S + MAX_DT and r.vctx >= prev.vctx and r.nvctx >= prev.nvctx
                e.vctx_rate, e.nvctx_rate = ((r.vctx - prev.vctx) / sdt, (r.nvctx - prev.nvctx) / sdt) if ctx_ok else (0.0, 0.0)
                e.status_t = now
            if valid and r.io is not None and prev.io is not None and r.io >= prev.io:
                io_delta = r.io - prev.io
            e.io_rate = None if io_delta is None else io_delta / dt
            e.t = now
            e.history.append(e.cpu)
            s = e.state
            s.state, s.io_known, s.last_cpu, s.last_io_delta = r.state, r.io is not None, e.cpu, io_delta
            # Hängen nur ohne Fortschritt: gedrosseltes Schreiben (USB, NFS) schläft bei jeder Stichprobe in D, rechnet
            # und schreibt aber dazwischen; bei unbekannter E/A zählen nur die CPU-Ticks
            progressed = valid and (r.ticks > prev.ticks or (io_delta or 0) > 0)
            stuck = r.state == "D" and not progressed
            s.d_since = (s.d_since if s.d_since is not None else now) if stuck else None
            # Einstufung mit der Obergrenze dieses Takts: alle Wechsel seit dem letzten Lesen durch sein dt. Über die ganze
            # status-Lücke gemittelt könnte ein Takt mit mehr als 1/s als Dauerlast zählen (zu früh gemeldet).
            busy = valid and ctx_ok and is_busy_sample(e.cpu, (r.vctx - prev.vctx) / dt, io_delta)
            s.busy_since = (s.busy_since if s.busy_since is not None else now - dt) if busy else None
            self._entries[key] = e
        self.cmdlines = {k: v for k, v in self.cmdlines.items() if k in self._entries}

    def _row(self, e: _Entry, now: float) -> dict:
        r = e.raw
        state, since = classify(e.state, now)
        return {"pid": r.pid, "start": r.start, "name": r.name,
                "args": r.args if len(r.args) <= ARGS_MAX else r.args[:ARGS_MAX - 1] + "…",
                "user": self._user(r.uid), "own": r.uid == self.uid, "cpu": e.cpu,
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
                "kernel": is_kernel(r.pid, r.ppid, r.cmdline),
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
