# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import shutil

from orbitop.gpu import GpuReader, discover_gpus, fdinfo_busy
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
    (open(f"{root}/sys/class/drm/card1/device/product_name", "w")).write("Iris Xe\n")
    os.makedirs(f"{root}/sys/class/drm/card1-DP-1")
    gpus = discover_gpus(root)
    assert [(g.card, g.name) for g in gpus] == [("card1", "Iris Xe")]


def test_amdgpu_sample():
    amd0 = gpu(AMD, "card0")
    s = GpuReader(AMD, amd0).read(0)
    assert (s.busy, s.busy_scope, s.freq_mhz, s.power_w) == (37.0, "global", 1850.0, 45.0)
    assert s.temp_c == 61.0 and s.freq_max_mhz == 2400.0
    assert s.vram_total > 0 and s.vram_used is not None


def test_amdgpu_sclk_without_star_and_power_fallback(tree_copy):
    root = tree_copy(AMD)
    dev = f"{root}/sys/class/drm/card0/device"
    open(f"{dev}/pp_dpm_sclk", "w").write("0: 500Mhz\n1: 1850Mhz\n")
    hw = f"{dev}/hwmon/hwmon5"
    os.remove(f"{hw}/power1_average")
    open(f"{hw}/power1_input", "w").write("7000000\n")
    s = GpuReader(root, gpu(root, "card0")).read(0)
    assert s.freq_mhz is None and s.power_w == 7.0


def test_amdgpu_card_vanished(tree_copy):
    root = tree_copy(AMD)
    reader = GpuReader(root, gpu(root, "card0"))
    shutil.rmtree(f"{root}/sys/class/drm/card0")
    s = reader.read(0)
    assert (s.busy, s.busy_scope, s.freq_mhz, s.power_w, s.temp_c) == (None,) * 5


def test_intel_freq_without_tools():
    s = GpuReader(INTEL, gpu(INTEL, "card1")).read(0)
    assert s.freq_mhz is not None and s.busy_scope in ("own", None)
    assert s.freq_max_mhz == 1150.0


def test_intel_tools_preferred():
    tools = FakeTools(intel={"busy": 12.5, "freq_mhz": 800.0, "gpu_w": 3.5, "pkg_w": 9.0})
    s = GpuReader(INTEL, gpu(INTEL, "card1"), tools).read(0)
    assert (s.busy, s.busy_scope, s.freq_mhz, s.power_w) == (12.5, "global", 800.0, 3.5)
    assert tools.calls == [("intel", "card1")]


def test_xe_freq(tree_copy):
    root = tree_copy(INTEL)
    dev = f"{root}/sys/class/drm/card1/device"
    os.remove(f"{dev}/driver")
    os.symlink("../../../bus/pci/drivers/xe", f"{dev}/driver")
    os.makedirs(f"{dev}/tile0/gt0/freq0")
    open(f"{dev}/tile0/gt0/freq0/act_freq", "w").write("650\n")
    open(f"{dev}/tile0/gt0/freq0/max_freq", "w").write("1300\n")
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
                              "freq_max_mhz": 2700.0, "fan_pct": 40.0})
    r = GpuReader(AMD, nv1, tools)
    s = r.read(0)
    assert tools.calls == [("nvidia", "0000:01:00.0")]
    assert (s.busy, s.busy_scope, s.temp_c, s.power_w, s.freq_max_mhz) == (80.0, "global", 55.0, 120.0, 2700.0)
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
    open(f"{d}/cur_freq", "w").write("300000000\n")
    open(f"{d}/max_freq", "w").write("600000000\n")
    s = GpuReader(root, gpu(root, "card0")).read(0)
    assert (s.freq_mhz, s.freq_max_mhz) == (300.0, 600.0)


def make_fdinfo(proc, pid, uid, files):
    p = proc / str(pid)
    (p / "fdinfo").mkdir(parents=True)
    (p / "status").write_text(f"Name:\tx\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
    for i, (cid, drv, render) in enumerate(files):
        (p / "fdinfo" / str(10 + i)).write_text(
            f"pos:\t0\ndrm-driver:\t{drv}\ndrm-client-id:\t{cid}\n"
            f"drm-engine-Render:\t{render} ns\ndrm-engine-capacity-render:\t1\n")


def test_fdinfo_dedupes_client_ids(tmp_path):
    proc = tmp_path / "proc"
    uid = os.getuid()
    make_fdinfo(proc, 100, uid, [(7, "i915", 1_000_000), (7, "i915", 1_000_000)])
    make_fdinfo(proc, 101, uid, [(8, "i915", 2_000_000), (9, "xe", 500)])
    make_fdinfo(proc, 102, uid + 1, [(10, "i915", 9_000_000)])  # fremder Prozess
    assert fdinfo_busy(str(tmp_path), "i915", uid) == {"render": 3_000_000}


def test_fdinfo_skips_unreadable_and_foreign(tmp_path):
    proc = tmp_path / "proc"
    (proc / "5").mkdir(parents=True)  # ohne status
    (proc / "6" / "fdinfo").mkdir(parents=True)
    (proc / "6" / "status").write_text("Uid:\tbroken\n")
    assert fdinfo_busy(str(tmp_path), "i915", os.getuid()) == {}
    assert fdinfo_busy(str(tmp_path / "nope"), "i915", os.getuid()) == {}


def test_own_busy_delta_throttle_and_gap(tmp_path):
    root = str(tmp_path)
    uid = os.getuid()
    make_fdinfo(tmp_path / "proc", 100, uid, [(7, "i915", 0)])
    f = tmp_path / "proc/100/fdinfo/10"

    def set_ns(ns):
        f.write_text(f"drm-driver:\ti915\ndrm-client-id:\t7\ndrm-engine-render:\t{ns} ns\n")

    r = GpuReader(root, gpu(INTEL, "card1"))
    assert r._own_busy(0.0) is None  # kein Vorgänger
    set_ns(1_000_000_000)
    assert r._own_busy(1.0) is None  # gedrosselt, kein neuer Wert
    assert r._own_busy(2.0) == 50.0  # 1 s Last in 2 s
    set_ns(9_000_000_000)
    assert r._own_busy(3.0) == 50.0  # gedrosselt: letzter Wert
    assert r._own_busy(4.0) == 100.0  # begrenzt
    set_ns(1)
    assert r._own_busy(6.0) is None  # Zähler gefallen
    set_ns(2_000_000_000)
    assert r._own_busy(20.0) is None  # dt > MAX_DT
    assert r._own_busy(22.0) == 0.0  # nichts verändert
