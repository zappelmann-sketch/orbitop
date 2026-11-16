# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

from orbitop import sampler as sampler_mod
from orbitop.gpu import discover_gpus
from orbitop.gpu_tools import GpuTools
from orbitop.sampler import Sampler, _nice
from tests.roots import AMD, ARM, INTEL, VM
from tests.test_procs import make_proc

OVERVIEW = {"tab": "overview", "pid": None, "start": None}


class NoTools:
    """Ersatz für GpuTools: keine Kindprozesse; pkg_w und Hinweise einstellbar."""
    def __init__(self, pkg_w=None):
        self.pkg_w = pkg_w

    def intel(self, card):
        return {"pkg_w": self.pkg_w} if self.pkg_w is not None else None

    def nvidia(self, pci):
        return None

    def hints(self):
        return []

    def stop(self):
        pass


def run(root, ticks=3, tools=None):
    clock = itertools.count(1000.0)
    s = Sampler(root, tools=tools or NoTools(), clock=lambda: float(next(clock)), uid=1000)
    for _ in range(ticks):
        s.tick_system()
        s.tick_procs()
    return s


def kinds(snap):
    return [t["kind"] for t in snap["tiles"]]


def tile(snap, id):
    return next(t for t in snap["tiles"] if t["id"] == id)


def test_intel_laptop_eight_tiles():
    snap = run(INTEL).snapshot(OVERVIEW)
    assert kinds(snap) == ["cpu", "gpu", "mem", "power", "temp", "fan", "net", "disk"]
    assert snap["missing"] == []
    assert snap["hints"] == ["hint.rapl_noperm"]  # RAPL-Zone da, energy_uj nicht lesbar, keine andere Paketleistung
    assert tile(snap, "temp")["series"][0]["key"] == "series.cpu_package"


def test_intel_package_power_from_tools_replaces_rapl_hint():
    snap = run(INTEL, tools=NoTools(pkg_w=7.5)).snapshot(OVERVIEW)
    p = tile(snap, "power")
    assert p["main"] == {"v": 7.5, "u": "W"} and p["aside"]["v"] == 7.5
    assert snap["hints"] == []


def test_amd_gpu_tile_and_nvsmi_hint():
    snap = run(AMD, tools=GpuTools(discover_gpus(AMD))).snapshot(OVERVIEW)
    assert [t["id"] for t in snap["tiles"] if t["kind"] == "gpu"] == ["gpu0"]  # nvidia ohne Werkzeug: keine Kachel
    assert "hint.nvsmi_missing" in snap["hints"]
    assert tile(snap, "gpu0")["main"] == {"v": 37.0, "u": "%"}
    assert tile(snap, "power")["main"]["u"] == "W"  # RAPL ist lesbar, aber ein Takt reicht nicht: hwmon fam15h fehlt
    assert "hint.rapl_noperm" not in snap["hints"]


def test_amd_disk_temperatures_by_device_path():
    snap = run(AMD).snapshot(OVERVIEW)
    d = {x["name"]: x["values"][4] for x in tile(snap, "disk")["devices"]}
    assert d["nvme0n1"]["v"] is not None and d["sda"]["v"] is not None
    assert d["nvme0n1"]["v"] != d["sda"]["v"]


def test_arm_missing_fan_and_power_and_gpu_by_frequency():
    snap = run(ARM).snapshot(OVERVIEW)
    assert set(snap["missing"]) == {"fan", "power"} and "gpu" in kinds(snap)
    g = tile(snap, "gpu0")
    assert g["series"][0]["key"] == "kv.clock"
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


def test_series_gap_stays_none():
    t = tile(run(INTEL, ticks=2).snapshot(OVERVIEW), "cpu")
    assert t["series"][0]["values"][-1] is None and t["main"]["v"] is None


@pytest.fixture
def with_procs(intel_copy):
    for pid in (10, 11):
        make_proc(Path(intel_copy), pid)
    return intel_copy


def test_procs_only_in_procs_view(with_procs):
    s = run(with_procs)
    assert s.snapshot(OVERVIEW)["procs"] is None and s.snapshot(OVERVIEW)["detail"] is None
    snap = s.snapshot({"tab": "procs", "pid": None, "start": None})
    assert isinstance(snap["procs"], list) and snap["detail"] is None
    assert snap["top"]["mem"]["rss"] > 0 and tile(snap, "cpu")["kv"][-1] == {"k": "kv.procs_threads", "v": "2 / 14"}


def test_detail_needs_int_pid_and_start(with_procs):
    s = run(with_procs)
    row = s.snapshot({"tab": "procs", "pid": None, "start": None})["procs"][0]
    ok = s.snapshot({"tab": "procs", "pid": row["pid"], "start": row["start"]})
    assert ok["detail"]["pid"] == row["pid"] and len(ok["detail"]["history"]) <= 150
    assert s.snapshot({"tab": "procs", "pid": row["pid"], "start": "x"})["detail"] is None
    assert s.snapshot({"tab": "procs", "pid": True, "start": row["start"]})["detail"] is None


def test_reader_exception_does_not_break(monkeypatch):
    s = Sampler(INTEL, tools=NoTools(), uid=1000)

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(s._cpu, "read", boom)
    monkeypatch.setattr(sampler_mod, "read_sensors", boom)
    monkeypatch.setattr(sampler_mod.procs, "scan", boom)
    s.tick_system()
    s.tick_procs()
    snap = s.snapshot({"tab": "procs", "pid": 1, "start": 1})
    assert "cpu" in snap["missing"] and "temp" in snap["missing"] and "mem" in kinds(snap)
    json.dumps(snap, allow_nan=False)


def test_snapshot_before_first_tick():
    snap = Sampler(VM, tools=NoTools(), uid=1000).snapshot(OVERVIEW)
    assert snap["tiles"] == [] and snap["missing"] == list(sampler_mod.KINDS)


@pytest.mark.parametrize("v,want", [(0, 1), (0.3, 1), (1, 1), (1.5, 2), (3, 5), (5, 5), (6, 10), (130, 200), (4.2e6, 5e6)])
def test_nice_ceiling(v, want):
    assert _nice(v) == want


def test_temperature_scale_grows_above_100():
    s = run(INTEL)
    s._bufs["temp:series.cpu_package"].append(120.0)
    t = tile(s.snapshot(OVERVIEW), "temp")
    assert t["series"][0]["max"] == pytest.approx(132.0)


def test_dump_snapshot_js(tmp_path):
    out = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "scripts" / "dump-snapshot.py"),
         "--root", INTEL, "--ticks", "2", "--interval", "0.05", "--js"],
        capture_output=True, text=True, check=True, env={"LANG": "de_DE.UTF-8", "PATH": "/usr/bin:/bin"}).stdout
    assert out.startswith("window.ORBITOP_DEMO = ") and out.rstrip().endswith("};")
    demo = json.loads(out[len("window.ORBITOP_DEMO = "):].rstrip().removesuffix(";"))
    assert demo["init"]["lang"] == "de" and demo["init"]["version"] and demo["init"]["texts"]["tab.procs"]
    assert demo["tick"]["type"] == "tick" and len(demo["tick"]["tiles"]) == 8
