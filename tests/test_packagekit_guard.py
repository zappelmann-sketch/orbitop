# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""install_tool in den Aufträgen (B2.7, B2.6 „Unit“): harte Vorbedingung, Tor und wachsende Sperre, einmal je Sitzung,
neu erkennen im Auftrags-Thread, Cancel beim Beenden. PackageKit ist immer der Fake-Bus."""
import json
import threading
from types import SimpleNamespace

import pytest
from gi.repository import Gio

from orbitop import gate, jobs, packagekit
from orbitop.messages import parse_message
from orbitop.sampler import Sampler
from tests.packagekit_helpers import GI_ASYNCIO, FakeBus, Step, bus_error, short_wait  # noqa: F401
from tests.roots import VM
from tests.sampler_helpers import NoTools

pytestmark = GI_ASYNCIO


class Tools:
    """Ersatz für den Sampler: intel, igt_missing() und recheck_tools(); rechecks zählt, fail lässt es scheitern."""
    def __init__(self):
        self.intel, self.missing, self.rechecks, self.fail = True, True, 0, False

    def igt_missing(self):
        return self.missing

    def recheck_tools(self):
        self.rechecks += 1
        if self.fail:
            raise RuntimeError("x")


@pytest.fixture
def irig(threads, monkeypatch):
    """Jobs mit GLib-Attrappe, Uhr für das Tor und dem Fake-Bus; usable ist counters_usable, refreshes zählt refresh."""
    sent, glib = [], SimpleNamespace(idle=[])
    glib.idle_add = lambda fn, *args: glib.idle.append((fn, args))
    r = SimpleNamespace(sent=sent, glib=glib, threads=threads, now=0.0, bus=FakeBus(), tools=Tools(), refreshes=[],
                        usable="yes", j=jobs.Jobs(sent.append, glib))
    r.j._gate = gate.Gate(lambda: r.now)
    real = packagekit.Install  # jobs.packagekit ist dasselbe Modul
    monkeypatch.setattr(jobs.packagekit, "Install", lambda: real(bus_factory=lambda: r.bus, distro="apt-get"))
    monkeypatch.setattr(jobs.packagekit, "command", lambda: "sudo apt install intel-gpu-tools")
    monkeypatch.setattr(jobs.actions, "counters_usable", lambda: r.usable)
    return r


def run_jobs(r):
    while r.threads:
        t = r.threads.pop(0)
        t.target(*t.args)
    while r.glib.idle:
        fn, args = r.glib.idle.pop(0)
        fn(*args)


def ask(r):
    """Ein install_tool der Seite bis zur Antwort; die Ergebniswörter."""
    r.sent.clear()
    r.j.install_tool(r.tools, lambda: r.refreshes.append(len(r.sent)))
    run_jobs(r)
    return [json.loads(s)["result"] for s in r.sent]


def interactive(r):
    return [a for m, a in r.bus.methods() if m == "InstallPackages" and a[0] == packagekit.ONLY_TRUSTED]


def test_installed_rechecks_in_the_thread_then_refreshes(irig):  # Q3 ohne Neustart; recheck nie im Hauptthread
    irig.j.install_tool(irig.tools, lambda: irig.refreshes.append(len(irig.sent)))
    t = irig.threads.pop()
    t.target(*t.args)
    assert irig.tools.rechecks == 1 and irig.sent == []
    run_jobs(irig)
    assert [json.loads(s) for s in irig.sent] == [{"type": "install_state", "result": "installed"}]
    assert irig.refreshes == [1]  # danach der frische Stand: Hinweise, Zeilen der Freigabe


def test_second_install_after_success_makes_no_call(irig):  # B2.6, B2.7: einmal je Sitzung
    assert ask(irig) == ["installed"]
    calls = len(irig.bus.calls)
    # closed, nicht locked: das ist die Sperre nach Ablehnungen, die Seite zeigte sonst „zu oft abgelehnt“
    assert ask(irig) == ["closed"] and len(irig.bus.calls) == calls and irig.tools.rechecks == 1


@pytest.mark.parametrize("bus,want", [(FakeBus(), "installed"), (FakeBus(install=Step(exit=2)), "failed"),
                                      (FakeBus(simulate=(13,)), "failed"), (FakeBus(resolve=()), "unavailable"),
                                      (FakeBus(version=bus_error()), "unavailable")],
                         ids=["installed", "failed-install", "failed-simulation", "unavailable", "no-packagekit"])
def test_session_ends_after_a_terminal_result(irig, bus, want):  # Fix 1/2: keine Schleife über das root-packagekitd
    irig.bus = bus
    assert irig.j.closed is False
    assert ask(irig) == [want]
    assert irig.j.closed is True  # 0.4.0 (Triage #31): init meldet das, die Seite zeigt nach Neuladen gleich den Befehl
    with pytest.raises(AttributeError):  # nur lesbar: zu ist die Sitzung allein nach einem Lauf
        irig.j.closed = False
    calls = len(bus.calls)
    irig.now = 1e9  # keine Wartezeit mehr: nur das Ende der Sitzung hält auf
    assert [ask(irig)[0] for _ in range(5)] == ["closed"] * 5
    assert len(bus.calls) == calls and irig.threads == [] and irig.refreshes == [1]
    assert irig.j._gate.begin("counters") is None  # das Ende der Sitzung sperrt nicht wie zu viele Ablehnungen


@pytest.mark.parametrize("attr,value", [("intel", False), ("missing", False), ("usable", "nohelper")],
                         ids=["no-intel", "hint-not-active", "no-package"])
def test_precondition_missing_makes_no_call(irig, attr, value):  # B2.7; ohne Paket fehlt auch der Knopf
    setattr(irig.tools if attr != "usable" else irig, attr, value)
    assert ask(irig) == ["unavailable"]
    assert irig.bus.calls == [] and irig.tools.rechecks == 0 and irig.refreshes == []
    assert ask(irig) == ["unavailable"]  # zählt nicht als Ablehnung: keine Wartezeit


def test_foreign_pkexec_does_not_block_the_install(irig):  # PackageKit braucht kein pkexec
    irig.usable = "nopkexec"
    assert ask(irig) == ["installed"]


def test_name_never_comes_from_the_message(irig):
    msg = parse_message('{"type":"install_tool","package":"evil","names":["evil"]}')
    assert msg == {"type": "install_tool"}
    assert ask(irig) == ["installed"]
    resolved = [a[1] for m, a in irig.bus.methods() if m == "Resolve"]
    assert resolved == [["igt-gpu-tools", "intel-gpu-tools"]]
    assert all("evil" not in str(a) for _, a in irig.bus.methods())


def test_denied_escalates_like_counters(irig):  # M-10: 10 s, 60 s, dann gesperrt bis zum Neustart
    irig.bus = FakeBus(install=Step(errors=[packagekit.ERROR_NOT_AUTHORIZED], exit=2))
    assert ask(irig) == ["denied"] and ask(irig) == ["busy"]
    irig.now = 9.9
    assert ask(irig) == ["busy"] and irig.j._gate.begin("counters") == "busy"  # ein Zähler für beide Arten (R9)
    irig.now = 10.0
    assert ask(irig) == ["denied"]
    irig.now = 69.9
    assert ask(irig) == ["busy"]
    irig.now = 70.0
    assert ask(irig) == ["denied"]
    irig.now = 1e9
    assert ask(irig) == ["locked"] and irig.j._gate.begin("counters") == "locked"
    assert len(interactive(irig)) == 3  # höchstens drei Dialoge
    assert irig.j.closed is False  # abgelehnt schließt die Sitzung nicht, locked hat seinen eigenen Text


def test_cancelled_counts_as_refusal(irig):
    irig.bus = FakeBus(install=Step(exit=packagekit.EXIT_CANCELLED))
    assert ask(irig) == ["denied"] and ask(irig) == ["busy"]


def test_failure_after_the_interactive_step_counts_as_refusal(irig):  # fail closed: es kann ein Dialog gewesen sein
    irig.bus = FakeBus(install=Step(exit=2))
    assert ask(irig) == ["failed"]
    g = irig.j._gate
    assert g.begin("counters") == "busy"  # die Wartezeit nach einer Ablehnung
    irig.now = 10.0
    assert g.begin("counters") is None


@pytest.mark.parametrize("bus,want", [(FakeBus(resolve=()), "unavailable"), (FakeBus(simulate=(13,)), "failed"),
                                      (FakeBus(version=2), "unavailable")], ids=["resolve", "simulate", "version"])
def test_fallback_before_the_interactive_step_does_not_count(irig, bus, want):  # dort fragt PackageKit nie
    irig.bus = bus
    assert ask(irig) == [want] and interactive(irig) == []
    assert irig.j._gate.begin("counters") is None


def test_silent_install_does_not_reset_the_count(irig):  # Fix 1/1: sonst fünf statt drei Dialoge für counters (R9)
    g, dialogs = irig.j._gate, 0

    def refuse_counters():
        nonlocal dialogs
        assert g.begin("counters") is None
        dialogs += 1
        g.end("counters", "refused")
    refuse_counters()
    irig.now = 10.0
    refuse_counters()
    irig.now = 70.0
    assert ask(irig) == ["installed"]  # Fedora: ohne Dialog (I-2)
    refuse_counters()
    irig.now = 1e9
    assert g.begin("counters") == "locked" and dialogs == 3


def test_busy_while_another_job_runs(irig):
    irig.j.terminate(5, 6, False)  # nur aufgezeichnet, nie ausgeführt
    irig.j.install_tool(irig.tools, lambda: None)
    assert [json.loads(s) for s in irig.sent] == [{"type": "install_state", "result": "busy"}]
    assert irig.bus.calls == [] and len(irig.threads) == 1


@pytest.mark.parametrize("where", ["install", "recheck"])
def test_exception_gives_an_answer_and_frees_the_gate(irig, monkeypatch, where):
    if where == "install":
        monkeypatch.setattr(irig.bus, "call_sync", lambda *a: 1 / 0)  # keine GLib.Error: run() selbst wirft
        want = ["failed", "closed"]
    else:
        irig.tools.fail = True
        want = ["installed", "closed"]
    assert [ask(irig)[0], ask(irig)[0]] == want and irig.j._gate.begin("counters") is None


def test_stop_cancels_a_running_install(irig):  # beim Beenden: kein Dialog und keine Installation ohne orbitop
    irig.bus = FakeBus(install=Step(exit=None))
    irig.j.install_tool(irig.tools, lambda: None)
    t = irig.threads.pop()
    worker = threading.Thread(target=t.target, args=t.args)
    worker.start()
    assert irig.bus.started.wait(5)
    irig.j.stop()
    worker.join(5)
    assert not worker.is_alive() and irig.bus.methods()[-1] == ("Cancel", None)
    run_jobs(irig)
    assert json.loads(irig.sent[-1])["result"] == "denied" and irig.j._install is None
    irig.j.stop()  # ohne laufenden Auftrag: nichts
    assert irig.bus.methods()[-1] == ("Cancel", None) and len(irig.bus.calls) == 11


def test_quit_right_after_install_tool_cancels_the_job(irig):  # Fix 1/3: stop() vor dem Start des Threads
    irig.j.install_tool(irig.tools, lambda: None)
    irig.j.stop()  # quit gleich danach, der Thread lief noch nicht
    run_jobs(irig)
    assert irig.bus.methods() == [] and irig.j._install is None  # C2 (#37): auch kein Get VersionMajor


@pytest.mark.parametrize("intel,usable,want", [(True, "yes", True), (True, "nopkexec", True),
                                               (True, "nohelper", False), (False, "yes", False)])
def test_install_payload(irig, intel, usable, want):  # Review Focus 5: ohne Paket kein Knopf, nur der Befehl
    irig.usable = usable
    assert jobs.install_payload(intel) == {"usable": want, "command": "sudo apt install intel-gpu-tools"}


def test_sampler_igt_missing_follows_the_hint():
    class Hinted(NoTools):
        def __init__(self, hints):
            super().__init__()
            self.list = hints

        def hints(self):
            return self.list
    assert Sampler(VM, tools=Hinted(["hint.igt_missing"]), uid=1000).igt_missing()
    assert not Sampler(VM, tools=Hinted(["hint.igt_noperm", "hint.nvsmi_missing"]), uid=1000).igt_missing()


def test_tests_never_reach_the_system_bus():  # Wächter in conftest.py: der Default von Install
    with pytest.raises(AssertionError, match="System-Bus"):
        packagekit.system_bus()
    with pytest.raises(AssertionError, match="System-Bus"):
        Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
