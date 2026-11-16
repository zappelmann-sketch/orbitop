# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from orbitop import killhelper
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


def test_foreign_uses_pkexec_helper():
    calls = []
    assert terminate(1, start_of(1), False, run=fake(calls, 126)) == "denied"
    argv, kw = calls[0]
    assert argv == ["/usr/bin/pkexec", "/usr/bin/python3", "-I", HELPER, "1", str(start_of(1)), "TERM"]
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
    ("0", "1", "TERM"), ("4194305", "1", "TERM"), ("99999999999", "1", "TERM"),
    ("5", "+1", "TERM"), ("5", "", "TERM"), ("٥", "1", "TERM"),
    ("5", "1", "HUP"), ("5", "1", "term"), ("5", "1", "")])
def test_helper_rejects_invalid(args, child):
    assert helper(*args) == 2
    assert child.poll() is None


def test_helper_kills_own_child_and_checks_start(child):
    s = start_of(child.pid)
    assert helper(str(child.pid), str(s + 1), "TERM") == 3
    assert child.poll() is None
    assert helper(str(child.pid), str(s), "TERM") == 0
    assert child.wait(5) == -signal.SIGTERM


def test_helper_pid1_refused():
    assert helper("1", "1", "TERM") == 6 == helper("1", "1", "KILL")


def test_helper_root_side_oserror_is_nonzero(monkeypatch):
    def deny(*a):
        raise PermissionError
    monkeypatch.setattr(killhelper, "send", deny)
    assert killhelper.main(["5", "1", "TERM"]) == 1


def test_send_rejects_unknown_signal(child):
    with pytest.raises(KeyError):
        killhelper.send(child.pid, start_of(child.pid), "term")
    assert child.poll() is None


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
    monkeypatch.setattr(os, "pidfd_open", lambda pid: calls.append("open") or o(pid))
    monkeypatch.setattr(killhelper, "_stat", lambda pid, root: calls.append("stat") or st(pid, root))
    monkeypatch.setattr(signal, "pidfd_send_signal", lambda fd, s: calls.append("signal") or sd(fd, s))
    monkeypatch.setattr(os, "kill", lambda *a: pytest.fail("Signal per PID"))
    assert terminate(child.pid, start_of(child.pid), False) == "sent"
    assert calls == ["open", "stat", "signal"]


def fake_proc(tmp_path, pid, start, ppid, cmdline):
    d = tmp_path / "proc" / str(pid)
    d.mkdir(parents=True)
    (d / "stat").write_text(f"{pid} (kworker/0:1) S {ppid} " + "0 " * 17 + f"{start} 0 0\n")
    (d / "cmdline").write_bytes(cmdline)


@pytest.mark.parametrize("ppid", ["0", "2"])
def test_kernel_thread_refused(child, tmp_path, ppid):
    s = start_of(child.pid)
    fake_proc(tmp_path, child.pid, s, ppid, b"")
    assert killhelper.send(child.pid, s, "KILL", str(tmp_path)) == killhelper.KERNEL
    assert child.poll() is None


def test_empty_cmdline_with_other_ppid_not_refused(child, tmp_path):
    s = start_of(child.pid)
    fake_proc(tmp_path, child.pid, s, "1234", b"")
    assert killhelper.send(child.pid, s, "KILL", str(tmp_path)) == killhelper.SENT
    assert child.wait(5) == -signal.SIGKILL


def test_missing_pkexec_is_error():
    assert terminate(1, 1, False, run=fake([], exc=FileNotFoundError("/usr/bin/pkexec"))) == "error"


def test_helper_has_no_orbitop_import():
    src = open(HELPER).read()
    assert "import orbitop" not in src and "from orbitop" not in src
    assert src.startswith("#!/usr/bin/python3 -I\n") and os.stat(HELPER).st_mode & 0o777 == 0o755


def test_ppid2_with_cmdline_not_refused(child, tmp_path):
    s = start_of(child.pid)
    fake_proc(tmp_path, child.pid, s, "2", b"sleep\0")
    assert killhelper.send(child.pid, s, "KILL", str(tmp_path)) == killhelper.SENT
    assert child.wait(5) == -signal.SIGKILL
