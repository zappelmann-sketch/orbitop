# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Fake-Bus für die PackageKit-Tests: ein PackageKit 1.x ohne System-Bus, ohne Installation und ohne Dialog.

FakeBus hat die Teile von Gio.DBusConnection, die orbitop/packagekit.py nutzt. Wie bei Gio kommen die Signale über
den MainContext, der beim Abonnieren der Standard des Threads war; ein Signal aus einem anderen Thread weckt ihn."""
import threading

import pytest
from gi.repository import Gio, GLib

from orbitop import packagekit

# PyGObject 3.56 ruft in MainContext.iteration die unter Python 3.14 veralteten asyncio-Policy-Funktionen auf
# (gi/events.py, nicht orbitop); nur diese Warnungen, nur in den Modulen mit dem Fake-Bus
GI_ASYNCIO = pytest.mark.filterwarnings("ignore:'asyncio\\.:DeprecationWarning:gi.events")


@pytest.fixture(autouse=True)
def short_wait(monkeypatch):
    """In den Modulen, die es importieren: ein Fehler beim Abbruch endet nach 5 s in failed statt nach 10 min."""
    monkeypatch.setattr(packagekit, "WAIT_S", 5.0)

IGT = "igt-gpu-tools;2.3-1;amd64;ubuntu-resolute-main"
INTEL = "intel-gpu-tools;2.3-1;all;ubuntu-resolute-main"


def bus_error(text="org.freedesktop.DBus.Error.ServiceUnknown"):
    return GLib.Error.new_literal(Gio.dbus_error_quark(), text, Gio.DBusError.SERVICE_UNKNOWN)


class Step:
    """Antwort einer Transaktion: Package-Signale (info, id), ErrorCode-Werte, Exit; exit None: läuft bis Cancel."""
    def __init__(self, packages=(), errors=(), exit=packagekit.EXIT_SUCCESS):
        self.packages, self.errors, self.exit = list(packages), list(errors), exit


class FakeBus:
    def __init__(self, version=1, resolve=(IGT,), simulate=(12,), install=None):
        self.version = version  # eine Ausnahme: PackageKit fehlt
        # je Schritt die Antwort; Resolve meldet AVAILABLE (2), die Simulation die Info-Werte zu ihrer Paket-ID
        self.steps = {"resolve": Step([(2, i) for i in resolve]), "simulate": Step([(i, IGT) for i in simulate]),
                      "install": install or Step()}
        self.calls: list[tuple] = []  # (Pfad, Methode, Argumente) in der Reihenfolge der Aufrufe
        self.hints: dict[str, list[str]] = {}  # SetHints je Transaktion
        self.started = threading.Event()  # die echte Installation hat begonnen
        self._subs: dict[int, tuple] = {}
        self._lock = threading.Lock()

    # ---- Gio.DBusConnection ----
    def call_sync(self, name, path, iface, method, params, reply_type, flags, timeout, cancellable):
        assert name == packagekit.NAME and timeout > 0
        args = params.unpack() if params is not None else None
        with self._lock:
            self.calls.append((path, method, args))
            n = len(self.calls)
        if method == "Get":
            assert (path, iface, args) == (packagekit.PATH, "org.freedesktop.DBus.Properties",
                                           (packagekit.NAME, "VersionMajor"))
            if isinstance(self.version, Exception):
                raise self.version
            return GLib.Variant("(v)", (GLib.Variant("u", self.version),))
        if method == "CreateTransaction":
            return GLib.Variant("(o)", (f"/{n}",))
        assert iface == packagekit.TX
        if method == "SetHints":
            self.hints[path] = args[0]
        elif method == "Cancel":
            self._emit(path, [("ErrorCode", GLib.Variant("(us)", (packagekit.ERROR_CANCELLED, "cancelled"))),
                              ("Finished", GLib.Variant("(uu)", (packagekit.EXIT_CANCELLED, 0)))])
        else:
            assert method in ("Resolve", "InstallPackages")
            self._answer(path, method, args)
        return None

    def signal_subscribe(self, sender, iface, member, path, arg0, flags, callback):
        assert (sender, iface, member, arg0) == (packagekit.NAME, packagekit.TX, None, None)
        with self._lock:
            sub = len(self._subs) + 1
            self._subs[sub] = (path, GLib.MainContext.ref_thread_default(), callback)
        return sub

    def signal_unsubscribe(self, sub):
        with self._lock:
            del self._subs[sub]

    # ---- Ablauf ----
    def methods(self):
        """Die Aufrufe ohne Pfade: (Methode, Argumente)."""
        return [(m, a) for _, m, a in self.calls]

    def _answer(self, path, method, args):
        kind = "resolve" if method == "Resolve" else "simulate" if args[0] & packagekit.SIMULATE else "install"
        step = self.steps[kind]
        if kind == "install":
            self.started.set()
        signals = [("Package", GLib.Variant("(uss)", (info, pid, ""))) for info, pid in step.packages]
        signals += [("ErrorCode", GLib.Variant("(us)", (e, "detail"))) for e in step.errors]
        if step.exit is not None:
            signals.append(("Finished", GLib.Variant("(uu)", (step.exit, 7))))
        self._emit(path, signals)

    def _emit(self, path, signals):
        with self._lock:
            subs = [s for s in self._subs.values() if s[0] == path]
        for _, ctx, callback in subs:
            def deliver(*_, callback=callback):
                for signal, params in signals:
                    callback(self, ":1.7", path, packagekit.TX, signal, params)
                return False
            src = GLib.idle_source_new()
            src.set_callback(deliver)
            src.attach(ctx)  # wie Gio: im Kontext des Abonnenten, auch aus einem anderen Thread
