# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Start und GTK-freie Teile der Hülle: Laufzeitprüfung, Nachrichten-Schleuse, Navigationsprüfung, Mess-Thread."""
import argparse
import json
import os
import sys
import threading
import time
from urllib.parse import unquote, urlsplit

import gi

from orbitop import __version__
from orbitop.i18n import detect_language, load_texts

MAX_MESSAGE = 4096
PERIOD_S = 1.0  # tick_system; tick_procs läuft jeden zweiten Takt
RUNTIME = (("Gtk", "4.0", "gir1.2-gtk-4.0"), ("WebKit", "6.0", "gir1.2-webkit-6.0"))


def check_runtime(require_version=gi.require_version) -> str | None:
    """Fehlertext in der Systemsprache, wenn GTK 4 oder WebKitGTK 6.0 fehlt, sonst None."""
    for namespace, version, package in RUNTIME:
        try:
            require_version(namespace, version)
        except ValueError:
            return load_texts(detect_language(os.environ))["error.runtime_missing"].format(package=package)
    return None


def encode(msg: dict) -> str:
    """JSON nur mit ASCII (auch U+2028/2029 maskiert) und ohne NaN: als JS-Literal sicher."""
    return json.dumps(msg, ensure_ascii=True, allow_nan=False)


def _uint(v) -> bool:
    return type(v) is int and v >= 0  # bool ist kein int im Sinne des Vertrags


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
        if tab in ("overview", "procs") and all(x is None or _uint(x) for x in (pid, start)):
            return {"type": "view", "tab": tab, "pid": pid, "start": start}
    if kind == "terminate":
        pid, start, force = m.get("pid"), m.get("start"), m.get("force")
        if _uint(pid) and _uint(start) and type(force) is bool:
            return {"type": "terminate", "pid": pid, "start": start, "force": force}
    return None


def allowed_uri(uri: str, ui_dir: str) -> bool:
    """Nur file://-Adressen von Dateien unterhalb von ui_dir, nach Auflösen von %-Kodierung, .. und Symlinks."""
    try:
        u = urlsplit(uri)
        if u.scheme != "file" or u.netloc:
            return False
        path = os.path.realpath(unquote(u.path))
    except (TypeError, ValueError):  # z. B. Nullbyte im Pfad
        return False
    return path.startswith(os.path.realpath(ui_dir) + os.sep)


def snapshot_path(value: str | None) -> str | None:
    """ORBITOP_SNAPSHOT: nur eine .png-Datei in einem vorhandenen Verzeichnis."""
    if not value or not value.endswith(".png"):
        return None
    path = os.path.abspath(value)
    return path if os.path.isdir(os.path.dirname(path)) else None


class Worker:
    """Einziger Benutzer des Samplers: Takte, Schnappschuss und JSON im eigenen Thread.

    Ruft nie GTK auf; fertiges JSON geht an post (in der Hülle GLib.idle_add)."""

    def __init__(self, sampler, post, clock=time.monotonic, wait=None):
        self._sampler, self._post, self._clock = sampler, post, clock
        self._lock = threading.Lock()  # schützt _visible, _ready, _view
        self._visible = self._ready = False
        self._view = {"tab": "overview", "pid": None, "start": None}
        self._stop, self._wake = threading.Event(), threading.Event()
        self._wait = wait or self._wake.wait
        self._thread = threading.Thread(target=self.run, name="orbitop-worker", daemon=True)

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
        self._thread.start()

    def stop(self, timeout=3.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout)

    def run(self) -> None:
        due, n, fresh = self._clock(), 0, False
        while not self._stop.is_set():
            if self._clock() >= due:
                self._sampler.tick_system()
                if n % 2 == 0:
                    self._sampler.tick_procs()
                n += 1
                due += PERIOD_S
                now = self._clock()
                while due <= now:  # verpasste Takte auslassen statt nachholen; der Takt bleibt ohne Drift
                    due += PERIOD_S
                fresh = True
            if fresh:
                self._publish()
            fresh = self._wait(max(0.0, due - self._clock()))  # True: von update() oder stop() geweckt
            self._wake.clear()

    def _publish(self) -> None:
        with self._lock:
            if not (self._visible and self._ready):
                return
            view = self._view
        try:
            text = encode(self._sampler.snapshot(view))
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
