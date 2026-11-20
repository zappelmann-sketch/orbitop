# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Root-Helfer killhelper: Argumentprüfung, Rückgabecodes, Kernel-Threads und Dateiform."""
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from orbitop import killhelper
from tests.actions_helpers import HELPER, start_of


def helper(*args):
    return subprocess.run([sys.executable, "-IS", HELPER, *args], capture_output=True, timeout=20).returncode


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
    src = Path(HELPER).read_text()
    assert "import orbitop" not in src and "from orbitop" not in src
    assert os.access(HELPER, os.X_OK)


def test_killhelper_shebang():  # B2.1: unter -S lädt Python keine .pth-Datei aus site-packages, auch nicht als root
    assert Path(HELPER).read_bytes().split(b"\n", 1)[0] == b"#!/usr/bin/python3 -IS"


def test_helper_is_executable_in_git():
    """Der Checkout-Modus hängt von der umask ab (0775 unter Ubuntu); das Repository garantiert nur 100755."""
    root = os.path.dirname(os.path.dirname(HELPER))
    try:
        out = subprocess.run(["git", "ls-files", "-s", "--", HELPER], cwd=root, capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("git nicht verfügbar")
    if out.returncode != 0 or not out.stdout:
        pytest.skip("kein Git-Checkout")
    assert out.stdout.startswith("100755 ")


def test_ppid2_with_cmdline_not_refused(child, tmp_path):
    s = start_of(child.pid)
    fake_proc(tmp_path, child.pid, s, "2", b"sleep\0")
    assert killhelper.send(child.pid, s, "KILL", str(tmp_path)) == killhelper.SENT
    assert child.wait(5) == -signal.SIGKILL
