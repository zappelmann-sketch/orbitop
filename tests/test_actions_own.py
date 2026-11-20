# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""terminate und is_alive für eigene Prozesse: Signale über pidfd, Startzeitprüfung, Fehlerfälle."""
import os
import signal
import subprocess
import threading
import time

import pytest

from orbitop import killhelper
from orbitop.actions import is_alive, terminate
from orbitop.procs import parse_stat
from tests.actions_helpers import fake, start_of


def test_terminate_own_child(child):
    assert terminate(child.pid, start_of(child.pid), False) == "sent"
    assert child.wait(5) == -signal.SIGTERM


def test_kill_own_child(child):
    assert terminate(child.pid, start_of(child.pid), True) == "sent"
    assert child.wait(5) == -signal.SIGKILL


def test_mismatch_leaves_child_alive(child):
    assert terminate(child.pid, start_of(child.pid) + 1, False) == "mismatch"
    time.sleep(0.1)
    assert child.poll() is None


def test_gone():
    calls = []
    assert terminate(999999, 1, False, run=fake(calls)) == "gone"
    assert calls == []  # kein pkexec für nicht vorhandene Prozesse


def test_stopped_gets_sigcont(child):
    child.send_signal(signal.SIGSTOP)
    time.sleep(0.2)
    assert terminate(child.pid, start_of(child.pid), False) == "sent"
    assert child.wait(5) == -signal.SIGTERM


def test_zombie_gets_no_signal():
    p = subprocess.Popen(["true"])
    while True:
        with open(f"/proc/{p.pid}/stat") as f:
            if parse_stat(f.read())["state"] == "Z":
                break
        time.sleep(0.01)
    start = start_of(p.pid)
    assert not is_alive(p.pid, start)
    assert terminate(p.pid, start, True) == "zombie"
    p.wait()


def test_is_alive(child):
    s = start_of(child.pid)
    assert is_alive(child.pid, s)
    assert not is_alive(child.pid, s + 1)
    assert not is_alive(999999, 1)


def test_bad_types_are_error(child):
    s = start_of(child.pid)
    calls = []
    for pid, start in [(str(child.pid), s), (True, s), (child.pid, str(s)), (child.pid, None)]:
        assert terminate(pid, start, False, run=fake(calls)) == "error"
    assert calls == [] and child.poll() is None


def test_thread_id_is_error():
    ev = threading.Event()
    t = threading.Thread(target=ev.wait)
    t.start()
    try:
        assert terminate(t.native_id, 1, False) == "error"
    finally:
        ev.set()
        t.join()


def test_unexpected_oserror_is_error(child, monkeypatch):
    def boom(pid):
        raise OSError(24, "EMFILE")
    monkeypatch.setattr(os, "pidfd_open", boom)
    assert terminate(child.pid, start_of(child.pid), False) == "error"


def test_pidfd_before_check_and_signal_via_pidfd(child, monkeypatch):
    calls = []
    o, st, sd = os.pidfd_open, killhelper._stat, signal.pidfd_send_signal
    # *flags: unter Python 3.15 (Fedora 45) ruft auch Popen.wait os.pidfd_open(pid, 0)
    monkeypatch.setattr(os, "pidfd_open", lambda pid, *flags: calls.append("open") or o(pid, *flags))
    monkeypatch.setattr(killhelper, "_stat", lambda pid, root: calls.append("stat") or st(pid, root))
    monkeypatch.setattr(signal, "pidfd_send_signal", lambda fd, s: calls.append("signal") or sd(fd, s))
    monkeypatch.setattr(os, "kill", lambda *a: pytest.fail("Signal per PID"))
    assert terminate(child.pid, start_of(child.pid), False) == "sent"
    assert calls == ["open", "stat", "signal"]
    assert child.wait(5) == -signal.SIGTERM  # sonst rief der Abbau von child noch das gesperrte os.kill (Wettlauf)


def test_own_permission_error_is_denied(child, monkeypatch):
    def deny(fd, s):
        raise PermissionError
    monkeypatch.setattr(signal, "pidfd_send_signal", deny)
    assert terminate(child.pid, start_of(child.pid), False) == "denied"
