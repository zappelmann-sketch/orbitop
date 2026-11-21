# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Werkzeug-Leser: ToolReader (Start, Neustart, Stopp) und GpuTools (Hinweise, Aufrufe, Zuordnung)."""
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

from orbitop import gpu_tools
from orbitop.gpu import GpuInfo, discover_gpus
from orbitop.gpu_tools import GpuTools, ToolReader, parse_intel
from tests.gpu_tools_helpers import LOOP, OBJ, ONCE, wait_until
from tests.gpu_tools_helpers import gpus as _gpus
from tests.gpu_tools_helpers import no_popen as _no_popen


def test_tool_reader_marks_failed_on_bad_command():
    r = ToolReader(["false"], parse_intel)
    r.start()
    wait_until(lambda: r.failed)
    assert r.latest() is None
    r.stop()


def test_tool_reader_delivers_and_stop_kills_process():
    r = ToolReader([sys.executable, "-c", LOOP], parse_intel)
    r.start()
    wait_until(lambda: r.latest() is not None)
    assert r.latest()["busy"] == 7.5 and not r.failed
    proc = r._proc
    r.stop()
    assert proc.poll() is not None
    r.stop()  # idempotent


def test_tool_reader_restarts_at_most_every_30s(monkeypatch):
    r = ToolReader([sys.executable, "-c", ONCE], parse_intel)
    r.start()
    wait_until(lambda: r.latest() is not None)
    wait_until(lambda: r._proc.poll() is not None)
    first = r._proc
    wait_until(lambda: not r._thread.is_alive())
    r.latest()
    assert r._proc is first  # <30 s: kein Neustart
    r._started -= 31
    r.latest()
    assert r._proc is not first
    r.stop()
    first.stdout.close()  # der ersetzte Lauf; stop() schließt nur den aktuellen


def test_hints_missing_tools(monkeypatch):
    _no_popen(monkeypatch)
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: None)
    t = GpuTools(_gpus("intel", "nvidia"))
    assert t.hints() == ["hint.igt_missing", "hint.nvsmi_missing"]
    assert t.intel("card0") is None and t.nvidia("0000:01:00.0") is None
    assert GpuTools(_gpus("amd")).hints() == []


def test_hint_noperm_does_not_start(monkeypatch):
    """Ohne root entscheidet der Parser (B2.5, M-1): eine fremde Fähigkeit genügt nicht mehr."""
    _no_popen(monkeypatch)
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: "/usr/bin/" + n)
    monkeypatch.setattr(gpu_tools.os, "geteuid", lambda: 1000)
    seen = []
    monkeypatch.setattr(gpu_tools.counters, "perf_capable", lambda p: seen.append(p) or False)
    t = GpuTools(_gpus("intel"))
    assert t.hints() == ["hint.igt_noperm"] and t.intel("card0") is None
    assert seen == ["/usr/bin/intel_gpu_top"]


@pytest.mark.parametrize("bits,starts", [((38,), True), ((21,), True), ((21, 38), True), ((13,), False), ((), False)])
def test_reader_starts_with_perfmon_or_sys_admin(monkeypatch, bits, starts):
    """M-1: cap_sys_admin von Hand (eine ältere Anleitung) startet den Leser wie in 0.2.0, passend zu „von Hand
    freigegeben“ in den Einstellungen; eine andere Fähigkeit nicht. Nur das Permitted-Set ist gefälscht."""
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: "/usr/bin/" + n)
    monkeypatch.setattr(gpu_tools.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(gpu_tools.counters, "_permitted", lambda path, getxattr: sum(1 << b for b in bits))
    started = []
    monkeypatch.setattr(gpu_tools.ToolReader, "start", lambda self: started.append(self._cmd))
    t = GpuTools(_gpus("intel"))
    assert t.hints() == ([] if starts else ["hint.igt_noperm"])
    assert started == ([["/usr/bin/intel_gpu_top", "-J", "-s", "2000"]] if starts else [])
    t.stop()


def test_hint_failed_and_device_argument(monkeypatch):
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: "/usr/bin/" + n)
    monkeypatch.setattr(gpu_tools.os, "geteuid", lambda: 0)
    cmds = []
    real = gpu_tools.subprocess.Popen

    def fake(cmd, **kw):
        cmds.append(cmd)
        return real(["false"], **kw)
    monkeypatch.setattr(gpu_tools.subprocess, "Popen", fake)
    t = GpuTools(_gpus("intel", "intel"))
    wait_until(lambda: "hint.igt_failed" in t.hints())
    assert {tuple(c) for c in cmds} == {
        ("/usr/bin/intel_gpu_top", "-J", "-s", "2000", "-d", "drm:/dev/dri/card0"),
        ("/usr/bin/intel_gpu_top", "-J", "-s", "2000", "-d", "drm:/dev/dri/card1")}
    t.stop()


def test_nvidia_lookup_by_normalized_pci(monkeypatch):
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: sys.executable if n == "nvidia-smi" else None)
    line = "00000000:01:00.0, GTX, 18, 1, 2, 54, 40.5, 607, 1911"
    monkeypatch.setattr(gpu_tools, "_nvidia_cmd", lambda path: [sys.executable, "-c", f"print({line!r}, flush=True);import time;time.sleep(5)"])
    t = GpuTools(_gpus("nvidia"))
    wait_until(lambda: t.nvidia("0000:01:00.0") is not None)
    assert t.nvidia("0000:01:00.0")["busy"] == 18.0 and t.nvidia("0000:02:00.0") is None
    t.stop()


# /dev/dri/card1: im Container sind sysfs und intel_gpu_top da, das Gerät nicht; der Test meint nur den Referenzrechner
@pytest.mark.skipif(not shutil.which("intel_gpu_top", path=gpu_tools.TOOL_PATH)
                    or not Path("/sys/class/drm/card1").exists() or not Path("/dev/dri/card1").exists(),
                    reason="intel_gpu_top oder Intel-GPU card1 fehlt")
def test_real_intel_gpu_top_delivers_within_3s():
    t = GpuTools(discover_gpus("/"))
    try:
        wait_until(lambda: t.intel("card1") is not None, 3)
    finally:
        t.stop()


def test_nouveau_gets_no_nvidia_smi(monkeypatch):
    _no_popen(monkeypatch)
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: None)
    t = GpuTools([GpuInfo("card0", "nouveau", "nvidia", "n", "0000:01:00.0")])
    assert t.hints() == [] and t.nvidia("0000:01:00.0") is None


def test_which_uses_fixed_path_and_absolute_result(monkeypatch):
    seen = []
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: seen.append(path))
    GpuTools(_gpus("intel", "nvidia"))
    assert seen == [gpu_tools.TOOL_PATH] * 2 and "." not in gpu_tools.TOOL_PATH.split(":")


def test_invalid_card_names_rejected_for_d_argument(monkeypatch):
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: "/usr/bin/" + n)
    monkeypatch.setattr(gpu_tools.os, "geteuid", lambda: 0)
    cmds = []
    real = gpu_tools.subprocess.Popen
    monkeypatch.setattr(gpu_tools.subprocess, "Popen", lambda cmd, **kw: cmds.append(cmd) or real(["false"], **kw))
    gpus = [GpuInfo(c, "i915", "intel", "n", None) for c in ("card0", "card1", "card0-DP-1", "card1\n")]
    t = GpuTools(gpus)
    t.stop()
    assert sorted(c[-1] for c in cmds) == ["drm:/dev/dri/card0", "drm:/dev/dri/card1"]


def test_failed_reader_is_never_restarted(monkeypatch):
    r = ToolReader(["false"], parse_intel)
    r.start()
    wait_until(lambda: r.failed)
    n = []
    real = gpu_tools.subprocess.Popen
    monkeypatch.setattr(gpu_tools.subprocess, "Popen", lambda *a, **k: n.append(1) or real(*a, **k))
    r._started -= 31
    r.latest()
    r.stop()
    assert n == []


def test_stale_value_is_none(monkeypatch):
    monkeypatch.setattr(gpu_tools, "STALE_S", 0.3)
    r = ToolReader([sys.executable, "-c", ONCE], parse_intel)
    r.start()
    wait_until(lambda: r.latest() is not None)
    time.sleep(0.4)
    assert r.latest() is None
    r.stop()


def test_reader_survives_deep_nesting():
    deep = "print('{'); print('\"a\": ' + '[' * 300000 + ']' * 300000); print('}')"
    r = ToolReader([sys.executable, "-c", deep + ";" + ONCE], parse_intel)
    r.start()
    wait_until(lambda: r.latest() is not None)
    assert r.latest()["busy"] == 7.5
    r.stop()


class YieldingLock:
    """Gibt nach dem Freigeben kurz den Prozessor ab und weitet so das Rennfenster."""

    def __init__(self):
        self._l = threading.Lock()

    def __enter__(self):
        self._l.acquire()

    def __exit__(self, *a):
        self._l.release()
        time.sleep(0.05)


def test_concurrent_latest_spawns_one_child(monkeypatch):
    r = ToolReader([sys.executable, "-c", LOOP], parse_intel)
    r.start()
    wait_until(lambda: r.latest() is not None)
    first = r._proc
    first.kill()
    first.wait()
    wait_until(lambda: not r._thread.is_alive())
    first.stdout.close()  # stop() schließt nur den neuen Lauf
    r._lock = YieldingLock()
    r._started -= 31
    procs = []
    real = gpu_tools.subprocess.Popen
    monkeypatch.setattr(gpu_tools.subprocess, "Popen", lambda *a, **k: procs.append(real(*a, **k)) or procs[-1])
    ts = [threading.Thread(target=r.latest) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    r.stop()
    for p in procs:  # Aufräumen, falls die Prüfung unten fehlschlägt
        p.kill()
        p.wait()
    assert len(procs) == 1


def test_stop_kills_child_ignoring_sigterm():
    code = ("import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"while True:\n print({OBJ!r}, flush=True); time.sleep(0.1)")
    r = ToolReader([sys.executable, "-c", code], parse_intel)
    r.start()
    wait_until(lambda: r.latest() is not None)
    proc = r._proc
    t0 = time.monotonic()
    r.stop()
    assert proc.poll() is not None and time.monotonic() - t0 < 4
