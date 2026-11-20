# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scan und parse_stat: was aus /proc/<pid> gelesen, bereinigt und übersprungen wird."""
import os
import statistics
import timeit

from orbitop import procs
from orbitop.procs import parse_stat, scan
from tests.procs_helpers import make_proc, stat_line


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


def test_scan_real_proc_fast():
    times = [timeit.timeit(lambda: scan("/"), number=1) for _ in range(5)]
    print("median scan:", statistics.median(times))
    assert statistics.median(times) < 0.05
    assert any(r.pid == os.getpid() for r in scan("/").values())


def test_parse_stat_priority_nice_vsize():
    d = parse_stat(stat_line(7, pri=39, nice=19, virt=123_456_789))
    assert (d["pri"], d["nice"], d["virt"]) == (39, 19, 123_456_789)
    assert parse_stat(stat_line(8, pri=0, nice=-20))["nice"] == -20


def test_scan_reads_statm_only_when_wanted(tmp_path, monkeypatch):
    make_proc(tmp_path, 100, statm="1000 321 77 10 0 200 0\n")
    seen, real = [], procs._read
    monkeypatch.setattr(procs, "_read", lambda p: seen.append(p) or real(p))
    assert scan(str(tmp_path), page_size=4096)[(100, 98765)].shr is None
    assert not any(p.endswith("/statm") for p in seen)
    assert scan(str(tmp_path), page_size=4096, want_shr=True)[(100, 98765)].shr == 77 * 4096


def test_scan_statm_missing_or_broken_keeps_process(tmp_path):  # verschwindet zwischen stat und statm
    make_proc(tmp_path, 100)
    make_proc(tmp_path, 101, statm="kaputt")
    got = scan(str(tmp_path), want_shr=True)
    assert sorted(k[0] for k in got) == [100, 101] and {r.shr for r in got.values()} == {None}
