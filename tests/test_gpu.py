# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""GPU-Erkennung und Leser je Treiber (sysfs, devfreq, Werkzeuge)."""
import os
import shutil
from pathlib import Path

import pytest

from orbitop.gpu import GpuReader, GpuSample, discover_gpus
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


@pytest.mark.parametrize("bad", ["00:02.0", "0000:00:02.8", "0000:00:02.9", "0000:00:0A.0", "0000:00:02.0x"])
def test_pci_regex_negatives(tree_copy, bad):
    root = tree_copy(INTEL)
    dev = f"{root}/sys/class/drm/card1/device"
    shutil.rmtree(dev)
    os.makedirs(f"{root}/sys/devices/{bad}")
    os.symlink(f"../../../devices/{bad}", dev)
    assert gpu(root, "card1").pci is None


def test_pci_hex_device_number(tree_copy):
    root = tree_copy(INTEL)
    dev = f"{root}/sys/class/drm/card1/device"
    shutil.rmtree(dev)
    os.makedirs(f"{root}/sys/devices/0000:0a:1f.0")
    os.symlink("../../../devices/0000:0a:1f.0", dev)
    assert gpu(root, "card1").pci == "0000:0a:1f.0"
