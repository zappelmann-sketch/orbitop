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
    --import) echo "e652ba57-6afe03a5: Test Signing <test@example.com> public key" >> "$STATE/keys" ;;
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


@pytest.mark.parametrize("report,passed", [("digests signatures OK", True), ("digests OK", False),
                                           ("digests SIGNATURES NOT OK", False)])
def test_rpm_key_requires_a_signature_on_every_rpm(tmp_path, report, passed):  # rpm -K: "digests OK" ohne Signatur
    root = rpm_site(tmp_path)
    ok, out = call(tmp_path, f"FAMILY=opensuse; rpm_key {root}", "rpm.sh", env={"RPMK": report})
    assert ok is passed, out
    assert (tmp_path / "state" / "rpmkey").read_text() == "e652ba57-6afe03a5\n"


@pytest.mark.parametrize("env,passed", [({}, True), ({"KEEP": "1"}, False), ({"LIST_FAILS": "1"}, False)])
def test_drop_key_fails_when_the_key_stays_or_the_listing_fails(tmp_path, env, passed):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "rpmkey").write_text("e652ba57-6afe03a5\n")
    call(tmp_path, "true")  # legt keys an
    (tmp_path / "state" / "keys").write_text("e652ba57-6afe03a5: Test Signing <test@example.com> public key\n")
    ok, out = call(tmp_path, "drop_key", "rpm.sh", env=env)
    assert ok is passed, out


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
