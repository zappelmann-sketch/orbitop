# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import json
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

from orbitop import gpu_tools
from orbitop.gpu import GpuInfo, discover_gpus
from orbitop.gpu_tools import (GpuTools, ToolReader, parse_intel, parse_nvidia_line,
                               split_json_stream, split_lines)

FIX = Path(__file__).parent / "fixtures" / "tools"
OBJ = '{\n\t"engines": {"Render/3D": {"busy": 7.5}}\n},'
LOOP = f"import time\nprint('[', flush=True)\nwhile True:\n print({OBJ!r}, flush=True); time.sleep(0.1)"
ONCE = f"print({OBJ!r}, flush=True)"


def wait_until(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    raise AssertionError("Bedingung nicht erreicht")


def test_split_and_parse_recorded_intel():
    with open(FIX / "intel_gpu_top.json") as f:
        objs = list(split_json_stream(f))
    assert len(objs) >= 2
    s = parse_intel(objs[-1])
    assert 0 <= s["busy"] <= 100 and s["freq_mhz"] >= 0


def test_parse_intel_old_engine_names():
    assert parse_intel({"engines": {"Render/3D/0": {"busy": 12.5}}})["busy"] == 12.5


def test_parse_intel_missing_fields():
    assert parse_intel({}) == {"busy": None, "freq_mhz": None, "gpu_w": None, "pkg_w": None}


def test_split_clients_block_with_hostile_names():
    with open(FIX / "intel_gpu_top_clients.json") as f:
        objs = list(split_json_stream(f))
    assert [parse_intel(o)["busy"] for o in objs] == [0.0, 1.004995, 2.733251]
    assert [parse_intel(o)["freq_mhz"] for o in objs] == [0.0, 7.848317, 4.919986]
    assert [parse_intel(o)["pkg_w"] for o in objs] == [21.701609, 10.824967, 12.486207]
    assert all("clients" not in o for o in objs)


def test_split_clients_not_last_member():
    lines = ['{\n', '\t"clients": {\n', '\t\t"1": {"name": "a"b"},\n', '\t},\n', '\t"x": 1\n', '}\n']
    assert list(split_json_stream(lines)) == [{"x": 1}]


def test_split_newline_in_name_does_not_freeze():
    bad = ['{\n', '\t"engines": {"R": {"busy": 1}},\n', '\t"clients": {\n', '\t\t"1": {\n',
           '\t\t\t"name": "x\n', '}\n', '{\n', '",\n', '\t\t}\n', '\t}\n', '}\n']
    good = ['{\n', '\t"engines": {"R": {"busy": 9}}\n', '}\n']
    assert list(split_json_stream(bad + good))[-1] == {"engines": {"R": {"busy": 9}}}


def test_split_skips_malformed():
    assert list(split_json_stream(['{\n', '"a": }\n', '},\n', '{\n', '"b": 1\n', '}\n'])) == [{"b": 1}]


def test_split_drops_oversized_object_and_resyncs():
    big = ['{\n'] + ['\t"x": "' + "a" * 65000 + '",\n'] * 20 + ['}\n', '{\n', '"ok": 1\n', '}\n']
    assert list(split_json_stream(big)) == [{"ok": 1}]


def test_split_deep_nesting_does_not_raise():
    deep = ['{\n', '"a": ' + "[" * 300000 + "]" * 300000 + '\n', '}\n', '{\n', '"ok": 1\n', '}\n']
    assert list(split_json_stream(deep)) == [{"ok": 1}]


def test_parse_non_finite_is_none():
    d = parse_intel(json.loads('{"engines": {"R": {"busy": NaN}}, "power": {"GPU": Infinity}}'))
    assert d["busy"] is None and d["gpu_w"] is None
    n = parse_nvidia_line("00000000:01:00.0, X, nan, inf, -inf, 1, 2, 3, 4, 5")
    assert n["busy"] is None and n["vram_used"] is None and n["vram_total"] is None and n["temp_c"] == 1.0


def test_parse_intel_max_over_engines():
    assert parse_intel({"engines": {"A": {"busy": 1}, "B": {"busy": 50}}})["busy"] == 50


def test_parse_nvidia_pci_normalized():
    assert parse_nvidia_line("00000000:0A:00.0, X, 1, 1, 1, 1, 1, 1, 1, 1")["pci"] == "0000:0a:00.0"


def test_parse_nvidia_na():
    d = parse_nvidia_line("00000000:01:00.0, NVIDIA GeForce GTX 1080, 18, 3379, 8192, 54, [N/A], 607, 1911, 0")
    assert d["pci"] == "0000:01:00.0" and d["power_w"] is None and d["busy"] == 18.0
    assert d["name"] == "NVIDIA GeForce GTX 1080" and d["vram_total"] == 8192.0 and d["fan_pct"] == 0.0


def test_parse_nvidia_fixture_not_supported():
    with open(FIX / "nvidia-smi.csv") as f:
        lines = list(split_lines(f))
    assert parse_nvidia_line(lines[1])["fan_pct"] is None
    with pytest.raises(ValueError):
        parse_nvidia_line("kaputt")


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


def _gpus(*vendors):
    return [GpuInfo(f"card{i}", "nvidia" if v == "nvidia" else "i915", v, "n", "0000:01:00.0")
            for i, v in enumerate(vendors)]


def _no_popen(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Prozess gestartet")
    monkeypatch.setattr(gpu_tools.subprocess, "Popen", boom)


def test_hints_missing_tools(monkeypatch):
    _no_popen(monkeypatch)
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: None)
    t = GpuTools(_gpus("intel", "nvidia"))
    assert t.hints() == ["hint.igt_missing", "hint.nvsmi_missing"]
    assert t.intel("card0") is None and t.nvidia("0000:01:00.0") is None
    assert GpuTools(_gpus("amd")).hints() == []


def test_hint_noperm_does_not_start(monkeypatch):
    _no_popen(monkeypatch)
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: "/usr/bin/" + n)
    monkeypatch.setattr(gpu_tools.os, "geteuid", lambda: 1000)

    def nocap(*a):
        raise OSError
    monkeypatch.setattr(gpu_tools.os, "getxattr", nocap)
    t = GpuTools(_gpus("intel"))
    assert t.hints() == ["hint.igt_noperm"] and t.intel("card0") is None


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
        ("/usr/bin/intel_gpu_top", "-J", "-s", "1000", "-d", "drm:/dev/dri/card0"),
        ("/usr/bin/intel_gpu_top", "-J", "-s", "1000", "-d", "drm:/dev/dri/card1")}
    t.stop()


def test_nvidia_lookup_by_normalized_pci(monkeypatch):
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: sys.executable if n == "nvidia-smi" else None)
    line = "00000000:01:00.0, GTX, 18, 1, 2, 54, 40.5, 607, 1911, 0"
    monkeypatch.setattr(gpu_tools, "_nvidia_cmd", lambda path: [sys.executable, "-c", f"print({line!r}, flush=True);import time;time.sleep(5)"])
    t = GpuTools(_gpus("nvidia"))
    wait_until(lambda: t.nvidia("0000:01:00.0") is not None)
    assert t.nvidia("0000:01:00.0")["busy"] == 18.0 and t.nvidia("0000:02:00.0") is None
    t.stop()


@pytest.mark.skipif(not shutil.which("intel_gpu_top", path=gpu_tools.TOOL_PATH) or not Path("/sys/class/drm/card1").exists(),
                    reason="intel_gpu_top fehlt")
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


def test_brace_prefixed_line_in_name_keeps_object():
    lines = ['{\n', '\t"engines": {"R": {"busy": 3}},\n', '\t"clients": {\n', '\t\t"1": {\n',
             '\t\t\t"name": "x\n', '{y",\n', '\t\t\t"n2": "p\n', '\t{\n', 'q",\n', '\t\t}\n', '\t}\n', '}\n']
    assert list(split_json_stream(lines)) == [{"engines": {"R": {"busy": 3}}}]


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
