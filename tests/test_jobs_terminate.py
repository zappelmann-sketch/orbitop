# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""terminate durch das Tor (Schlussaudit 0.3.0, B2.7, R9): Ablehnungen fremder Prozesse eskalieren wie counters und
install_tool, der eigene Prozess ohne pkexec zählt nie. Eigene Datei, weil test_jobs.py sonst über 300 Zeilen wüchse.

Kein Test startet pkexec oder sendet ein Signal: _run und killhelper.send sind Ersatz, die Prozesse stehen in einem
Testbaum, und die echte actions.terminate prüft Kette und pkexec über Attrappen."""
import functools
import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from orbitop import actions, gate, jobs
from tests.actions_helpers import as_root, foreign_proc, opener

FOREIGN, OWN, START = 4242, 4343, 77


@pytest.fixture
def trig(jobrig, monkeypatch, tmp_path):
    """rc: Exit-Code des pkexec-Ersatzes; own: was killhelper.send beim eigenen Prozess tut; now: die Uhr des Tors."""
    foreign_proc(tmp_path, FOREIGN, START, "S")
    foreign_proc(tmp_path, OWN, START, "S")
    (tmp_path / "proc" / str(OWN) / "status").write_text(f"Name:\tx\nUid:\t{os.getuid()}\t0\t0\t0\n")
    t = SimpleNamespace(rc=126, own=0, now=0.0, runs=[], tree=tmp_path, **vars(jobrig))
    t.j._gate = gate.Gate(lambda: t.now)

    def send(pid, start, sig, root):
        if isinstance(t.own, Exception):
            raise t.own
        return t.own

    def run(argv, timeout):  # rc als Ausnahme: was Jobs._run wirft, etwa TimeoutExpired nach p.kill()
        t.runs.append(argv)
        if isinstance(t.rc, Exception):
            raise t.rc
        return subprocess.CompletedProcess(argv, t.rc)
    monkeypatch.setattr(actions.killhelper, "send", send)
    monkeypatch.setattr(t.j, "_run", run)
    monkeypatch.setattr(jobs.actions, "terminate", functools.partial(actions.terminate, root=str(tmp_path),
                                                                     lstat=as_root(tmp_path), opener=opener()))
    monkeypatch.setattr(jobs.actions, "is_own", functools.partial(actions.is_own, root=str(tmp_path)))
    return t


def run_jobs(t):
    """Thread und idle-Aufrufe laufen hier sofort, wie in der Hülle nacheinander."""
    while t.threads:
        th = t.threads.pop(0)
        th.target(*th.args)
    while t.glib.idle:
        fn, args = t.glib.idle.pop(0)
        fn(*args)


def kill(t, pid=FOREIGN):
    """Ein terminate der Seite bis zur Antwort; die Ergebniswörter."""
    t.sent.clear()
    t.j.terminate(pid, START, False)
    run_jobs(t)
    return [json.loads(s)["result"] for s in t.sent]


TIMEOUT = subprocess.TimeoutExpired("pkexec", 120)  # Dialog bis zum Ablauf offen gelassen (N1)


@pytest.mark.parametrize("rc,word", [(126, "denied"), (127, "denied"), (-15, "error"), (TIMEOUT, "denied")],
                         ids=["126", "127", "signal", "timeout"])
def test_refused_terminates_escalate_until_locked(trig, rc, word):
    """Höchstens drei Dialoge bis zum Neustart; dazwischen 10 s und 60 s. Die Seite bekommt busy oder locked als
    Ergebnis, sonst wartete sie ewig. Der Tod von pkexec durch ein Signal zählt wie bei counters (fail closed)."""
    trig.rc = rc
    assert kill(trig) == [word] and kill(trig) == ["busy"]
    trig.now = 10.0
    assert kill(trig) == [word]
    trig.now = 69.9
    assert kill(trig) == ["busy"]
    trig.now = 70.0
    assert kill(trig) == [word]
    trig.now = 1e9
    assert kill(trig) == ["locked"] and len(trig.runs) == 3


@pytest.mark.parametrize("own,word", [(PermissionError(1, "x"), "denied"), (0, "sent")])
def test_own_process_without_pkexec_never_counts(trig, own, word):
    trig.own = own
    assert [kill(trig, OWN) for _ in range(4)] == [[word]] * 4 and trig.runs == []
    assert kill(trig) == ["denied"]  # die erste Ablehnung: danach nur 10 s, nicht gesperrt
    trig.now = 10.0
    assert kill(trig) == ["denied"] and len(trig.runs) == 2


@pytest.mark.parametrize("rc", [126, TIMEOUT], ids=["126", "timeout"])
def test_own_process_is_never_locked_and_never_waits(trig, rc):
    """Nachtrag: Den eigenen Prozess beendet orbitop ohne pkexec und ohne Dialog, die Sperre hätte dort keinen Nutzen.
    Er wartet nie die 10 s oder 60 s und ist nach der Sperre weiter möglich; fremde bleiben gesperrt."""
    trig.rc = rc
    assert kill(trig) == ["denied"] and kill(trig, OWN) == ["sent"]  # in der Wartezeit von 10 s
    trig.now = 10.0
    assert kill(trig) == ["denied"] and kill(trig, OWN) == ["sent"]  # in der Wartezeit von 60 s
    trig.now = 70.0
    assert kill(trig) == ["denied"]
    trig.now = 1e9
    assert kill(trig) == ["locked"] and kill(trig, OWN) == ["sent"] and kill(trig) == ["locked"]
    assert len(trig.runs) == 3


def test_own_process_keeps_one_job_at_a_time(trig):
    trig.j.terminate(OWN, START, False)  # läuft noch, der Thread ist nur aufgezeichnet
    trig.j.terminate(OWN, START, False)
    assert [json.loads(s)["result"] for s in trig.sent] == ["busy"] and len(trig.threads) == 1


def test_own_before_the_gate_never_reaches_pkexec(trig):
    """Vor dem Tor eigen, im Thread fremd (etwa eine neu vergebene PID): kein pkexec, also nie ein Dialog am Tor
    vorbei. Die Seite kann die Wahl nicht treffen, sie sendet nur pid und start."""
    trig.j.terminate(OWN, START, False)
    (trig.tree / "proc" / str(OWN) / "status").write_text("Name:\tx\nUid:\t0\t0\t0\t0\n")
    run_jobs(trig)
    assert [json.loads(s)["result"] for s in trig.sent] == ["error"] and trig.runs == []
