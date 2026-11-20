# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Sampler: Leser je Abschnitt, Raten, Leistungsquelle, Verläufe und Hinweise."""
import json
from pathlib import Path

import pytest

from orbitop import sampler as sampler_mod
from orbitop.gpu import discover_gpus
from orbitop.sampler import Sampler
from orbitop.sensors import Battery, Temp, read_sensors
from orbitop.system import NetDev, NetReader
from tests.procs_helpers import make_proc
from tests.roots import AMD, ARM, INTEL, VM
from tests.sampler_helpers import OVERVIEW, NoTools, fake_clock, kinds, power_of, run, sens, tile


def test_intel_package_power_from_tools_replaces_rapl_hint():
    snap = run(INTEL, ticks=4, tools=NoTools(pkg_w=7.5)).snapshot(OVERVIEW)
    p = tile(snap, "power")
    assert p["main"] == {"v": 7.5, "u": "W"} and p["aside"] == {"k": "series.cpu_package"}
    assert snap["hints"] == []


def test_series_gap_stays_none():
    t = tile(run(INTEL, ticks=2).snapshot(OVERVIEW), "cpu")
    assert t["series"][0]["values"][-1] is None and t["main"]["v"] is None


def test_reader_exception_does_not_break(monkeypatch):
    s = Sampler(INTEL, tools=NoTools(), uid=1000)

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(s._cpu, "read", boom)
    monkeypatch.setattr(sampler_mod, "read_sensors", boom)
    monkeypatch.setattr(sampler_mod.procs, "scan", boom)
    s.tick_system()
    with pytest.raises(RuntimeError):  # Prozess-Takt: der Worker meldet den Fehler einmal (_guard) und läuft weiter
        s.tick_procs()
    snap = s.snapshot({"tab": "procs", "pid": 1, "start": 1})
    assert "cpu" in snap["missing"] and "temp" in snap["missing"] and "mem" in kinds(snap)
    json.dumps(snap, allow_nan=False)


# 13: Puffer
def test_buffers_all_none_are_dropped_others_stay():
    s = Sampler(VM, tools=NoTools(), clock=fake_clock(), uid=1000)
    s._push("gone", None)
    s._push("kept", 1.0)
    s._end_tick()
    s._end_tick()
    assert "gone" not in s._bufs and list(s._bufs["kept"]) == [1.0, None]


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


def test_gpu_without_freq_source_does_not_stop_the_tick(tree_copy):
    root = tree_copy(ARM)
    (Path(root) / "sys/class/devfreq/v3d/cur_freq").unlink()
    s = run(root, ticks=4)
    assert s._n == 4
    snap = s.snapshot(OVERVIEW)
    assert {"cpu", "temp", "net", "disk"} <= set(kinds(snap))
    assert all(len(x["values"]) == 4 for t in snap["tiles"] for x in t["series"])


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


def test_intel_and_recheck_tools():  # für die Freigabe: perfmon nur mit Intel-Grafik (Q2), neu erkennen (Q3)
    tools = NoTools()
    assert Sampler(INTEL, tools=tools, uid=1000).intel is True and Sampler(VM, tools=tools, uid=1000).intel is False
    Sampler(VM, tools=tools, uid=1000).recheck_tools()
    assert tools.rechecks == 1


def test_default_clock_counts_suspend(monkeypatch):  # s2idle: monotonic steht im Ruhezustand, RAPL zählt weiter
    real, boot = sampler_mod.time.clock_gettime, [1000.0]
    monkeypatch.setattr(sampler_mod.time, "clock_gettime",
                        lambda cid: boot[0] if cid == sampler_mod.time.CLOCK_BOOTTIME else real(cid))
    s = Sampler(INTEL, tools=NoTools(), uid=1000)
    for boot[0] in (1001.0, 1002.0, 1062.0):  # der letzte Takt kommt 60 s Ruhezustand später
        s.tick_system()
    assert list(s._bufs["rx"]) == [None, 0.0, None]  # erster Takt Basis, nach dem Aufwachen eine Lücke


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


# 3 / 22 / 1a-1c: Leistungskette und Name der Series
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


def test_power_curve_never_mixes_sources(monkeypatch):  # powerprobe: Anlauf von intel_gpu_top im Akkubetrieb
    tools = NoTools()
    monkeypatch.setattr(sampler_mod, "read_battery", lambda *a: BATT)
    s = Sampler(INTEL, tools=tools, clock=fake_clock(), uid=1000)
    s._rapl.read = lambda now: None
    for i in range(6):
        tools.pkg_w = 4.0 if i >= 3 else None  # erste Takte: nur die Akku-Entladung (9 W)
        s.tick_system()
    p = tile(s.snapshot(OVERVIEW), "power")
    assert p["series"][0]["key"] == "series.cpu_package"
    assert p["series"][0]["values"] == [None, None, None, 4.0, 4.0, 4.0]  # der Quellenwechsel ist eine Lücke


def test_power_chain_picks_hwmon_first_entry(patched):
    p = power_of(patched, hw=[("a", 1.0), ("b", 2.0)])
    assert p["main"]["v"] == 1.0


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


# 3b: GPU-Nummern zählen nur Karten mit Kachel
def test_gpu_ids_skip_gpus_without_tile(monkeypatch):
    monkeypatch.setattr(sampler_mod, "discover_gpus", lambda root: discover_gpus(root)[::-1])  # nvidia ohne Werte zuerst
    snap = run(AMD).snapshot(OVERVIEW)
    assert [t["id"] for t in snap["tiles"] if t["kind"] == "gpu"] == ["gpu0"]


# 9 (Minor): GPU-Kurve mischt nie Busy und Takt
def test_gpu_series_decided_once(tree_copy):
    t = tile(run(INTEL).snapshot(OVERVIEW), "gpu0")  # Intel: Busy-Quelle möglich, aber ohne Werte
    assert t["series"][0]["key"] == "series.used" and set(t["series"][0]["values"]) == {None}
    assert t["aside"]["of"] > 0
    root = tree_copy(AMD)
    (Path(root) / "sys/class/drm/card0/device/gpu_busy_percent").unlink()
    t = tile(run(root).snapshot(OVERVIEW), "gpu0")
    assert t["series"][0]["key"] == "kv.clock" and t["main"]["u"] == "%"


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


# 15c: rx-Kurve summiert alle Geräte
def test_rx_series_sums_all_devices(monkeypatch):
    devs = [NetDev("a", 100.0, 1.0, 0, 0, True), NetDev("b", 50.0, 2.0, 0, 0, True)]
    s = Sampler(VM, tools=NoTools(), clock=fake_clock(), uid=1000)
    monkeypatch.setattr(s._net, "read", lambda now: devs)
    s.tick_system()
    series = {x["key"]: x["values"] for x in tile(s.snapshot(OVERVIEW), "net")["series"]}
    assert series == {"series.rx": [150.0], "series.tx": [3.0]}


def test_net_reader_reads_link_speed(tree_copy):
    root = tree_copy(VM)
    speed = Path(root) / "sys/class/net/ens3/speed"
    speed.write_text("1000\n")
    assert [d.speed for d in NetReader(root).read(1.0)] == [1000]
    speed.write_text("-1\n")  # Kabel gezogen
    assert [d.speed for d in NetReader(root).read(1.0)] == [None]
    speed.unlink()  # WLAN: Lesen scheitert
    assert [d.speed for d in NetReader(root).read(1.0)] == [None]
