# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import statistics
import timeit

import pytest

from orbitop.procs import ProcTable, RawProc, parse_stat, scan

CLK = 100


def stat_line(pid, comm="proc", state="S", ppid=1, ticks=(150, 50), threads=7, start=98765, rss=321):
    return (f"{pid} ({comm}) {state} {ppid} {pid} {pid} 0 -1 4194560 0 0 0 0 {ticks[0]} {ticks[1]} 0 0 20 0 "
            f"{threads} 0 {start} 0 {rss} 18446744073709551615")


def make_proc(root, pid, *, stat=True, status=True, io="rchar: 10\nwchar: 5\n", cmdline=b"/bin/x\0-a\0-b\0",
              uid=1000, **kw):
    d = root / "proc" / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    if stat:
        (d / "stat").write_text(stat if isinstance(stat, str) else stat_line(pid, **kw))
    if status:
        (d / "status").write_text(f"Name:\tx\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n"
                                  "voluntary_ctxt_switches:\t30\nnonvoluntary_ctxt_switches:\t4\n")
    if io is not None:
        (d / "io").write_text(io)
    (d / "cmdline").write_bytes(cmdline)


def raw(pid=10, start=1, ticks=0, io=0, vctx=0, nvctx=0, state="S", name="p", cmdline="/bin/p a", uid=1000,
        rss=4096, threads=1, ppid=1):
    return RawProc(pid, start, ppid, name, cmdline, uid, state, ticks, rss, threads, vctx, nvctx, io)


def test_parse_stat_comm_with_parens_and_spaces():
    d = parse_stat(stat_line(4242, comm="Web (Content) x"))
    assert d["name"] == "Web (Content) x" and d["state"] == "S" and d["ppid"] == 1
    assert d["threads"] == 7 and d["start"] == 98765 and d["ticks"] == 200 and d["rss"] == 321


def test_scan_skips_process_vanished_midway(tmp_path):
    make_proc(tmp_path, 100, status=False)
    make_proc(tmp_path, 101, stat=False)
    assert scan(str(tmp_path)) == {}


def test_scan_skips_malformed(tmp_path):
    make_proc(tmp_path, 100, stat="100 (x) S 1")
    make_proc(tmp_path, 101)
    (tmp_path / "proc" / "101" / "status").write_text("Name:\tx\n")
    assert scan(str(tmp_path)) == {}


def test_scan_ignores_non_pid_entries(tmp_path):
    make_proc(tmp_path, 100)
    (tmp_path / "proc" / "self").mkdir()
    (tmp_path / "proc" / "1٣").mkdir()
    assert list(scan(str(tmp_path))) == [(100, 98765)]


def test_scan_fields_and_bytes(tmp_path):
    make_proc(tmp_path, 100, comm="a)b c")
    r = scan(str(tmp_path), page_size=4096)[(100, 98765)]
    assert (r.name, r.cmdline, r.uid, r.io, r.rss, r.vctx, r.nvctx) == ("a)b c", "/bin/x -a -b", 1000, 15,
                                                                         321 * 4096, 30, 4)


def test_scan_io_none_for_foreign(tmp_path):
    make_proc(tmp_path, 100, io=None)
    assert scan(str(tmp_path))[(100, 98765)].io is None


def test_scan_kernel_thread_and_zombie_have_bracket_name(tmp_path):
    make_proc(tmp_path, 2, comm="kthreadd", cmdline=b"", io=None)
    r = scan(str(tmp_path))[(2, 98765)]
    assert r.name == "[kthreadd]" and r.cmdline == ""


def test_scan_cmdline_sanitized_and_bounded(tmp_path):
    make_proc(tmp_path, 100, cmdline=b"a\x1b[31m\0" + b"b" * 10000)
    c = scan(str(tmp_path))[(100, 98765)].cmdline
    assert c.startswith("a?[31m b") and len(c) == 4096


def test_scan_reads_cmdline_once_per_key(tmp_path):
    make_proc(tmp_path, 100)
    cache = {}
    scan(str(tmp_path), cache)
    (tmp_path / "proc" / "100" / "cmdline").write_bytes(b"changed")
    assert scan(str(tmp_path), cache)[(100, 98765)].cmdline == "/bin/x -a -b"


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


def test_history_caps_at_150_and_spark_at_30():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(200):
        t.update({(10, 1): raw(ticks=i * 50)}, i * 2.0)
    assert len(t.detail(10, 1, 400)["history"]) == 150
    assert len(t.rows(400)[0]["spark"]) == 30


def test_busy_noio_after_120s():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(62):  # 61 Intervalle; das erste Sample zählt nicht als ausgelastet
        t.update({(10, 1): raw(ticks=i * 198, io=7)}, i * 2.0)
    assert t.rows(122.0)[0]["state"] == "busy_noio"


def test_busy_streak_broken_by_one_sample_and_unknown_io():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(62):
        t.update({(10, 1): raw(ticks=(i if i != 30 else 29) * 198, io=None)}, i * 2.0)
    assert t.rows(122.0)[0]["state"] != "busy_iounknown"  # Sample 30 ist nicht ausgelastet
    t2 = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(62):
        t2.update({(10, 1): raw(ticks=i * 198, io=None)}, i * 2.0)
    assert t2.rows(122.0)[0]["state"] == "busy_iounknown"


def test_d_state_becomes_kernel_hang_then_resets():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for i in range(7):
        t.update({(10, 1): raw(state="D")}, i * 2.0)
    assert t.rows(12.0)[0]["state"] == "kernel_hang"
    t.update({(10, 1): raw(state="S")}, 14.0)
    assert t.rows(14.0)[0]["state"] == "waiting"


def test_pid_reuse_gets_fresh_history_and_dead_removed():
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(start=1), (11, 1): raw(pid=11)}, 0)
    t.update({(10, 2): raw(start=2)}, 2.0)
    assert t.detail(10, 1, 2.0) is None and t.detail(11, 1, 2.0) is None
    assert len(t.detail(10, 2, 2.0)["history"]) == 1
    assert t.counts() == (1, 1) and len(t.cmdlines) == 0


def test_rows_and_detail_shape(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "stat").write_text("cpu 1 2\nbtime 1000000\n")
    t = ProcTable(clk_tck=CLK, uid=1000, root=str(tmp_path))
    t.update({(1, 5): raw(pid=1, start=5, name="init"),
              (10, 1): raw(vctx=0, nvctx=0, io=0, uid=4242424, cmdline="/bin/p " + "y" * 200, ppid=1)}, 0)
    t.update({(1, 5): raw(pid=1, start=5, name="init"),
              (10, 1): raw(vctx=20, nvctx=4, io=2000, uid=4242424, cmdline="/bin/p " + "y" * 200, ppid=1)}, 2.0)
    d = t.detail(10, 1, 2.0)
    assert d["parent"] == "init" and d["own"] is False and d["user"] == "4242424"
    assert d["vctx"] == 10 and d["nvctx"] == 2 and d["io"] == 1000
    assert len(d["args"]) == 120 and d["args"].endswith("…") and d["cmdline"].startswith("/bin/p yy")
    assert d["started"] == 1000000 + 0 and t.detail(1, 5, 2.0)["started"] == 1000000
    assert t.detail(10, 99, 2.0) is None
    assert t.rows(2.0)[0]["own"] is True


def test_top_lists_and_counts():
    t = ProcTable(clk_tck=CLK, uid=1000)
    assert t.top_mem() is None and t.top_cpu() == []
    mk = lambda n, ticks, rss: raw(pid=n, ticks=ticks, rss=rss, threads=2)
    t.update({(n, 1): mk(n, 0, n * 10) for n in range(1, 6)}, 0)
    t.update({(n, 1): mk(n, n * 20 if n != 3 else 0, n * 10) for n in range(1, 6)}, 2.0)
    assert [b["pid"] for b in t.top_cpu()] == [5, 4, 2]
    assert set(t.top_cpu()[0]) == {"pid", "start", "name", "cpu", "rss"}
    assert t.top_mem()["pid"] == 5 and t.counts() == (5, 10)


def test_scan_real_proc_fast():
    times = [timeit.timeit(lambda: scan("/"), number=1) for _ in range(5)]
    print("median scan:", statistics.median(times))
    assert statistics.median(times) < 0.05
    assert any(r.pid == os.getpid() for r in scan("/").values())
