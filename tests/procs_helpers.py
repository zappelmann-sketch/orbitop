# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Hilfen der Prozess-Tests: stat-Zeilen, Prozesse im Testbaum, RawProc mit Vorgaben."""
from orbitop.procs import RawProc

CLK = 100


def stat_line(pid, comm="proc", state="S", ppid=1, ticks=(150, 50), threads=7, start=98765, rss=321, pri=20, nice=0, virt=0):
    return (f"{pid} ({comm}) {state} {ppid} {pid} {pid} 0 -1 4194560 0 0 0 0 {ticks[0]} {ticks[1]} 0 0 {pri} {nice} "
            f"{threads} 0 {start} {virt} {rss} 18446744073709551615")


def make_proc(root, pid, *, stat=True, status=True, io="rchar: 10\nwchar: 5\n", cmdline=b"/bin/x\0-a\0-b\0",
              uid=1000, statm=None, **kw):
    d = root / "proc" / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    if stat:
        (d / "stat").write_text(stat if isinstance(stat, str) else stat_line(pid, **kw))
    if status:
        (d / "status").write_text(f"Name:\tx\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n"
                                  "voluntary_ctxt_switches:\t30\nnonvoluntary_ctxt_switches:\t4\n")
    if io is not None:
        (d / "io").write_text(io)
    if statm is not None:
        (d / "statm").write_text(statm)
    (d / "cmdline").write_bytes(cmdline)


def raw(pid=10, start=1, ticks=0, io=0, vctx=0, nvctx=0, state="S", name="p", cmdline="/bin/p a", uid=1000,
        rss=4096, threads=1, ppid=1, args="a", pri=20, nice=0, virt=0, shr=None):
    return RawProc(pid, start, ppid, name, cmdline, uid, state, ticks, rss, threads, vctx, nvctx, io, args,
                   pri, nice, virt, shr)
