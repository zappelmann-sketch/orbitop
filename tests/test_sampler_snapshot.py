# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Sampler: Schnappschuss je Testbaum und Ansicht, Vertrag des tick, Prozessliste und snapshot_json."""
import json
from pathlib import Path

import pytest

from orbitop import sampler as sampler_mod
from orbitop.sampler import Sampler
from orbitop.gpu import discover_gpus
from orbitop.gpu_tools import GpuTools
from tests.procs_helpers import make_proc
from tests.roots import AMD, ARM, INTEL, VM
from tests.sampler_helpers import OVERVIEW, PROCS, NoTools, fake_clock, kinds, run, tile


def test_intel_laptop_eight_tiles():
    snap = run(INTEL, ticks=4).snapshot(OVERVIEW)
    assert kinds(snap) == ["cpu", "gpu", "mem", "power", "temp", "fan", "net", "disk"]
    assert snap["missing"] == []
    assert snap["hints"] == ["hint.rapl_noperm"]  # RAPL-Zone da, energy_uj nicht lesbar, keine andere Paketleistung
    assert tile(snap, "temp")["series"][0]["key"] == "series.cpu_package"


def test_amd_gpu_tile_and_nvsmi_hint():
    snap = run(AMD, tools=GpuTools(discover_gpus(AMD))).snapshot(OVERVIEW)
    assert [t["id"] for t in snap["tiles"] if t["kind"] == "gpu"] == ["gpu0"]  # nvidia ohne Werkzeug: keine Kachel
    assert "hint.nvsmi_missing" in snap["hints"]
    assert tile(snap, "gpu0")["main"] == {"v": 37.0, "u": "%"}
    assert tile(snap, "power")["main"]["u"] == "W"  # RAPL ist lesbar, aber ein Takt reicht nicht: hwmon fam15h fehlt
    assert "hint.rapl_noperm" not in snap["hints"]


def test_arm_missing_fan_and_power_and_gpu_by_frequency():
    snap = run(ARM).snapshot(OVERVIEW)
    assert set(snap["missing"]) == {"fan", "power"} and "gpu" in kinds(snap)
    g = tile(snap, "gpu0")
    assert g["series"][0]["key"] == "kv.clock" and g["aside"]["of"] == 960
    assert g["main"] == {"v": pytest.approx(500 / 960 * 100, abs=0.01), "u": "%"}


def test_vm_only_four():
    snap = run(VM).snapshot(OVERVIEW)
    assert kinds(snap) == ["cpu", "mem", "net", "disk"]
    assert snap["missing"] == ["gpu", "power", "temp", "fan"]


@pytest.mark.parametrize("root", [INTEL, AMD, ARM, VM])
def test_contract_limits_and_json(root):
    snap = run(root, ticks=320).snapshot({"tab": "procs", "pid": None, "start": None})
    json.dumps(snap, allow_nan=False)
    for t in snap["tiles"]:
        assert 0 <= t["seg"] <= 100
        for s in t["series"]:
            assert len(s["values"]) == 300 and s["max"] > 0
        for th in t["threads"] or []:
            assert len(th) == 60
    assert len(tile(snap, "cpu")["threads"]) == {INTEL: 4, AMD: 16, ARM: 4, VM: 2}[root]


def test_snapshot_before_first_tick():
    snap = Sampler(VM, tools=NoTools(), uid=1000).snapshot(OVERVIEW)
    assert snap["tiles"] == [] and snap["missing"] == list(sampler_mod.KINDS)


# 7b: view, der kein dict ist
@pytest.mark.parametrize("view", [None, [], "procs", 5])
def test_snapshot_survives_non_dict_view(view):
    snap = run(VM).snapshot(view)
    assert snap["procs"] is None and snap["detail"] is None


def num_ok(n):
    assert set(n) <= {"v", "u", "of", "p"} and {"v", "u"} <= set(n)
    assert n["v"] is None or isinstance(n["v"], (int, float)) and not isinstance(n["v"], bool)
    assert n["u"] in ("%", "GHz", "MHz", "W", "°C", "rpm", "B/s", "B", "")
    assert n.get("of") is None or isinstance(n["of"], (int, float))
    assert n.get("p", "↓") in ("↓", "↑")


def txt_ok(x, texts):
    assert len(x) == 1 and ("k" in x and x["k"] in texts or "l" in x and isinstance(x["l"], str))


def val_ok(v, texts):
    """Num, Txt oder eine Liste davon; nie ein nacktes str."""
    if isinstance(v, list):
        assert v
        for x in v:
            assert not isinstance(x, list)
            val_ok(x, texts)
    else:
        assert isinstance(v, dict)
        num_ok(v) if "v" in v else txt_ok(v, texts)


def validate_tick(snap, texts):
    """Prüft einen tick gegen den Schnappschuss-Vertrag (wiederverwendbar)."""
    assert snap["type"] == "tick" and set(snap["missing"]) <= set(sampler_mod.KINDS)
    assert all(h in texts for h in snap["hints"])
    for t in snap["tiles"]:
        assert t["kind"] in sampler_mod.KINDS and t["id"].startswith(t["kind"])
        assert isinstance(t["name"], str) and 0 <= t["seg"] <= 100
        num_ok(t["main"])
        if t["aside"] is not None:
            val_ok(t["aside"], texts)
            assert not isinstance(t["aside"], list)
        for s in t["series"]:
            assert ("key" in s) != ("label" in s)
            assert "key" not in s or s["key"] in texts
            assert isinstance(s["fill"], bool) and s["max"] > 0 and len(s["values"]) <= 300
            assert all(v is None or isinstance(v, float) for v in s["values"])
        assert [s["fill"] for s in t["series"]][:1] == [True]
        for kv in t["kv"]:
            assert ("k" in kv) != ("l" in kv) and set(kv) == {"v", "k" if "k" in kv else "l"}
            assert "k" not in kv or kv["k"] in texts
            val_ok(kv["v"], texts)
        assert type(t["warn"]) is bool
        if t["devices"] is not None:
            assert set(t["devices"]) == {"cols", "rows"} and all(c in texts for c in t["devices"]["cols"])
            for d in t["devices"]["rows"]:
                assert isinstance(d["name"], str) and len(d["values"]) == len(t["devices"]["cols"])
                assert all(n is None or num_ok(n) is None for n in d["values"])
        assert t["threads"] is None or all(len(x) <= 60 for x in t["threads"])
    for r in snap["procs"] or []:
        assert type(r["pri"]) is int and type(r["nice"]) is int and type(r["virt"]) is int
        assert r["shr"] is None or type(r["shr"]) is int
        assert isinstance(r["s"], str) and len(r["s"]) == 1 and type(r["time"]) is float
    d = snap["detail"]
    if d is not None:
        assert type(d["kernel"]) is bool and type(d["ppid"]) is int and isinstance(d["cmdline"], str)
        assert len(d["history"]) <= 150 and any((r["pid"], r["start"]) == (d["pid"], d["start"]) for r in snap["procs"])


@pytest.mark.parametrize("root", [INTEL, AMD, ARM, VM])
def test_tick_matches_contract(root):
    from orbitop.i18n import load_texts
    validate_tick(run(root, ticks=4).snapshot(OVERVIEW), load_texts("en"))


@pytest.fixture
def with_procs(intel_copy):
    for pid in (10, 11):
        make_proc(Path(intel_copy), pid, statm="1000 321 77 10 0 200 0\n")
    return intel_copy


def test_procs_view_matches_contract(with_procs):
    from orbitop.i18n import load_texts
    s = run(with_procs)
    row = s.snapshot({"tab": "procs", "pid": None, "start": None})["procs"][0]
    snap = s.snapshot({"tab": "procs", "pid": row["pid"], "start": row["start"]})
    assert snap["detail"] is not None
    validate_tick(snap, load_texts("en"))


def test_procs_only_in_procs_view(with_procs):
    s = run(with_procs)
    assert s.snapshot(OVERVIEW)["procs"] is None and s.snapshot(OVERVIEW)["detail"] is None
    snap = s.snapshot({"tab": "procs", "pid": None, "start": None})
    assert isinstance(snap["procs"], list) and snap["detail"] is None
    assert snap["top"]["mem"]["rss"] > 0 and tile(snap, "cpu")["kv"][-1] == {"k": "kv.procs_threads", "v": {"v": 2, "u": "", "of": 14}}


def test_shr_only_after_procs_tick_with_shr(with_procs):
    s = run(with_procs)
    assert {r["shr"] for r in s.snapshot(PROCS)["procs"]} == {None}
    s.tick_procs(shr=True)
    assert all(type(r["shr"]) is int and r["shr"] > 0 for r in s.snapshot(PROCS)["procs"])


def test_detail_needs_int_pid_and_start(with_procs):
    s = run(with_procs)
    row = s.snapshot({"tab": "procs", "pid": None, "start": None})["procs"][0]
    ok = s.snapshot({"tab": "procs", "pid": row["pid"], "start": row["start"]})
    assert ok["detail"]["pid"] == row["pid"] and len(ok["detail"]["history"]) <= 150
    assert s.snapshot({"tab": "procs", "pid": row["pid"], "start": "x"})["detail"] is None
    assert s.snapshot({"tab": "procs", "pid": True, "start": row["start"]})["detail"] is None


# 8 / 16: pid 1 und bool, detail nur im Reiter procs
def test_detail_bool_pid_and_overview(intel_copy):
    make_proc(Path(intel_copy), 1)
    s = run(intel_copy)
    row = s.snapshot({"tab": "procs", "pid": None, "start": None})["procs"][0]
    assert row["pid"] == 1
    assert s.snapshot({"tab": "procs", "pid": True, "start": row["start"]})["detail"] is None
    assert s.snapshot({"tab": "procs", "pid": 1, "start": row["start"]})["detail"]["pid"] == 1
    assert s.snapshot({"tab": "overview", "pid": 1, "start": row["start"]})["detail"] is None


# 21: top_cpu(3)
def test_top_cpu_is_three_sorted(tree_copy):
    root = tree_copy(INTEL)
    for pid in range(10, 15):
        make_proc(Path(root), pid, ticks=(0, 0))
    s = Sampler(root, tools=NoTools(), clock=fake_clock(), uid=1000)
    s.tick_procs()
    for pid in range(10, 15):
        make_proc(Path(root), pid, ticks=(100 * (pid - 9), 0))
    s.tick_procs()
    top = s.snapshot(OVERVIEW)["top"]["cpu"]
    assert [p["pid"] for p in top] == [14, 13, 12]


def test_snapshot_hands_selection_to_status_reading():
    """Der gewählte Prozess bekommt bei jedem Prozess-Takt frische Kontextwechsel (procs.ProcTable.wants_status)."""
    s = Sampler(VM, tools=NoTools(), uid=1000)
    s.snapshot({"tab": "procs", "pid": 5, "start": 7})
    assert s._table.selected == (5, 7)
    s.snapshot(OVERVIEW)
    assert s._table.selected is None


def test_tick_procs_passes_status_gate(monkeypatch):
    gates = []
    monkeypatch.setattr(sampler_mod.procs, "scan", lambda root, cmdlines, want_status=None, want_shr=False: gates.append(want_status) or {})
    Sampler(VM, tools=NoTools(), uid=1000).tick_procs()
    assert len(gates) == 1 and callable(gates[0])


def test_snapshot_json_byte_identical_and_rows_once_per_process_tick(with_procs):
    """Die Prozessliste ändert sich nur alle 2 s: Zeilen und ihr JSON einmal je Prozess-Takt, sonst eingesetzt."""
    from orbitop.app import encode
    s = run(with_procs)
    first = s.snapshot({"tab": "procs", "pid": None, "start": None})["procs"][0]
    views = [OVERVIEW, {"tab": "procs", "pid": None, "start": None},
             {"tab": "procs", "pid": first["pid"], "start": first["start"]}]
    built = []
    real = s._table.rows
    s._table.rows = lambda now: (built.append(now), real(now))[1]
    for v in views:
        assert s.snapshot_json(v) == encode(s.snapshot(v)), v
    built.clear()
    for v in views * 2:
        s.snapshot_json(v)
    assert len(built) == 0  # Zeilen stammen aus dem Prozess-Takt davor
    s.tick_procs()
    for v in views:
        assert s.snapshot_json(v) == encode(s.snapshot(v)), v
    assert len(built) == 1 + 2  # einmal je Prozess-Takt; dazu die zwei snapshot() mit procs zum Vergleich


def test_snapshot_json_sends_unchanged_procs_once(with_procs):
    """resend=False: Die Liste steht nur im Tick, wenn sie sich seit der zuletzt gelieferten geändert hat."""
    from orbitop.app import encode
    s = run(with_procs)
    first = json.loads(s.snapshot_json(PROCS, resend=False))
    assert first["procs"] and "procs_same" not in first
    again = json.loads(s.snapshot_json(PROCS, resend=False))
    assert again.pop("procs") is None and again.pop("procs_same") is True
    assert again == {k: v for k, v in first.items() if k != "procs"}
    assert s.snapshot_json(PROCS) == encode(s.snapshot(PROCS))  # resend=True: volle Liste
    s.tick_procs()
    new = json.loads(s.snapshot_json(PROCS, resend=False))
    assert new["procs"] and "procs_same" not in new
    for _ in range(2):
        over = json.loads(s.snapshot_json(OVERVIEW, resend=False))
        assert over["procs"] is None and "procs_same" not in over


def test_selection_never_unset_during_snapshot(with_procs):
    """Der Prozess-Thread liest table.selected ohne Sperre: Während eines Schnappschusses mit gültiger Auswahl darf es
    nie kurz None sein, sonst fehlt dem gewählten Prozess ein status-Lesen."""
    s = run(with_procs)
    row = s.snapshot({"tab": "procs", "pid": None, "start": None})["procs"][0]
    view = {"tab": "procs", "pid": row["pid"], "start": row["start"]}
    s.snapshot_json(view)
    seen = []
    for name in ("rows", "detail", "top_cpu", "top_mem", "counts"):
        real = getattr(s._table, name)
        setattr(s._table, name, lambda *a, real=real: (seen.append(s._table.selected), real(*a))[1])
    s.tick_procs()  # neue Zeilen, damit snapshot_json sie auch baut
    s.snapshot_json(view)
    s.snapshot(view)
    assert seen and set(seen) == {(row["pid"], row["start"])}, seen
