# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Scriptlets der Freigabe im RPM (Fedora, openSUSE; Security-Dokument 0.3.0, B2.4, B2.8, E4): wörtlich die
Zeilen des Dokuments, kein %transfiletriggerin, kein Scriptlet ruft je "on", und keins scheitert wegen des Helfers.
Die Scriptlets laufen hier mit bash wie unter rpm (tests/scriptlets.py)."""
import re

import pytest

from orbitop import counterhelper
from tests.scriptlets import SPEC, recorded, rpm_scriptlets, run_rpm

SYNC = "/usr/lib/orbitop/counterhelper sync || :"
TRIGGER = f"%filetriggerin -- {counterhelper.TOOL}"
# B2.8 wörtlich, "…" ist die Merkdatei; %postun macht das Löschen danach mit sync -f dauerhaft (wie postrm, M-1).
PREUN = 'if [ "$1" -eq 0 ]; then /usr/lib/orbitop/counterhelper off || :; fi'
POSTUN = ('if [ "$1" -eq 0 ]; then rm -f /etc/orbitop/counters-released; rmdir /etc/orbitop 2>/dev/null || :;'
          ' sync -f /etc 2>/dev/null || :; fi')


def test_scriptlets_are_the_lines_of_the_document():
    """B2.4: sync in %filetriggerin auf dem Pfad des Werkzeugs und in %posttrans (E4: auch beim Upgrade in einer
    Transaktion, I-1); B2.8: off nur in %preun, die Sicherung in %postun, je nur bei $1 = 0. Sonst kein Scriptlet."""
    assert rpm_scriptlets() == {"%preun": [PREUN], "%postun": [POSTUN], "%posttrans": [SYNC], TRIGGER: [SYNC]}
    assert counterhelper.MARKER == "/etc/orbitop/counters-released"


def test_no_transaction_file_trigger():  # R4.4: %transfiletriggerin mit Dateipfad feuert nie
    assert "%transfiletrigger" not in SPEC.read_text(encoding="utf-8")


def test_no_scriptlet_says_on():
    for head, body in rpm_scriptlets().items():
        assert not re.search(r"\bon\b", "\n".join(body)), head


@pytest.mark.parametrize("head", ["%posttrans", TRIGGER])
@pytest.mark.parametrize("arg", ["1", "2"])  # Erstinstallation, Upgrade oder Reinstall
def test_install_scriptlets_run_sync(tmp_path, head, arg):
    r, called, _ = run_rpm(tmp_path, head, arg)
    assert (r.returncode, called, r.stderr) == (0, ["sync"], "")


@pytest.mark.parametrize("arg,words", [("0", ["off"]), ("1", [])])  # 1: ein Upgrade behält die Freigabe (B2.8, 4)
def test_preun_runs_off_only_on_the_final_removal(tmp_path, arg, words):
    r, called, _ = run_rpm(tmp_path, "%preun", arg)
    assert (r.returncode, called, r.stderr) == (0, words, "")


@pytest.mark.parametrize("head,arg", [("%posttrans", "1"), (TRIGGER, "1"), ("%preun", "0")])
@pytest.mark.parametrize("rc,helper", [(1, 0o755), (3, 0o755), (4, 0o755), (0, 0o644), (0, None)],
                         ids=["busy", "unsafe", "partial", "not-executable", "missing"])
def test_a_failing_helper_never_fails_a_scriptlet(tmp_path, head, arg, rc, helper):
    """B2.8: kein Skript scheitert wegen des Helfers; ein %preun mit Exit ≠ 0 verhinderte die Entfernung."""
    r, _, _ = run_rpm(tmp_path, head, arg, rc=rc, helper=helper)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("arg,marker,directory", [("0", False, False), ("1", True, True)])
def test_postun_deletes_marker_and_directory_on_the_final_removal(tmp_path, arg, marker, directory):
    _, _, etc = run_rpm(tmp_path, "%postun", "1")  # legt etc an
    (etc / "counters-released").touch()
    r, called, _ = run_rpm(tmp_path, "%postun", arg)
    assert (r.returncode, called) == (0, [])
    assert ((etc / "counters-released").exists(), etc.exists()) == (marker, directory)
    assert recorded(tmp_path, "syncs") == ([] if marker else ["-f /etc marker-left=no"])  # erst gelöscht, dann dauerhaft


def test_postun_keeps_a_directory_that_is_not_empty_and_a_failing_sync_never_fails_it(tmp_path):
    _, _, etc = run_rpm(tmp_path, "%postun", "1")
    (etc / "counters-released").touch()
    (etc / "other").touch()  # nicht von orbitop: rmdir lässt den Ordner stehen
    r, _, _ = run_rpm(tmp_path, "%postun", "0", sync_rc=1)
    assert r.returncode == 0 and (etc / "other").exists() and not (etc / "counters-released").exists(), r.stderr


def test_scriptlets_never_touch_udev():  # B2.9: fremde Regeln unter /etc/udev bleiben; B2.3: kein udevadm
    assert "udev" not in "\n".join(line for body in rpm_scriptlets().values() for line in body)
