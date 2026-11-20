# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Kachelbau (orbitop.tiles): Formathilfen, Werte, Skalen, Segmente und Tabellen der Kacheln."""
from pathlib import Path

import pytest

from orbitop import tiles
from orbitop.sampler import Sampler
from orbitop.sensors import Battery, Fan, Temp
from orbitop.system import Disk, Mem, NetDev
from tests.roots import AMD, INTEL, VM
from tests.sampler_helpers import OVERVIEW, NoTools, fake_clock, power_of, run, sens, tile


@pytest.mark.parametrize("v,want", [(0, 1), (0.3, 1), (1, 1), (1.5, 2), (3, 5), (5, 5), (6, 10), (130, 200), (4.2e6, 5e6)])
def test_nice_ceiling(v, want):
    assert tiles.nice(v) == want


# 6: seg-Klemme
@pytest.mark.parametrize("v,ref,want", [(150, 100, 100), (-5, 100, 0), (None, 100, 0), (5, 0, 0), (5, None, 0), (50, 200, 25)])
def test_seg_clamped(v, ref, want):
    assert tiles.seg(v, ref) == want


@pytest.mark.parametrize("part,whole,want", [(None, 100, None), (5, None, None), (5, 0, None), (50, 200, 25.0), (0, 10, 0.0)])
def test_pct_is_none_safe(part, whole, want):
    assert tiles.pct(part, whole) == want


# 9: clean
def test_clean_rounds_and_removes_nonfinite():
    out = tiles.clean({"a": 1.23456, "b": [float("nan"), float("inf"), 2.0], "c": "x\x1b‮y", "d": 3})
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


def test_temperature_scale_grows_above_100():
    s = run(INTEL)
    s._bufs["temp:#cpu"].append(120.0)
    t = tile(s.snapshot(OVERVIEW), "temp")
    assert t["series"][0]["max"] == pytest.approx(132.0)
    assert t["main"]["v"] == max(v for _, _, v in s._s["temps"]) and t["aside"] == {"k": "tile.temp_aside"}


def test_pair_and_direction_shapes():
    snap = run(INTEL).snapshot(OVERVIEW)
    assert tile(snap, "mem")["aside"]["of"] > tile(snap, "mem")["aside"]["v"]
    net = tile(snap, "net")
    assert net["main"]["p"] == "↓" and net["aside"]["p"] == "↑"
    since = next(k for k in net["kv"] if k.get("k") == "kv.since_boot")["v"]
    assert [n["p"] for n in since] == ["↓", "↑"]


# 4: Akku-Zeile
def test_battery_row_on_ac_and_discharging(patched):
    p = power_of(patched, pkg_w=5.0, batt=Battery(80.0, True, None))
    assert next(k for k in p["kv"] if k["k"] == "kv.battery")["v"] == [{"v": 80.0, "u": "%"}, {"k": "kv.on_ac"}]
    p = power_of(patched, pkg_w=5.0, batt=Battery(80.0, False, 9.5))
    assert next(k for k in p["kv"] if k["k"] == "kv.battery")["v"] == [{"v": 80.0, "u": "%"}, {"v": 9.5, "u": "W"}]
    p = power_of(patched, pkg_w=5.0, batt=Battery(80.0, False, None))
    assert next(k for k in p["kv"] if k["k"] == "kv.battery")["v"] == [{"v": 80.0, "u": "%"}]


def test_power_row_cpu_cores_only_with_rapl_core_zone(patched):
    p = power_of(patched, rapl={"package-0": 12.0, "core": 3.0})
    assert {"k": "kv.cpu_cores", "v": {"v": 3.0, "u": "W"}} in p["kv"]
    assert not any(k["k"] == "kv.cpu_cores" for k in power_of(patched, rapl={"package-0": 12.0})["kv"])


def test_mem_tile_from_plain_values_and_history():  # Schnittstelle: Werte und Verläufe hinein, Kachel heraus
    t = tiles.mem_tile(Mem(total=8000, available=6000, used=2000, swap_total=0, swap_used=0), {"mem": [10.0, 25.0]})
    assert t == {"id": "mem", "kind": "mem", "name": "", "main": {"v": 25.0, "u": "%"},
                 "aside": {"v": 2000, "u": "B", "of": 8000}, "seg": 25.0, "threads": None, "devices": None,
                 "series": [{"key": "series.used", "fill": True, "max": 100.0, "u": "%", "values": [10.0, 25.0]}],
                 "kv": [{"k": "kv.available", "v": {"v": 6000, "u": "B"}}], "warn": True}
    assert tiles.mem_tile(None, {}) is None


# 3: aside-Entscheidungen nach dem Entwurf
def test_asides_follow_mockup():
    snap = run(AMD).snapshot(OVERVIEW)
    assert tile(snap, "temp")["aside"] == {"k": "tile.temp_aside"}
    assert tile(snap, "disk")["aside"] == {"k": "series.read"}
    fan = tile(snap, "fan")
    assert set(fan["aside"]) == {"l"} and fan["name"] == ""


def test_temp_main_is_hottest_sensor(patched):
    s = patched(read_sensors=sens(cpu=50.0, temps=[Temp("hot", 80.0, "x"), Temp("cool", 30.0, "x")]))
    t = tile(s.snapshot(OVERVIEW), "temp")
    assert t["main"]["v"] == 80.0 and t["series"][0]["key"] == "series.cpu_package"
    assert t["series"][0]["values"][-1] == 50.0  # gefüllt bleibt die CPU


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


# 19 / 20: seg für Lüfter und Temperatur
def test_fan_seg_uses_max_rpm_then_scale_top(patched):
    t = tile(patched(read_sensors=sens(fans=[Fan("f", 2000.0, 4000.0)])).snapshot(OVERVIEW), "fan")
    assert t["seg"] == 50 and t["warn"] is True
    t = tile(patched(read_sensors=sens(fans=[Fan("f", 3000.0, None)])).snapshot(OVERVIEW), "fan")
    assert t["seg"] == 60 and t["warn"] is False  # Skala nice(3000) = 5000, nicht das Fenstermaximum


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


# 10 (Minor): VRAM mit of
def test_gpu_memory_has_total():
    kv = next(k for k in tile(run(AMD).snapshot(OVERVIEW), "gpu0")["kv"] if k["k"] == "kv.memory")["v"]
    assert kv["of"] == 8 * 1024 ** 3 and kv["v"] == 3 * 1024 ** 3
    assert {"k": "kv.memory", "v": {"k": "kv.shared_with_ram"}} in tile(run(INTEL).snapshot(OVERVIEW), "gpu0")["kv"]


def test_warn_only_with_absolute_reference():
    snap = run(INTEL, ticks=4, tools=NoTools(pkg_w=7.5)).snapshot(OVERVIEW)
    assert {t["id"]: t["warn"] for t in snap["tiles"]} == {
        "cpu": True, "gpu0": True, "mem": True, "power": False, "temp": True, "fan": True, "net": False, "disk": False}
    assert tile(snap, "power")["seg"] == 75  # 7,5 W auf der Skala nice(7,5) = 10, nicht 100 % des Fenstermaximums


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
    assert net_seg(monkeypatch, *ticks) == (30, False)  # Skala nice(1500) = 2000


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
