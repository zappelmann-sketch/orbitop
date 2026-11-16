# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from orbitop import gpu_tools
from orbitop.gpu import GpuInfo, discover_gpus
from orbitop.gpu_tools import (GpuTools, ToolReader, parse_intel, parse_nvidia_line,
                               split_json_stream, split_lines)

FIX = Path(__file__).parent / "fixtures" / "tools"
LOOP = ("import time\nprint('[', flush=True)\n"
        "while True:\n print('{\"engines\":{\"Render/3D\":{\"busy\":7.5}}},', flush=True); time.sleep(0.1)")


def wait_until(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    raise AssertionError("Bedingung nicht erreicht")


def test_split_and_parse_recorded_intel():
    objs = list(split_json_stream(open(FIX / "intel_gpu_top.json")))
    assert len(objs) >= 2
    s = parse_intel(objs[-1])
    assert 0 <= s["busy"] <= 100 and s["freq_mhz"] >= 0


def test_parse_intel_old_engine_names():
    assert parse_intel({"engines": {"Render/3D/0": {"busy": 12.5}}})["busy"] == 12.5


def test_parse_intel_missing_fields():
    assert parse_intel({}) == {"busy": None, "freq_mhz": None, "gpu_w": None, "pkg_w": None}


def test_split_across_chunks_and_strings():
    chunks = ['[\n{"a": "}{", "b": {"c', '": 1}},\n{"d": 2', '}']
    assert list(split_json_stream(chunks)) == [{"a": "}{", "b": {"c": 1}}, {"d": 2}]


def test_split_skips_malformed():
    assert list(split_json_stream(['{"a": }, {"b": 1}'])) == [{"b": 1}]


def test_split_drops_oversized_object_and_resyncs():
    big = ['{"x": "'] + ["a" * 65536] * 20 + ['"}\n{"ok": 1}']  # ~1.3 MiB, schließt nie vor dem Limit
    assert list(split_json_stream(big)) == [{"ok": 1}]


def test_parse_nvidia_na():
    d = parse_nvidia_line("00000000:01:00.0, NVIDIA GeForce GTX 1080, 18, 3379, 8192, 54, [N/A], 607, 1911, 0")
    assert d["pci"] == "0000:01:00.0" and d["power_w"] is None and d["busy"] == 18.0
    assert d["name"] == "NVIDIA GeForce GTX 1080" and d["vram_total"] == 8192.0 and d["fan_pct"] == 0.0


def test_parse_nvidia_fixture_not_supported():
    lines = list(split_lines(open(FIX / "nvidia-smi.csv")))
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
    r = ToolReader([sys.executable, "-c", "print('{\"engines\":{}}', flush=True)"], parse_intel)
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


def _gpus(*vendors):
    return [GpuInfo(f"card{i}", "x", v, "n", "0000:01:00.0") for i, v in enumerate(vendors)]


def _no_popen(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Prozess gestartet")
    monkeypatch.setattr(gpu_tools.subprocess, "Popen", boom)


def test_hints_missing_tools(monkeypatch):
    _no_popen(monkeypatch)
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n: None)
    t = GpuTools(_gpus("intel", "nvidia"))
    assert t.hints() == ["hint.igt_missing", "hint.nvsmi_missing"]
    assert t.intel("card0") is None and t.nvidia("0000:01:00.0") is None
    assert GpuTools(_gpus("amd")).hints() == []


def test_hint_noperm_does_not_start(monkeypatch):
    _no_popen(monkeypatch)
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(gpu_tools.os, "geteuid", lambda: 1000)

    def nocap(*a):
        raise OSError
    monkeypatch.setattr(gpu_tools.os, "getxattr", nocap)
    t = GpuTools(_gpus("intel"))
    assert t.hints() == ["hint.igt_noperm"] and t.intel("card0") is None


def test_hint_failed_and_device_argument(monkeypatch):
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n: "/usr/bin/" + n)
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
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n: sys.executable if n == "nvidia-smi" else None)
    line = "00000000:01:00.0, GTX, 18, 1, 2, 54, 40.5, 607, 1911, 0"
    monkeypatch.setattr(gpu_tools, "_nvidia_cmd", lambda path: [sys.executable, "-c", f"print({line!r}, flush=True);import time;time.sleep(5)"])
    t = GpuTools(_gpus("nvidia"))
    wait_until(lambda: t.nvidia("0000:01:00.0") is not None)
    assert t.nvidia("0000:01:00.0")["busy"] == 18.0 and t.nvidia("0000:02:00.0") is None
    t.stop()


@pytest.mark.skipif(not shutil.which("intel_gpu_top") or not Path("/sys/class/drm/card1").exists(),
                    reason="intel_gpu_top fehlt")
def test_real_intel_gpu_top_delivers_within_3s():
    t = GpuTools(discover_gpus("/"))
    try:
        wait_until(lambda: t.intel("card1") is not None, 3)
    finally:
        t.stop()


def test_split_escaped_quote_in_string():
    assert list(split_json_stream(['{"a": "x\\"}y"}'])) == [{"a": 'x"}y'}]
