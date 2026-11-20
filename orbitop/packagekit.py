# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Knopf „Installieren“: das Paket mit intel_gpu_top über PackageKit auf dem System-D-Bus (Security-Dokument 0.3.0,
B2.6). Nur Gio und nur PackageKit 1.x. Der Name steht fest je Paketmanager; die Seite liefert nie einen.

Ablauf: Resolve, dann die Simulation mit SIMULATE | ONLY_TRUSTED und einer Positivliste, dann die echte Installation
mit ONLY_TRUSTED, erst sie mit interactive=true. Install.run() läuft im Auftrags-Thread (jobs) und blockiert bis zum
Ende; die Signale jeder Transaktion kommen über einen eigenen GLib.MainContext dieses Threads. cancel() ruft der
Hauptthread beim Beenden."""
import contextlib
import threading

from gi.repository import Gio, GLib

from orbitop.app import INSTALL_HINT, package_manager

NAME, PATH = "org.freedesktop.PackageKit", "/org/freedesktop/PackageKit"
TX = "org.freedesktop.PackageKit.Transaction"
# Werte von PackageKit 1.3.1 = 1.4.0; auf main sind sie umsortiert, daher nur mit VersionMajor == 1
ONLY_TRUSTED, SIMULATE = 2, 4  # TransactionFlag; nie ALLOW_REINSTALL, ALLOW_DOWNGRADE oder andere
NOT_INSTALLED, NEWEST, ARCH = 1 << 3, 1 << 16, 1 << 18  # Filter für Resolve
ALLOWED = {11, 12}  # Info UPDATING, INSTALLING: alles andere in der Simulation (etwa 13 REMOVING) heißt Rückfall
EXIT_SUCCESS, EXIT_CANCELLED = 1, 3
ERROR_CANCELLED, ERROR_NOT_AUTHORIZED = 17, 48  # TRANSACTION_CANCELLED, NOT_AUTHORIZED: zählen als Ablehnung
# apt: erst igt-gpu-tools (Ubuntu 26.04 und Nachfolger), sonst intel-gpu-tools (Ubuntu 24.04, Debian 13; auf 26.04 ein
# Metapaket, das igt-gpu-tools mitbringt). Der letzte Name jeder Liste steht im Befehl für den Rückfall.
NAMES = {"apt-get": ("igt-gpu-tools", "intel-gpu-tools"), "dnf": ("igt-gpu-tools",),
         "zypper": ("intel-gpu-tools",), "pacman": ("intel-gpu-tools",)}
CALL_MS = 30_000  # ein Methodenaufruf; die Arbeit selbst meldet PackageKit über Signale
CANCEL_MS = 3_000  # Cancel beim Beenden hält das Herunterfahren höchstens so lange auf
WAIT_S = 600.0  # eine Transaktion bis Finished, mit Passwortdialog und Herunterladen; danach Cancel


def command(distro: str | None = None) -> str:
    """Befehl für den Rückfall (app.INSTALL_HINT), mit dem Namen, den es auf jedem Ziel des Paketmanagers gibt."""
    distro = distro or package_manager()
    return INSTALL_HINT[distro].format(package=NAMES[distro][-1])


def system_bus():
    return Gio.bus_get_sync(Gio.BusType.SYSTEM, None)


def _call(bus, path: str, iface: str, method: str, args: GLib.Variant | None, timeout=CALL_MS):
    reply = bus.call_sync(NAME, path, iface, method, args, None, Gio.DBusCallFlags.NONE, timeout, None)
    return reply.unpack() if reply is not None else None


class Install:
    """Ein Auftrag „Installieren“ mit den Ergebnissen von install_state (Klärung Q2): installed, denied (nicht
    berechtigt oder abgebrochen), failed oder unavailable (kein PackageKit 1.x, kein passendes Paket)."""

    def __init__(self, bus_factory=system_bus, distro: str | None = None):
        self._bus_factory = bus_factory
        self._names = NAMES[distro or package_manager()]
        self.interactive = False  # der letzte Schritt hat begonnen: er kann einen Passwortdialog gezeigt haben
        self._lock = threading.Lock()  # _bus, _tx und _cancelled zwischen run() und cancel()
        self._bus = self._tx = None
        self._cancelled = False

    def run(self) -> str:
        try:
            self._bus = bus = self._bus_factory()
            version = _call(bus, PATH, "org.freedesktop.DBus.Properties", "Get",
                            GLib.Variant("(ss)", (NAME, "VersionMajor")))[0]
            if type(version) is not int or version != 1:  # R6.5: PackageKit 2.x kodiert anders
                return "unavailable"
            package = self._resolve(bus)
        except GLib.Error:  # kein System-Bus, kein PackageKit
            return "unavailable"
        if package is None:  # nicht im Archiv oder schon installiert; jobs erkennt danach neu
            return "unavailable"
        try:
            packages, errors, end = self._transaction(bus, False, "InstallPackages", SIMULATE | ONLY_TRUSTED, [package])
            # leer: nichts zu tun (dnf5 auf Fedora 45 findet trotz NOT_INSTALLED auch Installiertes, Container-Probe)
            # oder ein Backend meldet nichts; beides kein Grund, ohne Positivliste zu installieren
            if errors or end != EXIT_SUCCESS or not packages or any(info not in ALLOWED for info, _, _ in packages):
                return "failed"
            self.interactive = True
            _, errors, end = self._transaction(bus, True, "InstallPackages", ONLY_TRUSTED, [package])
        except GLib.Error:
            return "failed"
        if ERROR_NOT_AUTHORIZED in errors or ERROR_CANCELLED in errors or end == EXIT_CANCELLED:
            return "denied"
        return "installed" if not errors and end == EXIT_SUCCESS else "failed"

    def cancel(self) -> None:
        """Aus dem Hauptthread: die laufende Transaktion abbrechen, keine neue mehr beginnen."""
        with self._lock:
            self._cancelled = True
            bus, path = self._bus, self._tx
        if path is not None:
            _cancel(bus, path)

    def _resolve(self, bus) -> str | None:
        """Paket-ID des ersten festen Namens, für den genau ein Package mit genau diesem Namen kommt (B2.6, 3)."""
        packages, errors, end = self._transaction(bus, False, "Resolve", NOT_INSTALLED | NEWEST | ARCH,
                                                  list(self._names))
        if errors or end != EXIT_SUCCESS:
            return None
        ids = [pid for _, pid, _ in packages if pid.count(";") == 3]  # name;version;arch;data
        for name in self._names:
            hits = [pid for pid in ids if pid.split(";")[0] == name]
            if len(hits) == 1:
                return hits[0]
        return None

    def _transaction(self, bus, interactive: bool, method: str, flags: int, names: list[str]
                     ) -> tuple[list, list, int | None]:
        """Eine neue Transaktion bis Finished: (Package-Signale, ErrorCode-Werte, Exit; None nach WAIT_S). names: die
        Namen für Resolve, sonst die Paket-IDs."""
        ctx = GLib.MainContext.new()
        ctx.push_thread_default()  # Gio liefert die Signale dieses Abonnements nur an diesen Kontext
        try:
            return self._run_transaction(bus, ctx, interactive, method, flags, names)
        finally:
            ctx.pop_thread_default()

    def _run_transaction(self, bus, ctx, interactive, method, flags, names):
        path = _call(bus, PATH, NAME, "CreateTransaction", None)[0]
        packages, errors, end = [], [], []

        def on_signal(_bus, _sender, _path, _iface, signal, params):
            if signal == "Package":
                packages.append(params.unpack())
            elif signal == "ErrorCode":
                errors.append(params.unpack()[0])
            elif signal == "Finished":
                end.append(params.unpack()[0])
        # Absender ist der Name von PackageKit: GLib ab 2.80.1 prüft dessen Besitzer (CVE-2024-34397)
        sub = bus.signal_subscribe(NAME, TX, None, path, None, Gio.DBusSignalFlags.NONE, on_signal)
        timeout = GLib.timeout_source_new(int(WAIT_S * 1000))
        timeout.set_callback(lambda *_: end.append(None) or False)
        timeout.attach(ctx)
        try:
            with self._lock:
                if self._cancelled:  # orbitop endet: keine neue Transaktion
                    return packages, [ERROR_CANCELLED], EXIT_CANCELLED
            _call(bus, path, TX, "SetHints", GLib.Variant("(as)", ([f"interactive={str(interactive).lower()}"],)))
            _call(bus, path, TX, method, GLib.Variant("(tas)", (flags, names)))
            with self._lock:  # erst jetzt läuft sie: ein Cancel davor lehnt PackageKit ab (NoRole, Probe 26.04)
                self._tx = path
                cancelled = self._cancelled
            if cancelled:  # cancel() kam während der Aufrufe und fand noch keine Transaktion
                _cancel(bus, path)
            while not end:
                ctx.iteration(True)
        finally:
            with self._lock:
                self._tx = None
            timeout.destroy()
            bus.signal_unsubscribe(sub)
        if end[0] is None:  # Zeit um, etwa ein offen gelassener Dialog: nicht später noch installieren
            _cancel(bus, path)
        return packages, errors, end[0]


def _cancel(bus, path: str) -> None:
    with contextlib.suppress(GLib.Error):  # schon zu Ende, oder PackageKit ist weg
        _call(bus, path, TX, "Cancel", None, CANCEL_MS)
