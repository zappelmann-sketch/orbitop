# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os

import pytest

from orbitop.system import CpuReader, read_memory
from tests.conftest import AMD, ARM, INTEL, VM


def write_stat(root, rows):
    """rows: Liste (busy, idle) je Thread; Zeile "cpu" ist die Summe."""
    lines = [f"cpu {sum(b for b, _ in rows)} 0 0 {sum(i for _, i in rows)} 0 0 0 0 0 0"]
    lines += [f"cpu{n} {b} 0 0 {i} 0 0 0 0 0 0" for n, (b, i) in enumerate(rows)]
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
    assert r.read(10.0 + dt).total is None


def test_cpu_counter_decrease_is_gap(intel_copy):
    write_stat(intel_copy, [(100, 100)] * 4)
    r = CpuReader(intel_copy)
    r.read(0.0)
    write_stat(intel_copy, [(10, 10)] * 4)
    assert r.read(1.0).total is None


def test_cpu_thread_goes_offline(intel_copy):
    write_stat(intel_copy, [(100, 100)] * 4)
    r = CpuReader(intel_copy)
    r.read(0.0)
    write_stat(intel_copy, [(150, 150)] * 3)
    assert len(r.read(1.0).threads) == 3
    write_stat(intel_copy, [(200, 200)] * 4)
    s = r.read(2.0)
    assert len(s.threads) == 4 and s.threads[3] is None


def test_cpu_empty_or_missing_stat(intel_copy):
    r = CpuReader(intel_copy)
    open(f"{intel_copy}/proc/stat", "w").close()
    s = r.read(0.0)
    assert s.total is None and s.threads == []
    with open(f"{intel_copy}/proc/stat", "w") as f:
        f.write("cpu abc\ncpu0 1 2\ngarbage\n")
    assert r.read(1.0).total is None
    os.remove(f"{intel_copy}/proc/stat")
    assert r.read(2.0).threads == []


def test_cpu_model_and_freq_fallbacks():
    assert CpuReader(ARM).read(0).model == "Raspberry Pi 5 Model B"
    assert "model name" not in open(f"{ARM}/proc/cpuinfo").read()
    assert CpuReader(INTEL).read(0).model != ""


def test_cpu_threads_amd():
    assert len(CpuReader(AMD).read(0).threads) == 16


def test_cpu_vm_two_threads():
    assert len(CpuReader(VM).read(0).threads) == 2


def test_memory_used_is_total_minus_available():
    m = read_memory(INTEL)
    assert m.used == m.total - m.available and m.swap_total > 0
    assert 0 <= m.swap_used <= m.swap_total


def test_memory_missing_file(tmp_path):
    m = read_memory(str(tmp_path))
    assert (m.total, m.available, m.used, m.swap_total, m.swap_used) == (0, 0, 0, 0, 0)
