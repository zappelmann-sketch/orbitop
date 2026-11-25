# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Testbäume und Stellvertreter für orbitop.netdisk (Netz und Datenträger)."""
import os
from types import SimpleNamespace

from orbitop.netdisk import DiskReader


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
