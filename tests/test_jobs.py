# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Aufträge ohne GTK: das Nachsehen nach dem Beenden, das pkexec-Kind von _run, die Freigabe durch das Tor.

Der Weg der Nachrichten in die Aufträge steht in test_shell_messages.py und test_shell_lifecycle.py. Kein Test startet
pkexec: die Freigabe läuft durch die echte actions.counters, aber _run ist ein Ersatz mit festem Exit-Code."""
import functools
import json
import subprocess
import threading
from types import SimpleNamespace

import pytest

from orbitop import actions, gate, jobs
from orbitop.sampler import Sampler
from tests.actions_helpers import COUNTERHELPER, PKEXEC, as_root, opener
from tests.counterhelper_helpers import make_tree
from tests.roots import VM
from tests.sampler_helpers import NoTools


@pytest.mark.parametrize("force,result,check", [(False, "sent", True), (True, "sent", False),
                                                (False, "denied", False), (False, "gone", False)])
def test_check_only_after_plain_sent(jobrig, force, result, check):
    jobrig.j._terminated(5, 6, force, result, "other")
    assert jobrig.glib.timeouts == ([(5, jobrig.j._check, (5, 6))] if check else [])


def test_check_reports_alive_from_thread(jobrig, monkeypatch):
    monkeypatch.setattr(jobs.actions, "is_alive", lambda pid, start: (pid, start) == (5, 6))
    assert jobrig.j._check(5, 6) is False  # einmalig
    t = jobrig.threads[0]
    t.target(*t.args)
    fn, args = jobrig.glib.idle[0]
    fn(*args)
    assert jobrig.sent == [json.dumps({"type": "terminate_check", "pid": 5, "alive": True})]


def test_run_timeout_kills_child(jobrig):
    with pytest.raises(subprocess.TimeoutExpired):
        jobrig.j._run(["sleep", "30"], timeout=0.05)
    assert jobrig.j._pkexec is None


def test_stop_while_pkexec_starts_leaves_no_child(jobrig, monkeypatch):
    """stop() genau während Popen: das Kind wird beendet oder nie gestartet. Sonst bliebe sein Dialog nach dem Ende
    von orbitop offen, und der Helfer handelte nach einer späteren Bestätigung."""
    starting, go, children = threading.Event(), threading.Event(), []

    class SlowPopen:
        def __init__(self, argv):
            starting.set()
            go.wait(5)  # der Start dauert: genau jetzt kommt stop()
            self.ended = threading.Event()
            children.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def terminate(self):
            self.ended.set()

        def kill(self):
            self.ended.set()

        def wait(self, timeout):
            if not self.ended.wait(timeout):
                raise subprocess.TimeoutExpired("helper", timeout)
            return -15
    monkeypatch.setattr(jobs.subprocess, "Popen", SlowPopen)
    out = []
    runner = threading.Thread(target=lambda: out.append(jobrig.j._run(["helper"], timeout=2)), daemon=True)
    runner.start()
    assert starting.wait(5)
    stopper = threading.Thread(target=jobrig.j.stop, daemon=True)
    stopper.start()
    stopper.join(0.2)  # vorher: stop() war schon fertig und fand nichts; jetzt wartet es, bis das Kind eingetragen ist
    go.set()
    stopper.join(5)
    runner.join(5)
    assert [r.returncode for r in out] == [-15] and children[0].ended.is_set() and jobrig.j._pkexec is None


def test_run_after_stop_starts_nothing(jobrig, monkeypatch):
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *a, **k: pytest.fail("nach stop() gestartet"))
    jobrig.j.stop()
    with pytest.raises(subprocess.SubprocessError):
        jobrig.j._run(["helper"], timeout=120)


# ---- Freigabe durch das Tor (B2.7, B2.1 „Unit (App)“) ----
class Tools:
    """Ersatz für den Sampler: intel und recheck_tools(); fail lässt recheck_tools scheitern."""
    def __init__(self):
        self.intel, self.rechecks, self.fail = True, 0, False

    def recheck_tools(self):
        self.rechecks += 1
        if self.fail:
            raise RuntimeError("x")


@pytest.fixture
def crig(jobrig, monkeypatch, tmp_path):
    """Freigabe über die echte actions.counters auf einem Testbaum ohne Merkdatei, mit vertrauenswürdiger Kette;
    _run ist der pkexec-Ersatz mit Exit-Code rc (oder wirft rc), now die Uhr des Tors."""
    make_tree(tmp_path)
    c = SimpleNamespace(rc=0, now=0.0, runs=[], reads=[], tools=Tools(), **vars(jobrig))
    c.j._gate = gate.Gate(lambda: c.now)

    def run(argv, timeout):
        c.runs.append((argv, timeout))
        if isinstance(c.rc, Exception):
            raise c.rc
        return subprocess.CompletedProcess(argv, c.rc)
    monkeypatch.setattr(c.j, "_run", run)
    monkeypatch.setattr(jobs.actions, "counters", functools.partial(actions.counters, root=str(tmp_path),
                                                                    lstat=as_root(tmp_path), opener=opener()))
    monkeypatch.setattr(jobs, "counters_payload", lambda intel: c.reads.append(intel) or {"read": len(c.reads)})
    return c


def ask(c, on=True):
    """Ein counters der Seite bis zur Antwort; Thread und idle-Aufrufe laufen hier sofort. Die Ergebniswörter."""
    c.sent.clear()
    c.j.counters(on, c.tools)
    while c.threads:
        t = c.threads.pop(0)
        t.target(*t.args)
    while c.glib.idle:
        fn, args = c.glib.idle.pop(0)
        fn(*args)
    return [json.loads(s)["result"] for s in c.sent]


@pytest.mark.parametrize("rc", [126, 127])
def test_gate_escalates(crig, rc):  # Review Focus 3: höchstens drei Dialoge, dann gesperrt bis zum Neustart
    crig.rc = rc
    want = "cancelled" if rc == 126 else "denied"
    assert ask(crig) == [want] and ask(crig) == ["busy"]
    crig.now = 9.9
    assert ask(crig) == ["busy"]
    crig.now = 10.0
    assert ask(crig) == [want]
    crig.now = 69.9
    assert ask(crig) == ["busy"]
    crig.now = 70.0
    assert ask(crig) == [want]
    crig.now = 1e9
    assert ask(crig) == ["locked"] and ask(crig, False) == ["locked"]
    assert len(crig.runs) == 3


def test_success_in_between_resets(crig):
    crig.rc = 126
    assert ask(crig) == ["cancelled"]
    crig.now, crig.rc = 10.0, 0
    assert ask(crig) == ["ok"]
    crig.rc = 126
    assert ask(crig) == ["cancelled"]  # sofort, und danach wieder nur 10 s
    crig.now, crig.rc = 20.0, 0
    assert ask(crig) == ["ok"]


def test_already_so_without_dialog_does_not_reset(crig):  # sonst öffnete eine Schleife alle 10 s einen Dialog
    crig.rc = 126
    assert ask(crig) == ["cancelled"]
    crig.now = 10.0
    assert ask(crig, False) == ["ok"] and len(crig.runs) == 1  # aus ist schon aus: kein pkexec
    assert crig.tools.rechecks == 1  # Q-1: neu erkannt wie nach einem echten ok, die Merkdatei kam etwa von außen
    assert ask(crig) == ["cancelled"]
    crig.now = 69.9
    assert ask(crig) == ["busy"]  # die zweite Ablehnung: 60 s


def test_already_so_twice_restarts_no_reader(crig):  # die Seite kann die Intel-Leser nicht ständig neu starten
    tools = NoTools()
    tools.changed = False  # Werkzeug und Fähigkeit wie erkannt
    crig.tools = Sampler(VM, tools=tools, uid=1000)
    assert ask(crig, False) == ["ok"] and ask(crig, False) == ["ok"]
    assert tools.rechecks == 0 and crig.runs == []
    tools.changed = True  # etwa die Fähigkeit von außen gesetzt
    assert ask(crig, False) == ["ok"] and tools.rechecks == 1


def test_signal_death_counts_as_refusal(crig):  # S-1: fail closed; die Seite sieht weiter nur error
    crig.rc = -15
    assert ask(crig) == ["error"] and ask(crig) == ["busy"]
    crig.now = 10.0
    assert ask(crig) == ["error"]
    crig.now = 69.9
    assert ask(crig) == ["busy"]  # die zweite Ablehnung: 60 s
    assert crig.tools.rechecks == 0


@pytest.mark.parametrize("rc,word", [(1, "error"), (2, "error"), (3, "unsafe"), (4, "partial"), (5, "error"),
                                     (120, "error"), (255, "error")])
def test_failed_exit_code_neither_resets_nor_counts(crig, rc, word):  # nur 0 setzt zurück, nur 126/127 zählen (B2.1)
    crig.rc = 126
    assert ask(crig) == ["cancelled"]
    crig.now, crig.rc = 10.0, rc
    assert ask(crig) == [word] and ask(crig) == [word]  # keine Wartezeit dazwischen
    crig.rc = 126
    assert ask(crig) == ["cancelled"]
    crig.now = 69.9
    assert ask(crig) == ["busy"]  # die zweite Ablehnung: nichts wurde zurückgesetzt


def test_two_jobs_give_one_run_and_one_busy(crig):
    crig.j.counters(True, crig.tools)
    crig.j.counters(True, crig.tools)
    crig.j.terminate(5, 6, False)  # busy als Ergebnis: sonst wartete die Seite ewig darauf (Schlussaudit)
    assert len(crig.threads) == 1 and [json.loads(s) for s in crig.sent] == [
        {"type": "counters_state", "counters": {"read": 1}, "result": "busy"},
        {"type": "terminate_result", "pid": 5, "result": "busy"}]
    t = crig.threads.pop()
    t.target(*t.args)
    fn, args = crig.glib.idle.pop()
    fn(*args)
    assert json.loads(crig.sent[-1])["result"] == "ok" and crig.runs == [([PKEXEC, COUNTERHELPER, "on"], 120)]


def test_counters_while_terminate_runs_is_busy(crig):
    crig.j.terminate(5, 6, False)  # der Thread wird nur aufgezeichnet, nie ausgeführt: kein echtes Beenden
    crig.j.counters(True, crig.tools)
    assert [json.loads(s)["result"] for s in crig.sent] == ["busy"]
    assert [t.target for t in crig.threads] == [crig.j._terminate_thread]


def test_permission_error_gives_error_and_frees_the_gate(crig):  # B2.1: kill() am Helfer, der schon als root läuft
    crig.rc = PermissionError(1, "x")
    assert ask(crig) == ["error"]
    crig.rc = 0
    assert ask(crig) == ["ok"] and len(crig.runs) == 2


def test_reply_carries_a_fresh_state_read_after_the_job(crig):
    crig.j.counters(True, crig.tools)
    t = crig.threads.pop()
    t.target(*t.args)
    assert crig.reads == []  # erst nach dem Auftrag gelesen (B2.1 „Ergebnis“), im Hauptthread
    fn, args = crig.glib.idle.pop()
    fn(*args)
    assert crig.reads == [True] and json.loads(crig.sent[-1])["counters"] == {"read": 1}


@pytest.mark.parametrize("rc,on,rechecks", [(0, True, 1), (1, True, 1), (2, True, 1), (3, True, 1), (4, True, 1),
                                            (126, True, 0), (OSError(), True, 0), (-15, True, 0), (0, False, 1)],
                         ids=["ok", "error", "usage", "unsafe", "partial", "cancelled", "oserror", "signal",
                              "already-so"])
def test_recheck_after_the_helper_ran_and_in_the_thread(crig, rc, on, rechecks):  # Q3, Q-1: auch nach „schon so“
    # Exit 1–4: der Helfer lief und kann einen Teil geändert haben, wie bisher neu erkennen (nur bei Änderung)
    crig.rc = rc
    crig.j.counters(on, crig.tools)
    t = crig.threads.pop()
    t.target(*t.args)
    assert crig.tools.rechecks == rechecks  # im Auftrags-Thread: recheck blockiert bis zu Sekunden


def test_failed_recheck_keeps_ok_and_frees_the_gate(crig):
    crig.tools.fail = True
    assert ask(crig) == ["ok"] and ask(crig) == ["ok"]


def test_counters_payload_adds_usable(monkeypatch):
    monkeypatch.setattr(jobs.counters, "state", lambda intel: {"marker": "off", "intel": intel})
    monkeypatch.setattr(jobs.actions, "counters_usable", lambda: "nopkexec")
    assert jobs.counters_payload(True) == {"marker": "off", "intel": True, "usable": "nopkexec"}
