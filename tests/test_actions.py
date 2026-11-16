# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from orbitop import actions, killhelper
from orbitop.actions import is_alive, terminate
from orbitop.procs import parse_stat

HELPER = os.path.abspath(killhelper.__file__)


def start_of(pid):
    with open(f"/proc/{pid}/stat") as f:
        return parse_stat(f.read())["start"]


@pytest.fixture
def child():
    p = subprocess.Popen(["sleep", "1000"])
    yield p
    p.kill()
    p.wait()


def fake(calls, rc=0, exc=None):
    def run(argv, **kw):
        calls.append((argv, kw))
        if exc:
            raise exc
        return SimpleNamespace(returncode=rc)
    return run


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
    assert terminate(999999, 1, False) == "gone"


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


def test_foreign_uses_pkexec_helper():
    calls = []
    assert terminate(1, start_of(1), False, run=fake(calls, 126)) == "denied"
    argv, kw = calls[0]
    assert argv == ["pkexec", sys.executable, "-I", HELPER, "1", str(start_of(1)), "TERM"]
    assert os.path.isabs(argv[3]) and kw["timeout"] == 120 and "shell" not in kw
    calls.clear()
    terminate(1, 5, True, run=fake(calls, 0))
    assert calls[0][0][-1] == "KILL"


@pytest.mark.parametrize("rc,want", [(0, "sent"), (3, "mismatch"), (4, "gone"), (5, "zombie"), (6, "kernel"),
                                     (126, "denied"), (127, "denied"), (2, "error"), (1, "error")])
def test_exit_code_mapping(rc, want):
    assert terminate(1, 1, False, run=fake([], rc)) == want


@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired("pkexec", 120), FileNotFoundError("pkexec")])
def test_pkexec_failures_are_error(exc):
    assert terminate(1, 1, False, run=fake([], exc=exc)) == "error"


def helper(*args):
    return subprocess.run([sys.executable, "-I", HELPER, *args], capture_output=True, timeout=20).returncode


@pytest.mark.parametrize("args", [
    (), ("5",), ("5", "1"), ("5", "1", "TERM", "x"), ("+5", "1", "TERM"), ("5x", "1", "TERM"),
    ("0", "1", "TERM"), ("1", "1", "TERM"), ("4194305", "1", "TERM"), ("99999999999", "1", "TERM"),
    ("5", "+1", "TERM"), ("5", "", "TERM"), ("٥", "1", "TERM"),
    ("5", "1", "HUP"), ("5", "1", "term"), ("5", "1", "")])
def test_helper_rejects_invalid(args, child):
    assert helper(*args) in (2, 6)
    assert child.poll() is None


def test_helper_kills_own_child_and_checks_start(child):
    s = start_of(child.pid)
    assert helper(str(child.pid), str(s + 1), "TERM") == 3
    assert child.poll() is None
    assert helper(str(child.pid), str(s), "TERM") == 0
    assert child.wait(5) == -signal.SIGTERM


def test_helper_pid1_refused():
    assert helper("1", "1", "KILL") == 6


def test_helper_has_no_orbitop_import():
    src = open(HELPER).read()
    assert "import orbitop" not in src and "from orbitop" not in src
    assert src.startswith("#!/usr/bin/python3\n") and os.stat(HELPER).st_mode & 0o777 == 0o755
