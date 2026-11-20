# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Freigabe im Arch-Paket (Security-Dokument 0.3.0, B2.4, B2.8): der pacman-Hook wörtlich nach B2.4, pre_remove
und post_remove wörtlich nach B2.8; post_install und post_upgrade bleiben beim Schlüssel und rufen den Helfer nie.
Die Funktionen laufen hier mit bash wie unter pacman (tests/scriptlets.py)."""
import re

import pytest

from orbitop import counterhelper
from tests.packaging_common import PKG
from tests.scriptlets import INSTALL, recorded, run_arch

HOOK = PKG / "arch" / "orbitop-counters.hook"
HOOKS = "/usr/share/libalpm/hooks"
# B2.4 wörtlich; Kommentarzeilen davor tragen nur den Kopf der Datei.
HOOK_LINES = ["[Trigger]", "Type = Path", "Operation = Install", "Operation = Upgrade",
              f"Target = {counterhelper.TOOL.lstrip('/')}", "", "[Action]",
              "Description = Applying the orbitop counter release, if turned on...", "When = PostTransaction",
              "Exec = /usr/lib/orbitop/counterhelper sync"]
# B2.8 wörtlich, "…" ist die Merkdatei; post_remove macht das Löschen danach mit sync -f dauerhaft (wie postrm, M-1).
PRE_REMOVE = "pre_remove() { /usr/lib/orbitop/counterhelper off || true; }"
POST_REMOVE = ("post_remove() { rm -f /etc/orbitop/counters-released; rmdir /etc/orbitop 2>/dev/null || true;"
               " sync -f /etc 2>/dev/null || true; }")


def test_hook_is_the_one_of_the_document():
    """Nur ganze Kommentarzeilen vor [Trigger]: libalpm liest Hooks mit pacmans INI-Leser, der # als Kommentar nimmt;
    dahinter genau die Zeilen von B2.4 (PostTransaction deckt auch das gemeinsame Upgrade ab, I-1). Kein Remove:
    ohne das Werkzeug gibt es nichts freizugeben."""
    lines = HOOK.read_text(encoding="utf-8").splitlines()
    start = lines.index("[Trigger]")
    assert all(ln.startswith("# ") for ln in lines[:start]) and lines[start:] == HOOK_LINES


def test_pkgbuild_installs_the_hook():  # der Testbau prüft das Paket (test_packaging_arch.py)
    text = (PKG / "arch" / "PKGBUILD").read_text(encoding="utf-8")
    assert f'install -D -m 0644 -t "$pkgdir{HOOKS}" packaging/arch/orbitop-counters.hook' in text


def test_remove_functions_are_the_lines_of_the_document():
    lines = INSTALL.read_text(encoding="utf-8").splitlines()
    assert [ln for ln in lines if "counterhelper" in ln or "/etc/orbitop" in ln] == [PRE_REMOVE, POST_REMOVE]
    for line in (PRE_REMOVE, POST_REMOVE):
        assert not re.search(r"\bon\b", line)


@pytest.mark.parametrize("function,words", [("pre_remove", ["off"]), ("post_remove", [])])
def test_only_pre_remove_calls_the_helper(tmp_path, function, words):
    """pacman ruft bei einem Upgrade nur post_upgrade (beim Schlüssel, ohne Helfer: oben); die Freigabe bleibt
    (B2.8, 4)."""
    r, called, _ = run_arch(tmp_path, function)
    assert (r.returncode, called, r.stderr) == (0, words, "")


@pytest.mark.parametrize("rc,helper", [(1, 0o755), (3, 0o755), (4, 0o755), (0, 0o644), (0, None)],
                         ids=["busy", "unsafe", "partial", "not-executable", "missing"])
def test_a_failing_helper_never_fails_pre_remove(tmp_path, rc, helper):
    r, _, _ = run_arch(tmp_path, "pre_remove", rc=rc, helper=helper)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("sync_rc", [0, 1])
def test_post_remove_deletes_marker_and_directory(tmp_path, sync_rc):
    etc = tmp_path / "etc" / "orbitop"
    etc.mkdir(parents=True)
    (etc / "counters-released").touch()
    r, called, _ = run_arch(tmp_path, "post_remove", sync_rc=sync_rc)
    assert (r.returncode, called, etc.exists()) == (0, [], False), r.stderr
    assert recorded(tmp_path, "syncs") == ["-f /etc marker-left=no"]  # erst gelöscht, dann dauerhaft


def test_post_remove_keeps_a_directory_that_is_not_empty(tmp_path):
    etc = tmp_path / "etc" / "orbitop"
    etc.mkdir(parents=True)
    (etc / "other").touch()  # nicht von orbitop
    r, _, _ = run_arch(tmp_path, "post_remove")
    assert r.returncode == 0 and (etc / "other").exists(), r.stderr
