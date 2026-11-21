# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Erkennen von intel_gpu_top: Vorrang von /usr/bin in TOOL_PATH (B2.5) und GpuTools.recheck() ohne Neustart (Q3)."""
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from orbitop import gpu_tools
from orbitop.gpu_tools import GpuTools
from orbitop.sampler import Sampler
from tests.gpu_tools_helpers import LOOP, gpus, no_popen, wait_until
from tests.roots import VM

IGT = "/usr/bin/intel_gpu_top"


# ---- TOOL_PATH (B2.5: /usr/bin zuerst, /usr/local/bin nur als Rückfall) ----
def _tools(tmp_path, *dirs):
    for d in dirs:
        f = tmp_path / d.lstrip("/") / "intel_gpu_top"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"\x7fELF")
        f.chmod(0o755)
    return ":".join(str(tmp_path) + d for d in gpu_tools.TOOL_PATH.split(":"))


def test_tool_path_prefers_usr_bin(tmp_path):
    path = _tools(tmp_path, "/usr/local/bin", "/usr/bin")
    assert gpu_tools.shutil.which("intel_gpu_top", path=path) == str(tmp_path / "usr/bin/intel_gpu_top")


def test_tool_path_falls_back_to_usr_local_bin(tmp_path):
    path = _tools(tmp_path, "/usr/local/bin")
    assert gpu_tools.shutil.which("intel_gpu_top", path=path) == str(tmp_path / "usr/local/bin/intel_gpu_top")


def test_tool_path_order():
    dirs = gpu_tools.TOOL_PATH.split(":")
    assert dirs[0] == "/usr/bin" and dirs.index("/usr/local/bin") > dirs.index("/usr/bin")
    assert all(os.path.isabs(d) for d in dirs) and len(set(dirs)) == len(dirs)


# ---- recheck (Q3): laufende Intel-Leser beenden und neu erkennen wie beim Start ----
@pytest.fixture
def world(monkeypatch):
    """Ein Rechner, dessen intel_gpu_top und Fähigkeit der Test umstellt; jeder Start läuft als Python-Schleife."""
    state = {"tool": None, "cap": False, "cmds": [], "procs": []}
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: state["tool"] if n == "intel_gpu_top" else None)
    monkeypatch.setattr(gpu_tools.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(gpu_tools.counters, "perf_capable", lambda p: state["cap"])
    real = gpu_tools.subprocess.Popen

    def popen(cmd, **kw):
        state["cmds"].append(cmd)
        state["procs"].append(real([sys.executable, "-c", LOOP], **kw))
        return state["procs"][-1]
    monkeypatch.setattr(gpu_tools.subprocess, "Popen", popen)
    return state


@pytest.mark.parametrize("before,hint", [({"tool": None}, "hint.igt_missing"),
                                         ({"tool": IGT, "cap": False}, "hint.igt_noperm")])
def test_recheck_starts_reader_after_install(world, before, hint):
    """Erst kein Werkzeug (oder keine Fähigkeit), dann ist es da: nach recheck() läuft ein Leser, kein Hinweis."""
    world.update(before)
    t = GpuTools(gpus("intel"))
    try:
        assert t.hints() == [hint] and t.intel("card0") is None and world["cmds"] == []
        world.update(tool=IGT, cap=True)
        t.recheck()
        wait_until(lambda: t.intel("card0") is not None)
        assert t.hints() == [] and world["cmds"] == [[IGT, "-J", "-s", "2000"]]
    finally:
        t.stop()


def test_recheck_stops_running_readers_before_detecting(world):
    world.update(tool=IGT, cap=True)
    t = GpuTools(gpus("intel", "intel"))
    try:
        wait_until(lambda: t.intel("card0") is not None and t.intel("card1") is not None)
        old = list(world["procs"])
        world["cap"] = False  # etwa nach „aus“: die Fähigkeit ist weg
        t.recheck()
        assert all(p.poll() is not None for p in old)
        assert t.hints() == ["hint.igt_noperm"] and t.intel("card0") is None and len(world["procs"]) == 2
        world["cap"] = True
        t.recheck()
        wait_until(lambda: t.intel("card1") is not None)
        assert len(world["procs"]) == 4 and [c[-1] for c in world["cmds"][2:]] == ["drm:/dev/dri/card0",
                                                                                    "drm:/dev/dri/card1"]
    finally:
        t.stop()
    assert all(p.poll() is not None for p in world["procs"])


def test_recheck_keeps_nvidia_hint(world):
    t = GpuTools(gpus("intel", "nvidia"))
    assert t.hints() == ["hint.igt_missing", "hint.nvsmi_missing"]
    world.update(tool=IGT, cap=False)
    t.recheck()
    assert t.hints() == ["hint.igt_noperm", "hint.nvsmi_missing"]
    t.stop()


def test_recheck_without_intel_gpu_starts_nothing(monkeypatch):
    no_popen(monkeypatch)
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: "/usr/bin/" + n)
    t = GpuTools(gpus("amd"))
    t.recheck()
    assert t.hints() == []


def test_recheck_after_stop_starts_nothing(world):
    """Beim Beenden der App kann ein Auftrag noch recheck() auslösen: danach darf kein Leser mehr starten."""
    world.update(tool=IGT, cap=True)
    t = GpuTools(gpus("intel"))
    t.stop()
    started = len(world["procs"])
    t.recheck()
    assert len(world["procs"]) == started and t.intel("card0") is None
    assert all(p.poll() is not None for p in world["procs"])


# ---- recheck aus einem Auftrags-Thread, neben dem Mess-Thread; Ersatz-Leser, kein Kindprozess ----
@pytest.fixture
def fake_readers(monkeypatch):
    """ToolReader ersetzt; live: gestartete und nicht beendete Leser, starts/stops: Zahl der Aufrufe, stopping:
    gesetzt beim ersten stop(), slow: so lange dauert stop() (wie das Warten auf intel_gpu_top), tool: Pfad des
    Werkzeugs oder None, cap: die Fähigkeit, uid: die euid."""
    s = SimpleNamespace(live=set(), starts=0, stops=0, stopping=threading.Event(), slow=0.0, tool=IGT, cap=False,
                        uid=0)

    class Reader:
        failed = False

        def __init__(self, cmd, parse):
            pass

        def start(self):
            s.live.add(self)
            s.starts += 1

        def latest(self, key=None):
            return {"busy": 1.0} if self in s.live else None

        def stop(self):
            s.stopping.set()
            s.stops += 1
            time.sleep(s.slow)
            s.live.discard(self)
    monkeypatch.setattr(gpu_tools, "ToolReader", Reader)
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda n, path=None: s.tool if n == "intel_gpu_top" else None)
    monkeypatch.setattr(gpu_tools.os, "geteuid", lambda: s.uid)  # root liest ohne Fähigkeit
    monkeypatch.setattr(gpu_tools.counters, "perf_capable", lambda path: s.cap)
    return s


def test_needs_recheck_is_pure_and_follows_tool_and_capability(fake_readers, monkeypatch):
    """Vergleicht nur, was GpuTools annimmt, mit dem, was jetzt zu sehen ist; startet und beendet nie etwas."""
    fake_readers.uid = 1000
    t = GpuTools(gpus("intel"))
    assert t.hints() == ["hint.igt_noperm"]
    no_popen(monkeypatch)
    assert [t.needs_recheck() for _ in range(3)] == [False] * 3
    fake_readers.cap = True  # etwa nach „an“ von außen
    assert t.needs_recheck() and t.hints() == ["hint.igt_noperm"] and fake_readers.starts == 0
    fake_readers.tool = None  # Werkzeug entfernt
    assert t.needs_recheck()
    t.recheck()
    assert t.hints() == ["hint.igt_missing"] and not t.needs_recheck()
    fake_readers.tool = IGT
    t.recheck()
    assert fake_readers.live and not t.needs_recheck()  # Leser laufen, wie es die Fähigkeit erlaubt
    fake_readers.cap = False
    assert t.needs_recheck()
    assert not GpuTools(gpus("amd")).needs_recheck()  # ohne Intel-Grafik gibt es nichts neu zu erkennen
    t.stop()


def test_recheck_tools_leaves_running_readers_alone_when_nothing_changed(fake_readers):
    """Zweimal „schon so“ bei gleichem Zustand: kein Neustart der Leser; erst eine neue Fähigkeit erkennt neu."""
    fake_readers.uid = 1000
    t = GpuTools(gpus("intel"))
    s = Sampler(VM, tools=t, uid=1000)
    s.recheck_tools()
    s.recheck_tools()
    assert (fake_readers.starts, fake_readers.stops) == (0, 0) and t.hints() == ["hint.igt_noperm"]
    fake_readers.cap = True
    s.recheck_tools()
    assert (fake_readers.starts, fake_readers.stops) == (1, 0) and t.hints() == []
    s.recheck_tools()
    s.recheck_tools()
    assert (fake_readers.starts, fake_readers.stops) == (1, 0) and len(fake_readers.live) == 1
    t.stop()


def test_two_concurrent_rechecks_then_stop_leave_no_reader(fake_readers):
    """Ein zweites recheck, während das erste noch alte Leser beendet, ließ einen Leser laufen, den stop() nie fand."""
    fake_readers.slow = 0.2
    t = GpuTools(gpus("intel"))
    first = threading.Thread(target=t.recheck)
    first.start()
    assert fake_readers.stopping.wait(2)
    second = threading.Thread(target=t.recheck)
    second.start()
    first.join(5)
    second.join(5)
    assert len(fake_readers.live) == 1
    t.stop()
    assert fake_readers.live == set()


def test_recheck_while_the_sampler_reads(fake_readers):
    t = GpuTools(gpus("intel"))
    seen, errors, done = set(), [], threading.Event()

    def sampler():
        while not done.is_set():
            try:
                t.intel("card0")
                seen.add(tuple(t.hints()))
            except Exception as e:  # jeder Fehler im Mess-Thread zählt
                errors.append(e)
    reader = threading.Thread(target=sampler)
    reader.start()
    for i in range(40):
        fake_readers.tool = IGT if i % 2 else None  # abwechselnd installiert und entfernt
        t.recheck()
    done.set()
    reader.join(5)
    t.stop()
    assert errors == [] and seen <= {(), ("hint.igt_missing",)} and fake_readers.live == set()
