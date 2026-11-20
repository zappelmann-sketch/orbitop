# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Worker mit echten Threads: sofortiger Start, schnelles Ende, hängender Prozess-Scan."""
import json
import threading
import time

from orbitop.app import Worker
from tests.app_helpers import FakeSampler


def test_worker_thread_kicks_immediately_and_stops_fast():
    s = FakeSampler()
    got = threading.Event()
    posts = []
    w = Worker(s, lambda p: (posts.append(p), got.set()))
    w.start()
    deadline = time.monotonic() + 2
    while not s.calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert s.sys_times() == [None] and posts == []
    t0 = time.monotonic()
    assert w.update(visible=True, ready=True)
    assert got.wait(0.5)  # sofort, nicht erst beim nächsten Takt
    assert time.monotonic() - t0 < 0.5 and len(s.sys_times()) == 1
    t0 = time.monotonic()
    w.stop()
    assert time.monotonic() - t0 < 0.5
    assert not any(t.name in ("orbitop-worker", "orbitop-procs") for t in threading.enumerate())
    n = len(s.calls)
    time.sleep(1.2)
    assert len(s.calls) == n


def test_blocking_process_scan_does_not_stop_tiles(monkeypatch):
    """/proc/<pid>/cmdline kann blockieren (mmap-Lock bei hängendem FUSE/NFS): Das hält nur die Prozessliste an."""
    from orbitop import app, sampler as sampler_mod
    from orbitop.gpu_tools import GpuTools
    from tests.roots import VM
    from tests.procs_helpers import raw
    monkeypatch.setattr(app, "PERIOD_S", 0.05)
    monkeypatch.setattr(app, "PROCS_PERIOD_S", 0.1)
    entered, release = threading.Event(), threading.Event()

    def blocking(*a, **k):
        entered.set()
        release.wait(5)
        return {(10, 1): raw()}
    monkeypatch.setattr(sampler_mod.procs, "scan", blocking)
    s = sampler_mod.Sampler(VM, tools=GpuTools([]), uid=1000)
    posts = []
    w = Worker(s, posts.append)
    w.start()
    try:
        assert w.update(visible=True, ready=True)
        assert entered.wait(2)
        cpu_points = lambda: len(next(t for t in json.loads(posts[-1])["tiles"] if t["id"] == "cpu")["series"][0]["values"])  # noqa: E731
        time.sleep(0.1)
        before = (len(posts), cpu_points())
        time.sleep(0.4)
        assert len(posts) >= before[0] + 4 and cpu_points() >= before[1] + 4  # Kacheln laufen weiter
        assert json.loads(posts[-1])["top"]["mem"] is None  # Prozessliste steht
        release.set()
        deadline = time.monotonic() + 2
        while json.loads(posts[-1])["top"]["mem"] is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert json.loads(posts[-1])["top"]["mem"]["pid"] == 10  # nach der Freigabe geht es weiter
    finally:
        release.set()
        w.stop()
    assert not any(t.name in ("orbitop-worker", "orbitop-procs") for t in threading.enumerate())
