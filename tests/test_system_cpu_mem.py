# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import glob
import os
import shutil

import pytest

from orbitop.system import CpuReader, read_memory
from tests.roots import AMD, ARM, INTEL, VM


def write_stat(root, rows, ids=None):
    """rows: Liste (busy, idle) je Thread (CPU-Nummern ids, sonst 0..n-1); Zeile "cpu" ist die Summe."""
    lines = [f"cpu {sum(b for b, _ in rows)} 0 0 {sum(i for _, i in rows)} 0 0 0 0 0 0"]
    lines += [f"cpu{n} {b} 0 0 {i} 0 0 0 0 0 0" for n, (b, i) in zip(ids or range(len(rows)), rows)]
    with open(f"{root}/proc/stat", "w") as f:
        f.write("\n".join(lines) + "\nintr 1\n")


def test_cpu_first_read_none_then_percent(intel_copy):
    write_stat(intel_copy, [(100, 100)] * 4)
    r = CpuReader(intel_copy)
    first = r.read(0.0)
    assert first.total is None and first.threads == [None] * 4
    write_stat(intel_copy, [(150, 150)] * 4)
    s = r.read(1.0)
    assert s.total == pytest.approx(50.0) and len(s.threads) == 4
    assert s.threads == [pytest.approx(50.0)] * 4
    assert s.freq_ghz and 0.1 < s.freq_ghz < 10


@pytest.mark.parametrize("dt", [400.0, 0.0, -1.0])
def test_cpu_gap_after_bad_dt(intel_copy, dt):
    write_stat(intel_copy, [(100, 100)] * 4)
    r = CpuReader(intel_copy)
    r.read(10.0)
    write_stat(intel_copy, [(150, 150)] * 4)
    s = r.read(10.0 + dt)
    assert s.total is None and s.threads == [None] * 4


def test_cpu_counter_decrease_is_gap(intel_copy):
    write_stat(intel_copy, [(100, 100)] * 4)
    r = CpuReader(intel_copy)
    r.read(0.0)
    write_stat(intel_copy, [(10, 10)] * 4)
    s = r.read(1.0)
    assert s.total is None and s.threads == [None] * 4


def test_cpu_busy_or_idle_backwards_is_gap(intel_copy):
    write_stat(intel_copy, [(100, 100)] * 4)
    r = CpuReader(intel_copy)
    r.read(0.0)
    write_stat(intel_copy, [(200, 50)] * 4)  # idle ging zurück, Summe stieg
    s = r.read(1.0)
    assert s.total is None and s.threads == [None] * 4


def test_cpu_middle_thread_offline_keeps_index(intel_copy):
    write_stat(intel_copy, [(100, 100)] * 4)
    r = CpuReader(intel_copy)
    r.read(0.0)
    write_stat(intel_copy, [(150, 150), (190, 190), (200, 100)], ids=[0, 2, 3])
    t = r.read(1.0).threads
    assert len(t) == 4 and t[1] is None
    assert t[0] == pytest.approx(50.0) and t[2] == pytest.approx(50.0)
    assert t[3] == pytest.approx(100.0)
    write_stat(intel_copy, [(200, 200)] * 4)
    t = r.read(2.0).threads
    assert len(t) == 4 and t[1] is None and t[0] == pytest.approx(50.0)
    write_stat(intel_copy, [(250, 250)] * 4)
    assert r.read(3.0).threads == [pytest.approx(50.0)] * 4


def test_cpu_empty_or_missing_stat(intel_copy):
    r = CpuReader(intel_copy)
    open(f"{intel_copy}/proc/stat", "w").close()
    s = r.read(0.0)
    assert s.total is None and s.threads == []
    with open(f"{intel_copy}/proc/stat", "w") as f:
        f.write("cpu abc\ncpu0 1 2\ngarbage\n")
    s = r.read(1.0)
    assert s.total is None and s.threads == []
    os.remove(f"{intel_copy}/proc/stat")
    assert r.read(2.0).threads == []


def test_cpu_model_and_freq():
    assert CpuReader(ARM).read(0).model == "Raspberry Pi 5 Model B"
    assert "model name" not in open(f"{ARM}/proc/cpuinfo").read()
    assert CpuReader(INTEL).read(0).model == "Intel(R) Core(TM) i7-7600U CPU @ 2.80GHz"


def test_cpu_model_priority_and_hardware(tmp_path):
    (tmp_path / "proc").mkdir()
    cpuinfo = tmp_path / "proc/cpuinfo"
    cpuinfo.write_text("Hardware\t: H\nModel\t: M\nmodel name\t: N\n")
    assert CpuReader(str(tmp_path)).read(0).model == "N"
    cpuinfo.write_text("Hardware\t: H\nModel\t: M\n")
    assert CpuReader(str(tmp_path)).read(0).model == "M"
    cpuinfo.write_text("Hardware\t: H\n")
    assert CpuReader(str(tmp_path)).read(0).model == "H"
    cpuinfo.write_text("processor\t: 0\n")
    assert CpuReader(str(tmp_path)).read(0).model == ""


def test_cpu_freq_none_without_cpufreq(intel_copy):
    for p in glob.glob(f"{intel_copy}/sys/devices/system/cpu/cpu*/cpufreq"):
        shutil.rmtree(p)
    assert CpuReader(intel_copy).read(0).freq_ghz is None


def test_cpu_threads_amd():
    assert len(CpuReader(AMD).read(0).threads) == 16


def test_cpu_vm_two_threads():
    assert len(CpuReader(VM).read(0).threads) == 2


def _meminfo_kb(root, key):
    for line in open(f"{root}/proc/meminfo"):
        if line.startswith(key + ":"):
            return int(line.split()[1])


def test_memory_values_pinned():
    m = read_memory(INTEL)
    kb = lambda k: _meminfo_kb(INTEL, k) * 1024  # noqa: E731
    assert m.total == kb("MemTotal") == 15727988 * 1024
    assert m.available == kb("MemAvailable")
    assert m.used == m.total - m.available
    assert m.swap_total == kb("SwapTotal") > 0
    assert m.swap_used == kb("SwapTotal") - kb("SwapFree")


def test_memory_missing_file(tmp_path):
    m = read_memory(str(tmp_path))
    assert (m.total, m.available, m.used, m.swap_total, m.swap_used) == (0, 0, 0, 0, 0)
