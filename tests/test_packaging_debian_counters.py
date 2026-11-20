# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Paket-Skripte der Freigabe unter Debian (Security-Dokument 0.3.0, B2.4, B2.8, E1, E4): wörtlich die Zeilen des
Dokuments, kein Paket-Skript ruft je "on", und keins scheitert wegen des Helfers. Die Skripte laufen hier mit sh auf
Kopien, in denen der Helfer ein Stellvertreter und /etc/orbitop ein Ordner in tmp_path ist."""
import re
import shutil
import subprocess

import pytest

from orbitop import counterhelper
from tests.packaging_common import PKG
from tests.scriptlets import HELPER, deb_script as script, recorded, run_deb as run

DEBIAN = PKG / "debian"
SCRIPTS = ("postinst", "prerm", "postrm")
# B2.4 und B2.8, wörtlich; "…" der Tabelle in B2.8 ist hier der Text für off. postrm macht das Löschen danach mit
# sync -f dauerhaft (Audit Task 3, M-1).
POSTINST = ('    configure|triggered) /usr/lib/orbitop/counterhelper sync || echo "orbitop: counter release not applied"'
            ' >&2 ;;')
PRERM = '    remove) /usr/lib/orbitop/counterhelper off || echo "orbitop: counter release not revoked" >&2 ;;'
POSTRM = ["    remove) rm -f /etc/orbitop/counters-released; sync -f /etc 2>/dev/null || true ;;",
          "    purge) rm -f /etc/orbitop/counters-released; rmdir /etc/orbitop 2>/dev/null || true;"
          " sync -f /etc 2>/dev/null || true ;;"]
# Ein Aufruf des Helfers mit seinem Wort, in jeder Datei unter packaging/, aller Formate.
CALL = re.compile(r"counterhelper[ \t]+(\S+)")


def calls():
    """{Datei: [Wort, …]} für jeden Aufruf des Helfers mit einem Wort unter packaging/, ohne Kommentarzeilen und ohne
    die Doku README.*."""
    found = {}
    for p in sorted(PKG.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith("README"):
            code = [ln for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()
                    if not ln.lstrip().startswith("#")]
            words = CALL.findall("\n".join(code))
            if words:
                found[str(p.relative_to(PKG))] = words
    return found


def test_package_scripts_call_only_sync_and_off():
    """B2.4, alle Formate: sync nur in postinst, %posttrans, %filetriggerin und im pacman-Hook, off nur in den
    Entfern-Skripten (prerm, %preun, pre_remove), on nirgends; die Zweige prüfen die Tests je Format. Hier für
    Debian auch keine andere Schreibweise von on."""
    assert calls() == {"arch/orbitop-counters.hook": ["sync"], "arch/orbitop.install": ["off"],
                       "debian/orbitop.postinst": ["sync"], "debian/orbitop.prerm": ["off"],
                       "rpm/orbitop.spec": ["off", "sync", "sync"]}
    for p in (DEBIAN / f"orbitop.{n}" for n in SCRIPTS):
        assert not re.search(r"\bon\b", p.read_text().split("set -e", 1)[1].replace("#DEBHELPER#", "")), p


def test_postinst_syncs_only_on_configure_and_triggered():
    lines = script("postinst").splitlines()
    assert [ln for ln in lines if HELPER in ln] == [POSTINST]


def test_prerm_locks_only_on_remove():  # nie bei upgrade: ein Update behält die Freigabe (B2.8, Fall 4)
    lines = script("prerm").splitlines()
    assert [ln for ln in lines if HELPER in ln] == [PRERM]


def test_postrm_deletes_the_marker_on_remove_and_the_directory_on_purge():
    lines = script("postrm").splitlines()
    assert [ln for ln in lines if "/etc/orbitop" in ln and not ln.startswith("#")] == POSTRM
    assert counterhelper.MARKER == "/etc/orbitop/counters-released"


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_keep_debhelper_and_set_e(name):  # dh_python3 setzt bei #DEBHELPER# das Byte-Kompilieren ein
    lines = script(name).splitlines()
    assert lines[0] == "#!/bin/sh" and "set -e" in lines and lines.count("#DEBHELPER#") == 1
    assert lines[-1] == "exit 0"


def test_trigger_is_the_path_of_the_tool():
    """Nur ganze Kommentarzeilen: dpkg in trixie lehnt ein # hinter der Anweisung ab ("trigger name contains invalid
    character"), obwohl deb-triggers(5) es beschreibt (Audit Task 3)."""
    lines = [ln.strip() for ln in (DEBIAN / "orbitop.triggers").read_text().splitlines()]
    assert [ln for ln in lines if ln and not ln.startswith("#")] == [f"interest-noawait {counterhelper.TOOL}"]


def test_readme_debian_names_the_policy_deviation():  # E1
    text = " ".join((DEBIAN / "README.Debian").read_text(encoding="utf-8").split())
    assert "Debian Policy 10.7.3" in text and counterhelper.MARKER in text
    assert "setcap -r /usr/bin/intel_gpu_top" in text  # M-3: der Weg, wenn der Helfer beim Entfernen nicht lief


@pytest.mark.parametrize("arg,words", [("configure", ["sync"]), ("triggered", ["sync"]), ("abort-upgrade", []),
                                       ("abort-remove", []), ("abort-deconfigure", [])])
def test_postinst_runs_sync(tmp_path, arg, words):
    r, called, _ = run(tmp_path, "postinst", arg)
    assert (r.returncode, called, r.stderr) == (0, words, "")


@pytest.mark.parametrize("arg,words", [("remove", ["off"]), ("upgrade", []), ("deconfigure", []),
                                       ("failed-upgrade", [])])
def test_prerm_runs_off(tmp_path, arg, words):
    r, called, _ = run(tmp_path, "prerm", arg)
    assert (r.returncode, called, r.stderr) == (0, words, "")


@pytest.mark.parametrize("name,arg,text", [("postinst", "configure", "orbitop: counter release not applied"),
                                           ("postinst", "triggered", "orbitop: counter release not applied"),
                                           ("prerm", "remove", "orbitop: counter release not revoked")])
@pytest.mark.parametrize("rc,helper", [(1, 0o755), (3, 0o755), (4, 0o755), (126, 0o755), (0, None)],
                         ids=["busy", "unsafe", "partial", "not-executable", "missing"])
def test_a_failing_helper_never_fails_the_script(tmp_path, name, arg, text, rc, helper):
    r, _, _ = run(tmp_path, name, arg, rc=rc, helper=helper)
    assert r.returncode == 0 and text in r.stderr, r.stderr


@pytest.mark.parametrize("arg,marker,directory", [("remove", False, True), ("purge", False, False),
                                                  ("upgrade", True, True), ("failed-upgrade", True, True),
                                                  ("abort-upgrade", True, True), ("abort-install", True, True),
                                                  ("disappear", True, True)])
def test_postrm_marker_and_directory(tmp_path, arg, marker, directory):
    _, _, etc = run(tmp_path, "postrm", "remove")  # legt etc an
    (tmp_path / "syncs").unlink(missing_ok=True)
    (etc / "counters-released").touch()
    r, called, _ = run(tmp_path, "postrm", arg)
    assert (r.returncode, called) == (0, [])
    assert ((etc / "counters-released").exists(), etc.exists()) == (marker, directory)
    assert recorded(tmp_path, "syncs") == ([] if marker else ["-f /etc marker-left=no"])  # erst gelöscht, dann dauerhaft (M-1)


@pytest.mark.parametrize("arg", ["remove", "purge"])
def test_a_failing_sync_never_fails_postrm(tmp_path, arg):
    r, _, etc = run(tmp_path, "postrm", arg, sync_rc=1)
    assert (r.returncode, (etc / "counters-released").exists()) == (0, False), r.stderr


def test_purge_keeps_a_directory_that_is_not_empty_and_one_that_is_gone(tmp_path):
    _, _, etc = run(tmp_path, "postrm", "remove")
    (etc / "other").touch()  # nicht von orbitop: rmdir lässt den Ordner stehen, und purge gelingt
    assert run(tmp_path, "postrm", "purge")[0].returncode == 0 and (etc / "other").exists()
    shutil.rmtree(etc)
    r = subprocess.run(["sh", str(tmp_path / "postrm"), "purge"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and not etc.exists(), r.stderr


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck fehlt")
def test_scripts_pass_shellcheck():
    paths = [str(DEBIAN / f"orbitop.{n}") for n in SCRIPTS]
    assert subprocess.run(["shellcheck", "-s", "sh", *paths]).returncode == 0


def test_scripts_are_not_conffiles_and_never_touch_udev():  # B2.9: fremde Regeln unter /etc/udev bleiben
    for name in SCRIPTS:
        assert "udev" not in script(name).split("set -e", 1)[1], name
    assert not (DEBIAN / "orbitop.conffiles").exists()  # die Merkdatei ist kein Conffile (B2.2)
