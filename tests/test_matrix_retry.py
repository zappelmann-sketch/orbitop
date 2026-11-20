# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Netzaussetzer der Spiegel in der Container-Matrix: net und quiet in scripts/matrix/lib.sh wiederholen einen
gescheiterten Lauf, der einen Aussetzer meldet; jeder andere Fehler zählt sofort, der Manipulationstest läuft einmal.
Die Programme der Paketverwaltungen sind Shell-Funktionen, die pm aufrufen."""
import pytest

from tests.test_matrix_lib import call

# Ersatz-Paketmanager pm: Lauf N gibt STATE/out.N aus und endet mit STATE/rc.N (fehlen sie: nichts, 0); jeder Lauf
# hängt eine Zeile an STATE/calls. sleep schreibt seine Dauer nach STATE/slept, statt zu warten.
PM = ('pm() { echo >> "$STATE/calls"; local n; n=$(wc -l < "$STATE/calls"); cat "$STATE/out.$n" 2> /dev/null;'
      ' return "$(cat "$STATE/rc.$n" 2> /dev/null || echo 0)"; }; sleep() { echo "$1" >> "$STATE/slept"; };')
AS_PM = {"apt.sh": 'apt() { pm "$@"; }; apt-get() { pm "$@"; }; apt-cache() { echo policy; };',
         "dnf.sh": 'dnf() { pm "$@"; };', "zypper.sh": 'zypper() { pm "$@"; };', "pacman.sh": 'pacman() { pm "$@"; };'}
CURL = (">>> Curl error (56): Failure when receiving data from the peer for https://mirrors.fedoraproject.org/"
        "metalink?repo=updates-released-f45&arch=x86_64 [Recv failure: Connection reset by peer]")  # 2026-11-19
RESET = ("W: Failed to fetch http://deb.example.com/debian/dists/trixie/InRelease  Error reading from server - read "
         "(104: Connection reset by peer)")
# Ein Aussetzer je Paketverwaltung, mit ihrem Exit-Code.
HICCUPS = {
    "apt.sh": (RESET, 100),
    "dnf.sh": (CURL, 1),
    "pacman.sh": ("error: failed retrieving file 'core.db' from mirror.example.com : Could not resolve host: "
                  "mirror.example.com", 1),
    "zypper.sh": ("Download (curl) error for 'https://download.example.com/repodata/repomd.xml':\nError code: "
                  "Connection failed\nError message: Operation timed out after 60000 milliseconds", 4),
}
MANAGERS = sorted(HICCUPS)
# Die Läufe von pm vor und nach dem Schritt der Paketverwaltung, der von den Spiegeln holt.
AROUND = {("apt.sh", "install_pkg"): ([("Hit:1 http://deb.example.com/debian trixie InRelease", 0)], []),
          ("zypper.sh", "install_pkg"): ([], [("GPG Check               : (rp) Yes", 0)])}


def runs(tmp_path, command, *outputs, files=("dnf.sh",)):
    """COMMAND nach lib.sh und FILES mit pm (auch als Programme von FILES), dessen Lauf N outputs[N-1] = (Ausgabe, rc)
    liefert; gibt (bestanden, Ausgabe, Zahl der Läufe von pm, Pausen) zurück."""
    state = tmp_path / "state"
    state.mkdir(parents=True)
    for n, (text, rc) in enumerate(outputs, 1):
        (state / f"out.{n}").write_text(text + "\n")
        (state / f"rc.{n}").write_text(f"{rc}\n")
    stand_ins = " ".join(AS_PM[f] for f in files if f in AS_PM)
    ok, out = call(tmp_path, f"{PM} {stand_ins} {command}", *files)
    calls = (state / "calls").read_text().count("\n") if (state / "calls").exists() else 0
    slept = (state / "slept").read_text().split() if (state / "slept").exists() else []
    return ok, out, calls, slept


@pytest.mark.parametrize("files,line,rc", [
    (("dnf.sh",), CURL, 0),  # dnf5 holte die Metadaten von einem anderen Spiegel und endete mit 0
    (("dnf.sh",), "Curl error (6): Could not resolve hostname for https://mirrors.example.com/", 1),
    (("dnf.sh",), "Curl error (28): Timeout was reached for https://mirrors.example.com/", 1),
    (("zypper.sh",), HICCUPS["zypper.sh"][0], 4),
    (("apt.sh",), RESET, 0),  # apt update meldet einen Abbruch als W: und endet mit 0
    # nur das Muster: apt selbst schreibt "Could not resolve '<host>'" (Probe in debian:trixie, 2026-11-20)
    (("apt.sh",), "W: Failed to fetch http://deb.example.com/  Temporary failure in name resolution", 0),
    (("pacman.sh",), "error: failed retrieving file 'core.db' from mirror.example.com : Curl error (35): TLS", 1),
    (("pacman.sh",), "error: failed retrieving file 'core.db' from mirror.example.com : Curl error (52): Empty", 1),
], ids=["dnf-56-exit-0", "dnf-6", "dnf-28", "zypper-timeout", "apt-reset", "apt-name", "pacman-35", "pacman-52"])
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


@pytest.mark.parametrize("manager", MANAGERS)
@pytest.mark.parametrize("step", ["refresh", "install_pkg"])
def test_network_steps_retry_a_hiccup(tmp_path, manager, step):
    """refresh und install holen von den Spiegeln; apt prüft vor der Installation den Index (quiet apt update), zypper
    danach die Quelle (zypper lr)."""
    before, after = AROUND.get((manager, step), ([], []))
    outputs = [*before, HICCUPS[manager], ("", 0), *after]
    ok, out, calls, slept = runs(tmp_path, step, *outputs, files=(manager,))
    assert ok and calls == len(outputs) and slept == ["10"], out


def test_refusal_without_hiccup_is_not_retried(tmp_path):
    """Die erwartete Ablehnung auf debian:bookworm und ubuntu:22.04 (Python älter als 3.12): ein Lauf, die Meldung im
    Protokoll, nach der check-distros.sh sie erkennt."""
    refusal = (" orbitop : Depends: python3 (>= 3.12) but 3.11.2-1+b1 is to be installed\n"
               "E: Unable to correct problems, you have held broken packages.")
    ok, out, calls, slept = runs(tmp_path, "install_pkg", ("Hit:1 http://deb.example.com/debian bookworm InRelease", 0),
                                 (refusal, 100), ("", 0), files=("apt.sh",))
    assert not ok and calls == 2 and slept == [], out  # apt update, dann genau eine Installation
    assert "orbitop : Depends: python3 (>= 3.12)" in out


@pytest.mark.parametrize("manager,reason", [("apt.sh", "Hash Sum mismatch"), ("dnf.sh", "Bad PGP signature"),
                                            ("pacman.sh", "invalid or corrupted database (PGP signature)"),
                                            ("zypper.sh", "Signature verification failed for repomd.xml")])
def test_tamper_refresh_runs_once(tmp_path, manager, reason):  # refresh_index bleibt ohne net
    ok, out, calls, slept = runs(tmp_path, f"refused '{reason}' refresh_index", (f"{CURL}\n{reason}", 1), ("", 0),
                                 files=(manager,))
    assert ok and calls == 1 and slept == [], out
