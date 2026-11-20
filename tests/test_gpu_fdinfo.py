# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Eigene GPU-Last über /proc/<pid>/fdinfo: FdinfoScanner und GpuReader._own_busy."""
import os
import shutil
import statistics
import time

import pytest

from orbitop import gpu as gpumod
from orbitop.gpu import FdinfoScanner, GpuReader, discover_gpus
from tests.roots import INTEL


def gpu(root, card):
    return next(g for g in discover_gpus(root) if g.card == card)


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
