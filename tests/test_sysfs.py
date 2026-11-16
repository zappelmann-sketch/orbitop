# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
from orbitop import sysfs


def test_read_int_missing_returns_none(tmp_path):
    assert sysfs.read_int(str(tmp_path / "nope")) is None


def test_read_str_strips(tmp_path):
    (tmp_path / "f").write_text("coretemp\n")
    assert sysfs.read_str(str(tmp_path / "f")) == "coretemp"


def test_glob_natural_order(tmp_path):
    for n in ("hwmon10", "hwmon2", "hwmon1"):
        (tmp_path / "sys/class/hwmon" / n).mkdir(parents=True)
    names = [p.rsplit("/", 1)[1] for p in sysfs.glob(str(tmp_path), "/sys/class/hwmon/hwmon*")]
    assert names == ["hwmon1", "hwmon2", "hwmon10"]


def test_link_name_dangling(tmp_path):
    (tmp_path / "driver").symlink_to("../../bus/pci/drivers/amdgpu")
    assert sysfs.link_name(str(tmp_path / "driver")) == "amdgpu"
