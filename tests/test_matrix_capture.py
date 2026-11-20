# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Kopie der Ausgabe, nach der net und clean in scripts/matrix/lib.sh urteilen (logged, matching): Sie stammt immer
aus dem laufenden Lauf, wird als Text gelesen, und ein Fehler beim Schreiben oder Lesen zählt nie als sauber oder als
Aussetzer. Der Ersatz-Paketmanager pm steht in tests/matrix_helpers.py."""
import os

import pytest

from tests.matrix_helpers import runs

HICCUP_LINE = ">>> Curl error (56): Failure when receiving data from the peer for https://mirror.example.com/"
PACKAGE_ERROR = "Error: Unable to find a match: orbitop"
WARNING = "W: GPG error: file:/site/apt stable InRelease: NO_PUBKEY 0123456789ABCDEF"  # apt update endet mit 0
AS_ROOT = pytest.mark.skipif(os.geteuid() == 0, reason="root liest und schreibt auch ohne die Rechte der Datei")


@pytest.mark.parametrize("command", ["clean pm", "net pm"])
def test_a_capture_file_that_cannot_be_removed_stops_the_run(tmp_path, command):
    """Jeder Lauf entfernt zuerst die Kopie der Ausgabe des vorigen; geht das nicht (hier ein Verzeichnis), läuft der
    Befehl gar nicht."""
    state = tmp_path / "state"
    state.mkdir()
    for log in ("clean.out", "net.out"):
        (state / log).mkdir()
    ok, out, calls, slept = runs(tmp_path, command, (WARNING, 0), files=("apt.sh",))
    assert not ok and calls == 0 and slept == [], out


@pytest.mark.parametrize("rc,status", [(0, 1), (3, 3)], ids=["command-ok", "command-failed"])
def test_logged_fails_when_tee_cannot_write(tmp_path, rc, status):  # ohne die Kopie wertet niemand die Ausgabe
    ok, out, calls, _ = runs(tmp_path, f'logged "$STATE/missing/out" pm; [ "$?" -eq {status} ]', ("Hit:1", rc))
    assert ok and calls == 1, out


# wait_for FILE: bis tee die Kopie angelegt hat (tee und pm starten zugleich), höchstens 5 s; sonst eine Zeile, die der
# Test sieht. command sleep: runs ersetzt sleep durch einen Stellvertreter.
WAIT_FOR = ('wait_for() { local _; for _ in $(seq 500); do [ -e "$1" ] && return 0; command sleep 0.01; done;'
            ' echo "NO CAPTURE FILE"; };')


@AS_ROOT
@pytest.mark.parametrize("command,log,output,reason", [
    ("clean pm", "clean.out", ("Hit:1 x", 0), "NOISE unknown: cannot read"),
    ("net pm", "net.out", (HICCUP_LINE, 1), "")], ids=["clean", "net"])
def test_unreadable_capture_fails_clean_and_net_does_not_retry(tmp_path, command, log, output, reason):
    """Der Befehl nimmt seiner Kopie das Leserecht: grep scheitert mit 2. clean scheitert dann trotz sauberer
    Ausgabe, net wiederholt den Aussetzer nicht."""
    unreadable = (f'{WAIT_FOR} pm() {{ echo >> "$STATE/calls"; cat "$STATE/out.1"; wait_for "$STATE/{log}";'
                  f' chmod 200 "$STATE/{log}"; return "$(cat "$STATE/rc.1")"; }};')
    ok, out, calls, slept = runs(tmp_path, f"{unreadable} {command}", output, ("", 0), files=("apt.sh",))
    assert not ok and calls == 1 and slept == [] and reason in out and "NO CAPTURE FILE" not in out, out


@AS_ROOT
def test_a_stale_capture_file_never_decides(tmp_path):
    """Die Kopie eines früheren Laufs mit einem Aussetzer, die tee nicht überschreiben kann: Ein Fehler des Pakets im
    neuen Lauf wird trotzdem nicht wiederholt."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "net.out").write_text(HICCUP_LINE + "\n")
    (state / "net.out").chmod(0o400)
    ok, out, calls, slept = runs(tmp_path, "net pm", ("Error: Unable to find a match: orbitop", 1), ("", 0))
    assert not ok and calls == 1 and slept == [], out


@pytest.mark.parametrize("command,output,passed,count", [
    ("clean pm", (f"{WARNING}\n\0binary", 0), False, 1),  # GNU grep sähe sonst nur "binary file matches"
    ("net pm", (f"{HICCUP_LINE}\n\0binary", 1), True, 2),
], ids=["clean-warning", "net-hiccup"])
def test_a_nul_byte_does_not_hide_the_output(tmp_path, command, output, passed, count):
    ok, out, calls, _ = runs(tmp_path, command, output, ("", 0), files=("apt.sh",))
    assert ok is passed and calls == count, out


@pytest.mark.parametrize("unset", ["unset NOISE", "NOISE="])
def test_clean_fails_without_noise(tmp_path, unset):  # ein leeres Muster träfe jede Zeile, eine leere Ausgabe keine
    ok, out, _, _ = runs(tmp_path, f"( {unset}; clean pm )", ("", 0), files=("apt.sh",))
    assert not ok, out


@pytest.mark.parametrize("pipefail", ["", "set -o pipefail;"])
def test_net_streams_the_output_and_keeps_the_exit_code(tmp_path, pipefail):
    ok, out, calls, _ = runs(tmp_path, f'{pipefail} net pm; [ "$?" -eq 4 ]', ("Problem retrieving files", 4))
    assert ok and calls == 1 and out.count("Problem retrieving files") == 1, out
    assert (tmp_path / "state" / "net.out").read_text() == "Problem retrieving files\n"


@pytest.mark.parametrize("manager,line", [
    ("apt.sh", WARNING), ("pacman.sh", "warning: orbitop: local (0.2.0-1) is newer than extra (0.1.0-1)"),
], ids=["apt", "pacman"])
def test_a_nul_byte_before_an_anchored_prefix_still_counts(tmp_path, manager, line):
    """Wie printf 'Hit:1 x\\n\\0W: GPG error …' mit Exit 0: Das NUL-Byte steht direkt vor dem verankerten Präfix von
    NOISE; matching liest es als Zeilenumbruch."""
    ok, out, calls, _ = runs(tmp_path, "clean pm", (f"Hit:1 x\n\0{line}", 0), files=(manager,))
    assert not ok and calls == 1 and f"NOISE {line}" in out.splitlines(), out


@pytest.mark.parametrize("manager,line", [
    ("apt.sh", WARNING), ("pacman.sh", "warning: orbitop: local (0.2.0-1) is newer than extra (0.1.0-1)"),
], ids=["apt", "pacman"])
def test_a_carriage_return_before_an_anchored_prefix_still_counts(tmp_path, manager, line):
    """Wie ein Fortschrittsbalken, den \\r überschreibt: Ohne Zeilenumbruch stünde das Präfix von NOISE mitten in der
    Zeile; matching liest \\r wie das NUL-Byte als Zeilenumbruch."""
    ok, out, calls, _ = runs(tmp_path, "clean pm", (f"Hit:1 x\r{line}", 0), files=(manager,))
    assert not ok and calls == 1 and f"NOISE {line}" in out.splitlines(), out


@pytest.mark.parametrize("command,output", [("clean pm", ("Hit:1 x", 0)), ("net pm", (HICCUP_LINE, 1))],
                         ids=["clean", "net"])
def test_a_failing_tr_is_never_no_match(tmp_path, command, output):
    """tr scheitert (Stellvertreter): clean scheitert auch bei sauberer Ausgabe, net wiederholt nicht."""
    ok, out, calls, slept = runs(tmp_path, f"tr() {{ return 1; }}; {command}", output, ("", 0), files=("apt.sh",))
    assert not ok and calls == 1 and slept == [], out


@pytest.mark.parametrize("command,output", [("clean pm", ("Hit:1 x", 0)), ("net pm", (HICCUP_LINE, 1))],
                         ids=["clean", "net"])
def test_a_failing_grep_is_never_no_match(tmp_path, command, output):
    """grep endet mit 2, nachdem es alles gelesen hat (Stellvertreter; ein ungültiges Muster ließe tr je nach Zeitpunkt
    an SIGPIPE scheitern): clean scheitert auch bei sauberer Ausgabe, net wiederholt nicht."""
    failing = "grep() { cat > /dev/null; return 2; };"
    ok, out, calls, slept = runs(tmp_path, f"{failing} {command}", output, ("", 0), files=("apt.sh",))
    assert not ok and calls == 1 and slept == [], out


# pm sperrt nach jedem Lauf seine Kopie (nur lesbar), sobald tee sie angelegt hat: Ohne rm vor dem nächsten Lauf
# könnte tee sie nicht ersetzen, und die alte Kopie entschiede.
LOCKING = (f'{WAIT_FOR} pm() {{ echo >> "$STATE/calls"; local n; n=$(wc -l < "$STATE/calls");'
           ' wait_for "$STATE/net.out"; cat "$STATE/out.$n"; chmod 400 "$STATE/net.out";'
           ' return "$(cat "$STATE/rc.$n")"; };')


@AS_ROOT
def test_the_capture_file_is_removed_before_every_run(tmp_path):
    """Lauf 1 meldet einen Aussetzer, Lauf 2 einen Fehler des Pakets: Die gesperrte Kopie von Lauf 1 entscheidet nicht
    über Lauf 2. Bei drei Läufen hält die Kopie am Ende die Ausgabe von Lauf 3."""
    ok, out, calls, slept = runs(tmp_path / "two", f"{LOCKING} net pm", (HICCUP_LINE, 1), (PACKAGE_ERROR, 1), ("", 0))
    assert not ok and calls == 2 and slept == ["10"] and "NO CAPTURE FILE" not in out, out
    ok, out, calls, slept = runs(tmp_path / "three", f"{LOCKING} net pm", (HICCUP_LINE, 1), (HICCUP_LINE, 1),
                                 (PACKAGE_ERROR, 1))
    assert not ok and calls == 3 and slept == ["10", "10"] and "NO CAPTURE FILE" not in out, out
    assert (tmp_path / "three" / "state" / "net.out").read_text() == PACKAGE_ERROR + "\n"
