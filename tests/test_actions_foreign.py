# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""terminate für fremde Prozesse: pkexec-Aufruf, Rückgabecodes und Vorprüfung ohne Passwortdialog."""
import os
import subprocess
import sys
import threading

import pytest

from orbitop import actions
from orbitop.actions import is_alive, terminate
from tests.actions_helpers import ELF, INSTALLED, TRUSTED, fake, foreign_proc, start_of


def test_foreign_uses_pkexec_helper(monkeypatch, foreign):
    monkeypatch.setattr(sys, "executable", "/venv/bin/python")
    calls = []
    assert terminate(4242, 77, False, root=foreign, run=fake(calls, 126), lstat=TRUSTED, opener=ELF) == "denied"
    argv, kw = calls[0]
    assert argv == ["/usr/bin/pkexec", INSTALLED, "4242", "77", "TERM"]
    assert kw["timeout"] == 120 and "shell" not in kw
    calls.clear()
    terminate(4242, 77, True, root=foreign, run=fake(calls, 0), lstat=TRUSTED, opener=ELF)
    assert calls[0][0][-1] == "KILL"


def test_pkexec_runs_helper_directly(monkeypatch, tmp_path):
    """Kein Interpreter im argv: nur so passt die polkit-Annotation exec.path genau auf den Helfer."""
    monkeypatch.setattr(sys, "executable", "/venv/bin/python")
    foreign_proc(tmp_path, 123, 456, "S")
    calls = []
    terminate(123, 456, False, root=str(tmp_path), run=fake(calls, 0), lstat=TRUSTED, opener=ELF)
    assert [c[0] for c in calls] == [["/usr/bin/pkexec", "/usr/lib/orbitop/killhelper", "123", "456", "TERM"]]


@pytest.mark.parametrize("rc,want", [(0, "sent"), (3, "mismatch"), (4, "gone"), (5, "zombie"), (6, "kernel"),
                                     (126, "denied"), (127, "denied"), (2, "error"), (1, "error")])
def test_exit_code_mapping(rc, want, foreign):
    assert terminate(4242, 77, False, root=foreign, run=fake([], rc), lstat=TRUSTED, opener=ELF) == want


@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired("pkexec", 120), FileNotFoundError("pkexec")])
def test_pkexec_failures_are_error(exc, foreign):
    assert terminate(4242, 77, False, root=foreign, run=fake([], exc=exc), lstat=TRUSTED, opener=ELF) == "error"


def test_foreign_wrong_start_is_mismatch_without_prompt():
    calls = []
    assert terminate(1, start_of(1) + 1, False, run=fake(calls)) == "mismatch"
    assert terminate(1, 0, True, run=fake(calls)) == "mismatch"
    assert calls == []  # veraltete oder falsche Startzeit: nie ein Passwortdialog


@pytest.mark.parametrize("state,want", [("Z", "zombie"), ("X", "zombie"), (None, "gone")])
def test_foreign_dead_target_needs_no_prompt(tmp_path, state, want):
    foreign_proc(tmp_path, 4242, 77, state)
    calls = []
    assert terminate(4242, 77, False, root=str(tmp_path), run=fake(calls)) == want
    assert calls == []


def test_foreign_live_target_goes_to_pkexec(foreign):
    calls = []
    assert terminate(4242, 77, False, root=foreign, run=fake(calls, 0), lstat=TRUSTED, opener=ELF) == "sent"
    assert len(calls) == 1


@pytest.mark.parametrize("force", [False, True])
def test_pid1_is_kernel_without_prompt(force):
    calls = []
    assert terminate(1, start_of(1), force, run=fake(calls)) == "kernel"
    assert calls == [] and is_alive(1, start_of(1))


@pytest.mark.parametrize("ppid,cmdline,want,prompts", [
    (2, b"", "kernel", 0), (0, b"", "kernel", 0),     # Kernel-Thread: verweigert der Helfer ohnehin
    (2, None, "gone", 0),                             # cmdline schon weg
    (2, b"sleep\0", "sent", 1), (1, b"", "sent", 1),  # wie im Helfer: nur ppid 0/2 UND leere cmdline
])
def test_kernel_thread_needs_no_prompt(tmp_path, ppid, cmdline, want, prompts):
    foreign_proc(tmp_path, 4243, 77, "S", ppid=ppid, cmdline=cmdline)
    calls = []
    assert terminate(4243, 77, True, root=str(tmp_path), run=fake(calls, 0), lstat=TRUSTED, opener=ELF) == want
    assert len(calls) == prompts
    assert is_alive(4243, 77, str(tmp_path)) is (want != "gone")


def test_precheck_reads_cmdline_only_for_kernel_thread_candidates(tmp_path):  # Audit: hängendes Lesen sperrt Beenden
    foreign_proc(tmp_path, 4244, 77, "S", ppid=1000, cmdline=None)
    fifo = tmp_path / "proc" / "4244" / "cmdline"
    os.mkfifo(fifo)  # ohne Schreiber blockiert schon das Öffnen, wie ein hängendes /proc/<pid>/cmdline
    out = []
    t = threading.Thread(target=lambda: out.append(actions._precheck(4244, 77, str(tmp_path))), daemon=True)
    t.start()
    t.join(2)
    blocked = t.is_alive()
    if blocked:  # Regression: den Leser freigeben, damit der Test scheitert statt zu hängen
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        t.join(2)
    assert (blocked, out) == (False, [None])
    foreign_proc(tmp_path, 4245, 77, "S", ppid=2, cmdline=b"")
    foreign_proc(tmp_path, 1, 77, "S", ppid=0, cmdline=b"/sbin/init\0")
    assert [actions._precheck(pid, 77, str(tmp_path)) for pid in (4245, 1)] == ["kernel", "kernel"]


def test_guard_blocks_real_pkexec(foreign):
    with pytest.raises(AssertionError):
        terminate(4242, 77, False, root=foreign, lstat=TRUSTED, opener=ELF)
