# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/measure-load.py: CPU über den ganzen Prozessbaum, auch kurzlebige Kinder, nur innerhalb des Fensters."""
import subprocess
import sys
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
