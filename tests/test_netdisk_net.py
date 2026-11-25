# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""NetReader: Raten, Filter, Lücken und kaputte Eingaben."""
import shutil

import pytest

from orbitop.netdisk import NetReader
from tests.netdisk_helpers import HEADER, mk, names, write_net
from tests.roots import AMD, ARM, INTEL, VM


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


def test_net_filter_regex_alone_excludes(tmp_path):
    root = str(tmp_path)
    mk(root, "sys/class/net/docker0/device", "sys/class/net/eth9", "sys/class/net/enp1/device", "sys/class/net/tun0/device",
       **{"proc/net/dev": HEADER + "".join(f"{n}: 1 1 0 0 0 0 0 0 1 1 0 0 0 0 0 0\n" for n in ("docker0", "eth9", "enp1", "tun0"))})
    assert names(NetReader(root).read(0)) == ["enp1"]
