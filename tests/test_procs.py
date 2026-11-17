# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import statistics
import timeit

import pytest

from orbitop import procs
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
        rss=4096, threads=1, ppid=1, args="a"):
    return RawProc(pid, start, ppid, name, cmdline, uid, state, ticks, rss, threads, vctx, nvctx, io, args)


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


def test_scan_brackets_only_kernel_threads(tmp_path):
    make_proc(tmp_path, 2, comm="kthreadd", cmdline=b"", io=None, ppid=0)
    make_proc(tmp_path, 3, comm="kworker/0:1", cmdline=b"", ppid=2)
    make_proc(tmp_path, 1, comm="systemd", cmdline=b"/sbin/init\0", ppid=0)
    r = scan(str(tmp_path))
    assert r[(2, 98765)].name == "[kthreadd]" and r[(2, 98765)].cmdline == ""
    assert r[(3, 98765)].name == "[kworker/0:1]" and r[(1, 98765)].name == "systemd"


def test_scan_user_process_with_empty_cmdline_gets_no_brackets(tmp_path):
    make_proc(tmp_path, 100, comm="kworker/0:1", cmdline=b"", ppid=1000)
    assert scan(str(tmp_path))[(100, 98765)].name == "kworker/0:1"


def test_scan_name_and_cmdline_sanitized(tmp_path):
    make_proc(tmp_path, 100, comm="a\x1b[1m\n\u202eX\u2066", cmdline="x\u202e\x85y\0z\x1b".encode())
    r = scan(str(tmp_path))[(100, 98765)]
    assert r.name == "a?[1m??X?" and r.cmdline == "x??y z?" and r.args == "z?"


def test_scan_args_split_nul_or_space(tmp_path):
    make_proc(tmp_path, 100, cmdline=b"/opt/My App/bin/x\0--flag\0")
    make_proc(tmp_path, 101, cmdline=b"sshd: alice@pts/0")
    r = scan(str(tmp_path))
    assert r[(100, 98765)].args == "--flag" and r[(100, 98765)].cmdline == "/opt/My App/bin/x --flag"
    assert r[(101, 98765)].args == "alice@pts/0"


def test_scan_rereads_cmdline_after_comm_change(tmp_path):
    make_proc(tmp_path, 100, comm="old", cmdline=b"/bin/old\0-a")
    cache = {}
    scan(str(tmp_path), cache)
    make_proc(tmp_path, 100, comm="new", cmdline=b"/bin/new\0-b")
    r = scan(str(tmp_path), cache)[(100, 98765)]
    assert (r.name, r.cmdline, r.args) == ("new", "/bin/new -b", "-b")


def test_scan_uses_real_uid_and_large_status(tmp_path):
    make_proc(tmp_path, 100)
    (tmp_path / "proc" / "100" / "status").write_text(
        "Name:\tx\nUid:\t1000\t0\t0\t0\nGroups:" + " 1" * 12000 +
        "\nvoluntary_ctxt_switches:\t30\nnonvoluntary_ctxt_switches:\t4\n")
    r = scan(str(tmp_path))[(100, 98765)]
    assert (r.uid, r.vctx, r.nvctx) == (1000, 30, 4)


def test_scan_status_over_64kib_with_ctxt_lines_at_end(tmp_path):
    make_proc(tmp_path, 100)
    (tmp_path / "proc" / "100" / "status").write_text(
        "Name:\tx\nUid:\t1000\t0\t0\t0\nGroups:" + " 1" * 40000 +
        "\nvoluntary_ctxt_switches:\t30\nnonvoluntary_ctxt_switches:\t4\n")
    assert (tmp_path / "proc" / "100" / "status").stat().st_size > 65536
    assert (100, 98765) in scan(str(tmp_path))


def test_read_small_file_needs_one_read_call(tmp_path, monkeypatch):
    f = tmp_path / "f"
    f.write_text("abc")
    calls = []
    real = os.read
    monkeypatch.setattr(os, "read", lambda fd, n: calls.append(n) or real(fd, n))
    assert procs._read(str(f)) == "abc" and len(calls) == 1


def test_scan_non_ascii_digit_pid_with_stat_skipped(tmp_path):
    make_proc(tmp_path, "1\u0663")
    assert scan(str(tmp_path)) == {}


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


def test_d_state_reentry_restarts_clock():
    t = ProcTable(clk_tck=CLK, uid=1000)
    for now, st in [(0, "D"), (2, "D"), (4, "S"), (16, "D")]:
        t.update({(10, 1): raw(state=st)}, float(now))
    assert t.rows(16.0)[0]["state"] == "working"


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


def test_dt_boundary_and_io_decrease():
    for now, ok in [(5.0, True), (5.01, False)]:
        t = ProcTable(clk_tck=CLK, uid=1000)
        t.update({(10, 1): raw(ticks=0, io=100)}, 0)
        t.update({(10, 1): raw(ticks=500, io=50)}, now)
        r = t.rows(now)[0]
        assert (r["cpu"] > 0) is ok and r["io"] is None


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


# ---- Task 17: /proc/<pid>/status nur, wenn nötig ----
def _status(root, pid, uid=1000, vctx=30):
    (root / "proc" / str(pid) / "status").write_text(f"Name:\tx\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n"
                                                     f"voluntary_ctxt_switches:\t{vctx}\nnonvoluntary_ctxt_switches:\t4\n")


def _tick(t, root, now):
    t.update(scan(str(root), t.cmdlines, want_status=t.wants_status(now)), now)


def test_status_only_for_new_selected_candidates_and_every_10_s(tmp_path):
    for pid in (100, 101, 102):
        make_proc(tmp_path, pid, ticks=(0, 0))
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.selected = (101, 98765)
    _tick(t, tmp_path, 0.0)
    for pid in (100, 101, 102):
        _status(tmp_path, pid, uid=4242, vctx=50)
    make_proc(tmp_path, 102, status=False, ticks=(180, 0))  # 1,8 s CPU in 2 s: Kandidat der Dauerlast (90 %)
    _tick(t, tmp_path, 2.0)
    own = lambda now: {r["pid"]: r["own"] for r in t.rows(now)}  # noqa: E731
    assert own(2.0) == {100: True, 101: False, 102: False}  # 100 wurde nicht neu gelesen
    assert t.detail(101, 98765, 2.0)["vctx"] == 10.0  # (50 - 30) / 2 s
    _tick(t, tmp_path, 8.0)
    assert own(8.0)[100] is True
    _tick(t, tmp_path, 10.0)
    assert own(10.0)[100] is False  # spätestens nach 10 s
    assert t.detail(100, 98765, 10.0)["vctx"] == 2.0  # Rate über das tatsächliche dt: (50 - 30) / 10 s


def _gated_and_full(seq):
    """Dieselbe Folge (ticks, vctx, io) je 2 s einmal mit status bei jedem Takt, einmal nur bei Bedarf.
    Je Takt: (Zustand voll, Zustand gegatet, status gelesen, since voll, since gegatet)."""
    full, gated = ProcTable(clk_tck=CLK, uid=1000), ProcTable(clk_tck=CLK, uid=1000)
    out = []
    for i, (ticks, vctx, io) in enumerate(seq):
        now = i * 2.0
        due = gated.wants_status(now)((10, 1), ticks)
        full.update({(10, 1): raw(ticks=ticks, vctx=vctx, io=io)}, now)
        gated.update({(10, 1): raw(ticks=ticks, vctx=vctx if due else None, nvctx=0 if due else None, io=io)}, now)
        a, b = full.rows(now)[0], gated.rows(now)[0]
        out.append((a["state"], b["state"], due, a["since"], b["since"]))
    return out


@pytest.mark.parametrize("switches,io", [(0, 7), (0, None), (1, 7), (3, 7)])
def test_status_gating_same_classification_with_steady_switching(switches, io):
    """12 Takte Leerlauf (wenige freiwillige Kontextwechsel), dann 70 Takte Dauerlast mit gleich vielen Wechseln je
    Takt: gegatet und voll stufen bei jedem Takt gleich ein. Allgemein gilt nur: nie früher, höchstens einen Takt
    später (test_status_gating_never_reports_busy_earlier)."""
    seq, ticks, vctx = [], 0, 0
    for i in range(82):
        if i >= 12:
            ticks += 200
            vctx += switches
        elif i % 6 == 0:
            vctx += 1
        seq.append((ticks, vctx, io))
    out = _gated_and_full(seq)
    assert [o[:2] for o in out if o[0] != o[1]] == []
    assert sum(o[2] for o in out[:12]) < 6  # im Leerlauf wurde status nur selten gelesen
    want = "working" if switches > 2 else "busy_noio" if io == 7 else "busy_iounknown"  # Grenze: 1 je s, also 2 je Takt
    assert out[-1][0] == want


def test_status_gating_never_reports_busy_earlier():
    """Muster aus dem Review (dilution.py): 8 s ohne Wechsel, dann Dauerlast mit 3 Wechseln in den ersten 2 s (1,5/s),
    danach keine. Über die ganze status-Lücke gemittelt wären es unter 1/s; gemeldet würde 2 s zu früh."""
    seq, ticks, vctx = [], 0, 0
    for i in range(80):
        if i >= 9:
            ticks += 200
            vctx += 3 if i == 9 else 0
        seq.append((ticks, vctx, 7))
    out = _gated_and_full(seq)
    busy = [(o[0].startswith("busy"), o[1].startswith("busy")) for o in out]
    first_full = next(i for i, b in enumerate(busy) if b[0])
    first_gated = next(i for i, b in enumerate(busy) if b[1])
    assert first_full <= first_gated <= first_full + 1
    assert all(o[4] <= o[3] for o, b in zip(out, busy) if all(b))  # since nie größer als voll


def test_status_skipped_keeps_uid_and_rates():
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(uid=0, vctx=10, nvctx=2)}, 0.0)
    t.update({(10, 1): raw(uid=0, vctx=30, nvctx=6)}, 2.0)
    t.update({(10, 1): raw(uid=None, vctx=None, nvctx=None)}, 4.0)
    d = t.detail(10, 1, 4.0)
    assert d["user"] == "root" and d["own"] is False and (d["vctx"], d["nvctx"]) == (10.0, 2.0)
