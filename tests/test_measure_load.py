# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/measure-load.py: CPU über den ganzen Prozessbaum, auch kurzlebige Kinder, nur innerhalb des Fensters."""
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "measure-load.py"
BUSY = "import time\nend = time.process_time() + {s}\nwhile time.process_time() < end: pass\n"
# Der Elternprozess rechnet 1 s vor dem Fenster (zählt nicht), startet im Fenster ein Kind, das 1 s rechnet und endet
# (zählt), und schläft selbst. Erwartet: etwa 1 s CPU in 3 s, also ein Drittel eines Kerns.
PARENT = (BUSY.format(s=1.0) + "import subprocess, sys\nprint('ready', flush=True)\ntime.sleep(0.4)\n"
          f"subprocess.run([sys.executable, '-c', {BUSY.format(s=1.0)!r}])\ntime.sleep(30)\n")


def _measure(pid: int, seconds: int) -> dict[str, str]:
    out = subprocess.run([sys.executable, str(SCRIPT), "--pid", str(pid), "--seconds", str(seconds)],
                         capture_output=True, text=True, timeout=seconds + 15, check=True).stdout
    return dict(line.split("=", 1) for line in out.split())


def test_counts_short_lived_child_but_not_cpu_before_the_window():
    p = subprocess.Popen([sys.executable, "-c", PARENT], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline() == "ready\n"
        got = _measure(p.pid, 3)
    finally:
        p.kill()
        p.wait()
        p.stdout.close()
    assert 20 <= float(got["cpu_pct_of_one_core"]) <= 45, got
    assert float(got["pss_mb"]) > 0
    assert got["processes"] == "2"  # Eltern und das kurzlebige Kind


def test_missing_pid_fails():
    r = subprocess.run([sys.executable, str(SCRIPT), "--pid", "999999999", "--seconds", "1"],
                       capture_output=True, text=True, timeout=10)
    assert r.returncode == 1 and "no process" in r.stderr


def _module():
    spec = importlib.util.spec_from_file_location("measure_load", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_child_found_late_counts_only_its_cpu_in_the_window(monkeypatch, capsys):
    """task/*/children ist nur bei angehaltenen Kindern verlässlich: Ein Kind, das schon vor dem Fenster rechnete und
    erst im zweiten Scan auftaucht, zählt nur mit der CPU im Fenster (hier fast keine)."""
    parent = subprocess.Popen([sys.executable, "-c", "import time\ntime.sleep(30)\n"])
    child = subprocess.Popen([sys.executable, "-c", BUSY.format(s=1.0) + "print('ready', flush=True)\ntime.sleep(30)\n"],
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline() == "ready\n"  # 1 s CPU vor dem Fenster
        m, scans = _module(), []

        def tree(root):
            scans.append(root)
            return [root] if len(scans) == 1 else [root, child.pid]
        monkeypatch.setattr(m, "_tree", tree)
        assert m.main(["--pid", str(parent.pid), "--seconds", "1"]) == 0
    finally:
        for p in (parent, child):
            p.kill()
            p.wait()
        child.stdout.close()
    got = dict(line.split("=", 1) for line in capsys.readouterr().out.split())
    assert float(got["cpu_pct_of_one_core"]) < 10 and got["processes"] == "2", got


def test_unreadable_pss_is_reported_not_counted_as_zero():
    """Ein nicht auslesbarer Prozess (PR_SET_DUMPABLE 0, wie intel_gpu_top mit Datei-Capability) wird gezählt und
    markiert, statt still 0 MB beizutragen."""
    p = subprocess.Popen([sys.executable, "-c", "import ctypes, time\nctypes.CDLL(None).prctl(4, 0, 0, 0, 0)\n"
                          "print('ready', flush=True)\ntime.sleep(30)\n"], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline() == "ready\n"
        r = subprocess.run([sys.executable, str(SCRIPT), "--pid", str(p.pid), "--seconds", "1"],
                           capture_output=True, text=True, timeout=15, check=True)
    finally:
        p.kill()
        p.wait()
        p.stdout.close()
    got = dict(line.split("=", 1) for line in r.stdout.split())
    assert got["pss_unreadable"] == "1" and got["pss_mb"] == "0.0" and " ? " in r.stderr, (r.stdout, r.stderr)


def test_child_born_in_the_window_but_found_late_counts_from_zero(monkeypatch, capsys):
    """Gegenstück: Ein im Fenster gestartetes Kind, das erst nach seiner Rechenzeit sichtbar wird, zählt ab 0."""
    parent = subprocess.Popen([sys.executable, "-c", "import time\ntime.sleep(30)\n"])
    kids, m = [], _module()

    def tree(root):
        if len(kids) < 2:  # im zweiten Scan, also sicher nach dem Fensterbeginn, ein Kind mit 0,5 s Rechenzeit starten
            kids.append(time.monotonic() if not kids else subprocess.Popen(
                [sys.executable, "-c", BUSY.format(s=0.5) + "time.sleep(30)\n"]))
            return [root]
        return [root] if time.monotonic() - kids[0] < 1.2 else [root, kids[1].pid]
    monkeypatch.setattr(m, "_tree", tree)
    try:
        assert m.main(["--pid", str(parent.pid), "--seconds", "1.5"]) == 0
    finally:
        for p in (parent, *kids[1:]):
            p.kill()
            p.wait()
    got = dict(line.split("=", 1) for line in capsys.readouterr().out.split())
    assert 20 <= float(got["cpu_pct_of_one_core"]) <= 45 and got["processes"] == "2", got
