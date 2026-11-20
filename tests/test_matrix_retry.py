# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Netzaussetzer der Spiegel in der Container-Matrix: net und quiet in scripts/matrix/lib.sh wiederholen einen
gescheiterten Lauf, der einen Aussetzer meldet und die Paketdatenbank nicht änderte; jeder andere Fehler zählt
sofort, der Manipulationstest läuft einmal. Die Programme der Paketverwaltungen sind Shell-Funktionen, die pm
aufrufen (runs in tests/matrix_helpers.py)."""
import os
import shlex

import pytest

from tests.matrix_helpers import call, rpm_site, runs

CURL = (">>> Curl error (56): Failure when receiving data from the peer for https://mirrors.fedoraproject.org/"
        "metalink?repo=updates-released-f45&arch=x86_64 [Recv failure: Connection reset by peer]")  # 2026-11-19
RESET = ("W: Failed to fetch http://deb.example.com/debian/dists/trixie/InRelease  Error reading from server - read "
         "(104: Connection reset by peer)")
SLOW = ("error: failed retrieving file 'core.db' from mirror.example.com : Operation too slow. Less than 1 bytes/sec "
        "transferred the last 10 seconds")
# Ein Aussetzer je Paketverwaltung, mit ihrem Exit-Code.
HICCUPS = {
    "apt.sh": (RESET, 100),
    "dnf.sh": (CURL, 1),
    "pacman.sh": (SLOW, 1),
    "zypper.sh": ("Timeout exceeded when accessing 'https://download.example.com/repodata/repomd.xml'.", 4),
}
MANAGERS = sorted(HICCUPS)
FETCH = "error: failed retrieving file 'core.db' from mirror.example.com : "  # libalpm, dann der Text von libcurl
APT = "W: Failed to fetch http://deb.example.com/debian/dists/trixie/InRelease  "
# Die Meldungen der Images (Zeichenketten in librepo, libzypp, libalpm, libcurl 8, libapt-pkg und libc, gelesen in
# fedora:latest, opensuse/tumbleweed, archlinux:latest, debian:trixie und ubuntu:24.04 am 2026-11-20). Die Fälle
# zypper-6, -7 und -56 und dnf-56 treffen nur über den Code.
MATCHES = {
    "dnf-56": ">>> Curl error (56): Failure when receiving data from the peer for https://mirror.example.com/",
    "dnf-6": ">>> Curl error (6): Could not resolve hostname for http://mirror.invalid/repodata/repomd.xml "
             "[Could not resolve host: mirror.invalid]",
    "dnf-28": ">>> Curl error (28): Timeout was reached for https://mirror.example.com/ [Operation timed out after "
              "30000 milliseconds with 0 bytes received]",
    "zypper-6": "Error code: Curl error 6",
    "zypper-7": "Error code: Curl error 7",
    "zypper-28": "Error code: Curl error 28",
    "zypper-35": "Error code: Curl error 35",
    "zypper-52": "Error code: Curl error 52",
    "zypper-56": "Error code: Curl error 56",
    "zypper-timeout": "Timeout exceeded when accessing 'https://download.example.com/repodata/repomd.xml'.",
    "pacman-slow": SLOW,
    "pacman-empty": f"{FETCH}Empty reply from server",
    "pacman-connect": f"{FETCH}Failed to connect to mirror.example.com port 443 after 3 ms: "
                      "Could not connect to server",
    "pacman-couldnt": f"{FETCH}Couldn't connect to server",  # libcurl vor 8
    "pacman-timeout": f"{FETCH}Connection timed out after 10001 milliseconds",
    "pacman-resolving": f"{FETCH}Resolving timed out after 10000 milliseconds",  # "%s timed out after" mit "Resolving"
    "pacman-connect-timeout": f"{FETCH}Connection timeout after 10001 ms",
    "pacman-host": f"{FETCH}Could not resolve host: mirror.example.com",
    "pacman-reset": f"{FETCH}Recv failure: Connection reset by peer",
    "apt-resolving": f"{APT}Temporary failure resolving 'deb.example.com'",
    "apt-resolve": f"{APT}Could not resolve 'deb.example.com'",
    "apt-connect": f"{APT}Could not connect to deb.example.com:80 (192.0.2.1). - connect (111: Connection refused)",
    "apt-timeout": "  Could not connect to deb.example.com:80 (192.0.2.1), connection timed out",
    "apt-timed-out": f"{APT}Unable to connect to deb.example.com:80: connect (110: Connection timed out)",
    "apt-reset": RESET,
    "libc-name": "Temporary failure in name resolution",
    "curl-timeout": "Operation timed out after 30000 milliseconds with 0 bytes received",
}
# Keine Aussetzer: systemd in den Skripten der Pakete, Zertifikate, Signaturen, Pakete, die Ablehnung.
OTHERS = {
    "systemd-bus": "Failed to connect to bus: No such file or directory",
    "dnf-60": ">>> Curl error (60): SSL peer certificate or SSH remote key was not OK for https://mirror.example.com/ "
              "[SSL certificate problem: unable to get local issuer certificate]",
    "zypper-60": "Error code: Curl error 60",
    "apt-unsigned": "E: The repository 'file:/site/apt stable InRelease' is not signed.",
    "apt-hash": "E: Failed to fetch file:/site/apt/dists/stable/main/binary-all/Packages.gz  Hash Sum mismatch",
    "apt-depends": " orbitop : Depends: python3 (>= 3.12) but 3.11.2-1+b1 is to be installed",
    "dnf-gpg": "Error: GPG check FAILED",
    "dnf-signature": ">>> repomd.xml OpenPGP signature verification error: Bad PGP signature",
    "zypper-signature": "Signature verification failed for repomd.xml",
    "pacman-signature": 'error: orbitop: signature from "orbitop archive signing key" is invalid',
    "pacman-db": "error: database 'orbitop' is not valid (invalid or corrupted database (PGP signature))",
}


@pytest.mark.parametrize("line", MATCHES.values(), ids=MATCHES.keys())
def test_hiccup_matches_the_network_messages(tmp_path, line):
    assert call(tmp_path, f'grep -qE -- "$HICCUP" <<< {shlex.quote(line)}')[0]


@pytest.mark.parametrize("line", OTHERS.values(), ids=OTHERS.keys())
def test_hiccup_leaves_other_errors_alone(tmp_path, line):
    assert not call(tmp_path, f'grep -qE -- "$HICCUP" <<< {shlex.quote(line)}')[0]


@pytest.mark.parametrize("files,line,rc", [
    (("dnf.sh",), CURL, 0),  # dnf5 holte die Metadaten von einem anderen Spiegel und endete mit 0
    (("dnf.sh",), "Curl error (6): Could not resolve hostname for https://mirrors.example.com/", 1),
    (("dnf.sh",), "Curl error (28): Timeout was reached for https://mirrors.example.com/", 1),
    (("zypper.sh",), HICCUPS["zypper.sh"][0], 4),
    (("apt.sh",), RESET, 0),  # apt update meldet einen Abbruch als W: und endet mit 0
    (("apt.sh",), MATCHES["apt-resolving"], 0),
    (("pacman.sh",), SLOW, 1),
    (("pacman.sh",), MATCHES["pacman-empty"], 1),
], ids=["dnf-56-exit-0", "dnf-6", "dnf-28", "zypper-timeout", "apt-reset", "apt-name", "pacman-slow", "pacman-empty"])
def test_network_hiccup_is_retried_then_passes(tmp_path, files, line, rc):
    ok, out, calls, slept = runs(tmp_path, "quiet pm", (line, rc), ("Metadata cache created.", 0), files=files)
    assert ok and calls == 2 and slept == ["10"], out
    assert "RETRY run 2 of 3 in 10 s: network hiccup" in out


def test_network_hiccup_three_times_fails(tmp_path):  # höchstens drei Läufe; ein vierter wäre sauber
    ok, out, calls, slept = runs(tmp_path, "quiet pm", *[(CURL, 0)] * 3, ("Metadata cache created.", 0))
    assert not ok and calls == 3 and slept == ["10", "10"], out
    assert out.count(f"NOISE {CURL}") == 3


@pytest.mark.parametrize("line,rc", [
    ("Error: GPG check FAILED", 1),
    ("Warning: skipped OpenPGP checks for 1 package from repository: @commandline", 0),
    ("Curl error (60): SSL certificate problem: unable to get local issuer certificate", 1),  # kein Aussetzer
    ("", 1),  # Fehler ohne Meldung
], ids=["gpg-check", "warning", "curl-60", "silent"])
def test_package_error_is_never_retried(tmp_path, line, rc):
    ok, out, calls, slept = runs(tmp_path, "quiet pm", (line, rc), ("Metadata cache created.", 0))
    assert not ok and calls == 1 and slept == [], out


def test_tampered_index_still_fails(tmp_path):
    """Der Manipulationstest (tampered in inside.sh, mit refused): Die Aktualisierung mit der veränderten Quelle läuft
    genau einmal, auch mit einem Aussetzer daneben. Lehnt sie ab, besteht er; nimmt sie an, scheitert er. In quiet
    ist eine abgelehnte Quelle kein Aussetzer."""
    for name, outputs, passed in [("refused", [(f"{CURL}\nError: Bad PGP signature", 1), ("", 0)], True),
                                  ("accepted", [(CURL, 0), ("Error: Bad PGP signature", 1)], False)]:
        ok, out, calls, slept = runs(tmp_path / name, "refused 'Bad PGP signature' pm", *outputs)
        assert ok is passed and calls == 1 and slept == [], out
    mismatch = ("E: Failed to fetch file:/tmp/matrix/tamper-index/apt/dists/stable/main/binary-all/Packages.gz  "
                "Hash Sum mismatch")
    ok, out, calls, slept = runs(tmp_path / "quiet", "quiet pm", (mismatch, 100), ("", 0), files=("apt.sh",))
    assert not ok and calls == 1 and slept == [], out


@pytest.mark.parametrize("outputs,passed,count", [
    ([(CURL, 0)], True, 1),  # net bewertet keine Meldungen: dnf fand einen anderen Spiegel
    ([(CURL, 1), ("", 0)], True, 2),
    ([(CURL, 1)] * 3 + [("", 0)], False, 3),
    ([("Error: Unable to find a match: orbitop", 1), ("", 0)], False, 1),
], ids=["exit-0", "hiccup-then-clean", "three-hiccups", "package-error"])
def test_net_repeats_only_a_failed_run_with_a_hiccup(tmp_path, outputs, passed, count):
    ok, out, calls, slept = runs(tmp_path, "net pm", *outputs)
    assert ok is passed and calls == count and slept == ["10"] * (count - 1), out
    assert out.count("RETRY run") == count - 1


@pytest.mark.parametrize("prelude,outputs", [
    ("", [(CURL, 1, "orbitop 0.2.0-1"), ("", 0)]),  # der gescheiterte Lauf installierte schon ein Paket
    ("packages() { return 1; };", [(CURL, 1), ("", 0)]),  # ohne Fingerabdruck kein zweiter Lauf
    ("packages() { :; };", [(CURL, 1), ("", 0)]),  # eine leere Liste ist kein Fingerabdruck
], ids=["packages-changed", "packages-unknown", "packages-empty"])
def test_hiccup_after_a_package_change_is_not_retried(tmp_path, prelude, outputs):
    ok, out, calls, slept = runs(tmp_path, f"{prelude} net pm", *outputs)
    assert not ok and calls == 1 and slept == [], out
    assert "NO RETRY: the installed packages changed or are unknown" in out


# dpkg-query gibt STATE/dpkg nur mit dem Format von apt.sh aus, sonst nichts.
DPKG = (r"""dpkg-query() { [ "$*" = '-W -f ${db:Status-Abbrev} ${binary:Package} ${Version}\n' ] &&"""
        r""" cat "$STATE/dpkg"; };""")


def test_apt_fingerprint_sees_a_status_change(tmp_path):
    """apt remove behält die conffiles: Version gleich, Status ii → rc. Der Fingerabdruck ändert sich."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "dpkg").write_text("ii  bash 5.2.37-2\nii  orbitop 0.2.0-1\n")
    command = f"""{DPKG} a=$(held) && sed -i 's/^ii  orbitop/rc  orbitop/' "$STATE/dpkg" && b=$(held) &&
        [ -n "$a" ] && [ "$a" != "$b" ]"""
    assert call(tmp_path, command, "apt.sh")[0]


AS_ROOT = pytest.mark.skipif(os.geteuid() == 0, reason="root liest und schreibt auch ohne die Rechte der Datei")


WARNING = "W: GPG error: file:/site/apt stable InRelease: NO_PUBKEY 0123456789ABCDEF"  # apt update endet mit 0


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


@AS_ROOT
@pytest.mark.parametrize("command,log,output", [("clean pm", "clean.out", (WARNING, 0)),
                                                ("net pm", "net.out", (CURL, 1))], ids=["clean", "net"])
def test_unreadable_capture_fails_clean_and_net_does_not_retry(tmp_path, command, log, output):
    """Der Befehl nimmt seiner Kopie das Leserecht: grep scheitert mit 2. clean scheitert dann, net wiederholt nicht."""
    unreadable = (f'pm() {{ echo >> "$STATE/calls"; cat "$STATE/out.1"; chmod 200 "$STATE/{log}";'
                  ' return "$(cat "$STATE/rc.1")"; };')
    ok, out, calls, slept = runs(tmp_path, f"{unreadable} {command}", output, ("", 0), files=("apt.sh",))
    assert not ok and calls == 1 and slept == [], out


@AS_ROOT
def test_a_stale_capture_file_never_decides(tmp_path):
    """Die Kopie eines früheren Laufs mit einem Aussetzer, die tee nicht überschreiben kann: Ein Fehler des Pakets im
    neuen Lauf wird trotzdem nicht wiederholt."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "net.out").write_text(CURL + "\n")
    (state / "net.out").chmod(0o400)
    ok, out, calls, slept = runs(tmp_path, "net pm", ("Error: Unable to find a match: orbitop", 1), ("", 0))
    assert not ok and calls == 1 and slept == [], out


@pytest.mark.parametrize("command,output,passed,count", [
    ("clean pm", (f"{WARNING}\n\0binary", 0), False, 1),  # GNU grep sähe sonst nur "binary file matches"
    ("net pm", (f"{CURL}\n\0binary", 1), True, 2),
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


HIT = ("Hit:1 http://deb.example.com/debian trixie InRelease", 0)  # quiet apt update vor dem Schritt
# Schritt, Paketverwaltung, Läufe von pm vor dem Aussetzer und nach dem sauberen Lauf.
STEPS = [*[("refresh", m, [], []) for m in MANAGERS],
         ("install_pkg", "apt.sh", [HIT], []), ("install_pkg", "dnf.sh", [], []), ("install_pkg", "pacman.sh", [], []),
         ("install_pkg", "zypper.sh", [], [("GPG Check               : (rp) Yes", 0)]),  # zypper lr
         *[("tools", m, [], []) for m in MANAGERS],
         ("update_from", "apt.sh", [HIT], []), *[("update_from", m, [], []) for m in MANAGERS if m != "apt.sh"],
         ("keyring", "dnf.sh", [], []),
         ("keyring", "zypper.sh", [], [("", 0)])]  # erst findutils, dann orbitop-release


@pytest.mark.parametrize("step,manager,before,after", STEPS, ids=[f"{s[0]}-{s[1][:-3]}" for s in STEPS])
def test_network_steps_retry_a_hiccup(tmp_path, step, manager, before, after):
    """Jeder Schritt, der von den Spiegeln holt, mit den echten Funktionen aus den Dateien der Paketverwaltungen und
    einer Quelle (ROOT) in tmp_path."""
    site = rpm_site(tmp_path)
    files = ("rpm.sh", manager) if manager in ("dnf.sh", "zypper.sh") else (manager,)
    outputs = [*before, HICCUPS[manager], ("", 0), *after]
    ok, out, calls, slept = runs(tmp_path, f"{step} {site}", *outputs, files=files)
    assert ok and calls == len(outputs) and slept == ["10"], out


def test_refusal_without_hiccup_is_not_retried(tmp_path):
    """Die erwartete Ablehnung auf debian:bookworm und ubuntu:22.04 (Python älter als 3.12): ein Lauf, die Meldung im
    Protokoll, nach der check-distros.sh sie erkennt."""
    refusal = (f"{OTHERS['apt-depends']}\nE: Unable to correct problems, you have held broken packages.")
    ok, out, calls, slept = runs(tmp_path, "install_pkg", HIT, (refusal, 100), ("", 0), files=("apt.sh",))
    assert not ok and calls == 2 and slept == [], out  # apt update, dann genau eine Installation
    assert "orbitop : Depends: python3 (>= 3.12)" in out


@pytest.mark.parametrize("manager,reason", [("apt.sh", "Hash Sum mismatch"), ("dnf.sh", "Bad PGP signature"),
                                            ("pacman.sh", "invalid or corrupted database (PGP signature)"),
                                            ("zypper.sh", "Signature verification failed for repomd.xml")])
def test_tamper_refresh_runs_once(tmp_path, manager, reason):  # refresh_index bleibt ohne net
    ok, out, calls, slept = runs(tmp_path, f"refused '{reason}' refresh_index", (f"{CURL}\n{reason}", 1), ("", 0),
                                 files=(manager,))
    assert ok and calls == 1 and slept == [], out
