#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Eigenlast eines Prozessbaums: CPU (utime + stime) von --pid und allen Nachkommen über --seconds, PSS am Ende.

Gezählt wird je (pid, start) der Zuwachs im Fenster; wer erst im Fenster entsteht, zählt ab 0, wer älter ist und
später auftaucht, ab dem ersten gesehenen Wert. Abgetastet wird alle 50 ms über /proc/<pid>/task/<tid>/children.
Ausgabe auf stdout: cpu_pct_of_one_core, pss_mb, pss_unreadable (Prozesse ohne lesbares smaps_rollup, in pss_mb nicht
enthalten), processes; auf stderr die Aufteilung je Prozess ("?" für nicht lesbare PSS)."""
import argparse
import os
import sys
import time

TICK = os.sysconf("SC_CLK_TCK")
STEP_S = 0.05


def _read(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def _tree(root: int) -> list[int]:
    out, todo = [], [root]
    while todo:
        pid = todo.pop()
        out.append(pid)
        try:
            tasks = os.listdir(f"/proc/{pid}/task")
        except OSError:
            continue
        for t in tasks:
            todo += [int(c) for c in _read(f"/proc/{pid}/task/{t}/children").split()]
    return out


def _scan(root: int) -> dict[tuple[int, int], tuple[int, str]]:
    """(pid, start) -> (utime + stime in Ticks, comm) für den lebenden Baum."""
    got = {}
    for pid in _tree(root):
        text = _read(f"/proc/{pid}/stat")
        if not text:
            continue
        end = text.rindex(")")  # comm darf ')' und Leerzeichen enthalten
        f = text[end + 2:].split()
        got[(pid, int(f[19]))] = (int(f[11]) + int(f[12]), text[text.index("(") + 1:end])
    return got


def _pss_kb(pid: int) -> int | None:
    """None: nicht lesbar, etwa ein nicht dumpbarer Prozess (Datei-Capability wie bei intel_gpu_top)."""
    for line in _read(f"/proc/{pid}/smaps_rollup").splitlines():
        if line.startswith("Pss:"):
            return int(line.split()[1])
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--seconds", type=float, required=True)
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    t0_ticks = float(_read("/proc/uptime").split()[0]) * TICK  # Startzeiten in /proc/<pid>/stat zählen ab dem Booten
    now = _scan(a.pid)
    if not now:
        print(f"measure-load: no process {a.pid}", file=sys.stderr)
        return 1
    seen = {k: [ticks, ticks, comm] for k, (ticks, comm) in now.items()}  # Basis, letzter Wert, Name
    while time.monotonic() - t0 < a.seconds:
        time.sleep(STEP_S)
        now = _scan(a.pid)
        for k, (ticks, comm) in now.items():  # spät entdeckt, aber älter als das Fenster: ab dem ersten Wert
            seen.setdefault(k, [0 if k[1] >= t0_ticks else ticks, 0, comm])[1:] = [ticks, comm]
    elapsed = time.monotonic() - t0
    pct = {k: 100 * (last - base) / TICK / elapsed for k, (base, last, _) in seen.items()}
    pss = {k: _pss_kb(k[0]) for k in now}  # am Ende lebende Prozesse
    for k in sorted(pct, key=pct.get, reverse=True):
        mb = "-" if k not in pss else "?" if pss[k] is None else f"{pss[k] / 1024:.1f}"
        print(f"  {k[0]:>7} {seen[k][2]:<20} {pct[k]:6.2f} % {mb:>7} MB", file=sys.stderr)
    print(f"cpu_pct_of_one_core={sum(pct.values()):.2f}")
    print(f"pss_mb={sum(v for v in pss.values() if v is not None) / 1024:.1f}")
    print(f"pss_unreadable={sum(v is None for v in pss.values())}")
    print(f"processes={len(seen)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
