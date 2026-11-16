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


def foreign_proc(root, pid, start, state, ppid=1, cmdline=b"x\0"):
    """Fremder Prozess (Uid 0) in einem Testbaum; state None: stat fehlt, cmdline None: cmdline fehlt."""
    d = root / "proc" / str(pid)
    d.mkdir(parents=True)
    (d / "status").write_text("Name:\tx\nUid:\t0\t0\t0\t0\n")
    if state:
        (d / "stat").write_text(f"{pid} (x y) {state} {ppid} " + "0 " * 17 + f"{start} 0 0\n")
    if cmdline is not None:
        (d / "cmdline").write_bytes(cmdline)


@pytest.fixture
def foreign(tmp_path):
    """Lebender fremder Prozess 4242 mit Startzeit 77; der Testbaum als root."""
    foreign_proc(tmp_path, 4242, 77, "S")
    return str(tmp_path)


def test_foreign_uses_pkexec_helper(monkeypatch, foreign):
    monkeypatch.setattr(sys, "executable", "/venv/bin/python")
    calls = []
    assert terminate(4242, 77, False, root=foreign, run=fake(calls, 126)) == "denied"
    argv, kw = calls[0]
    assert argv == ["/usr/bin/pkexec", "/usr/bin/python3", "-I", HELPER, "4242", "77", "TERM"]
    assert os.path.isabs(argv[3]) and kw["timeout"] == 120 and "shell" not in kw
    calls.clear()
    terminate(4242, 77, True, root=foreign, run=fake(calls, 0))
    assert calls[0][0][-1] == "KILL"


@pytest.mark.parametrize("rc,want", [(0, "sent"), (3, "mismatch"), (4, "gone"), (5, "zombie"), (6, "kernel"),
                                     (126, "denied"), (127, "denied"), (2, "error"), (1, "error")])
def test_exit_code_mapping(rc, want, foreign):
    assert terminate(4242, 77, False, root=foreign, run=fake([], rc)) == want


@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired("pkexec", 120), FileNotFoundError("pkexec")])
def test_pkexec_failures_are_error(exc, foreign):
    assert terminate(4242, 77, False, root=foreign, run=fake([], exc=exc)) == "error"


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
    assert terminate(4242, 77, False, root=foreign, run=fake(calls, 0)) == "sent"
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
    assert terminate(4243, 77, True, root=str(tmp_path), run=fake(calls, 0)) == want
    assert len(calls) == prompts
    assert is_alive(4243, 77, str(tmp_path)) is (want != "gone")


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


def test_helper_has_no_orbitop_import():
    src = open(HELPER).read()
    assert "import orbitop" not in src and "from orbitop" not in src
    assert src.startswith("#!/usr/bin/python3 -I\n") and os.stat(HELPER).st_mode & 0o777 == 0o755


def test_ppid2_with_cmdline_not_refused(child, tmp_path):
    s = start_of(child.pid)
    fake_proc(tmp_path, child.pid, s, "2", b"sleep\0")
    assert killhelper.send(child.pid, s, "KILL", str(tmp_path)) == killhelper.SENT
    assert child.wait(5) == -signal.SIGKILL


def test_own_permission_error_is_denied(child, monkeypatch):
    def deny(fd, s):
        raise PermissionError
    monkeypatch.setattr(signal, "pidfd_send_signal", deny)
    assert terminate(child.pid, start_of(child.pid), False) == "denied"


def test_guard_blocks_real_pkexec(foreign):
    with pytest.raises(AssertionError):
        terminate(4242, 77, False, root=foreign)
