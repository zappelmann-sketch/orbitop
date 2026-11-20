# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""ProcTable und scan: /proc/<pid>/status nur, wenn nötig, ohne die Einstufung zu ändern."""
import pytest

from orbitop.procs import ProcTable, scan
from tests.procs_helpers import CLK, make_proc, raw


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
