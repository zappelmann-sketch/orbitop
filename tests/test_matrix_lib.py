# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Prüfungen der Container-Matrix, die ohne root laufen: scripts/matrix/lib.sh und Teile der Dateien der
Paketverwaltungen, mit Stellvertretern für rpm und rpmkeys. Jede Funktion läuft wie in step, ohne set -e."""
import gzip
import hashlib
import os
import re
import subprocess

import pytest

from tests.packaging_common import ROOT

MATRIX = ROOT / "scripts" / "matrix"
PAGES = "https://zappelmann-sketch.github.io/orbitop/"
# rpm --import legt einen Schlüssel in keys ab, rpm -K meldet für jede Datei $RPMK; rpmkeys liest und löscht dort.
RPM = """#!/bin/sh
case $1 in
    --import) [ -n "$KNOWN" ] || echo "e652ba57-6afe03a5: orbitop archive signing key public key" >> "$STATE/keys" ;;
    -K) shift; for f; do echo "$f: $RPMK"; done ;;
esac
"""
RPMKEYS = """#!/bin/sh
case $1 in
    --list) [ -z "$LIST_FAILS" ] || exit 1; cat "$STATE/keys" ;;
    --delete) [ -n "$KEEP" ] || grep -v "^$2:" "$STATE/keys" > "$STATE/keys.new"; mv "$STATE/keys.new" "$STATE/keys" ;;
esac
"""


def call(tmp_path, command, *files, env=()):
    """COMMAND nach lib.sh und FILES aus scripts/matrix, mit STATE in tmp_path und rpm/rpmkeys-Stellvertretern;
    gibt (bestanden, Ausgabe) zurück."""
    state, fake = tmp_path / "state", tmp_path / "stubs"
    for d in (state, fake):
        d.mkdir(exist_ok=True)
    (state / "keys").touch()
    for name, text in {"rpm": RPM, "rpmkeys": RPMKEYS}.items():
        (fake / name).write_text(text)
        (fake / name).chmod(0o755)
    sourced = " ".join(f". {MATRIX / f};" for f in ("lib.sh", *files))
    r = subprocess.run(["bash", "-c", f"{sourced} if {command}; then echo PASSED; else echo FAILED; fi"],
                       capture_output=True, text=True, timeout=30,
                       env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "STATE": str(state), **dict(env)})
    assert r.stdout.splitlines()[-1] in {"PASSED", "FAILED"}, r.stderr
    return r.stdout.splitlines()[-1] == "PASSED", r.stdout


def rpm_site(tmp_path):
    root = tmp_path / "site"
    (root / "rpm" / "opensuse").mkdir(parents=True)
    for name in ("orbitop-0.2.0-1.noarch.rpm", "orbitop-release-2026.11.18-1.noarch.rpm"):
        (root / "rpm" / "opensuse" / name).write_bytes(b"rpm")
    (root / "orbitop-archive-keyring.asc").write_text("key\n")
    return root


@pytest.mark.parametrize("env,passed", [({"RPMK": "digests signatures OK"}, True), ({"RPMK": "digests OK"}, False),
                                        ({"RPMK": "digests SIGNATURES NOT OK"}, False),
                                        ({"RPMK": "digests signatures OK", "KNOWN": "1"}, False)])
def test_rpm_key_requires_a_signature_on_every_rpm(tmp_path, env, passed):  # rpm -K: "digests OK" ohne Signatur
    root = rpm_site(tmp_path)
    ok, out = call(tmp_path, f"FAMILY=opensuse; rpm_key {root}", "rpm.sh", env=env)
    assert ok is passed, out  # KNOWN: rpm --import brachte keinen neuen Schlüssel


@pytest.mark.parametrize("env,passed", [({}, True), ({"KEEP": "1"}, False), ({"LIST_FAILS": "1"}, False)])
def test_drop_key_fails_when_the_key_stays_or_the_listing_fails(tmp_path, env, passed):
    """Wie die README: jeder Schlüssel mit dem Namen des Archivschlüssels geht, auch ein erneuerter; andere bleiben."""
    call(tmp_path, "true")  # legt keys an
    (tmp_path / "state" / "keys").write_text("e652ba57-6afe03a5: orbitop archive signing key public key\n"
                                             "e652ba57-6c0a1b2c: orbitop archive signing key public key\n"
                                             "12345678-6afe03a5: Other Key <other@example.com> public key\n")
    ok, out = call(tmp_path, "drop_key", "rpm.sh", env=env)
    assert ok is passed, out
    if passed:
        assert (tmp_path / "state" / "keys").read_text().startswith("12345678-")


def test_point_rewrites_from_the_package_and_refuses_a_file_changed_meanwhile(tmp_path):
    repo = tmp_path / "orbitop.repo"
    packaged = f"[orbitop]\nbaseurl={PAGES}rpm/opensuse\ngpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-orbitop\n"
    repo.write_text(packaged)
    assert call(tmp_path, f"point {repo} file:///site/")[0]
    assert repo.read_text() == packaged.replace(PAGES, "file:///site/")
    assert call(tmp_path, f"point {repo} file:///site2/")[0]
    repo.write_text(repo.read_text() + "type=rpm-md\n")  # wie wenn die Paketverwaltung die Datei umschriebe
    ok, out = call(tmp_path, f'point {repo} "$PAGES"')
    assert not ok and f"changed since the last point: {repo}" in out
    assert repo.read_text().endswith("type=rpm-md\n")  # nicht überschrieben
    repo.write_text(packaged.replace(PAGES, "file:///site2/"))
    assert call(tmp_path, f'point {repo} "$PAGES"')[0] and repo.read_text() == packaged


def test_forget_checks_the_file_and_lets_point_start_over(tmp_path):  # die Paketverwaltung installiert sie neu
    repo = tmp_path / "orbitop.sources"
    repo.write_text(f"URIs: {PAGES}apt\n")
    assert call(tmp_path, f"point {repo} file:///site2/")[0]
    repo.write_text("URIs: file:///elsewhere/apt\n")
    ok, out = call(tmp_path, f"forget {repo}")
    assert not ok and "changed since the last point" in out
    repo.write_text(f"URIs: file:///site2/apt\n")
    assert call(tmp_path, f"forget {repo}")[0]
    repo.write_text(f"URIs: {PAGES}apt\n")  # neu installiert
    assert call(tmp_path, f"point {repo} file:///tamper/")[0] and repo.read_text() == "URIs: file:///tamper/apt\n"


def test_absent_names_what_is_left(tmp_path):
    (tmp_path / "lists").mkdir()
    (tmp_path / "lists" / "deb.example.com_dists_stable_InRelease").touch()
    assert call(tmp_path, f"absent '{tmp_path}/lists/*_site*'")[0]
    (tmp_path / "lists" / "_site2_apt_dists_stable_InRelease").touch()
    ok, out = call(tmp_path, f"absent '{tmp_path}/lists/*zappelmann*' '{tmp_path}/lists/*_site*'")
    assert not ok and "_site2_apt_dists_stable_InRelease" in out


# Ersatz-Paketmanager pm: Lauf N gibt STATE/out.N aus und endet mit STATE/rc.N (fehlen sie: nichts, 0); jeder Lauf
# hängt eine Zeile an STATE/calls. sleep schreibt seine Dauer nach STATE/slept, statt zu warten.
PM = ('pm() { echo >> "$STATE/calls"; local n; n=$(wc -l < "$STATE/calls"); cat "$STATE/out.$n" 2> /dev/null;'
      ' return "$(cat "$STATE/rc.$n" 2> /dev/null || echo 0)"; }; sleep() { echo "$1" >> "$STATE/slept"; };')
CURL = (">>> Curl error (56): Failure when receiving data from the peer for https://mirrors.fedoraproject.org/"
        "metalink?repo=updates-released-f45&arch=x86_64 [Recv failure: Connection reset by peer]")  # 2026-11-19


def runs(tmp_path, command, *outputs, files=("dnf.sh",)):
    """COMMAND nach lib.sh und FILES mit pm, dessen Lauf N outputs[N-1] = (Ausgabe, rc) liefert; gibt (bestanden,
    Ausgabe, Zahl der Läufe von pm, Pausen) zurück."""
    state = tmp_path / "state"
    state.mkdir(parents=True)
    for n, (text, rc) in enumerate(outputs, 1):
        (state / f"out.{n}").write_text(text + "\n")
        (state / f"rc.{n}").write_text(f"{rc}\n")
    ok, out = call(tmp_path, f"{PM} {command}", *files)
    calls = (state / "calls").read_text().count("\n") if (state / "calls").exists() else 0
    slept = (state / "slept").read_text().split() if (state / "slept").exists() else []
    return ok, out, calls, slept


@pytest.mark.parametrize("files,line,rc", [
    (("dnf.sh",), CURL, 0),  # dnf5 holte die Metadaten von einem anderen Spiegel und endete mit 0
    (("dnf.sh",), "Curl error (6): Could not resolve hostname for https://mirrors.example.com/", 1),
    (("dnf.sh",), "Curl error (28): Timeout was reached for https://mirrors.example.com/", 1),
    (("zypper.sh",), "Download (curl) error for 'https://download.example.com/':\nError code: Connection failed\n"
                     "Error message: Operation timed out after 60000 milliseconds", 4),
    (("apt.sh",), "W: Failed to fetch http://deb.example.com/dists/stable/InRelease  Could not resolve host: "
                  "deb.example.com", 0),
    (("apt.sh",), "W: Failed to fetch http://deb.example.com/dists/stable/InRelease  Temporary failure in name "
                  "resolution", 0),
    (("pacman.sh",), "error: failed retrieving file 'core.db' from mirror.example.com : Curl error (35): TLS", 1),
    (("pacman.sh",), "error: failed retrieving file 'core.db' from mirror.example.com : Curl error (52): Empty", 1),
], ids=["dnf-56-exit-0", "dnf-6", "dnf-28", "zypper-timeout", "apt-host", "apt-name", "pacman-35", "pacman-52"])
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


def changed(before, after):
    return [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]


INRELEASE = b"""-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA512

Origin: orbitop
Date: Wed, 18 Nov 2026 20:07:41 +0000
Architectures: all
-----BEGIN PGP SIGNATURE-----

AAAA
-----END PGP SIGNATURE-----
"""


def test_apt_tamper_changes_the_signed_date_and_the_index_everywhere(tmp_path):
    dists = tmp_path / "site" / "apt" / "dists" / "stable"
    index = dists / "main" / "binary-all"
    for algo in ("SHA256", "SHA512"):
        (index / "by-hash" / algo).mkdir(parents=True)
    (dists / "InRelease").write_bytes(INRELEASE)
    packages = b"Package: orbitop\nVersion: 0.2.0-1\n" * 20
    gz = gzip.compress(packages, mtime=0)
    for name, data in (("Packages", packages), ("Packages.gz", gz)):
        (index / name).write_bytes(data)
        (index / "by-hash" / "SHA256" / hashlib.sha256(data).hexdigest()).write_bytes(data)
        (index / "by-hash" / "SHA512" / hashlib.sha512(data).hexdigest()).write_bytes(data)
    assert call(tmp_path, f"change_release {tmp_path / 'site'}", "apt.sh")[0]
    after = (dists / "InRelease").read_bytes()
    assert changed(INRELEASE, after) == [INRELEASE.index(b"20:07:41") + 7]  # die letzte Ziffer der Sekunden
    assert re.search(rb"^Date: Wed, 18 Nov 2026 20:07:4\d \+0000$", after, re.M)
    assert call(tmp_path, f"change_index {tmp_path / 'site'}", "apt.sh")[0]
    new = (index / "Packages.gz").read_bytes()
    assert len(changed(gz, new)) == 1
    assert (index / "by-hash" / "SHA256" / hashlib.sha256(gz).hexdigest()).read_bytes() == new
    assert (index / "by-hash" / "SHA512" / hashlib.sha512(gz).hexdigest()).read_bytes() == new
    assert (index / "by-hash" / "SHA256" / hashlib.sha256(packages).hexdigest()).read_bytes() == packages


def test_rpm_tamper_changes_one_digit_of_the_revision(tmp_path):
    repodata = tmp_path / "site" / "rpm" / "fedora" / "repodata"
    repodata.mkdir(parents=True)
    repomd = b'<?xml version="1.0"?>\n<repomd>\n  <revision>1763496461</revision>\n</repomd>\n'
    (repodata / "repomd.xml").write_bytes(repomd)
    assert call(tmp_path, f"FAMILY=fedora; tamper_index {tmp_path / 'site'}", "rpm.sh")[0]
    after = (repodata / "repomd.xml").read_bytes()
    assert changed(repomd, after) == [repomd.index(b"<revision>") + 10]
    assert re.search(rb"<revision>\d{10}</revision>", after)
