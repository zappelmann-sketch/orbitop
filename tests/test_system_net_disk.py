# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import shutil
from types import SimpleNamespace

import pytest

from orbitop.system import DiskReader, NetReader
from tests.roots import AMD, ARM, INTEL, VM

HEADER = (
    "Inter-|   Receive |  Transmit\n face |bytes packets errs drop fifo frame compressed multicast"
    "|bytes packets errs drop fifo colls carrier compressed\n"
)


def write_net(root, counters):
    rows = "".join(f"{n}: {rx} 1 0 0 0 0 0 0 {tx} 1 0 0 0 0 0 0\n" for n, (rx, tx) in counters.items())
    with open(f"{root}/proc/net/dev", "w") as f:
        f.write(HEADER + rows)


def write_disk(root, name, rs, ws):
    with open(f"{root}/proc/diskstats", "w") as f:
        f.write(f"   8 0 {name} 1 0 {rs} 1 1 0 {ws} 1 0 1 1\n")


def fake_statvfs(point):
    return SimpleNamespace(f_blocks=1000, f_bfree=400, f_frsize=4096)


def names(devs):
    return [d.name for d in devs]


def test_net_excludes_virtual():
    assert names(NetReader(AMD).read(0)) == ["enp5s0"]
    assert names(NetReader(INTEL).read(0)) == ["enp0s31f6", "wlp2s0"]
    assert names(NetReader(VM).read(0)) == ["ens3"]


def test_net_totals_up_and_first_rate_none():
    d = NetReader(ARM).read(0)
    assert names(d) == ["eth0", "wlan0"]
    assert d[0].rx_bps is None and d[0].rx_total > 0 and isinstance(d[0].up, bool)


def test_net_rates(tree_copy):
    root = tree_copy(ARM)
    r = NetReader(root)
    write_net(root, {"eth0": (1000, 0), "wlan0": (0, 0)})
    r.read(0)
    write_net(root, {"eth0": (3000, 500), "wlan0": (0, 0)})
    d = r.read(2)[0]
    assert d.rx_bps == pytest.approx(1000.0) and d.tx_bps == pytest.approx(250.0)
    assert (d.rx_total, d.tx_total) == (3000, 500)


@pytest.mark.parametrize("t", [0, -1, 6])
def test_net_bad_dt_gives_gap(tree_copy, t):
    root = tree_copy(ARM)
    r = NetReader(root)
    r.read(0)
    assert r.read(t)[0].rx_bps is None


def test_net_counter_decrease_gives_gap(tree_copy):
    root = tree_copy(ARM)
    r = NetReader(root)
    write_net(root, {"eth0": (5000, 5000), "wlan0": (0, 0)})
    r.read(0)
    write_net(root, {"eth0": (10, 6000), "wlan0": (0, 0)})
    d = r.read(1)[0]
    assert d.rx_bps is None and d.tx_bps == pytest.approx(1000.0)


def test_net_interface_removed_and_added_between_reads(tree_copy):
    root = tree_copy(ARM)
    r = NetReader(root)
    r.read(0)
    shutil.rmtree(f"{root}/sys/class/net/wlan0")
    assert names(r.read(1)) == ["eth0"]
    shutil.copytree(ARM + "/sys/class/net/wlan0", f"{root}/sys/class/net/wlan0", symlinks=True)
    d = r.read(2)
    assert names(d) == ["eth0", "wlan0"] and d[1].rx_bps is None


def test_net_malformed_lines(tree_copy):
    root = tree_copy(ARM)
    with open(f"{root}/proc/net/dev", "w") as f:
        f.write(HEADER + "garbage\n eth0: x y\nwlan0: 1 2\n" + "eth0: 7 1 0 0 0 0 0 0 9 1 0 0 0 0 0 0\n")
    d = NetReader(root).read(0)
    assert names(d) == ["eth0"] and (d[0].rx_total, d[0].tx_total) == (7, 9)


def test_net_missing_files(tree_copy):
    root = tree_copy(ARM)
    shutil.rmtree(f"{root}/proc/net")
    assert NetReader(root).read(0) == []


def test_disk_excludes_partitions_and_loop():
    assert names(DiskReader(ARM, statvfs=fake_statvfs).read(0)) == ["mmcblk0"]
    assert names(DiskReader(INTEL, statvfs=fake_statvfs).read(0)) == ["nvme0n1", "sda"]


def test_disk_model():
    assert DiskReader(INTEL, statvfs=fake_statvfs).read(0)[0].model == "Micron 2300 NVMe 1024GB"
    assert DiskReader(INTEL, statvfs=fake_statvfs).read(0)[0].temp_c is None


def test_disk_usage_dedupes_bind_mounts():
    d = DiskReader(INTEL, statvfs=fake_statvfs).read(0)[0]
    # p3, p4, p1, p5 (p5 zweimal gemountet, einmal gezählt)
    assert d.used == 4 * 600 * 4096 and d.size == 4 * 1000 * 4096


def test_disk_without_mounts_has_no_usage():
    sda = DiskReader(INTEL, statvfs=fake_statvfs).read(0)[1]
    assert sda.name == "sda" and sda.used is None and sda.size is None


def test_disk_statvfs_oserror_skips_mount():
    def flaky(point):
        if point == "/data":
            raise OSError("weg")
        return fake_statvfs(point)
    d = DiskReader(INTEL, statvfs=flaky).read(0)[0]
    assert d.used == 3 * 600 * 4096 and d.size == 3 * 1000 * 4096


def test_disk_all_statvfs_fail_is_none():
    def boom(point):
        raise OSError("weg")
    d = DiskReader(INTEL, statvfs=boom).read(0)[0]
    assert d.used is None and d.size is None


def test_disk_bind_mount_falls_back_to_second_point():
    def flaky(point):
        if point == "/data/workspace":
            raise OSError("weg")
        return fake_statvfs(point)
    assert DiskReader(INTEL, statvfs=flaky).read(0)[0].size == 4 * 1000 * 4096


def test_disk_rates(tree_copy):
    root = tree_copy(ARM)
    r = DiskReader(root, statvfs=fake_statvfs)
    write_disk(root, "mmcblk0", 100, 200)
    r.read(0)
    write_disk(root, "mmcblk0", 300, 600)
    d = r.read(2)[0]
    assert d.read_bps == pytest.approx(200 * 512 / 2) and d.write_bps == pytest.approx(400 * 512 / 2)


def test_counter_decrease_gives_gap(tree_copy):
    root = tree_copy(ARM)
    r = DiskReader(root, statvfs=fake_statvfs)
    write_disk(root, "mmcblk0", 100, 200)
    r.read(0)
    write_disk(root, "mmcblk0", 50, 300)
    d = r.read(1)[0]
    assert d.read_bps is None and d.write_bps == pytest.approx(100 * 512)


@pytest.mark.parametrize("t", [0, -1, 6])
def test_disk_bad_dt_gives_gap(tree_copy, t):
    root = tree_copy(ARM)
    r = DiskReader(root, statvfs=fake_statvfs)
    r.read(0)
    d = r.read(t)[0]
    assert d.read_bps is None and d.write_bps is None


def test_disk_removed_and_added_between_reads(tree_copy):
    root = tree_copy(INTEL)
    r = DiskReader(root, statvfs=fake_statvfs)
    r.read(0)
    shutil.rmtree(f"{root}/sys/block/sda")
    assert names(r.read(1)) == ["nvme0n1"]
    shutil.copytree(INTEL + "/sys/block/sda", f"{root}/sys/block/sda", symlinks=True)
    d = r.read(2)
    assert names(d) == ["nvme0n1", "sda"] and d[1].read_bps is None


def test_disk_malformed_diskstats_and_mounts(tree_copy):
    root = tree_copy(ARM)
    with open(f"{root}/proc/diskstats", "w") as f:
        f.write("junk\n 1 2 mmcblk0 a b c\n 179 0 mmcblk0 1 0 8 1 1 0 8 1 0 1 1\n")
    with open(f"{root}/proc/mounts", "w") as f:
        f.write("/dev/my\\040disk /mnt/a\\040b ext4 rw 0 0\n/dev/ /x ext4 0 0\n/dev/../etc /y x 0 0\n/dev/mmcblk0p1\nnone /z tmpfs rw 0 0\n")
    d = DiskReader(root, statvfs=fake_statvfs).read(0)
    assert names(d) == ["mmcblk0"] and d[0].used is None


def test_disk_escaped_mount_point_is_unescaped(tree_copy):
    root = tree_copy(ARM)
    with open(f"{root}/proc/mounts", "w") as f:
        f.write("/dev/mmcblk0p1 /mnt/a\\040b ext4 rw 0 0\n")
    seen = []
    DiskReader(root, statvfs=lambda p: seen.append(p) or fake_statvfs(p)).read(0)
    assert seen == ["/mnt/a b"]
