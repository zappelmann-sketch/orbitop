# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""ProcTable: Zeilen, Detail, Verlauf, Toplisten und Kernel-Kennzeichen."""
import pytest

from orbitop import procs
from orbitop.procs import ProcTable
from tests.procs_helpers import CLK, raw


def test_history_caps_at_150_and_spark_at_30():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(200):
        t.update({(10, 1): raw(ticks=i * 50)}, i * 2.0)
    assert len(t.detail(10, 1, 400)["history"]) == 150
    assert len(t.rows(400)[0]["spark"]) == 30


def test_hidden_4_s_ticks_keep_one_history_point_per_2_s():
    """Ausgeblendet (Prozess-Takt 4 s) zählt jeder Wert doppelt: „Letzte 60 s“ und die 5-min-Kurve bleiben wahr."""
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(ticks=0)}, 0.0)
    for i in range(1, 4):  # sichtbar: alle 2 s, 10 % CPU
        t.update({(10, 1): raw(ticks=i * CLK // 5)}, i * 2.0)
    before = len(t.detail(10, 1, 6.0)["history"])
    for i in range(1, 6):  # ausgeblendet: alle 4 s, 50 % CPU
        t.update({(10, 1): raw(ticks=3 * CLK // 5 + i * 2 * CLK)}, 6.0 + i * 4.0)
    hist = t.detail(10, 1, 26.0)["history"]
    assert before == 4 and len(hist) == before + 2 * 5
    assert (len(hist) - 1) * 2.0 == 26.0  # ein Punkt je 2 s seit dem ersten Takt
    assert hist[before:] == pytest.approx([50.0] * 10)  # Treppe für die ausgeblendete Zeit


@pytest.mark.parametrize("dt,points,cpu", [(5.5, 3, 50.0), (10.0, 5, 50.0), (3600.0, 1, 0.0)])
def test_late_hidden_tick_counts_but_suspend_gap_does_not(dt, points, cpu):
    """Ein ausgeblendeter Takt (4 s), der 1,5 s zu spät kommt, ist gültig; höchstens PROCS_MAX_DT / STEP_S Punkte.
    Eine Lücke von einer Stunde (Ruhezustand) ist ungültig und hängt genau einen Punkt an."""
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(ticks=0)}, 0.0)
    t.update({(10, 1): raw(ticks=int(dt * CLK) // 2)}, dt)
    hist = t.detail(10, 1, dt)["history"]
    assert len(hist) == 1 + points and hist[-1] == pytest.approx(cpu)


def test_pid_reuse_gets_fresh_history_and_dead_removed():
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(start=1), (11, 1): raw(pid=11)}, 0)
    t.update({(10, 2): raw(start=2)}, 2.0)
    assert t.detail(10, 1, 2.0) is None and t.detail(11, 1, 2.0) is None
    assert len(t.detail(10, 2, 2.0)["history"]) == 1
    assert t.counts() == (1, 1)


def test_cmdline_cache_pruned_for_vanished_keys():
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.cmdlines.update({(10, 1): ("p", "x", ""), (11, 1): ("q", "y", "")})
    t.update({(10, 1): raw()}, 0)
    assert list(t.cmdlines) == [(10, 1)]


def test_rows_and_detail_shape(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "stat").write_text("cpu 1 2\nbtime 1000000\n")
    t = ProcTable(clk_tck=CLK, uid=1000, root=str(tmp_path))
    t.update({(1, 5): raw(pid=1, start=5, name="init"),
              (10, 1): raw(vctx=0, nvctx=0, io=0, uid=4242424, cmdline="/bin/p " + "y" * 200, ppid=1, args="y" * 200)}, 0)
    t.update({(1, 5): raw(pid=1, start=5, name="init"),
              (10, 1): raw(vctx=20, nvctx=4, io=2000, uid=4242424, cmdline="/bin/p " + "y" * 200, ppid=1, args="y" * 200)}, 2.0)
    d = t.detail(10, 1, 2.0)
    assert d["parent"] == "init" and d["own"] is False and d["user"] == "4242424"
    assert d["vctx"] == 10 and d["nvctx"] == 2 and d["io"] == 1000
    assert len(d["args"]) == 120 and d["args"].endswith("…") and d["cmdline"].startswith("/bin/p yy")
    assert d["started"] == 1000000 and t.detail(1, 5, 2.0)["started"] == 1000000
    assert t.detail(10, 99, 2.0) is None
    assert t.rows(2.0)[0]["own"] is True and t.rows(2.0)[1]["own"] is False


@pytest.mark.parametrize("pid,ppid,cmdline,want", [
    (1, 0, "/sbin/init splash", True),   # PID 1 auch mit Befehlszeile
    (5, 2, "", True), (5, 0, "", True),  # Kernel-Threads: Kind von 0 oder kthreadd, ohne Befehlszeile
    (5, 2, "/usr/bin/x", False),         # Kind von kthreadd mit Befehlszeile ist ein normaler Prozess
    (5, 1000, "", False),                # leere Befehlszeile allein reicht nicht
])
def test_is_kernel(pid, ppid, cmdline, want):
    assert procs.is_kernel(pid, ppid, cmdline) is want


def test_detail_has_kernel_flag(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "stat").write_text("btime 1000000\n")
    t = ProcTable(clk_tck=CLK, uid=1000, root=str(tmp_path))
    t.update({(1, 5): raw(pid=1, start=5, ppid=0, cmdline="/sbin/init"), (7, 1): raw(pid=7, ppid=2, cmdline=""),
              (8, 1): raw(pid=8, ppid=2, cmdline="/bin/x"), (9, 1): raw(pid=9, ppid=1000, cmdline="")}, 0)
    assert [t.detail(pid, start, 0)["kernel"] for pid, start in ((1, 5), (7, 1), (8, 1), (9, 1))] == [True, True, False, False]


def test_own_uses_table_uid():
    t = ProcTable(clk_tck=CLK, uid=4242)
    t.update({(10, 1): raw(uid=4242), (11, 1): raw(pid=11, uid=1000)}, 0)
    assert [r["own"] for r in t.rows(0)] == [True, False]


def test_started_offsets_btime_by_start_ticks(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "stat").write_text("btime 1000000\n")
    t = ProcTable(clk_tck=CLK, uid=1000, root=str(tmp_path))
    t.update({(10, 12345): raw(start=12345)}, 0)
    assert t.detail(10, 12345, 0)["started"] == 1000123


def test_user_refreshed_when_uid_changes():
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(uid=0)}, 0)
    assert t.rows(0)[0]["user"] == "root"
    t.update({(10, 1): raw(uid=4242424)}, 2.0)
    assert t.rows(2.0)[0]["user"] == "4242424"


def test_top_cpu_excludes_zero_cpu():
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(n, 1): raw(pid=n) for n in range(1, 6)}, 0)
    t.update({(n, 1): raw(pid=n, ticks=20 * n if n != 3 else 0) for n in range(1, 6)}, 2.0)
    assert len(t.top_cpu(n=5)) == 4


def test_spark_is_newest_30():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(40):
        t.update({(10, 1): raw(ticks=i * i * 10)}, i * 2.0)
    assert t.rows(80.0)[0]["spark"] == t.detail(10, 1, 80.0)["history"][-30:]
    assert t.rows(80.0)[0]["spark"][-1] > t.rows(80.0)[0]["spark"][0]


def test_top_lists_and_counts():
    t = ProcTable(clk_tck=CLK, uid=1000)
    assert t.top_mem() is None and t.top_cpu() == []
    mk = lambda n, ticks, rss: raw(pid=n, ticks=ticks, rss=rss, threads=2)
    t.update({(n, 1): mk(n, 0, n * 10) for n in range(1, 6)}, 0)
    t.update({(n, 1): mk(n, n * 20 if n != 3 else 0, n * 10) for n in range(1, 6)}, 2.0)
    assert [b["pid"] for b in t.top_cpu()] == [5, 4, 2]
    assert set(t.top_cpu()[0]) == {"pid", "start", "name", "cpu", "rss"}
    assert t.top_mem()["pid"] == 5 and t.counts() == (5, 10)


def test_row_has_top_fields():
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(ticks=12345, state="R", pri=20, nice=-5, virt=8192, shr=4096)}, 0.0)
    r = t.rows(0.0)[0]
    assert (r["pri"], r["nice"], r["virt"], r["shr"], r["s"], r["time"]) == (20, -5, 8192, 4096, "R", 123.45)
