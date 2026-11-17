# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
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
    assert d[0].rx_bps is None and d[0].rx_total > 0 and d[0].up is True and d[1].up is False


def test_net_up_from_operstate():
    assert [(d.name, d.up) for d in NetReader(INTEL).read(0)] == [("enp0s31f6", False), ("wlp2s0", True)]


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


def mk(root, *dirs, **files):
    for d in dirs:
        os.makedirs(f"{root}/{d}", exist_ok=True)
    for name, text in files.items():
        p = f"{root}/{name.replace('__', '/')}"
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)


def mk_disks(root, disks, mounts, dm=()):
    """disks: Name -> Partitionen (alle mit device); dm: (dm-N, mapper-Name, [Slaves])."""
    stats = ""
    for d, parts in disks.items():
        mk(root, f"sys/block/{d}/device", **{f"sys/block/{d}/device/model": d})
        for p in parts:
            mk(root, f"sys/block/{d}/{p}")
        stats += f"8 0 {d} 1 0 8 1 1 0 8 1 0 1 1\n"
    for n, name, slaves in dm:
        mk(root, f"sys/block/{n}/slaves", **{f"sys/block/{n}/dm/name": name + "\n"})
        for sl in slaves:
            mk(root, f"sys/block/{n}/slaves/{sl}")
    mk(root, **{"proc/diskstats": stats, "proc/mounts": "".join(f"{s} {m} ext4 rw 0 0\n" for s, m in mounts)})


def sized(root):
    return {d.name: (d.used, d.size) for d in DiskReader(root, statvfs=fake_statvfs).read(0)}


ONE = (600 * 4096, 1000 * 4096)  # fake_statvfs: belegt und Größe je Dateisystem


def test_net_filter_regex_alone_excludes(tmp_path):
    root = str(tmp_path)
    mk(root, "sys/class/net/docker0/device", "sys/class/net/eth9", "sys/class/net/enp1/device", "sys/class/net/tun0/device",
       **{"proc/net/dev": HEADER + "".join(f"{n}: 1 1 0 0 0 0 0 0 1 1 0 0 0 0 0 0\n" for n in ("docker0", "eth9", "enp1", "tun0"))})
    assert names(NetReader(root).read(0)) == ["enp1"]


def test_disk_filter_regex_and_device_check(tmp_path):
    root = str(tmp_path)
    mk_disks(root, {"sr0": [], "zram0": [], "loop3": [], "sda": []}, [])
    mk(root, "sys/block/vdz")  # harmlos benannt, aber ohne device
    with open(f"{root}/proc/diskstats", "a") as f:
        f.write("8 0 vdz 1 0 8 1 1 0 8 1 0 1 1\n")
    assert names(DiskReader(root, statvfs=fake_statvfs).read(0)) == ["sda"]


def test_disk_sibling_names_do_not_mix(tmp_path):
    root = str(tmp_path)
    mk_disks(root, {"nvme0n1": ["nvme0n1p1"], "nvme0n10": ["nvme0n10p1", "nvme0n10p2"], "sda": ["sda1"], "sdaa": ["sdaa1"]},
             [("/dev/nvme0n1p1", "/a"), ("/dev/nvme0n10p1", "/b"), ("/dev/nvme0n10p2", "/c"), ("/dev/sda1", "/d"),
              ("/dev/sdaa1", "/e"), ("/dev/sdaa1", "/f")])
    got = sized(root)
    assert got["nvme0n1"] == ONE and got["nvme0n10"] == (2 * ONE[0], 2 * ONE[1])
    assert got["sda"] == ONE and got["sdaa"] == ONE


def test_disk_whole_disk_mount(tmp_path):
    root = str(tmp_path)
    mk_disks(root, {"sdb": [], "sdc": []}, [("/dev/sdb", "/mnt")])
    assert sized(root) == {"sdb": ONE, "sdc": (None, None)}


@pytest.mark.parametrize("bad", ["/dev/.", "/dev/..", "/dev/\\056\\056", "/dev/\\056", "/dev/\\000", "/dev/mapper/.."])
def test_disk_dot_sources_ignored(tmp_path, bad):
    root = str(tmp_path)
    mk_disks(root, {"sda": ["sda1"], "sdb": []}, [("/dev/sda1", "/"), (bad, "/evil")], dm=[("dm-0", "x", [])])
    assert os.path.exists(f"{root}/sys/block/sda/..")  # nur die Sperre verhindert den Treffer
    assert sized(root) == {"sda": ONE, "sdb": (None, None)}


def test_disk_skips_fuse_mounts_with_device_names(tmp_path):  # fsname=/dev/… legt jeder User mit fusermount an
    root = str(tmp_path)
    mk_disks(root, {"sda": ["sda1"], "sdb": ["sdb1"]}, [])
    mk(root, **{"proc/mounts": "/dev/sda1 /home/u/fake fuse.evil rw 0 0\n/dev/sda1 / ext4 rw 0 0\n"
                               "/dev/sdb1 /home/u/m fuse.evil rw 0 0\n"})
    seen = []
    got = {d.name: (d.used, d.size) for d in DiskReader(root, statvfs=lambda p: seen.append(p) or fake_statvfs(p)).read(0)}
    assert got == {"sda": ONE, "sdb": (None, None)} and seen == ["/"]


def test_disk_skips_plain_fuse_type(tmp_path):  # fusermount legt je nach Aufruf den Typ "fuse" ohne Untertyp an
    root = str(tmp_path)
    mk_disks(root, {"sda": ["sda1"], "sdb": ["sdb1"]}, [])
    mk(root, **{"proc/mounts": "/dev/sda1 /home/u/fake fuse rw 0 0\n/dev/sda1 / ext4 rw 0 0\n"
                               "/dev/sdb1 /home/u/m fuse rw 0 0\n"})
    seen = []
    got = {d.name: (d.used, d.size) for d in DiskReader(root, statvfs=lambda p: seen.append(p) or fake_statvfs(p)).read(0)}
    assert got == {"sda": ONE, "sdb": (None, None)} and seen == ["/"]


def test_disk_luks(tmp_path):
    root = str(tmp_path)
    mk_disks(root, {"nvme0n1": ["nvme0n1p3"]}, [("/dev/mapper/nvme0n1p3_crypt", "/")],
             dm=[("dm-0", "nvme0n1p3_crypt", ["nvme0n1p3"])])
    assert sized(root) == {"nvme0n1": ONE}


def test_disk_luks_lvm(tmp_path):
    root = str(tmp_path)
    mk_disks(root, {"nvme0n1": ["nvme0n1p3"], "sda": ["sda1"]},
             [("/dev/mapper/vg-root", "/"), ("/dev/mapper/vg-home", "/home"), ("/dev/dm-2", "/bind"),
              ("/dev/mapper/vg-root", "/bind2"), ("/dev/sda1", "/mnt")],
             dm=[("dm-0", "crypt", ["nvme0n1p3"]), ("dm-1", "vg-root", ["dm-0"]), ("dm-2", "vg-home", ["dm-0"])])
    assert sized(root) == {"nvme0n1": (2 * ONE[0], 2 * ONE[1]), "sda": ONE}


def test_disk_dm_cycle_and_depth_are_safe(tmp_path):
    root = str(tmp_path)
    mk_disks(root, {"sda": ["sda1"]}, [("/dev/mapper/a", "/"), ("/dev/mapper/e", "/e")],
             dm=[("dm-0", "a", ["dm-1"]), ("dm-1", "b", ["dm-0"]),
                 ("dm-2", "e", ["dm-3"]), ("dm-3", "f", ["dm-4"]), ("dm-4", "g", ["dm-5"]), ("dm-5", "h", ["dm-6"]),
                 ("dm-6", "i", ["sda1"])])
    assert sized(root) == {"sda": (None, None)}


def test_disk_model_cached(tmp_path):
    root = str(tmp_path)
    mk_disks(root, {"sda": []}, [])
    r = DiskReader(root, statvfs=fake_statvfs)
    assert r.read(0)[0].model == "sda"
    os.remove(f"{root}/sys/block/sda/device/model")
    assert r.read(1)[0].model == "sda"
