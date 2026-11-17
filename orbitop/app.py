# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Start und GTK-freie Teile der Hülle: Laufzeitprüfung, Nachrichten-Schleuse, UI-Dateien, Mess-Thread."""
import argparse
import json
import os
import sys
import threading
import time
import traceback
from urllib.parse import unquote, urlsplit

from orbitop import __version__
from orbitop.layout import validate
from orbitop.i18n import detect_language, load_texts

MAX_MESSAGE = 4096
PERIOD_S = 1.0  # tick_system und Schnappschuss
PROCS_PERIOD_S = 2.0  # tick_procs, im eigenen Thread
RUNTIME = (("Gtk", "4.0", "gir1.2-gtk-4.0"), ("WebKit", "6.0", "gir1.2-webkit-6.0"))
SCHEME, UI_HOST = "orbitop", "ui"  # die Seite läuft unter orbitop://ui/…, nie unter file://
# nur Typen, die orbitop/ui/ enthält (.txt: Lizenztexte der Schriften)
MIME = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".ttf": "font/ttf", ".txt": "text/plain"}


def _missing(package: str) -> str:
    return load_texts(detect_language(os.environ))["error.runtime_missing"].format(package=package)


def check_runtime(require_version=None) -> str | None:
    """Fehlertext in der Systemsprache, wenn PyGObject, GTK 4 oder WebKitGTK 6.0 fehlt, sonst None."""
    if require_version is None:
        try:
            import gi  # erst hier, nie auf Modulebene: sampler importiert encode aus diesem Modul
        except ImportError:
            return _missing("python3-gi")
        require_version = gi.require_version
    for namespace, version, package in RUNTIME:
        try:
            require_version(namespace, version)
        except ValueError:
            return _missing(package)
    return None


def encode(msg: dict) -> str:
    """JSON nur mit ASCII (auch U+2028/2029 maskiert) und ohne NaN: als JS-Literal sicher."""
    return json.dumps(msg, ensure_ascii=True, allow_nan=False)


PID_MAX, START_MAX = 4194304, 2**63 - 1  # PID_MAX_LIMIT des Kernels; start ist ein u64-Zähler in Ticks


def _uint(v, top: int) -> bool:
    return type(v) is int and 0 <= v <= top  # bool ist kein int im Sinne des Vertrags


def parse_message(raw) -> dict | None:
    """Schleuse für Nachrichten der Seite: nur die Formen des Vertrags, sonst None (still verworfen)."""
    if not isinstance(raw, str) or len(raw) > MAX_MESSAGE:
        return None
    try:
        m = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(m, dict):
        return None
    kind = m.get("type")
    if kind in ("ready", "quit"):
        return {"type": kind}
    if kind == "view":
        tab, pid, start = m.get("tab"), m.get("pid"), m.get("start")
        if tab in ("overview", "procs") and (pid is None or _uint(pid, PID_MAX)) and (
                start is None or _uint(start, START_MAX)):
            return {"type": "view", "tab": tab, "pid": pid, "start": start}
    if kind == "layout":
        layout = validate(m)
        return {"type": "layout", **layout} if layout else None
    if kind == "terminate":
        pid, start, force = m.get("pid"), m.get("start"), m.get("force")
        if _uint(pid, PID_MAX) and _uint(start, START_MAX) and type(force) is bool:
            return {"type": "terminate", "pid": pid, "start": start, "force": force}
    return None


def ui_file(uri: str, ui_dir: str) -> tuple[str, str] | None:
    """(Pfad, Inhaltstyp) für orbitop://ui/<pfad>: eine reguläre Datei bekannten Typs unterhalb von ui_dir,
    nach Auflösen von %-Kodierung, .. und Symlinks. Alles andere: None (Navigation verboten, Laden scheitert)."""
    try:
        u = urlsplit(uri)
        if u.scheme != SCHEME or u.netloc != UI_HOST:
            return None
        root = os.path.realpath(ui_dir)
        path = os.path.realpath(os.path.join(root, unquote(u.path).lstrip("/")))
    except (TypeError, ValueError):  # z. B. Nullbyte im Pfad
        return None
    mime = MIME.get(os.path.splitext(path)[1])
    return (path, mime) if mime and path.startswith(root + os.sep) and os.path.isfile(path) else None


def snapshot_path(value: str | None) -> str | None:
    """ORBITOP_SNAPSHOT: nur eine .png-Datei in einem vorhandenen Verzeichnis."""
    if not value or not value.endswith(".png"):
        return None
    path = os.path.abspath(value)
    return path if os.path.isdir(os.path.dirname(path)) else None


class Worker:
    """Einziger Benutzer des Samplers, in zwei eigenen Threads: orbitop-worker (Systemtakt, Schnappschuss, JSON) und
    orbitop-procs (Prozess-Takt). Das Lesen von /proc/<pid>/cmdline kann blockieren (mmap-Lock bei hängendem FUSE oder
    NFS); das hält so nur die Prozessliste an, nie die Kacheln. Was beide Threads teilen, schützt der Sampler.

    Ruft nie GTK auf; fertiges JSON geht an post (in der Hülle GLib.idle_add)."""

    def __init__(self, sampler, post, clock=time.monotonic, wait=None):
        self._sampler, self._post, self._clock = sampler, post, clock
        self._lock = threading.Lock()  # schützt _visible, _ready, _view und _errors
        self._visible = self._ready = False
        self._view = {"tab": "overview", "pid": None, "start": None}
        self._stop, self._wake = threading.Event(), threading.Event()
        self._wait = wait or self._wake.wait
        self._errors: set[tuple[str, str]] = set()  # schon gemeldete Fehler (Typ, Text)
        self._threads = [threading.Thread(target=self.run, name="orbitop-worker", daemon=True),
                         threading.Thread(target=self.run_procs, name="orbitop-procs", daemon=True)]

    def update(self, *, visible=None, ready=None, view=None) -> bool:
        """True, wenn das Fenster sichtbar und die Seite bereit ist; dann folgt sofort ein Schnappschuss."""
        with self._lock:
            if visible is not None:
                self._visible = visible
            if ready is not None:
                self._ready = ready
            if view is not None:
                self._view = view
            live = self._visible and self._ready
        if live:
            self._wake.set()
        return live

    def start(self) -> None:
        for t in self._threads:
            t.start()

    def stop(self, timeout=3.0) -> None:
        """Beendet beide Threads, insgesamt höchstens timeout lang; ein in /proc hängender Daemon hält nichts auf."""
        self._stop.set()
        self._wake.set()
        deadline = time.monotonic() + timeout
        for t in self._threads:
            if t.is_alive():
                t.join(max(0.0, deadline - time.monotonic()))

    def _next(self, due: float, period: float) -> float:
        due += period
        now = self._clock()
        while due <= now:  # verpasste Takte auslassen statt nachholen; der Takt bleibt ohne Drift
            due += period
        return due

    def run(self) -> None:
        due, fresh = self._clock(), False
        while not self._stop.is_set():
            if self._clock() >= due:
                self._guard(self._sampler.tick_system)
                due = self._next(due, PERIOD_S)
                fresh = True
            if fresh:
                self._guard(self._publish)
            fresh = self._wait(max(0.0, due - self._clock()))  # True: von update() oder stop() geweckt
            self._wake.clear()

    def run_procs(self, wait=None) -> None:
        """Prozess-Takt alle PROCS_PERIOD_S, auch bei ausgeblendetem Fenster; wait nur für Tests."""
        wait = wait or self._stop.wait
        due = self._clock()
        while not self._stop.is_set():
            if self._clock() >= due:
                with self._lock:
                    shr = self._visible and self._ready and self._view.get("tab") == "procs"
                self._guard(lambda: self._sampler.tick_procs(shr=shr))
                due = self._next(due, PROCS_PERIOD_S)
            wait(max(0.0, due - self._clock()))

    def _guard(self, fn) -> None:
        """Ein Fehler im Sampler darf keinen Mess-Thread still beenden; jeder Fehler erscheint einmal, nicht je Takt."""
        try:
            fn()
        except Exception as e:
            key = (type(e).__name__, str(e))
            with self._lock:  # beide Threads melden hierher
                new = key not in self._errors and len(self._errors) < 100  # begrenzt, falls sich der Text ständig ändert
                if new:
                    self._errors.add(key)
            if new:
                traceback.print_exc()

    def _publish(self) -> None:
        with self._lock:
            if not (self._visible and self._ready):
                return
            view = self._view
        try:
            text = self._sampler.snapshot_json(view)
        except (TypeError, ValueError):  # nie ein ungültiges JS-Literal senden
            return
        self._post(text)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="orbitop")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--hidden", action="store_true")
    args = ap.parse_args(argv)
    if args.version:
        print(f"orbitop {__version__}")
        return 0
    msg = check_runtime()
    if msg:
        print(msg, file=sys.stderr)
        return 2
    from orbitop.shell import Shell  # braucht GTK und WebKit, also erst nach der Prüfung
    return Shell(args.hidden).run()
