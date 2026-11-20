# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Hilfen der Werkzeug-Tests: ein Ersatz für die Ausgabe von intel_gpu_top, Warten, GPU-Listen."""
import time

from orbitop import gpu_tools
from orbitop.gpu import GpuInfo

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


def gpus(*vendors):
    return [GpuInfo(f"card{i}", "nvidia" if v == "nvidia" else "i915", v, "n", "0000:01:00.0")
            for i, v in enumerate(vendors)]


def no_popen(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Prozess gestartet")
    monkeypatch.setattr(gpu_tools.subprocess, "Popen", boom)
