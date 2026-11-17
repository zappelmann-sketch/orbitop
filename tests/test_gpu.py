# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import shutil

import statistics
import time
from pathlib import Path

import pytest

from orbitop import gpu as gpumod
from orbitop.gpu import FdinfoScanner, GpuReader, GpuSample, discover_gpus
from tests.roots import AMD, ARM, INTEL, VM


class FakeTools:
    def __init__(self, intel=None, nvidia=None):
        self._intel, self._nvidia = intel, nvidia
        self.calls = []

    def intel(self, card):
        self.calls.append(("intel", card))
        return self._intel

    def nvidia(self, pci):
        self.calls.append(("nvidia", pci))
        return self._nvidia


def gpu(root, card):
    return next(g for g in discover_gpus(root) if g.card == card)


def test_discover_amd_two_cards():
    assert [(g.driver, g.vendor) for g in discover_gpus(AMD)] == [("amdgpu", "amd"), ("nvidia", "nvidia")]


def test_vm_no_gpus():
    assert discover_gpus(VM) == []


def test_pci_from_realpath_and_names():
    amd0, nv1 = discover_gpus(AMD)
    assert (amd0.pci, nv1.pci) == ("0000:03:00.0", "0000:01:00.0")
    assert gpu(INTEL, "card1").pci is None  # kein PCI-Name im Pfad
    assert gpu(INTEL, "card1").name == "Intel Graphics (i915)"
    assert nv1.name == "NVIDIA (nvidia)"
    assert gpu(ARM, "card0").vendor == "arm"


def test_product_name_and_connectors_ignored(tree_copy):
    root = tree_copy(INTEL)
    Path(f"{root}/sys/class/drm/card1/device/product_name").write_text("Iris Xe\n")
    os.makedirs(f"{root}/sys/class/drm/card1-DP-1")
    gpus = discover_gpus(root)
    assert [(g.card, g.name) for g in gpus] == [("card1", "Iris Xe")]


def test_gpu_sample_carries_only_shown_values():
    assert list(GpuSample.__dataclass_fields__) == ["busy", "freq_mhz", "freq_max_mhz", "power_w", "temp_c",
                                                    "vram_used", "vram_total"]


def test_amdgpu_sample():
    amd0 = gpu(AMD, "card0")
    s = GpuReader(AMD, amd0).read(0)
    assert (s.busy, s.freq_mhz, s.power_w) == (37.0, 1850.0, 45.0)
    assert s.temp_c == 61.0 and s.freq_max_mhz == 2400.0
    assert s.vram_total > 0 and s.vram_used is not None


def test_amdgpu_sclk_without_star_and_power_fallback(tree_copy):
    root = tree_copy(AMD)
    dev = f"{root}/sys/class/drm/card0/device"
    Path(f"{dev}/pp_dpm_sclk").write_text("0: 500Mhz\n1: 1850Mhz\n")
    hw = f"{dev}/hwmon/hwmon5"
    os.remove(f"{hw}/power1_average")
    Path(f"{hw}/power1_input").write_text("7000000\n")
    s = GpuReader(root, gpu(root, "card0")).read(0)
    assert s.freq_mhz is None and s.power_w == 7.0


def test_amdgpu_card_vanished(tree_copy):
    root = tree_copy(AMD)
    reader = GpuReader(root, gpu(root, "card0"))
    shutil.rmtree(f"{root}/sys/class/drm/card0")
    s = reader.read(0)
    assert (s.busy, s.freq_mhz, s.power_w, s.temp_c) == (None,) * 4


def test_intel_freq_without_tools():
    s = GpuReader(INTEL, gpu(INTEL, "card1")).read(0)
    assert s.freq_mhz is not None
    assert s.freq_max_mhz == 1150.0


def test_intel_tools_preferred():
    tools = FakeTools(intel={"busy": 12.5, "freq_mhz": 800.0, "gpu_w": 3.5, "pkg_w": 9.0})
    s = GpuReader(INTEL, gpu(INTEL, "card1"), tools).read(0)
    assert (s.busy, s.freq_mhz, s.power_w) == (12.5, 800.0, 3.5)
    assert tools.calls == [("intel", "card1")]


def test_xe_freq(tree_copy):
    root = tree_copy(INTEL)
    dev = f"{root}/sys/class/drm/card1/device"
    os.remove(f"{dev}/driver")
    os.symlink("../../../bus/pci/drivers/xe", f"{dev}/driver")
    os.makedirs(f"{dev}/tile0/gt0/freq0")
    Path(f"{dev}/tile0/gt0/freq0/act_freq").write_text("650\n")
    Path(f"{dev}/tile0/gt0/freq0/max_freq").write_text("1300\n")
    s = GpuReader(root, gpu(root, "card1")).read(0)
    assert (s.freq_mhz, s.freq_max_mhz) == (650.0, 1300.0)


def test_nvidia_without_tool_all_none():
    nv1 = gpu(AMD, "card1")
    s = GpuReader(AMD, nv1, tools=None).read(0)
    assert s.busy is None and s.freq_mhz is None and s.temp_c is None and s.vram_total is None


def test_nvidia_with_tool():
    nv1 = gpu(AMD, "card1")
    tools = FakeTools(nvidia={"name": "RTX 4070", "busy": 80.0, "vram_used": 2, "vram_total": 12,
                              "temp_c": 55.0, "power_w": 120.0, "freq_mhz": 2100.0,
                              "freq_max_mhz": 2700.0})
    r = GpuReader(AMD, nv1, tools)
    s = r.read(0)
    assert tools.calls == [("nvidia", "0000:01:00.0")]
    assert (s.busy, s.temp_c, s.power_w, s.freq_max_mhz) == (80.0, 55.0, 120.0, 2700.0)
    assert (s.vram_used, s.vram_total) == (2 * 1024 ** 2, 12 * 1024 ** 2)
    assert r.name == "RTX 4070"


def test_nvidia_tool_returns_none():
    tools = FakeTools(nvidia=None)
    assert GpuReader(AMD, gpu(AMD, "card1"), tools).read(0).busy is None


def test_nouveau_only_temperature(tree_copy):
    root = tree_copy(AMD)
    dev = f"{root}/sys/class/drm/card0/device"
    os.remove(f"{dev}/driver")
    os.symlink("../../../bus/pci/drivers/nouveau", f"{dev}/driver")
    s = GpuReader(root, gpu(root, "card0")).read(0)
    assert s.temp_c == 61.0 and s.busy is None and s.power_w is None and s.freq_mhz is None


def test_arm_v3d_devfreq():
    s = GpuReader(ARM, gpu(ARM, "card0")).read(0)
    assert (s.freq_mhz, s.freq_max_mhz) == (500.0, 960.0)


def test_devfreq_of_other_device_not_used(tree_copy):
    root = tree_copy(ARM)
    os.remove(f"{root}/sys/class/devfreq/v3d/device")
    os.makedirs(f"{root}/sys/devices/platform/other")
    os.symlink("../../../devices/platform/other", f"{root}/sys/class/devfreq/v3d/device")
    s = GpuReader(root, gpu(root, "card0")).read(0)
    assert s.freq_mhz is None and s.freq_max_mhz is None


def test_devfreq_below_device(tree_copy):
    root = tree_copy(ARM)
    shutil.rmtree(f"{root}/sys/class/devfreq")
    d = f"{root}/sys/class/drm/card0/device/devfreq/x"
    os.makedirs(d)
    Path(f"{d}/cur_freq").write_text("300000000\n")
    Path(f"{d}/max_freq").write_text("600000000\n")
    s = GpuReader(root, gpu(root, "card0")).read(0)
    assert (s.freq_mhz, s.freq_max_mhz) == (300.0, 600.0)


def add_client(proc, pid, fd, text, uid=None, status=None, target="/dev/dri/renderD128", start=1):
    p = proc / str(pid)
    (p / "fd").mkdir(parents=True, exist_ok=True)
    (p / "fdinfo").mkdir(parents=True, exist_ok=True)
    u = os.getuid() if uid is None else uid
    (p / "status").write_text(status or f"Name:\tx\nUid:\t{u}\t{u}\t{u}\t{u}\n")
    (p / "stat").write_text(f"{pid} (a) b) S " + "0 " * 18 + f"{start}\n")
    if not (p / "fd" / str(fd)).is_symlink():
        os.symlink(target, p / "fd" / str(fd))
    (p / "fdinfo" / str(fd)).write_text(text)


def info(drv="i915", cid=7, ns=0, pdev=None, engine="render"):
    extra = f"drm-pdev:\t{pdev}\n" if pdev else ""
    return f"pos:\t0\ndrm-driver:\t{drv}\ndrm-client-id:\t{cid}\n{extra}drm-engine-{engine}:\t{ns} ns\n"


def scanner(tmp_path):
    return FdinfoScanner(str(tmp_path), os.getuid())


def test_scanner_dedupes_client_ids_and_filters_uid(tmp_path):
    proc = tmp_path / "proc"
    uid = os.getuid()
    add_client(proc, 100, 10, info(ns=1_000_000))
    add_client(proc, 100, 11, info(ns=1_000_000))
    add_client(proc, 101, 10, info(cid=8, ns=2_000_000))
    add_client(proc, 101, 11, info("xe", 9, 500))
    add_client(proc, 102, 10, info(cid=10, ns=9_000_000), uid=uid + 1)  # fremder Prozess
    assert scanner(tmp_path).snapshot(0) == {"i915": {"7": {"render": 1_000_000}, "8": {"render": 2_000_000}},
                                             "xe": {"9": {"render": 500}}}


def test_scanner_real_uid_not_effective(tmp_path):
    add_client(tmp_path / "proc", 5, 10, info(),
               status=f"Uid:\t{os.getuid() + 1}\t{os.getuid()}\t0\t0\n")
    assert scanner(tmp_path).snapshot(0) == {}


def test_scanner_skips_broken_and_missing(tmp_path):
    proc = tmp_path / "proc"
    (proc / "5").mkdir(parents=True)  # ohne status
    (proc / "6").mkdir()
    (proc / "6" / "status").write_text("Uid:\tbroken\n")
    assert scanner(tmp_path).snapshot(0) == {}
    assert FdinfoScanner(str(tmp_path / "nope"), os.getuid()).snapshot(0) == {}


def test_scanner_never_reads_non_drm_fds(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    add_client(proc, 100, 10, info(ns=5))
    add_client(proc, 100, 11, "pos:\t0\n", target="/dev/null")
    add_client(proc, 100, 12, "pos:\t0\n", target="socket:[1]")
    seen = []
    real = gpumod.sysfs.read_str
    monkeypatch.setattr(gpumod.sysfs, "read_str", lambda p: (seen.append(p), real(p))[1])
    sc = scanner(tmp_path)
    sc.snapshot(0)
    sc.snapshot(1)
    assert not [p for p in seen if p.endswith(("/fdinfo/11", "/fdinfo/12"))]
    assert any(p.endswith("/fdinfo/10") for p in seen)


def test_scanner_new_pids_between_full_scans(tmp_path):
    proc = tmp_path / "proc"
    add_client(proc, 100, 10, info(ns=1))
    sc = scanner(tmp_path)
    assert list(sc.snapshot(0)["i915"]) == ["7"]
    add_client(proc, 200, 10, info(cid=8, ns=1))
    assert sorted(sc.snapshot(1)["i915"]) == ["7", "8"]  # neue PID ohne Voll-Scan
    shutil.rmtree(proc / "100")
    assert list(sc.snapshot(2)["i915"]) == ["8"]  # verschwundene PID entfällt


def test_scanner_ns_hardening(tmp_path):
    add_client(tmp_path / "proc", 1, 10, info(ns="9" * 21))
    assert scanner(tmp_path).snapshot(0) == {"i915": {"7": {}}}


def reader(tmp_path, root=INTEL, card="card1"):
    return GpuReader(str(tmp_path), gpu(root, card), scanner=scanner(tmp_path))


def test_own_busy_delta_throttle_and_gap(tmp_path):
    proc = tmp_path / "proc"
    add_client(proc, 100, 10, info(ns=0))
    r = reader(tmp_path)
    assert r._own_busy(0.0) is None  # kein Vorgänger
    add_client(proc, 100, 10, info(ns=1_000_000_000))
    assert r._own_busy(1.0) is None  # gedrosselt
    assert r._own_busy(2.0) == 50.0
    add_client(proc, 100, 10, info(ns=9_000_000_000))
    assert r._own_busy(3.0) == 50.0  # gedrosselt: letzter Wert
    assert r._own_busy(4.0) == 100.0  # begrenzt
    add_client(proc, 100, 10, info(ns=1))
    assert r._own_busy(6.0) is None  # Zähler gefallen
    add_client(proc, 100, 10, info(ns=2_000_000_000))
    assert r._own_busy(20.0) is None  # dt > MAX_DT
    assert r._own_busy(22.0) == 0.0


def test_own_busy_new_client_no_spike(tmp_path):
    proc = tmp_path / "proc"
    add_client(proc, 100, 10, info(ns=0))
    r = reader(tmp_path)
    r._own_busy(0.0)
    add_client(proc, 100, 10, info(ns=1_000_000_000))
    add_client(proc, 101, 10, info(cid=8, ns=50_000_000_000))  # neuer Client mit Altlast
    assert r._own_busy(2.0) == 50.0


def test_own_busy_none_without_engine_values(tmp_path):
    proc = tmp_path / "proc"
    for ns in (0, 5):
        add_client(proc, 100, 10, f"drm-driver:\txe\ndrm-client-id:\t7\ndrm-cycles-rcs:\t{ns}\n")
    r = GpuReader(str(tmp_path), gpumod.GpuInfo("card1", "xe", "intel", "x", None), scanner=scanner(tmp_path))
    r._own_busy(0.0)
    assert r._own_busy(2.0) is None


def test_own_busy_no_clients_is_none(tmp_path):
    (tmp_path / "proc").mkdir()
    r = reader(tmp_path)
    r._own_busy(0.0)
    assert r._own_busy(2.0) is None


def test_own_busy_per_card_by_pdev(tmp_path):
    proc = tmp_path / "proc"
    sc = scanner(tmp_path)
    mk = lambda pci: GpuReader(str(tmp_path), gpumod.GpuInfo("c", "i915", "intel", "x", pci), scanner=sc)
    a, b = mk("0000:00:02.0"), mk("0000:03:00.0")
    add_client(proc, 1, 10, info(cid=1, ns=0, pdev="0000:00:02.0"))
    add_client(proc, 1, 11, info(cid=2, ns=0, pdev="0000:03:00.0"))
    a._own_busy(0.0), b._own_busy(0.0)
    add_client(proc, 1, 10, info(cid=1, ns=1_000_000_000, pdev="0000:00:02.0"))
    add_client(proc, 1, 11, info(cid=2, ns=2_000_000_000, pdev="0000:03:00.0"))
    assert (a._own_busy(2.0), b._own_busy(2.0)) == (50.0, 100.0)


def test_intel_own_scope_via_fdinfo(tmp_path, tree_copy):
    root = tree_copy(INTEL)
    proc = tmp_path / "root" / "proc"
    add_client(proc, 1, 10, info(ns=0))
    r = GpuReader(root, gpu(root, "card1"))
    assert r.read(0).busy is None
    add_client(proc, 1, 10, info(ns=1_000_000_000))
    s = r.read(2.0)
    assert s.busy == 50.0


@pytest.mark.parametrize("bad", ["00:02.0", "0000:00:02.8", "0000:00:02.9", "0000:00:0A.0", "0000:00:02.0x"])
def test_pci_regex_negatives(tree_copy, bad):
    root = tree_copy(INTEL)
    dev = f"{root}/sys/class/drm/card1/device"
    shutil.rmtree(dev)
    os.makedirs(f"{root}/sys/devices/{bad}")
    os.symlink(f"../../../devices/{bad}", dev)
    assert gpu(root, "card1").pci is None


def test_scanner_cheap_on_real_proc():
    sc = FdinfoScanner("/", os.getuid())
    sc.snapshot(0.0)
    if not any(p for _, p in sc._fds.values()):
        pytest.skip("keine DRM-fds in /proc")
    times = []
    for i in range(1, 6):
        t = time.process_time()
        sc.snapshot(float(i))
        times.append(time.process_time() - t)
    assert statistics.median(times) < 0.015


def test_scanner_pid_reuse_by_other_user_not_counted(tmp_path):
    proc = tmp_path / "proc"
    add_client(proc, 100, 10, info(ns=1))
    sc = scanner(tmp_path)
    assert "i915" in sc.snapshot(0)
    shutil.rmtree(proc / "100")
    add_client(proc, 100, 10, info(cid=9, ns=1), uid=os.getuid() + 1, start=2)
    assert sc.snapshot(1) == {}  # kein Voll-Scan, aber Startzeit hat sich geändert


def test_scanner_pid_reuse_by_own_process_is_rescanned(tmp_path):
    proc = tmp_path / "proc"
    add_client(proc, 100, 10, info(ns=1))
    sc = scanner(tmp_path)
    sc.snapshot(0)
    shutil.rmtree(proc / "100")
    add_client(proc, 100, 12, info(cid=9, ns=1), start=2)
    assert list(sc.snapshot(1)["i915"]) == ["9"]


def test_scanner_full_relist_after_interval(tmp_path):
    proc = tmp_path / "proc"
    add_client(proc, 100, 10, info(ns=1))
    add_client(proc, 100, 11, info(cid=8, ns=1))
    sc = scanner(tmp_path)
    assert sorted(sc.snapshot(0)["i915"]) == ["7", "8"]
    add_client(proc, 100, 12, info(cid=9, ns=1))  # neuer fd in bekanntem Prozess
    os.remove(proc / "100/fd/11")  # fd geschlossen, fdinfo-Datei bleibt (veralteter Cache)
    assert sorted(sc.snapshot(9.9)["i915"]) == ["7", "8"]  # noch kein Voll-Scan
    assert sorted(sc.snapshot(10.0)["i915"]) == ["7", "9"]


def test_scanner_clock_backwards_forces_relist(tmp_path):
    proc = tmp_path / "proc"
    add_client(proc, 100, 10, info(ns=1))
    sc = scanner(tmp_path)
    sc.snapshot(100.0)
    add_client(proc, 100, 12, info(cid=9, ns=1))
    assert sorted(sc.snapshot(50.0)["i915"]) == ["7", "9"]


def test_pci_hex_device_number(tree_copy):
    root = tree_copy(INTEL)
    dev = f"{root}/sys/class/drm/card1/device"
    shutil.rmtree(dev)
    os.makedirs(f"{root}/sys/devices/0000:0a:1f.0")
    os.symlink("../../../devices/0000:0a:1f.0", dev)
    assert gpu(root, "card1").pci == "0000:0a:1f.0"
