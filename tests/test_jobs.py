# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Aufträge ohne GTK: das Nachsehen nach dem Beenden und das pkexec-Kind von _run.

Der Weg von der Nachricht terminate in die Aufträge steht in test_shell_messages.py und test_shell_lifecycle.py."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from orbitop import jobs


@pytest.fixture
def jobrig(threads):
    """Jobs mit einer GLib-Attrappe, deren idle_add und timeout_add_seconds nur aufzeichnen; sent: an die Seite."""
    sent, glib = [], SimpleNamespace(idle=[], timeouts=[])
    glib.idle_add = lambda fn, *args: glib.idle.append((fn, args))
    glib.timeout_add_seconds = lambda delay, fn, *args: glib.timeouts.append((delay, fn, args))
    return SimpleNamespace(j=jobs.Jobs(sent.append, glib), sent=sent, glib=glib, threads=threads)


@pytest.mark.parametrize("force,result,check", [(False, "sent", True), (True, "sent", False),
                                                (False, "denied", False), (False, "gone", False)])
def test_check_only_after_plain_sent(jobrig, force, result, check):
    jobrig.j._terminated(5, 6, force, result)
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
