# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Zustand der Freigabe ohne root (Security-Dokument 0.3.0, B2.5, B2.2 „Lesen in der App“, B2.9 „Erkennen“).

Testbaum aus counterhelper_helpers.make_tree; gefälscht sind nur uid 0 (lstat) und security.capability, weil beides
ohne root nicht anzulegen ist. Kein Aufruf schreibt; nur der letzte Test liest das echte /, und nur lesend."""
import builtins
import errno
import os
import struct
from types import SimpleNamespace

import pytest

from orbitop import counters
from orbitop.counterhelper import CAP, MARKER, TOOL
from tests.counterhelper_helpers import make_tree

SYS_ADMIN = struct.pack("<5I", 0x02000001, 1 << 21, 0, 0, 0)
FOREIGN_V3 = struct.pack("<I", 0x03000001) + CAP[4:] + struct.pack("<I", 1000)  # v3, rootid 1000
STATES = {"works", "missing", "broken", "manual", "none"}


@pytest.fixture
def root(tmp_path):
    make_tree(tmp_path)
    return tmp_path


def at(root, path):
    return root / path.lstrip("/")


def release(root):
    at(root, MARKER).write_bytes(b"")
    at(root, MARKER).chmod(0o644)


def zones(root, *modes):
    """modes je Zone in sortierter Reihenfolge; ein einzelner Modus gilt für alle."""
    files = sorted(at(root, "/sys/class/powercap").glob("intel-rapl:*/energy_uj"))
    for f, m in zip(files, modes * len(files) if len(modes) == 1 else modes, strict=True):
        f.chmod(m)


def read(root, intel=True, caps=None, owners=None):
    """counters.state über dem Testbaum. caps: logischer Pfad -> Bytes von security.capability; owners: logischer
    Pfad -> uid, sonst gehört jede Datei root."""
    caps, owners, base = caps or {}, owners or {}, str(root)

    def getxattr(path, name, *, follow_symlinks=True):
        assert path.startswith(base + "/") and name == "security.capability" and follow_symlinks is False
        if path[len(base):] in caps:
            return caps[path[len(base):]]
        raise OSError(errno.ENODATA, os.strerror(errno.ENODATA), path)

    def lstat(path):
        assert path.startswith(base + "/")
        st = os.lstat(path)
        return SimpleNamespace(st_mode=st.st_mode, st_uid=owners.get(path[len(base):], 0))
    return counters.state(base, intel, getxattr, lstat)


def part(result, name):
    return next(p["state"] for p in result["parts"] if p["part"] == name)


# ---- Zustandstabelle B2.5, perfmon ----
def _tool(root, kind):
    tool = at(root, TOOL)
    if kind == "missing":
        tool.unlink()
    elif kind == "symlink":  # ELOOP im Helfer: ein Symlink am festen Pfad wird nie behandelt
        tool.rename(tool.with_name("real_tool"))
        tool.symlink_to("real_tool")
    return {"perfmon": {TOOL: CAP}, "sysadmin": {TOOL: SYS_ADMIN}, "foreign_v3": {TOOL: FOREIGN_V3},
            "symlink": {TOOL: CAP, "/usr/bin/real_tool": CAP}}.get(kind, {})


@pytest.mark.parametrize("marker,kind,want", [
    (True, "perfmon", "works"),        # Merkdatei, Fähigkeit am festen Pfad: an, „wirkt“
    (True, "missing", "missing"),      # Werkzeug fehlt: „intel_gpu_top ist nicht installiert“
    (True, "nocap", "broken"),         # Werkzeug da, Fähigkeit fehlt: „wirkt nicht“
    (True, "sysadmin", "broken"),      # cap_sys_admin setzt der Helfer nie
    (True, "foreign_v3", "broken"),    # v3 mit rootid 1000 wirkt im Init-Namespace nicht
    (True, "symlink", "broken"),       # Pfad ist ein Symlink (ELOOP), auch wenn das Ziel die Fähigkeit hat
    (False, "perfmon", "manual"),      # keine Merkdatei, aber Wirkung: „von Hand freigegeben“ (B2.9)
    (False, "sysadmin", "manual"),     # für „von Hand“ zählt zusätzlich Bit 21
    (False, "nocap", "none"),
    (False, "foreign_v3", "none"),
    (False, "missing", "missing"),    # „nicht installiert“ auch bei aus: der Schalter wirkte hier nicht (Q2, C1)
    (False, "symlink", "none"),
])
def test_state_table_perfmon(root, marker, kind, want):
    caps = _tool(root, kind)
    if marker:
        release(root)
    got = read(root, caps=caps)
    assert got["marker"] == ("on" if marker else "off") and part(got, "perfmon") == want


# ---- Zustandstabelle B2.5, RAPL: an heißt alle Zonen o+r ----
@pytest.mark.parametrize("marker,modes,want", [
    (True, (0o444,), "works"),
    (True, (0o404,), "works"),                 # o+r genügt, so liest jedes Konto
    (True, (0o440,), "broken"),                # nur g+r: andere Konten lesen nicht
    (True, (0o400,), "broken"),                # Zonen nicht lesbar: „wirkt nicht“
    (True, (0o444, 0o400, 0o444), "broken"),   # eine Zone fehlt in der Freigabe
    (False, (0o444,), "manual"),
    (False, (0o444, 0o400, 0o444), "manual"),  # auch ein Teil der Zonen ist eine Freigabe
    (False, (0o400,), "none"),
])
def test_state_table_rapl(root, marker, modes, want):
    zones(root, *modes)
    if marker:
        release(root)
    assert part(read(root), "rapl") == want


@pytest.mark.parametrize("marker", ["on", "off", "unclear"])
def test_rapl_without_zones_is_missing(tmp_path, marker):
    """Q2: rapl steht immer in parts, ohne Zonen mit missing („keine Energiezähler“), bei jeder Merkdatei."""
    make_tree(tmp_path, zones=())
    if marker != "off":
        release(tmp_path)
    if marker == "unclear":
        at(tmp_path, MARKER).parent.chmod(0o755)
    got = read(tmp_path)
    assert got["marker"] == marker and part(got, "rapl") == "missing"


def test_only_intel_rapl_zones_count(tmp_path):
    """Genau die Menge von sensors.RaplReader und counterhelper.RAPL: intel-rapl-mmio:* bleibt 0400 und zählt nicht."""
    make_tree(tmp_path, powercap="intel-laptop")
    zones(tmp_path, 0o444)
    release(tmp_path)
    assert (tmp_path / "sys/class/powercap/intel-rapl-mmio:0/energy_uj").stat().st_mode & 0o777 == 0o400
    assert part(read(tmp_path), "rapl") == "works"


def test_symlinked_energy_uj_is_not_readable(root):
    zones(root, 0o444)
    release(root)
    f = root / "sys/class/powercap/intel-rapl:1/energy_uj"
    f.rename(f.with_name("other"))
    f.symlink_to("other")  # 0777 am Link; der Helfer öffnet mit O_NOFOLLOW und behandelt ihn nie
    assert part(read(root), "rapl") == "broken"


def test_parts_shape_and_order(root):
    want = {"marker": "off", "manual_rule": False, "parts": [{"part": "rapl", "state": "none"}]}
    assert read(root, intel=False) == want
    assert [p["part"] for p in read(root)["parts"]] == ["perfmon", "rapl"]


# ---- Merkdatei und Verzeichnis (B2.2, Lesen in der App) ----
def test_marker_regular_root_file_is_on(root):
    release(root)
    assert read(root)["marker"] == "on"


def test_no_marker_is_off(root):
    assert read(root)["marker"] == "off"


def test_no_directory_is_off(root):
    """Start ohne Paket: kein /etc/orbitop, also keine Merkdatei; die Wirkung zeigt sich trotzdem."""
    at(root, MARKER).parent.rmdir()
    zones(root, 0o444)
    got = read(root)
    assert got["marker"] == "off" and part(got, "rapl") == "manual"


@pytest.mark.parametrize("kind", ["symlink", "directory", "foreign", "fifo"])
def test_marker_that_is_not_a_root_file_is_never_on(root, kind):
    m = at(root, MARKER)
    if kind == "symlink":
        (m.parent.parent / "target").write_bytes(b"")
        m.symlink_to("../target")
    elif kind == "directory":
        m.mkdir()
    elif kind == "fifo":
        os.mkfifo(m)
    else:
        release(root)
    got = read(root, owners={MARKER: 1000} if kind == "foreign" else None, caps={TOOL: CAP})
    assert got["marker"] == "unclear"


@pytest.mark.parametrize("mode", [0o777, 0o755, 0o751, 0o731, 0o713, 0o750, 0o705])
def test_readable_or_writable_directory_is_unclear(root, mode):
    """Dieselbe Regel wie im Helfer: S_IMODE & 0o066 == 0; 0711 kommt aus dem Paket."""
    release(root)
    at(root, MARKER).parent.chmod(mode)
    assert read(root)["marker"] == "unclear"


@pytest.mark.parametrize("mode", [0o711, 0o700, 0o701])
def test_directory_without_group_other_rw_is_trusted(root, mode):
    release(root)
    at(root, MARKER).parent.chmod(mode)
    assert read(root)["marker"] == "on"


@pytest.mark.parametrize("kind", ["foreign", "symlink", "file"])
def test_odd_directory_is_unclear(root, kind):
    d = at(root, MARKER).parent
    if kind == "symlink":
        d.rename(d.with_name("real"))
        d.symlink_to("real")
    elif kind == "file":
        d.rmdir()
        d.write_bytes(b"")
    if kind != "file":
        release(root)
    assert read(root, owners={"/etc/orbitop": 1000} if kind == "foreign" else None)["marker"] == "unclear"


@pytest.mark.parametrize("cap,modes,want", [
    (CAP, (0o444,), "works"),       # die Wirkung des Helfers: ehrlich „wirkt“, nur die Merkdatei ist unklar
    (SYS_ADMIN, (0o444, 0o400, 0o444), "manual"),  # eine Wirkung, die der Helfer nie setzt
    (None, (0o400,), "none"),
])
def test_unclear_shows_the_measured_effect(root, cap, modes, want):
    release(root)
    at(root, MARKER).parent.chmod(0o755)  # etwa von Hand: der Helfer behandelt den Ordner nur noch als „schwach“
    zones(root, *modes)
    got = read(root, caps={TOOL: cap} if cap else None)
    assert got["marker"] == "unclear" and {p["state"] for p in got["parts"]} == {want}


def test_unclear_reports_missing_but_never_broken(root):
    """Fehlt das Werkzeug, heißt es auch bei unklarer Merkdatei missing; Zonen ohne Wirkung sind none, nie broken."""
    release(root)
    at(root, MARKER).parent.chmod(0o777)
    at(root, TOOL).unlink()
    assert [p["state"] for p in read(root)["parts"]] == ["missing", "none"]


# ---- Handregel der README 0.2.0 (B2.9) ----
def _manual_rule(root):
    rule = at(root, counters.MANUAL_RULE)
    rule.parent.mkdir(parents=True)
    rule.write_text('SUBSYSTEM=="powercap", RUN+="/bin/chmod 0444 ..."\n')
    return rule


def test_state_manual_rule(root):
    """Handregel ohne Merkdatei, Zonen 0444: aus, „von Hand freigegeben“, und der Hinweis nennt die Regel."""
    _manual_rule(root)
    zones(root, 0o444)
    got = read(root)
    assert got["marker"] == "off" and got["manual_rule"] is True and part(got, "rapl") == "manual"


def test_state_manual_rule_stays_with_marker(root):
    _manual_rule(root)
    zones(root, 0o444)
    release(root)
    got = read(root)
    assert got["marker"] == "on" and got["manual_rule"] is True and part(got, "rapl") == "works"


def test_manual_rule_as_dangling_symlink_counts(root):
    rule = _manual_rule(root)
    rule.unlink()
    rule.symlink_to("/nonexistent")  # os.path.lexists: der Name allein zählt
    assert read(root)["manual_rule"] is True


# ---- nur lesen ----
def test_state_opens_no_file(root, monkeypatch):
    """Nur lstat, getxattr und glob: kein open, also auch kein Öffnen zum Schreiben."""
    release(root)
    zones(root, 0o444)

    def boom(*a, **k):
        raise AssertionError("state() öffnet eine Datei")
    monkeypatch.setattr(os, "open", boom)
    monkeypatch.setattr(builtins, "open", boom)
    got = read(root, caps={TOOL: CAP})
    monkeypatch.undo()
    assert got["marker"] == "on" and [p["state"] for p in got["parts"]] == ["works", "works"]


def test_real_host_state_has_the_contract_shape():
    """Echtes /, nur lesend: ein gültiges COUNTERS, wie auch immer der Rechner steht."""
    got = counters.state(intel=True)
    assert set(got) == {"marker", "manual_rule", "parts"} and got["marker"] in {"on", "off", "unclear"}
    assert isinstance(got["manual_rule"], bool) and [p["part"] for p in got["parts"]] == ["perfmon", "rapl"]
    assert {p["state"] for p in got["parts"]} <= STATES
