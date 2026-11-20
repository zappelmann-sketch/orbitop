# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""ProcTable: CPU-Rate und Einstufung (Dauerlast, Kernel-Hänger) über die Stichproben."""
import pytest

from orbitop.procs import ProcTable
from tests.procs_helpers import CLK, raw


def test_cpu_percent_one_core_and_first_sample_zero():
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(ticks=1000)}, 0)
    assert t.rows(0)[0]["cpu"] == 0.0
    t.update({(10, 1): raw(ticks=1200)}, 2.0)
    assert t.rows(2.0)[0]["cpu"] == pytest.approx(100.0)


@pytest.mark.parametrize("now,ticks", [(2.0, 50), (9.0, 5000), (0.0, 5000)])
def test_cpu_zero_on_counter_decrease_or_bad_dt(now, ticks):
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(ticks=100)}, 0)
    t.update({(10, 1): raw(ticks=ticks)}, now)
    assert t.rows(now)[0]["cpu"] == 0.0


def test_busy_noio_after_120s():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(61):
        t.update({(10, 1): raw(ticks=i * 198, io=7)}, i * 2.0)
    assert t.rows(120.0)[0]["state"] == "busy_noio"


def test_busy_streak_broken_by_one_sample_and_unknown_io():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(61):
        t.update({(10, 1): raw(ticks=(i if i != 30 else 29) * 198, io=None)}, i * 2.0)
    assert t.rows(120.0)[0]["state"] != "busy_iounknown"  # Sample 30 ist nicht ausgelastet
    t2 = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(61):
        t2.update({(10, 1): raw(ticks=i * 198, io=None)}, i * 2.0)
    assert t2.rows(120.0)[0]["state"] == "busy_iounknown"


def test_d_state_becomes_kernel_hang_then_resets():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(7):
        t.update({(10, 1): raw(state="D")}, i * 2.0)
    assert t.rows(12.0)[0]["state"] == "kernel_hang"
    t.update({(10, 1): raw(state="S")}, 14.0)
    assert t.rows(14.0)[0]["state"] == "waiting"


def test_d_state_clock_restarts_after_suspend_gap():
    """Ruhezustand: dt > MAX_DT macht die Stichprobe ungültig; die D-Uhr darf nicht von vor dem Schlaf weiterlaufen."""
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(4):
        t.update({(10, 1): raw(state="D")}, i * 2.0)
    t.update({(10, 1): raw(state="D")}, 1000.0)
    assert t.rows(1000.0)[0]["state"] != "kernel_hang"
    for i in range(1, 7):
        t.update({(10, 1): raw(state="D")}, 1000.0 + i * 2.0)
    assert t.rows(1010.0)[0]["state"] == "working"  # genau 10 s: Schwelle ist strikt
    row = t.rows(1012.0)[0]
    assert row["state"] == "kernel_hang" and row["since"] == 12


@pytest.mark.parametrize("ticks,io", [(20, 4_000_000), (20, None), (0, 4_000_000)])
def test_d_state_with_progress_is_never_kernel_hang(ticks, io):
    """Gedrosseltes Schreiben (USB-Stick, NFS): jede Stichprobe D, aber CPU-Ticks oder E/A wachsen weiter."""
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(7):
        t.update({(10, 1): raw(state="D", ticks=i * ticks, io=None if io is None else i * io)}, i * 2.0)
    assert t.rows(12.0)[0]["state"] == "working"
    for i in range(7, 14):  # ab jetzt ohne Fortschritt: die Uhr beginnt erst hier
        t.update({(10, 1): raw(state="D", ticks=6 * ticks, io=None if io is None else 6 * io)}, i * 2.0)
    assert t.rows(26.0)[0]["state"] == "kernel_hang" and t.rows(26.0)[0]["since"] == 12


def test_d_state_reentry_restarts_clock():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for now, st in [(0, "D"), (2, "D"), (4, "S"), (16, "D")]:
        t.update({(10, 1): raw(state=st)}, float(now))
    assert t.rows(16.0)[0]["state"] == "working"


def test_dt_boundary_and_io_decrease():
    for now, ok in [(5.0, True), (5.01, False)]:
        t = ProcTable(clk_tck=CLK, uid=1000)
        t.update({(10, 1): raw(ticks=0, io=100)}, 0)
        t.update({(10, 1): raw(ticks=500, io=50)}, now)
        r = t.rows(now)[0]
        assert (r["cpu"] > 0) is ok and r["io"] is None
