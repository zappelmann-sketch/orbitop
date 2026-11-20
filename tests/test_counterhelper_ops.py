# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""counterhelper on, off und sync: Merkdatei, Kettenprüfung, Fähigkeit und RAPL-Rechte (B2.1–B2.3, B2.9)."""
import errno
import os
import stat

import pytest

from orbitop import counterhelper
from orbitop.counterhelper import CAP, MARKER, TOOL, main
from tests.counterhelper_helpers import ZONES, make_tree, marker, modes

XATTR = "security.capability"
ENERGY = [f"/sys/class/powercap/{z}/energy_uj" for z in ZONES]


@pytest.fixture
def osl(tmp_path):
    return make_tree(tmp_path)


def test_on_writes_marker_then_capability_and_read_bits(tmp_path, osl):
    assert main(["on"], osl) == counterhelper.OK
    assert osl.log == [("create", MARKER, 0o644), ("fsync", MARKER), ("fsync", "/etc/orbitop"),
                       ("setxattr", TOOL, CAP), *[("fchmod", p, 0o444) for p in ENERGY]]
    assert marker(tmp_path).read_bytes() == b""
    assert set(modes(tmp_path).values()) == {0o444}


def test_marker_is_created_exclusively_without_following_links(osl):  # R2.2: nur am fd des geprüften Ordners
    main(["on"], osl)
    flags = dict(osl.opens)[MARKER]
    assert flags == os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    assert dict(osl.opens)["/etc/orbitop"] == os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


@pytest.mark.parametrize("word", counterhelper.WORDS)
def test_marker_is_only_reached_through_the_checked_directory_fd(tmp_path, osl, word):  # R2.1, R2.2
    if word != "on":
        marker(tmp_path).touch()
    main([word], osl)
    near = [e for e in osl.at if e[1].endswith("counters-released")]
    assert near and all(e[1:] == ("counters-released", "/etc/orbitop") for e in near), near


def test_tool_and_energy_files_are_opened_without_blocking(osl):  # ein FIFO hielte sonst das Lock (M-5)
    main(["on"], osl)
    flags = dict(osl.opens)
    for path in (TOOL, *ENERGY):
        assert flags[path] == os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, path


def test_existing_marker_is_fine(tmp_path, osl):  # O_EXCL: EEXIST heißt schon an
    marker(tmp_path).touch()
    assert main(["on"], osl) == counterhelper.OK
    assert ("fsync", "/etc/orbitop") in osl.log and ("setxattr", TOOL, CAP) in osl.log


@pytest.mark.parametrize("make", ["symlink", "directory", "foreign"])
def test_on_refuses_a_marker_it_did_not_write(tmp_path, osl, make):  # wie sync: nur eine reguläre Datei von root
    if make == "symlink":
        marker(tmp_path).symlink_to(tmp_path / "victim")
    elif make == "directory":
        marker(tmp_path).mkdir()
    else:
        marker(tmp_path).touch()
        osl.owners[MARKER] = 1000
    assert main(["on"], osl) == counterhelper.UNSAFE
    assert osl.writes() == [] and not (tmp_path / "victim").exists()


def test_off_removes_marker_before_the_effects(tmp_path, osl):  # R1.4: kein Auslöser setzt nach einem Absturz neu
    assert main(["on"], osl) == counterhelper.OK
    osl.log.clear()
    assert main(["off"], osl) == counterhelper.OK
    assert osl.log == [("unlink", MARKER), ("fsync", "/etc/orbitop"), ("removexattr", TOOL),
                       *[("fchmod", p, 0o400) for p in ENERGY]]
    assert not marker(tmp_path).exists() and set(modes(tmp_path).values()) == {0o400}


def test_off_marker_is_gone_even_if_removexattr_fails(tmp_path, osl):
    marker(tmp_path).touch()
    osl.xattrs[TOOL] = {XATTR: CAP}
    osl.fail[("removexattr", TOOL)] = errno.EROFS
    assert main(["off"], osl) == counterhelper.PARTIAL
    assert not marker(tmp_path).exists()
    assert osl.log[:2] == [("unlink", MARKER), ("fsync", "/etc/orbitop")]
    assert set(modes(tmp_path).values()) == {0o400}  # RAPL trotzdem zurückgenommen


def test_off_without_marker_or_capability_is_ok(tmp_path, osl):  # ENOENT und ENODATA heißen schon aus
    assert main(["off"], osl) == counterhelper.OK
    assert ("fsync", "/etc/orbitop") in osl.log


def test_off_removes_a_capability_set_by_hand(osl):  # B2.9: auch eine von Hand gesetzte am festen Pfad
    osl.xattrs[TOOL] = {XATTR: CAP}
    assert main(["off"], osl) == counterhelper.OK
    assert osl.xattrs[TOOL] == {}


def test_off_leaves_etc_udev_alone(tmp_path, osl):  # B2.9: die Handregel bleibt
    rule = tmp_path / "etc/udev/rules.d/70-orbitop-rapl.rules"
    rule.parent.mkdir(parents=True)
    rule.write_text('SUBSYSTEM=="powercap", RUN+="/bin/chmod 0444 /sys%p/energy_uj"\n')
    main(["off"], osl)
    assert rule.exists() and not [e for e in osl.log if e[1].startswith("/etc/udev")]


def test_sync_without_marker_writes_nothing(tmp_path, osl):  # E4: Install und Upgrade geben nie frei
    osl.xattrs[TOOL] = {XATTR: CAP}
    (tmp_path / "sys/class/powercap/intel-rapl:0/energy_uj").chmod(0o444)
    assert main(["sync"], osl) == counterhelper.OK
    assert osl.writes() == []  # sync nimmt auch nie etwas zurück


@pytest.mark.parametrize("make", ["symlink", "directory", "foreign"])
def test_sync_needs_a_regular_root_marker(tmp_path, osl, make):
    if make == "symlink":
        marker(tmp_path).symlink_to(tmp_path / "victim")
        (tmp_path / "victim").touch()
    elif make == "directory":
        marker(tmp_path).mkdir()
    else:
        marker(tmp_path).touch()
        osl.owners[MARKER] = 1000
    assert main(["sync"], osl) == counterhelper.OK
    assert osl.writes() == []


def test_sync_with_marker_applies_everything(tmp_path, osl):
    marker(tmp_path).touch()
    assert main(["sync"], osl) == counterhelper.OK
    assert osl.writes() == [("setxattr", TOOL, CAP), *[("fchmod", p, 0o444) for p in ENERGY]]


def unsafe(tmp_path, osl, make):
    """Ein Glied der Kette von /usr/bin/intel_gpu_top, das root nicht allein gehört, oder ein zweiter harter Link."""
    tool = tmp_path / TOOL.lstrip("/")
    if make == "group_writable":
        tool.chmod(0o775)
    elif make == "other_writable_usr":
        (tmp_path / "usr").chmod(0o757)
    elif make == "foreign_owner":
        osl.owners[TOOL] = 1000
    elif make == "foreign_bin":
        osl.owners["/usr/bin"] = 1000
    elif make == "bin_symlink":  # /usr/bin selbst ein Verweis auf einen Ordner des Benutzers
        os.rename(tmp_path / "usr/bin", tmp_path / "usr/elsewhere")
        (tmp_path / "usr/bin").symlink_to("elsewhere")


@pytest.mark.parametrize("make", ["group_writable", "other_writable_usr", "foreign_owner", "foreign_bin",
                                  "bin_symlink"])
@pytest.mark.parametrize("word", ["on", "off"])
def test_unsafe_chain_writes_no_capability(tmp_path, osl, make, word):  # R1.1, R4.1, R4.6
    unsafe(tmp_path, osl, make)
    osl.xattrs[TOOL] = {XATTR: CAP}
    assert main([word], osl) == counterhelper.UNSAFE
    assert not [e for e in osl.writes() if e[0].endswith("xattr")]
    assert {e[1] for e in osl.writes() if e[0] == "fchmod"} == set(ENERGY)  # RAPL hängt nicht davon ab


def test_hard_link_blocks_setting_but_not_removing(tmp_path, osl):  # R4.6, R13: nlink == 1 nur beim Setzen
    os.link(tmp_path / TOOL.lstrip("/"), tmp_path / "usr/bin/copy")
    assert main(["on"], osl) == counterhelper.UNSAFE
    assert main(["sync"], osl) == counterhelper.UNSAFE  # die Merkdatei steht, der Inode bekommt trotzdem nichts
    assert not [e for e in osl.writes() if e[0] == "setxattr"]
    osl.xattrs[TOOL] = {XATTR: CAP}  # etwa von Hand gesetzt, bevor jemand den Link anlegte
    assert main(["off"], osl) == counterhelper.OK
    assert osl.xattrs[TOOL] == {} and ("removexattr", TOOL) in osl.log


def test_tool_symlink_gives_4_without_capability(tmp_path, osl):  # ELOOP: „nicht unterstützt“, wirkt nicht
    tool = tmp_path / TOOL.lstrip("/")
    tool.unlink()
    tool.symlink_to(os.path.realpath(__file__))
    assert main(["on"], osl) == counterhelper.PARTIAL
    assert not [e for e in osl.writes() if e[0] == "setxattr"] and osl.xattrs == {}


def test_tool_not_a_regular_file_writes_nothing(tmp_path, osl):
    tool = tmp_path / TOOL.lstrip("/")
    tool.unlink()
    tool.mkdir()
    assert main(["on"], osl) == counterhelper.UNSAFE
    assert osl.xattrs == {}


def test_missing_tool_is_fine(tmp_path, osl):  # ENOENT: nicht installiert, die RAPL-Zähler gelten trotzdem
    (tmp_path / TOOL.lstrip("/")).unlink()
    assert main(["on"], osl) == counterhelper.OK
    assert set(modes(tmp_path).values()) == {0o444}


@pytest.mark.parametrize("make", ["missing", "symlink", "file", "group_writable", "readable", "group_readable",
                                  "foreign", "foreign_etc"])
def test_unsafe_marker_directory(tmp_path, osl, make):  # R2.1; lesbar: jedes Konto könnte das Lock halten (I-1)
    d = tmp_path / "etc/orbitop"
    if make in ("missing", "symlink", "file"):
        d.rmdir()
    if make == "symlink":
        (tmp_path / "etc/elsewhere").mkdir()
        d.symlink_to("elsewhere")
    elif make == "file":
        d.touch()
    elif make == "group_writable":
        d.chmod(0o731)
    elif make in ("readable", "group_readable"):
        d.chmod(0o755 if make == "readable" else 0o741)
    elif make == "foreign":
        osl.owners["/etc/orbitop"] = 1000
    elif make == "foreign_etc":
        osl.owners["/etc"] = 1000
    osl.xattrs[TOOL] = {XATTR: CAP}
    assert main(["on"], osl) == counterhelper.UNSAFE
    assert main(["sync"], osl) == counterhelper.UNSAFE
    assert osl.writes() == []
    assert main(["off"], osl) == counterhelper.UNSAFE  # nimmt die Wirkungen trotzdem zurück
    assert osl.writes() == [("removexattr", TOOL), *[("fchmod", p, 0o400) for p in ENERGY]]


@pytest.mark.parametrize("start, on, off", [(stat.S_IFREG | 0o400, 0o444, 0o400), (0o600, 0o644, 0o600),
                                            (0o444, 0o444, 0o400), (0o640, 0o644, 0o600)])
def test_mode_keeps_only_permission_bits(tmp_path, osl, start, on, off):  # R3.3: symbolisch, nie absolut
    (tmp_path / "sys/class/powercap/intel-rapl:0/energy_uj").chmod(stat.S_IMODE(start))
    main(["on"], osl)
    main(["off"], osl)
    calls = [e[2] for e in osl.log if e[:2] == ("fchmod", ENERGY[0])]
    assert calls == [on, off] and all(m == stat.S_IMODE(m) for m in calls)


def test_read_only_sys_gives_4_and_still_sets_the_capability(osl):  # wie im Container: /sys nur lesbar
    for p in ENERGY:
        osl.fail[("fchmod", p)] = errno.EROFS
    assert main(["on"], osl) == counterhelper.PARTIAL
    assert osl.xattrs == {TOOL: {XATTR: CAP}}


@pytest.mark.parametrize("fixture, opened", [
    ("intel-laptop", ["intel-rapl:0", "intel-rapl:0:0", "intel-rapl:0:1", "intel-rapl:0:2", "intel-rapl:1"]),
    ("amd-desktop", ["intel-rapl:0"])])  # AMD Zen erscheint über intel_rapl_msr ebenfalls als intel-rapl:*
def test_only_intel_rapl_zones_change(tmp_path, fixture, opened):  # R3.4: MMIO bleibt zu; TPMI heißt intel-rapl:*
    osl = make_tree(tmp_path, powercap=fixture)
    before = modes(tmp_path)
    assert main(["on"], osl) == counterhelper.OK
    after = modes(tmp_path)
    assert sorted(z for z in before if after[z] != before[z]) == opened
    assert all(after[z] == 0o444 for z in opened)
    assert main(["off"], osl) == counterhelper.OK
    assert modes(tmp_path) == before
