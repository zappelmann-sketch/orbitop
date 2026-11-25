# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Ablauf über PackageKit (Security-Dokument 0.3.0, B2.6, Pflicht-Tests „Unit (Fake-Bus)“): Resolve, Simulation mit
der Positivliste, dann die echte Installation mit ONLY_TRUSTED. Nur der Fake-Bus, nie der System-Bus des Rechners."""
import gc
import threading

import pytest

from orbitop import packagekit
from tests.packagekit_helpers import GI_ASYNCIO, IGT, INTEL, FakeBus, Step, bus_error, short_wait  # noqa: F401

pytestmark = GI_ASYNCIO


def install(bus, distro="apt-get"):
    return packagekit.Install(bus_factory=lambda: bus, distro=distro).run()


def installs(bus):
    """Die Flags jedes InstallPackages."""
    return [a[0] for m, a in bus.methods() if m == "InstallPackages"]


def test_constants():  # PackageKit 1.3.1 = 1.4.0 (B2.6, Tabelle „Werte“); im Container gegen PackageKit-glib geprüft
    assert (packagekit.ONLY_TRUSTED, packagekit.SIMULATE) == (2, 4)
    assert (packagekit.NOT_INSTALLED, packagekit.NEWEST, packagekit.ARCH) == (1 << 3, 1 << 16, 1 << 18)
    assert packagekit.ALLOWED == {11, 12}  # UPDATING, INSTALLING
    assert (packagekit.EXIT_SUCCESS, packagekit.EXIT_CANCELLED) == (1, 3)
    assert (packagekit.ERROR_CANCELLED, packagekit.ERROR_NOT_AUTHORIZED) == (17, 48)
    assert (packagekit.NAME, packagekit.PATH, packagekit.TX) == (
        "org.freedesktop.PackageKit", "/org/freedesktop/PackageKit", "org.freedesktop.PackageKit.Transaction")


def test_names_per_package_manager():  # B2.6 „Paketnamen“ (P1 bis P4; M-12)
    assert packagekit.NAMES == {"apt-get": ("igt-gpu-tools", "intel-gpu-tools"), "dnf": ("igt-gpu-tools",),
                                "zypper": ("intel-gpu-tools",), "pacman": ("intel-gpu-tools",)}


def test_flow_resolve_simulate_install():
    bus = FakeBus()
    assert install(bus) == "installed"
    flt = packagekit.NOT_INSTALLED | packagekit.NEWEST | packagekit.ARCH
    assert bus.methods() == [
        ("Get", ("org.freedesktop.PackageKit", "VersionMajor")),
        ("CreateTransaction", None), ("SetHints", (["interactive=false"],)),
        ("Resolve", (flt, ["igt-gpu-tools", "intel-gpu-tools"])),
        ("CreateTransaction", None), ("SetHints", (["interactive=false"],)),
        ("InstallPackages", (packagekit.SIMULATE | packagekit.ONLY_TRUSTED, [IGT])),
        ("CreateTransaction", None), ("SetHints", (["interactive=true"],)),
        ("InstallPackages", (packagekit.ONLY_TRUSTED, [IGT]))]


def test_each_step_has_its_own_transaction_with_hints_first():
    bus = FakeBus()
    install(bus)
    steps = [(p, m) for p, m, _ in bus.calls if m != "Get"]
    paths = [p for p, m in steps if m in ("Resolve", "InstallPackages")]
    assert len(set(paths)) == 3
    assert all(steps[i - 1] == (p, "SetHints") for i, (p, m) in enumerate(steps) if m in ("Resolve", "InstallPackages"))


def test_flags_contain_only_bits_2_and_4():
    bus = FakeBus()
    install(bus)
    assert installs(bus) == [6, 2] and all(f & ~(2 | 4) == 0 for f in installs(bus))


def test_interactive_true_only_in_the_last_step():
    bus = FakeBus()
    install(bus)
    assert list(bus.hints.values()) == [["interactive=false"], ["interactive=false"], ["interactive=true"]]


def test_authorized_without_dialog_ends_installed():  # I-2, E3: Fedora installiert für Admins ohne Dialog
    bus = FakeBus(install=Step())  # Finished(success) gleich nach dem Aufruf: nichts wartet auf einen Dialog
    job = packagekit.Install(bus_factory=lambda: bus, distro="dnf")
    assert job.run() == "installed" and job.interactive


# ---- Resolve ----
@pytest.mark.parametrize("found,distro,want", [
    ((IGT, INTEL), "apt-get", IGT),  # Ubuntu 26.04: beide, intel-gpu-tools ist dort ein Metapaket
    ((INTEL,), "apt-get", INTEL),  # Ubuntu 24.04, Debian 13
    ((INTEL, IGT), "apt-get", IGT),  # die Reihenfolge der Namen zählt, nicht die der Signale
    ((IGT,), "dnf", IGT), ((INTEL,), "zypper", INTEL), ((INTEL,), "pacman", INTEL)])
def test_first_fixed_name_with_one_hit_wins(found, distro, want):
    bus = FakeBus(resolve=found)
    bus.steps["simulate"] = Step([(12, want)])
    assert install(bus, distro) == "installed" and bus.methods()[-1] == ("InstallPackages", (2, [want]))
    assert bus.methods()[3][1][1] == list(packagekit.NAMES[distro])


@pytest.mark.parametrize("found", [(), (IGT, IGT.replace("2.3-1", "2.4-1")), ("igt-gpu-tools-extra;1;amd64;x",),
                                   ("evil;1;amd64;x",), ("igt-gpu-tools",)],
                         ids=["none", "two", "longer-name", "wrong-name", "no-fields"])
def test_resolve_without_exactly_one_match_falls_back(found):
    bus = FakeBus(resolve=found)
    assert install(bus, "dnf") == "unavailable"
    assert installs(bus) == []


def test_two_hits_for_the_first_name_take_the_second():
    bus = FakeBus(resolve=(IGT, IGT.replace("amd64", "i386"), INTEL))
    bus.steps["simulate"] = Step([(12, INTEL)])
    assert install(bus) == "installed" and installs(bus) == [6, 2]
    assert bus.methods()[-1] == ("InstallPackages", (2, [INTEL]))


@pytest.mark.parametrize("step", [Step(errors=[8]), Step(exit=2)], ids=["error-code", "finished-failed"])
def test_failed_resolve_falls_back(step):
    bus = FakeBus()
    bus.steps["resolve"] = Step([(2, IGT)], step.errors, step.exit)
    assert install(bus) == "unavailable" and installs(bus) == []


# ---- Simulation: Positivliste ----
@pytest.mark.parametrize("info", [13, 15, 19, 20, 10, 18, 2, 99])  # REMOVING, OBSOLETING, REINSTALLING, DOWNGRADING …
def test_simulation_outside_the_allowlist_falls_back_without_install(info):
    bus = FakeBus(simulate=(12, info))
    job = packagekit.Install(bus_factory=lambda: bus, distro="apt-get")
    assert job.run() == "failed" and installs(bus) == [6] and not job.interactive


def test_empty_simulation_falls_back():  # dnf5 (Fedora 45) löst auch Installiertes auf, die Simulation ist dann leer
    bus = FakeBus(simulate=())
    assert install(bus) == "failed" and installs(bus) == [6]


def test_simulation_with_updating_is_allowed():
    assert install(FakeBus(simulate=(12, 11))) == "installed"


@pytest.mark.parametrize("step", [Step([(12, IGT)], errors=[30]), Step([(12, IGT)], exit=2),
                                  Step([(12, IGT)], exit=8)], ids=["error-code", "failed", "need-untrusted"])
def test_simulation_error_or_failure_falls_back(step):
    bus = FakeBus()
    bus.steps["simulate"] = step
    assert install(bus) == "failed" and installs(bus) == [6]


# ---- echte Installation ----
@pytest.mark.parametrize("step", [Step(errors=[48], exit=2), Step(errors=[17], exit=3), Step(exit=3)],
                         ids=["not-authorized", "cancelled-error", "cancelled-exit"])
def test_not_authorized_or_cancelled_is_denied(step):
    bus = FakeBus(install=step)
    assert install(bus) == "denied" and installs(bus) == [6, 2]  # kein zweiter Versuch ohne ONLY_TRUSTED


@pytest.mark.parametrize("step", [Step(errors=[50], exit=2), Step(exit=2), Step(exit=4), Step(errors=[13])],
                         ids=["unsigned", "failed", "key-required", "error-then-success"])
def test_other_install_failures_are_failed(step):
    bus = FakeBus(install=step)
    assert install(bus) == "failed" and installs(bus) == [6, 2]


@pytest.mark.parametrize("version", [2, 0, bus_error()], ids=["two", "zero", "no-packagekit"])
def test_version_other_than_one_falls_back_without_call(version):  # R6.5: PackageKit 2.x kodiert anders
    bus = FakeBus(version=version)
    assert install(bus) == "unavailable" and [m for m, _ in bus.methods()] == ["Get"]


def test_no_system_bus_is_unavailable():
    def no_bus():
        raise bus_error("no bus")
    assert packagekit.Install(bus_factory=no_bus, distro="apt-get").run() == "unavailable"


@pytest.mark.parametrize("method,want", [("Resolve", "unavailable"), ("InstallPackages", "failed")])
def test_bus_error_in_a_step(method, want):
    bus = FakeBus()
    real = bus.call_sync

    def call_sync(*a):
        if a[3] == method:
            raise bus_error("org.freedesktop.PackageKit.Transaction.Refused")
        return real(*a)
    bus.call_sync = call_sync
    assert install(bus) == want


# ---- Zeitgrenze und Abbruch ----
def test_timeout_cancels_the_transaction(monkeypatch):
    monkeypatch.setattr(packagekit, "WAIT_S", 0.05)
    bus = FakeBus(install=Step(exit=None))  # etwa ein offen gelassener Dialog
    assert install(bus) == "failed"
    assert [m for m, _ in bus.methods()][-2:] == ["InstallPackages", "Cancel"]


def test_cancel_from_another_thread_ends_the_install():  # beim Beenden von orbitop (Jobs.stop)
    bus = FakeBus(install=Step(exit=None))
    job = packagekit.Install(bus_factory=lambda: bus, distro="apt-get")
    out = []
    t = threading.Thread(target=lambda: out.append(job.run()))
    t.start()
    assert bus.started.wait(5)
    job.cancel()
    t.join(5)
    assert out == ["denied"] and bus.calls[-1][1] == "Cancel"
    assert bus.calls[-1][0] == bus.calls[-2][0]  # die laufende Transaktion, nicht eine neue


@pytest.mark.parametrize("during,tail", [
    ("SetHints", ["SetHints"]),  # Review T3 M-1 (0.4.0): kein Schritt mehr; ohne Rolle kein Cancel (NoRole)
    ("InstallPackages", ["SetHints", "InstallPackages", "Cancel"])], ids=["SetHints", "InstallPackages"])
def test_cancel_during_the_calls_reaches_the_transaction_after_them(during, tail):
    bus = FakeBus(install=Step(exit=None))  # cancel() kommt, bevor es eine laufende Transaktion gibt
    job = packagekit.Install(bus_factory=lambda: bus, distro="apt-get")
    real = bus.call_sync

    def call_sync(*a):
        if a[3] == during and job.interactive:
            job.cancel()
        return real(*a)
    bus.call_sync = call_sync
    assert job.run() == "denied"
    assert [m for _, m, _ in bus.calls[-len(tail) - 1:]] == ["CreateTransaction", *tail]
    assert len({p for p, _, _ in bus.calls[-len(tail):]}) == 1


def test_cancel_before_the_run_makes_no_bus_call():  # C2 (#37): Get VersionMajor weckte packagekitd beim Beenden
    bus, opened = FakeBus(), []
    job = packagekit.Install(bus_factory=lambda: opened.append(bus) or bus, distro="apt-get")
    job.cancel()
    assert job.run() == "denied" and opened == [] and bus.calls == []


def test_cancel_before_a_step_starts_no_new_transaction():  # Fix 1/5: nicht einmal CreateTransaction
    bus = FakeBus()
    job = packagekit.Install(bus_factory=lambda: bus, distro="apt-get")
    real = bus.signal_unsubscribe

    def signal_unsubscribe(sub):  # Resolve ist zu Ende, die Simulation hat noch nicht begonnen
        job.cancel()
        real(sub)
    bus.signal_unsubscribe = signal_unsubscribe
    assert job.run() == "failed"
    assert [m for m, _ in bus.methods()] == ["Get", "CreateTransaction", "SetHints", "Resolve"]


@pytest.mark.parametrize("n,want", [(1, "unavailable"), (2, "failed"), (3, "denied")],
                         ids=["resolve", "simulate", "install"])
def test_cancel_during_create_transaction_makes_no_call_on_it(n, want):  # C2 (#36)
    bus = FakeBus()
    job = packagekit.Install(bus_factory=lambda: bus, distro="apt-get")
    real = bus.call_sync

    def call_sync(*a):
        reply = real(*a)
        if a[3] == "CreateTransaction" and [m for m, _ in bus.methods()].count("CreateTransaction") == n:
            job.cancel()  # die Antwort ist unterwegs: cancel() findet noch keine Transaktion
        return reply
    bus.call_sync = call_sync
    assert job.run() == want
    assert bus.calls[-1][1] == "CreateTransaction"  # kein SetHints, kein Schritt, kein Cancel an ihr


def test_each_transaction_releases_its_callback():  # Fix 1/4: sonst hielte jeder Kontext Rückruf und Listen
    bus = FakeBus()
    assert install(bus) == "installed"
    gc.collect()
    assert len(bus.callbacks) == 3 and [r() for r in bus.callbacks] == [None] * 3


def test_cancel_without_a_job_does_nothing():
    packagekit.Install(bus_factory=lambda: FakeBus(), distro="apt-get").cancel()


# ---- Befehl für den Rückfall ----
@pytest.mark.parametrize("distro,want", [("apt-get", "sudo apt install intel-gpu-tools"),
                                         ("dnf", "sudo dnf install igt-gpu-tools"),
                                         ("zypper", "sudo zypper install intel-gpu-tools"),
                                         ("pacman", "sudo pacman -S intel-gpu-tools")])
def test_fallback_command(distro, want):  # app.INSTALL_HINT; apt: intel-gpu-tools gibt es auf jedem apt-Ziel
    assert packagekit.command(distro) == want
