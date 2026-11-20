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

from orbitop import __version__, sysfs
from orbitop.layout import validate
from orbitop.i18n import detect_language, load_texts

MAX_MESSAGE = 4096
PERIOD_S = 1.0  # tick_system und Schnappschuss
PROCS_PERIOD_S = 2.0  # tick_procs, im eigenen Thread
PROCS_PERIOD_HIDDEN_S = 4.0  # ausgeblendet: halbe Eigenlast des Prozess-Takts (Spec 2026-11-19, Messung Eigenlast)
RUNTIME = (("Gtk", "4.0"), ("WebKit", "6.0"))
# je Paketmanager PyGObject, GTK 4, WebKitGTK 6.0, dahinter weitere Laufzeitpakete; gleich mit Paketen und README (Tests)
PACKAGES = {
    "apt-get": ("python3-gi", "gir1.2-gtk-4.0", "gir1.2-webkit-6.0"),
    "dnf": ("python3-gobject", "gtk4", "webkitgtk6.0"),
    "pacman": ("python-gobject", "gtk4", "webkitgtk-6.0"),
    "zypper": ("python3-gobject", "typelib-1_0-Gtk-4_0", "typelib-1_0-WebKit-6_0", "python3-gobject-Gdk"),
}
INSTALL_HINT = {"apt-get": "sudo apt install {package}", "dnf": "sudo dnf install {package}",
                "pacman": "sudo pacman -S {package}", "zypper": "sudo zypper install {package}"}
DISTRO = {"debian": "apt-get", "ubuntu": "apt-get", "fedora": "dnf", "rhel": "dnf", "centos": "dnf",
          "arch": "pacman", "suse": "zypper", "opensuse": "zypper"}
SCHEME, UI_HOST = "orbitop", "ui"  # die Seite läuft unter orbitop://ui/…, nie unter file://
# nur Typen, die orbitop/ui/ enthält (.txt: Lizenztexte der Schriften)
MIME = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".ttf": "font/ttf", ".txt": "text/plain"}


def package_manager(root: str = "/") -> str:
    """Paketmanager der laufenden Distribution aus ID und ID_LIKE von os-release(5), sonst apt-get."""
    text = (sysfs.read_str(sysfs.path(root, "/etc/os-release"))
            or sysfs.read_str(sysfs.path(root, "/usr/lib/os-release")) or "")
    fields = dict(ln.partition("=")[::2] for ln in text.splitlines())
    for word in (fields.get("ID", "") + " " + fields.get("ID_LIKE", "")).split():
        word = word.strip("\"'")
        manager = DISTRO.get("opensuse" if word.startswith("opensuse-") else word)
        if manager:
            return manager
    return "apt-get"


def _missing(index: int, root: str) -> str:
    manager = package_manager(root)
    package = PACKAGES[manager][index]
    return load_texts(detect_language(os.environ))["error.runtime_missing"].format(
        package=package, command=INSTALL_HINT[manager].format(package=package))


def check_runtime(require_version=None, root: str = "/", version=sys.version_info) -> str | None:
    """Fehlertext in der Systemsprache, wenn Python zu alt ist oder PyGObject, GTK 4 oder WebKitGTK 6.0 fehlt."""
    if version < (3, 12):
        return load_texts(detect_language(os.environ))["error.python_old"].format(
            version=".".join(map(str, version[:3])))
    if require_version is None:
        try:
            import gi  # erst hier, nie auf Modulebene: sampler importiert encode aus diesem Modul
        except ImportError:
            return _missing(0, root)
        require_version = gi.require_version
    for index, (namespace, ns_version) in enumerate(RUNTIME, 1):
        try:
            require_version(namespace, ns_version)
        except ValueError:
            return _missing(index, root)
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
    if kind == "autostart" and type(m.get("on")) is bool:
        return {"type": "autostart", "on": m["on"]}
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
        self._lock = threading.Lock()  # schützt _visible, _shown, _ready, _view, _resend und _errors
        self._visible = self._ready = False
        self._shown = False  # eingeblendet seit dem letzten Prozess-Takt: der nächste spätestens PROCS_PERIOD_S danach
        self._view = {"tab": "overview", "pid": None, "start": None}
        # True: nächster Tick mit voller Prozessliste; sonst darf eine unveränderte fehlen, denn WebKit parst je Tick
        # das ganze Literal (~170 KB)
        self._resend = True
        self._stop, self._wake, self._procs_wake = threading.Event(), threading.Event(), threading.Event()
        self._wait = wait or self._wake.wait
        self._errors: set[tuple[str, str]] = set()  # schon gemeldete Fehler (Typ, Text)
        self._threads = [threading.Thread(target=self.run, name="orbitop-worker", daemon=True),
                         threading.Thread(target=self.run_procs, name="orbitop-procs", daemon=True)]

    def update(self, *, visible=None, ready=None, view=None) -> bool:
        """True, wenn das Fenster sichtbar und die Seite bereit ist; dann folgt sofort ein Schnappschuss."""
        with self._lock:
            shown = bool(visible) and not self._visible
            if visible is not None:
                self._visible = visible
                self._shown = self._shown or shown
            if ready is not None:
                self._ready = ready
            if view is not None:
                self._view = view
            if ready is not None or view is not None:  # neue Seite oder neue Ansicht: die volle Liste
                self._resend = True
            live = self._visible and self._ready
        if live:
            self._wake.set()
        if shown:
            self._procs_wake.set()
        return live

    def start(self) -> None:
        for t in self._threads:
            t.start()

    def stop(self, timeout=3.0) -> None:
        """Beendet beide Threads, insgesamt höchstens timeout lang; ein in /proc hängender Daemon hält nichts auf."""
        self._stop.set()
        self._wake.set()
        self._procs_wake.set()
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
        """Prozess-Takt alle PROCS_PERIOD_S, ausgeblendet alle PROCS_PERIOD_HIDDEN_S; wait nur für Tests."""
        wait = wait or self._procs_wake.wait
        due, last = self._clock(), None
        while not self._stop.is_set():
            with self._lock:
                shown, self._shown = self._shown, False
                visible = self._visible
                shr = visible and self._ready and self._view.get("tab") == "procs"
            now = self._clock()
            # eingeblendet: Prozesse höchstens PROCS_PERIOD_S alt, also oft sofort; nie kurz nach dem letzten Takt,
            # denn Raten über Bruchteile einer Sekunde wären verrauscht (etwa kurz nach dem Start)
            if shown and last is not None:
                due = min(due, max(now, last + PROCS_PERIOD_S))
            if now >= due:
                last = now
                self._guard(lambda: self._sampler.tick_procs(shr=shr))
                due = self._next(due, PROCS_PERIOD_S if visible else PROCS_PERIOD_HIDDEN_S)
            wait(max(0.0, due - self._clock()))
            self._procs_wake.clear()  # erst danach, wie in run(): _shown und _stop gehen so nie verloren

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
            view, resend, self._resend = self._view, self._resend, False
        try:
            text = self._sampler.snapshot_json(view, resend=resend)
        except (TypeError, ValueError):  # nie ein ungültiges JS-Literal senden
            with self._lock:  # die Seite wartet nie auf eine Liste, die sie nicht bekam
                self._resend = True
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
