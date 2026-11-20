# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Freigabe über pkexec und counterhelper (Security-Dokument 0.3.0, B2.1 „Unit (App)“, B2.7 „Vorbedingungen“).

Kein Test startet pkexec: run ist immer ein Ersatz. Der Testbaum stammt aus counterhelper_helpers.make_tree; nur
uid 0 ist gefälscht (lstat), weil sie sich ohne root nicht anlegen lässt."""
import errno
import stat
import subprocess

import pytest

from orbitop import actions, i18n
from orbitop.counterhelper import MARKER
from tests.actions_helpers import COUNTERHELPER, ELF_HEAD, PKEXEC, TRUSTED, as_root, chain_lstat, fake, opener
from tests.counterhelper_helpers import make_tree

BASE_TEXT = "Nicht ausgeführt – Umschalten geht nur in einer lokalen, aktiven Sitzung und mit dem Admin-Passwort."


@pytest.fixture
def tree(tmp_path):
    make_tree(tmp_path)
    return tmp_path


def release(tree):
    (tree / MARKER.lstrip("/")).write_bytes(b"")


def call(tree, on, rc=0, chain=TRUSTED, data=ELF_HEAD, exc=None):
    calls = []
    result = actions.counters(on, root=str(tree), run=fake(calls, rc, exc), lstat=as_root(tree, chain),
                              opener=opener(data))
    return result, [c[0] for c in calls]


# ---- Vorbedingung: der gewünschte Zustand weicht von der Merkdatei ab (B2.7) ----
def test_on_with_marker_present_does_not_run(tree):
    release(tree)
    assert call(tree, True) == ("ok", [])


def test_off_without_marker_does_not_run(tree):
    assert call(tree, False) == ("ok", [])


@pytest.mark.parametrize("on,released,word", [(True, False, "on"), (False, True, "off")])
def test_switch_runs_the_helper_with_exact_argv(tree, on, released, word):
    if released:
        release(tree)
    calls = []
    assert actions.counters(on, root=str(tree), run=fake(calls), lstat=as_root(tree), opener=opener()) == "ok"
    assert calls == [([PKEXEC, COUNTERHELPER, word], {"timeout": 120})]


@pytest.mark.parametrize("on", [True, False])
def test_unclear_marker_leaves_the_decision_to_the_helper(tree, on):
    (tree / "etc/orbitop").chmod(0o755)  # für andere lesbar: „aus, Zustand unklar“ (B2.2)
    assert call(tree, on) == ("ok", [[PKEXEC, COUNTERHELPER, "on" if on else "off"]])


@pytest.mark.parametrize("on", [1, "true", None])
def test_on_must_be_bool(tree, on):
    assert call(tree, on) == ("error", [])


# ---- Ergebnis: vom Exit-Code zählt nur 126 und 127, den Rest zeigt der frisch gelesene Zustand (B2.1) ----
@pytest.mark.parametrize("rc,want", [(0, "ok"), (1, "ok"), (3, "ok"), (4, "ok"), (126, "cancelled"),
                                     (127, "denied"), (-15, "error")])  # -15: pkexec von stop() beendet
def test_exit_codes(tree, rc, want):
    assert call(tree, True, rc=rc)[0] == want


def test_exit_127_gives_the_base_text(tree):  # M-1: polkit „no“ und Fehler sind für pkexec dasselbe
    assert call(tree, True, rc=127)[0] == "denied"
    de, en = i18n.load_texts("de")["counters.denied"], i18n.load_texts("en")["counters.denied"]
    assert de == BASE_TEXT
    assert "local, active session" in en and "admin password" in en


@pytest.mark.parametrize("exc,want", [
    (PermissionError(errno.EPERM, "x"), "error"),  # kill() am Helfer, der schon als root läuft
    (OSError(errno.ENOENT, "x"), "error"),
    (subprocess.SubprocessError(), "error"),
    (subprocess.TimeoutExpired(["pkexec"], 120), "cancelled"),  # Dialog offen gelassen: zählt als Abbruch (R9)
], ids=["eperm", "enoent", "subprocess", "timeout"])
def test_run_errors(tree, exc, want):
    assert call(tree, True, exc=exc)[0] == want


# ---- pkexec-Prüfung (E5) und Vertrauen in den Helfer (B2.1) ----
@pytest.mark.parametrize("over,data,want", [
    ({}, ELF_HEAD, "ok"),                                                    # ELF mit setuid und root
    ({}, b"#!/bin/bash\nexec run0 ", "nohelper"),                            # Skript (run0-wrappers)
    ({PKEXEC: (0, stat.S_IFREG | 0o755)}, ELF_HEAD, "nohelper"),             # ELF ohne setuid
    ({PKEXEC: (0, stat.S_IFLNK | stat.S_ISUID | 0o777)}, ELF_HEAD, "nohelper"),  # Symlink
    ({PKEXEC: (1000, stat.S_IFREG | stat.S_ISUID | 0o755)}, ELF_HEAD, "nohelper"),  # Eigentümer nicht root
    ({COUNTERHELPER: (1000, stat.S_IFREG | 0o755)}, ELF_HEAD, "nohelper"),   # Helfer gehört dem User
    ({COUNTERHELPER: (0, stat.S_IFREG | 0o775)}, ELF_HEAD, "nohelper"),      # Helfer für die Gruppe beschreibbar
    ({COUNTERHELPER: (0, stat.S_IFLNK | 0o777)}, ELF_HEAD, "nohelper"),      # Helfer als Symlink
    ({COUNTERHELPER: (0, stat.S_IFREG | 0o644)}, ELF_HEAD, "nohelper"),      # Helfer nicht ausführbar
    ({"/usr/lib/orbitop": (0, stat.S_IFDIR | 0o777)}, ELF_HEAD, "nohelper"),  # Ordner für alle beschreibbar
], ids=["elf-setuid", "script", "elf-no-setuid", "symlink", "pkexec-not-root", "helper-not-root",
        "helper-group-writable", "helper-symlink", "helper-not-executable", "dir-writable"])
def test_pkexec_and_helper_checks(tree, over, data, want):
    result, calls = call(tree, True, chain=chain_lstat(**over), data=data)
    assert result == want and len(calls) == (want == "ok")


def test_helper_in_user_tree_is_nohelper_with_real_lstat(monkeypatch, tree, tmp_path):
    """Echtes lstat: ein Helfer, den User-Code austauschen könnte, startet nie pkexec."""
    fake_helper = tmp_path / "counterhelper"
    fake_helper.write_bytes(b"#!/usr/bin/python3 -IS\n")
    fake_helper.chmod(0o755)
    monkeypatch.setattr(actions, "_COUNTERHELPER", str(fake_helper))
    calls = []
    assert actions.counters(True, root=str(tree), run=fake(calls)) == "nohelper" and calls == []
    assert actions.counters_usable() == "nohelper"


@pytest.mark.parametrize("over,data,want", [
    ({}, ELF_HEAD, "yes"),
    ({COUNTERHELPER: (1000, stat.S_IFREG | 0o755)}, ELF_HEAD, "nohelper"),  # Start aus einem Checkout ohne Paket
    ({}, b"#!/bin/bash\n", "nopkexec"),                                       # pkexec nicht von polkit
    ({PKEXEC: (0, stat.S_IFREG | 0o755)}, ELF_HEAD, "nopkexec"),
])
def test_counters_usable(over, data, want):
    assert actions.counters_usable(chain_lstat(**over), opener(data)) == want


def test_usable_needs_no_file_open_for_a_missing_helper():
    def missing(path):
        if path == COUNTERHELPER:
            raise FileNotFoundError(errno.ENOENT, "x", path)
        return TRUSTED(path)

    def no_open(path, flags):
        pytest.fail("ohne Helfer wird pkexec nicht gelesen")
    assert actions.counters_usable(missing, no_open) == "nohelper"

