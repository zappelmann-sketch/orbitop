# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import itertools
import os
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
    snap = run(INTEL, ticks=4).snapshot(OVERVIEW)
    assert kinds(snap) == ["cpu", "gpu", "mem", "power", "temp", "fan", "net", "disk"]
    assert snap["missing"] == []
    assert snap["hints"] == ["hint.rapl_noperm"]  # RAPL-Zone da, energy_uj nicht lesbar, keine andere Paketleistung
    assert tile(snap, "temp")["series"][0]["key"] == "series.cpu_package"


def test_intel_package_power_from_tools_replaces_rapl_hint():
    snap = run(INTEL, ticks=4, tools=NoTools(pkg_w=7.5)).snapshot(OVERVIEW)
    p = tile(snap, "power")
    assert p["main"] == {"v": 7.5, "u": "W"} and p["aside"] == {"k": "series.cpu_package"}
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
    d = {x["name"]: x["values"][3] for x in tile(snap, "disk")["devices"]["rows"]}
    assert d["nvme0n1"]["v"] is not None and d["sda"]["v"] is not None
    assert d["nvme0n1"]["v"] != d["sda"]["v"]


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
    assert snap["top"]["mem"]["rss"] > 0 and tile(snap, "cpu")["kv"][-1] == {"k": "kv.procs_threads", "v": {"v": 2, "u": "", "of": 14}}


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
    s._bufs["temp:#cpu"].append(120.0)
    t = tile(s.snapshot(OVERVIEW), "temp")
    assert t["series"][0]["max"] == pytest.approx(132.0)
    assert t["main"]["v"] == max(v for _, _, v in s._s["temps"]) and t["aside"] == {"k": "tile.temp_aside"}


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
    d = snap["detail"]
    if d is not None:
        assert type(d["kernel"]) is bool and type(d["ppid"]) is int and isinstance(d["cmdline"], str)
        assert len(d["history"]) <= 150 and any((r["pid"], r["start"]) == (d["pid"], d["start"]) for r in snap["procs"])


@pytest.mark.parametrize("root", [INTEL, AMD, ARM, VM])
def test_tick_matches_contract(root):
    from orbitop.i18n import load_texts
    validate_tick(run(root, ticks=4).snapshot(OVERVIEW), load_texts("en"))


def test_procs_view_matches_contract(with_procs):
    from orbitop.i18n import load_texts
    s = run(with_procs)
    row = s.snapshot({"tab": "procs", "pid": None, "start": None})["procs"][0]
    snap = s.snapshot({"tab": "procs", "pid": row["pid"], "start": row["start"]})
    assert snap["detail"] is not None
    validate_tick(snap, load_texts("en"))


def test_pair_and_direction_shapes():
    snap = run(INTEL).snapshot(OVERVIEW)
    assert tile(snap, "mem")["aside"]["of"] > tile(snap, "mem")["aside"]["v"]
    net = tile(snap, "net")
    assert net["main"]["p"] == "↓" and net["aside"]["p"] == "↑"
    since = next(k for k in net["kv"] if k.get("k") == "kv.since_boot")["v"]
    assert [n["p"] for n in since] == ["↓", "↑"]


def test_dump_snapshot_js(tmp_path):
    out = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "scripts" / "dump-snapshot.py"),
         "--root", INTEL, "--ticks", "2", "--interval", "0.05", "--js"],
        capture_output=True, text=True, check=True, env={"LANG": "de_DE.UTF-8", "PATH": "/usr/bin:/bin"}).stdout
    assert out.startswith("window.ORBITOP_DEMO = ") and out.rstrip().endswith("};")
    demo = json.loads(out[len("window.ORBITOP_DEMO = "):].rstrip().removesuffix(";"))
    assert demo["init"]["lang"] == "de" and demo["init"]["version"] and demo["init"]["texts"]["tab.procs"]
    assert demo["tick"]["type"] == "tick" and len(demo["tick"]["tiles"]) == 8


# ---- Fix-Runde 2: Befunde und Mutanten ----
from orbitop.sensors import Battery, Fan, SensorValues, Temp, read_sensors  # noqa: E402
from orbitop.system import Disk, NetDev, NetReader  # noqa: E402


def fake_clock():
    c = itertools.count(1000.0)
    return lambda: float(next(c))


@pytest.fixture
def patched(monkeypatch):
    """Sampler, dessen Leser (read_sensors, read_battery, RaplReader.read) feste Werte liefern."""
    def make(root=VM, rapl=None, tools=None, ticks=4, **readers):
        for name, val in readers.items():
            monkeypatch.setattr(sampler_mod, name, lambda *a, val=val: val)
        s = Sampler(root, tools=tools or NoTools(), clock=fake_clock(), uid=1000)
        s._rapl.read = lambda now: rapl
        for _ in range(ticks):
            s.tick_system()
            s.tick_procs()
        return s
    return make


def sens(power=(), fans=(), temps=(), cpu=None):
    return SensorValues(cpu, list(temps), list(fans), list(power))


# 1: Beschriftungen und Werte bleiben beieinander (Chipsatz-Sensor mitten in der Liste)
def test_temp_labels_carry_their_own_values():
    snap = run(INTEL).snapshot(OVERVIEW)
    truth = {t.label: t.value for t in read_sensors(INTEL).temps}
    t = tile(snap, "temp")
    pairs = [(s["label"], s["values"][-1]) for s in t["series"] if "label" in s]
    pairs += [(kv["l"], kv["v"]["v"]) for kv in t["kv"] if "l" in kv]
    assert pairs and all(truth[label] == pytest.approx(v) for label, v in pairs)
    assert any(label == "acpitz 1" for label, _ in pairs)


# 2: Verläufe hängen am Namen, nicht an der Listenposition
def test_temp_history_follows_label(monkeypatch):
    t = [Temp("A", 10.0, "x"), Temp("B", 20.0, "x"), Temp("C", 30.0, "x"), Temp("D", 40.0, "x")]
    vals = iter([sens(temps=t, cpu=50.0), sens(temps=t[1:], cpu=50.0)])
    monkeypatch.setattr(sampler_mod, "read_sensors", lambda *a: next(vals))
    s = Sampler(VM, tools=NoTools(), clock=fake_clock(), uid=1000)
    s.tick_system()
    s.tick_system()
    series = {x.get("label", x.get("key")): x["values"] for x in tile(s.snapshot(OVERVIEW), "temp")["series"]}
    assert series["series.cpu_package"] == [50.0, 50.0] and series["B"] == [20.0, 20.0]
    assert "A" not in series  # A fiel weg, B rutschte nicht in A's Platz


# 3 / 22 / 1a-1c: Leistungskette und Name der Series
def power_of(patched, rapl=None, pkg_w=None, batt=None, hw=()):
    s = patched(INTEL, rapl=rapl, read_battery=batt, read_sensors=sens(power=hw), tools=NoTools(pkg_w=pkg_w))
    return tile(s.snapshot(OVERVIEW), "power")


BATT = Battery(50.0, False, 9.0)
HW = [("ina2xx 1", 3.0)]


@pytest.mark.parametrize("kw,v,name", [
    (dict(rapl={"package-0": 12.0}, pkg_w=8.0, batt=BATT, hw=HW), 12.0, {"key": "series.cpu_package"}),
    (dict(rapl={"package": 20.0, "package-0": 12.0, "package-1": 8.0}, pkg_w=8.0, batt=BATT, hw=HW), 20.0,
     {"key": "series.cpu_package"}),
    (dict(rapl=None, pkg_w=8.0, batt=BATT, hw=HW), 8.0, {"key": "series.cpu_package"}),
    (dict(rapl=None, pkg_w=None, batt=BATT, hw=HW), 9.0, {"key": "kv.battery"}),
    (dict(rapl=None, pkg_w=None, batt=None, hw=HW), 3.0, {"label": "ina2xx 1"}),
])
def test_power_main_chain_and_series_name(patched, kw, v, name):
    p = power_of(patched, **kw)
    assert p["main"]["v"] == v and p["series"][0]["values"][-1] == v
    assert {k: x for k, x in p["series"][0].items() if k in ("key", "label")} == name
    assert p["aside"] == {("k" if "key" in name else "l"): next(iter(name.values()))}


def test_power_chain_picks_hwmon_first_entry(patched):
    p = power_of(patched, hw=[("a", 1.0), ("b", 2.0)])
    assert p["main"]["v"] == 1.0


# 4: Akku-Zeile
def test_battery_row_on_ac_and_discharging(patched):
    p = power_of(patched, pkg_w=5.0, batt=Battery(80.0, True, None))
    assert next(k for k in p["kv"] if k["k"] == "kv.battery")["v"] == [{"v": 80.0, "u": "%"}, {"k": "kv.on_ac"}]
    p = power_of(patched, pkg_w=5.0, batt=Battery(80.0, False, 9.5))
    assert next(k for k in p["kv"] if k["k"] == "kv.battery")["v"] == [{"v": 80.0, "u": "%"}, {"v": 9.5, "u": "W"}]
    p = power_of(patched, pkg_w=5.0, batt=Battery(80.0, False, None))
    assert next(k for k in p["kv"] if k["k"] == "kv.battery")["v"] == [{"v": 80.0, "u": "%"}]


# 3: aside-Entscheidungen nach dem Entwurf
def test_asides_follow_mockup():
    snap = run(AMD).snapshot(OVERVIEW)
    assert tile(snap, "temp")["aside"] == {"k": "tile.temp_aside"}
    assert tile(snap, "disk")["aside"] == {"k": "series.read"}
    fan = tile(snap, "fan")
    assert set(fan["aside"]) == {"l"} and fan["name"] == ""


# 2b / 2c / 7: rapl-Hinweis
@pytest.mark.parametrize("root", [VM, ARM])
def test_no_rapl_hint_without_zones(root):
    assert run(root, ticks=6).snapshot(OVERVIEW)["hints"] == []


def test_rapl_hint_not_in_first_ticks():
    s = run(INTEL, ticks=3)
    assert s.snapshot(OVERVIEW)["hints"] == []
    s.tick_system()
    assert s.snapshot(OVERVIEW)["hints"] == ["hint.rapl_noperm"]


def test_rapl_hint_only_if_all_zones_unreadable(tree_copy):
    root = tree_copy(AMD)  # intel-rapl:0 hat energy_uj; eine zweite, unlesbare Zone kommt dazu
    z = Path(root) / "sys/class/powercap/intel-rapl:1"
    z.mkdir()
    (z / "name").write_text("package-1\n")

    def hints():
        s = Sampler(root, tools=NoTools(), clock=fake_clock(), uid=1000)
        s._rapl.read = lambda now: None  # keine Paketleistung aus irgendeiner Quelle
        for _ in range(6):
            s.tick_system()
        return s.snapshot(OVERVIEW)["hints"]
    assert "hint.rapl_noperm" not in hints()
    (Path(root) / "sys/class/powercap/intel-rapl:0/energy_uj").unlink()
    assert "hint.rapl_noperm" in hints()


def test_temp_main_is_hottest_sensor(patched):
    s = patched(read_sensors=sens(cpu=50.0, temps=[Temp("hot", 80.0, "x"), Temp("cool", 30.0, "x")]))
    t = tile(s.snapshot(OVERVIEW), "temp")
    assert t["main"]["v"] == 80.0 and t["series"][0]["key"] == "series.cpu_package"
    assert t["series"][0]["values"][-1] == 50.0  # gefüllt bleibt die CPU


# 6: seg-Klemme
@pytest.mark.parametrize("v,ref,want", [(150, 100, 100), (-5, 100, 0), (None, 100, 0), (5, 0, 0), (5, None, 0), (50, 200, 25)])
def test_seg_clamped(v, ref, want):
    assert sampler_mod._seg(v, ref) == want


# 7b: view, der kein dict ist
@pytest.mark.parametrize("view", [None, [], "procs", 5])
def test_snapshot_survives_non_dict_view(view):
    snap = run(VM).snapshot(view)
    assert snap["procs"] is None and snap["detail"] is None


# 8 / 16: pid 1 und bool, detail nur im Reiter procs
def test_detail_bool_pid_and_overview(intel_copy):
    make_proc(Path(intel_copy), 1)
    s = run(intel_copy)
    row = s.snapshot({"tab": "procs", "pid": None, "start": None})["procs"][0]
    assert row["pid"] == 1
    assert s.snapshot({"tab": "procs", "pid": True, "start": row["start"]})["detail"] is None
    assert s.snapshot({"tab": "procs", "pid": 1, "start": row["start"]})["detail"]["pid"] == 1
    assert s.snapshot({"tab": "overview", "pid": 1, "start": row["start"]})["detail"] is None


# 9: _clean
def test_clean_rounds_and_removes_nonfinite():
    out = sampler_mod._clean({"a": 1.23456, "b": [float("nan"), float("inf"), 2.0], "c": "x\x1b‮y", "d": 3})
    assert out == {"a": 1.23, "b": [None, None, 2.0], "c": "x??y", "d": 3}


def test_snapshot_floats_have_two_decimals_at_most():
    snap = run(INTEL, ticks=5).snapshot(OVERVIEW)

    def walk(o):
        if isinstance(o, float):
            assert o == round(o, 2)
        elif isinstance(o, dict):
            [walk(v) for v in o.values()]
        elif isinstance(o, list):
            [walk(v) for v in o]
    walk(snap)


# 10 / 11: Laufwerkstemperatur
def disk_temps(root):
    rows = tile(run(root).snapshot(OVERVIEW), "disk")["devices"]["rows"]
    return {d["name"]: (d["values"][3] or {}).get("v") for d in rows}


def test_single_nvme_fallback_when_device_link_broken(tree_copy):
    root = tree_copy(AMD)
    want = disk_temps(root)["nvme0n1"]
    (Path(root) / "sys/class/hwmon/hwmon2/device").unlink()
    got = disk_temps(root)
    assert want is not None and got["nvme0n1"] == want and got["sda"] == disk_temps(AMD)["sda"]


def test_no_fallback_with_two_nvme_disks(tree_copy):
    root = tree_copy(AMD)
    (Path(root) / "sys/class/hwmon/hwmon2/device").unlink()
    import shutil
    shutil.copytree(Path(root) / "sys/block/nvme0n1", Path(root) / "sys/block/nvme1n1", symlinks=True)
    line = next(ln for ln in (Path(root) / "proc/diskstats").read_text().splitlines() if "nvme0n1 " in ln)
    with open(Path(root) / "proc/diskstats", "a") as f:
        f.write(line.replace("nvme0n1", "nvme1n1") + "\n")
    got = disk_temps(root)
    assert "nvme1n1" in got and got["nvme0n1"] is None and got["nvme1n1"] is None


def test_disk_temp_survives_hwmon_renumbering(tree_copy):
    root = tree_copy(AMD)
    base = Path(root) / "sys/class/hwmon"
    want = disk_temps(root)
    (base / "hwmon2").rename(base / "hwmon9")
    assert disk_temps(root) == want


# 13: Puffer
def test_buffers_all_none_are_dropped_others_stay():
    s = Sampler(VM, tools=NoTools(), clock=fake_clock(), uid=1000)
    s._push("gone", None)
    s._push("kept", 1.0)
    s._end_tick()
    s._end_tick()
    assert "gone" not in s._bufs and list(s._bufs["kept"]) == [1.0, None]


# 14 / 15: Netz
def net_tile(root, states):
    for name, st in states.items():
        (Path(root) / "sys/class/net" / name / "operstate").write_text(st + "\n")
    return tile(run(root).snapshot(OVERVIEW), "net")


def test_net_name_unknown_is_not_up(intel_copy):
    t = net_tile(intel_copy, {"enp0s31f6": "unknown", "wlp2s0": "up"})
    assert t["name"] == "wlp2s0" and {"k": "kv.interface", "v": {"l": "wlp2s0"}} in t["kv"]
    t = net_tile(intel_copy, {"enp0s31f6": "up", "wlp2s0": "up"})
    assert t["name"] == "" and not any(k.get("k") == "kv.interface" for k in t["kv"])


def test_net_sums_over_devices(monkeypatch):
    devs = [NetDev("a", 100.0, 10.0, 1000, 100, True), NetDev("b", 50.0, None, 2000, 200, False)]
    s = Sampler(VM, tools=NoTools(), clock=fake_clock(), uid=1000)
    monkeypatch.setattr(s._net, "read", lambda now: devs)
    s.tick_system()
    t = tile(s.snapshot(OVERVIEW), "net")
    assert t["main"] == {"v": 150.0, "u": "B/s", "p": "↓"} and t["aside"] == {"v": 10.0, "u": "B/s", "p": "↑"}
    since = next(k for k in t["kv"] if k["k"] == "kv.since_boot")["v"]
    assert [n["v"] for n in since] == [3000, 300]
    assert [d["values"][0]["v"] for d in t["devices"]["rows"]] == [100.0, 50.0]


# 18: close
def test_close_stops_only_own_tools(monkeypatch):
    stopped = []

    class Own(NoTools):
        def __init__(self, gpus):
            super().__init__()

        def stop(self):
            stopped.append(1)
    monkeypatch.setattr(sampler_mod, "GpuTools", Own)
    Sampler(VM, uid=1000).close()
    assert stopped == [1]
    injected = NoTools()
    injected.stop = lambda: stopped.append(2)
    Sampler(VM, tools=injected, uid=1000).close()
    assert stopped == [1]


# 19 / 20: seg für Lüfter und Temperatur
def test_fan_seg_uses_max_rpm_then_scale_top(patched):
    t = tile(patched(read_sensors=sens(fans=[Fan("f", 2000.0, 4000.0)])).snapshot(OVERVIEW), "fan")
    assert t["seg"] == 50 and t["warn"] is True
    t = tile(patched(read_sensors=sens(fans=[Fan("f", 3000.0, None)])).snapshot(OVERVIEW), "fan")
    assert t["seg"] == 60 and t["warn"] is False  # Skala _nice(3000) = 5000, nicht das Fenstermaximum


def test_temp_seg_uses_crit_else_100(tree_copy):
    root = tree_copy(INTEL)
    base = tile(run(root).snapshot(OVERVIEW), "temp")
    assert base["seg"] == pytest.approx(base["main"]["v"])
    for n in Path(root, "sys/class/hwmon").glob("hwmon*/name"):
        if n.read_text().strip() == "coretemp":
            for crit in n.parent.glob("temp*_crit"):
                crit.write_text("120000\n")
    t = tile(run(root).snapshot(OVERVIEW), "temp")
    assert t["seg"] == pytest.approx(t["main"]["v"] / 120 * 100, abs=0.01)


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


# 23: Swap-Zeile
def test_no_swap_no_swap_series_or_row(tree_copy):
    root = tree_copy(INTEL)
    mi = Path(root, "proc/meminfo")
    mi.write_text("".join(ln + "\n" for ln in mi.read_text().splitlines() if not ln.startswith("Swap")))
    m = tile(run(root).snapshot(OVERVIEW), "mem")
    assert [s["key"] for s in m["series"]] == ["series.used"] and not any(k["k"] == "kv.swap" for k in m["kv"])
    m = tile(run(INTEL).snapshot(OVERVIEW), "mem")
    assert [s["key"] for s in m["series"]] == ["series.used", "series.swap"]
    assert next(k for k in m["kv"] if k["k"] == "kv.swap")["v"]["of"] > 0


# 9 (Minor): GPU-Kurve mischt nie Busy und Takt
def test_gpu_series_decided_once(tree_copy):
    t = tile(run(INTEL).snapshot(OVERVIEW), "gpu0")  # Intel: Busy-Quelle möglich, aber ohne Werte
    assert t["series"][0]["key"] == "series.used" and set(t["series"][0]["values"]) == {None}
    assert t["aside"]["of"] > 0
    root = tree_copy(AMD)
    (Path(root) / "sys/class/drm/card0/device/gpu_busy_percent").unlink()
    t = tile(run(root).snapshot(OVERVIEW), "gpu0")
    assert t["series"][0]["key"] == "kv.clock" and t["main"]["u"] == "%"


# 10 (Minor): VRAM mit of
def test_gpu_memory_has_total():
    kv = next(k for k in tile(run(AMD).snapshot(OVERVIEW), "gpu0")["kv"] if k["k"] == "kv.memory")["v"]
    assert kv["of"] == 8 * 1024 ** 3 and kv["v"] == 3 * 1024 ** 3
    assert {"k": "kv.memory", "v": {"k": "kv.shared_with_ram"}} in tile(run(INTEL).snapshot(OVERVIEW), "gpu0")["kv"]


# Sicherheit: Systemtexte werden bereinigt
def test_system_strings_are_sanitized(tree_copy):
    root = tree_copy(VM)
    (Path(root) / "sys/block/vda/device/model").write_text("Evil\x1b[31m‮Disk\n")
    cpuinfo = Path(root, "proc/cpuinfo")
    cpuinfo.write_text(cpuinfo.read_text() + "model name\t: Bad\x1b CPU\n" if "model name" not in cpuinfo.read_text()
                       else cpuinfo.read_text().replace("model name\t:", "model name\t: \x1b‮"))
    snap = run(root).snapshot(OVERVIEW)

    def walk(o):
        if isinstance(o, str):
            assert o.isprintable(), repr(o)
        elif isinstance(o, dict):
            [walk(v) for v in o.values()]
        elif isinstance(o, list):
            [walk(v) for v in o]
    walk(snap)
    assert tile(snap, "disk")["name"] == "Evil?[31m?Disk"


# dump-snapshot
SCRIPT = str(Path(__file__).parent.parent / "scripts" / "dump-snapshot.py")


def dump(*args, check=True):
    return subprocess.run([sys.executable, SCRIPT, "--root", INTEL, "--ticks", "2", "--interval", "0.05", *args],
                          capture_output=True, text=True, check=check)


def test_dump_view_procs_fills_detail(intel_copy):
    make_proc(Path(intel_copy), 7)
    out = subprocess.run([sys.executable, SCRIPT, "--root", intel_copy, "--ticks", "2", "--interval", "0.05",
                          "--view", "procs"], capture_output=True, text=True, check=True).stdout
    tick = json.loads(out)
    assert tick["procs"] and tick["detail"]["pid"] == max(tick["procs"], key=lambda r: r["cpu"])["pid"]
    assert json.loads(dump().stdout)["procs"] is None


# R30: Demodaten ohne echte Prozessnamen, Befehlszeilen und Benutzer
def test_dump_anonymize_removes_names_cmdlines_users(intel_copy):
    # gegenseitige Eltern: detail (erste Zeile, Reihenfolge je Dateisystem) hat immer einen geheimen Elternnamen
    make_proc(Path(intel_copy), 7, comm="geheim-kind", ppid=8, cmdline=b"/opt/geheim\0--token=xyz\0")
    make_proc(Path(intel_copy), 8, comm="geheim-eltern", ppid=7, cmdline=b"/opt/geheim-eltern\0--pass\0")
    out = subprocess.run([sys.executable, SCRIPT, "--root", intel_copy, "--ticks", "2", "--interval", "0.05",
                          "--view", "procs", "--anonymize"], capture_output=True, text=True, check=True).stdout
    tick = json.loads(out)
    assert "geheim" not in out and "token" not in out and "--pass" not in out
    rows = tick["procs"] + [tick["detail"], tick["top"]["mem"]] + tick["top"]["cpu"]
    assert {r["name"] for r in rows} <= {f"proc-{i}" for i in range(1, len(rows) + 1)}
    assert {r["user"] for r in tick["procs"]} == {"user"} and {r["args"] for r in tick["procs"]} == {""}
    d = tick["detail"]
    assert d["cmdline"] == d["name"] and d["parent"] in {r["name"] for r in tick["procs"]} - {d["name"]}


@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf", "x"])
def test_dump_rejects_bad_interval(bad):
    r = dump("--interval", bad, check=False)
    assert r.returncode == 2 and "interval" in r.stderr


def test_dump_fixture_root_starts_no_tools():
    # Mit Fixture-Baum liefert keine Werkzeug-Quelle Werte: kein pkg_w, also bleibt der RAPL-Hinweis stehen
    tick = json.loads(dump("--ticks", "5").stdout)
    assert tick["hints"] == ["hint.rapl_noperm"]


# ---- Fix-Runde 3 ----
def test_gpu_without_freq_source_does_not_stop_the_tick(tree_copy):
    root = tree_copy(ARM)
    (Path(root) / "sys/class/devfreq/v3d/cur_freq").unlink()
    s = run(root, ticks=4)
    assert s._n == 4
    snap = s.snapshot(OVERVIEW)
    assert {"cpu", "temp", "net", "disk"} <= set(kinds(snap))
    assert all(len(x["values"]) == 4 for t in snap["tiles"] for x in t["series"])


def test_failing_section_does_not_stop_the_others(monkeypatch):
    s = Sampler(AMD, tools=NoTools(), clock=fake_clock(), uid=1000)

    def boom(now):
        raise RuntimeError("x")
    monkeypatch.setattr(s, "_tick_gpus", boom)
    for _ in range(3):
        s.tick_system()
    snap = s.snapshot(OVERVIEW)
    assert s._n == 3 and "gpu" in snap["missing"]
    assert {"cpu", "mem", "temp", "fan", "net", "disk"} <= set(kinds(snap))
    assert len(tile(snap, "net")["series"][0]["values"]) == 3


# 3b: GPU-Nummern zählen nur Karten mit Kachel
def test_gpu_ids_skip_gpus_without_tile(monkeypatch):
    monkeypatch.setattr(sampler_mod, "discover_gpus", lambda root: discover_gpus(root)[::-1])  # nvidia ohne Werte zuerst
    snap = run(AMD).snapshot(OVERVIEW)
    assert [t["id"] for t in snap["tiles"] if t["kind"] == "gpu"] == ["gpu0"]


# N7: Fixture-Baum startet keine echten Werkzeuge (hostunabhängig)
def test_dump_fixture_root_spawns_no_tool(monkeypatch):
    import importlib.util
    from orbitop import gpu_tools
    spec = importlib.util.spec_from_file_location("dump_snapshot", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    started = []
    monkeypatch.setattr(gpu_tools.ToolReader, "start", lambda self: started.append(self._cmd))
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda name, path=None: "/usr/bin/" + name)
    monkeypatch.setattr(gpu_tools, "_has_capability", lambda p: True)
    mod.main(["--root", INTEL, "--ticks", "1"])
    assert started == []


# 15c: rx-Kurve summiert alle Geräte
def test_rx_series_sums_all_devices(monkeypatch):
    devs = [NetDev("a", 100.0, 1.0, 0, 0, True), NetDev("b", 50.0, 2.0, 0, 0, True)]
    s = Sampler(VM, tools=NoTools(), clock=fake_clock(), uid=1000)
    monkeypatch.setattr(s._net, "read", lambda now: devs)
    s.tick_system()
    series = {x["key"]: x["values"] for x in tile(s.snapshot(OVERVIEW), "net")["series"]}
    assert series == {"series.rx": [150.0], "series.tx": [3.0]}


# X1: Laufwerkstemperatur ist der erste Sensor (Composite), nicht der letzte
def test_disk_temp_is_composite_not_last_sensor(tree_copy):
    root = tree_copy(AMD)
    h = Path(root) / "sys/class/hwmon/hwmon2"
    for f in h.glob("temp*"):
        f.unlink()
    (h / "temp1_input").write_text("41000\n")
    (h / "temp1_label").write_text("Composite\n")
    (h / "temp2_input").write_text("63000\n")
    (h / "temp2_label").write_text("Sensor 1\n")
    assert disk_temps(root)["nvme0n1"] == 41.0


# X3: devfreq-GPU mit fdinfo-Clients bekommt die Busy-Kurve
def test_devfreq_gpu_with_fdinfo_clients_gets_busy_series(tree_copy):
    root = tree_copy(ARM)
    assert tile(run(root).snapshot(OVERVIEW), "gpu0")["series"][0]["key"] == "kv.clock"
    make_proc(Path(root), 200)
    d = Path(root) / "proc/200"
    (d / "fd").mkdir()
    (d / "fd/3").symlink_to("/dev/dri/card0")
    (d / "fdinfo").mkdir()
    (d / "fdinfo/3").write_text("drm-driver: v3d\ndrm-client-id: 1\ndrm-engine-render: 100 ns\n")
    assert tile(run(root).snapshot(OVERVIEW), "gpu0")["series"][0]["key"] == "series.used"


# X6 / X21 / X22: Temperaturen vollständig, eindeutig, mit Füllung nur bei der ersten Kurve
def test_temps_complete_unique_and_fill_flags(patched):
    temps = [Temp("Sensor", 1.0, "a"), Temp("Sensor", 2.0, "b"), Temp("Sensor", 3.0, "c"),
             Temp("Sensor", 4.0, "d"), Temp("pch", 5.0, "pch_x"), Temp("Other", 6.0, "e")]
    s = patched(read_sensors=sens(cpu=50.0, temps=temps))
    t = tile(s.snapshot(OVERVIEW), "temp")
    assert [x["fill"] for x in t["series"]] == [True, False, False]
    names = [x.get("key") or x["label"] for x in t["series"]] + [k.get("k") or k["l"] for k in t["kv"]]
    assert names == ["series.cpu_package", "Sensor", "Sensor 2", "Sensor 3", "Sensor 4", "series.chipset", "Other"]
    values = [x["values"][-1] for x in t["series"]] + [k["v"]["v"] for k in t["kv"]]
    assert values == [50.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_disk_temps_built_once_per_tick(monkeypatch, tree_copy):
    root = tree_copy(AMD)
    s = Sampler(root, tools=NoTools(), clock=fake_clock(), uid=1000)
    s.tick_system()
    calls = []
    real = os.path.realpath
    monkeypatch.setattr(sampler_mod.os.path, "realpath", lambda p: (calls.append(p), real(p))[1])
    s.tick_system()
    chip_calls = [c for c in calls if "/hwmon/" in c]
    assert len(chip_calls) == len(set(chip_calls)) == 2  # nvme und drivetemp, je einmal


def test_dead_locale_key_removed():
    from orbitop.i18n import load_texts
    assert "tile.power_aside" not in load_texts("en") and "kv.battery_ac" not in load_texts("en")


@pytest.mark.parametrize("part,whole,want", [(None, 100, None), (5, None, None), (5, 0, None), (50, 200, 25.0), (0, 10, 0.0)])
def test_pct_is_none_safe(part, whole, want):
    assert sampler_mod._pct(part, whole) == want


# ---- Task 14, Fix-Runde 1: warn, Segmente relativ zur Skala, Geräte-Tabelle, Anonymisieren ----
def test_warn_only_with_absolute_reference():
    snap = run(INTEL, ticks=4, tools=NoTools(pkg_w=7.5)).snapshot(OVERVIEW)
    assert {t["id"]: t["warn"] for t in snap["tiles"]} == {
        "cpu": True, "gpu0": True, "mem": True, "power": False, "temp": True, "fan": True, "net": False, "disk": False}
    assert tile(snap, "power")["seg"] == 75  # 7,5 W auf der Skala _nice(7,5) = 10, nicht 100 % des Fenstermaximums


def net_seg(monkeypatch, *ticks):
    s = Sampler(VM, tools=NoTools(), clock=fake_clock(), uid=1000)
    seq = iter(ticks)
    monkeypatch.setattr(s._net, "read", lambda now: next(seq))
    for _ in ticks:
        s.tick_system()
    t = tile(s.snapshot(OVERVIEW), "net")
    return t["seg"], t["warn"]


def test_net_seg_relative_without_link_speed(monkeypatch):
    ticks = [NetDev("a", 1500.0, 1.0, 0, 0, True)], [NetDev("a", 600.0, 1.0, 0, 0, True)]
    assert net_seg(monkeypatch, *ticks) == (30, False)  # Skala _nice(1500) = 2000


def test_net_seg_absolute_with_link_speed_of_every_active_device(monkeypatch):
    fast = NetDev("a", 1.25e6, 1.0, 0, 0, True, 100)  # 100 Mbit/s = 12,5 MB/s
    assert net_seg(monkeypatch, [fast]) == (10, True)
    down = NetDev("b", 0.0, 0.0, 0, 0, False)
    assert net_seg(monkeypatch, [fast, down]) == (10, True)  # inaktive Geräte zählen nicht
    wifi = NetDev("c", 0.0, 0.0, 0, 0, True)  # aktiv, ohne Speed: Bezug unbekannt
    assert net_seg(monkeypatch, [fast, wifi]) == (62.5, False)


def test_net_link_reference_ignores_stale_speed_of_inactive_device(monkeypatch):
    fast = NetDev("a", 1.25e6, 1.0, 0, 0, True, 100)  # aktiv, 100 Mbit/s
    stale = NetDev("b", 0.0, 0.0, 0, 0, False, 1000)  # inaktiv, meldet noch 1000 Mbit/s
    assert net_seg(monkeypatch, [fast, stale]) == (10, True)  # Bezug 12,5 MB/s, nicht 137,5 MB/s


def test_disk_seg_relative_to_scale_top(monkeypatch):
    s = Sampler(VM, tools=NoTools(), clock=fake_clock(), uid=1000)
    monkeypatch.setattr(s._disk, "read", lambda now: [Disk("sda", "", 3000.0, 0.0, None, None, None)])
    s.tick_system()
    t = tile(s.snapshot(OVERVIEW), "disk")
    assert (t["seg"], t["warn"]) == (60, False)


def test_device_tables_have_columns_and_null_cells(monkeypatch):
    s = Sampler(VM, tools=NoTools(), clock=fake_clock(), uid=1000)
    monkeypatch.setattr(s._net, "read", lambda now: [NetDev("a", 100.0, None, 0, 0, True)])
    monkeypatch.setattr(s._disk, "read", lambda now: [Disk("sda", "M", 5.0, None, 10, 40, None),
                                                      Disk("sdb", "N", None, 1.0, None, None, None)])
    s.tick_system()
    snap = s.snapshot(OVERVIEW)
    assert tile(snap, "net")["devices"] == {
        "cols": ["series.rx", "series.tx"], "rows": [{"name": "a", "values": [{"v": 100.0, "u": "B/s"}, None]}]}
    assert tile(snap, "disk")["devices"] == {
        "cols": ["series.read", "series.write", "kv.used", "kv.temperature"],
        "rows": [{"name": "sda", "values": [{"v": 5.0, "u": "B/s"}, None, {"v": 10, "u": "B", "of": 40}, None]},
                 {"name": "sdb", "values": [None, {"v": 1.0, "u": "B/s"}, None, None]}]}


def test_net_reader_reads_link_speed(tree_copy):
    root = tree_copy(VM)
    speed = Path(root) / "sys/class/net/ens3/speed"
    speed.write_text("1000\n")
    assert [d.speed for d in NetReader(root).read(1.0)] == [1000]
    speed.write_text("-1\n")  # Kabel gezogen
    assert [d.speed for d in NetReader(root).read(1.0)] == [None]
    speed.unlink()  # WLAN: Lesen scheitert
    assert [d.speed for d in NetReader(root).read(1.0)] == [None]


def load_dump():
    import importlib.util
    spec = importlib.util.spec_from_file_location("dump_snapshot", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_anonymize_replaces_every_name_field():
    secret = "geheimname"
    brief = {"pid": 5, "start": 9, "name": secret, "cpu": 1.0, "rss": 1}
    row = {**brief, "args": secret + " --flag", "user": secret}
    tick = {"top": {"cpu": [dict(brief)], "mem": dict(brief)}, "procs": [dict(row)],
            "detail": {**row, "cmdline": secret + " --flag", "parent": secret}}
    out = load_dump().anonymize(tick)
    assert secret not in json.dumps(out)
    assert out["top"]["cpu"][0]["name"] == out["detail"]["parent"] == "proc-1"
    assert out["detail"]["user"] == "user" and out["procs"][0]["args"] == ""


def test_sampler_holds_slow_chip_between_ticks(tree_copy):
    """dell_smm (BIOS-SMM) wird höchstens alle 5 s gelesen; der Sampler behält den Wert über die Takte."""
    root = tree_copy(INTEL)
    t = [0.0]
    s = Sampler(root, tools=NoTools(), clock=lambda: t[0], uid=1000)
    fan = Path(root, "sys/class/hwmon/hwmon5/fan1_input")
    rpm = lambda: tile(s.snapshot(OVERVIEW), "fan")["main"]["v"]  # noqa: E731
    s.tick_system()
    old = rpm()
    fan.write_text("1234")
    for now in (1.0, 2.0, 3.0, 4.0):
        t[0] = now
        s.tick_system()
        assert rpm() == old
    t[0] = 5.0
    s.tick_system()
    assert rpm() == 1234
