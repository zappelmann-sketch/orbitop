# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Prüfungen der Container-Matrix, die ohne root laufen: scripts/matrix/lib.sh und Teile der Dateien der
Paketverwaltungen, mit Stellvertretern für rpm und rpmkeys (tests/matrix_helpers.py). Jede Funktion läuft wie in
step, ohne set -e."""
import gzip
import hashlib
import inspect
import re

import pytest

from orbitop import __version__, actions
from tests.matrix_helpers import PAGES, call, rpm_site
from tests.packaging_common import ROOT


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


FPR = "57B9C66DCA7AE595D49760EE49D4A78C4130D679"


@pytest.mark.parametrize("content,passed", [
    (f"{FPR}:3:\n", True), (f"{FPR}:4:\n", False), (f"{FPR}:2:\n", False), (f"{FPR}:3:", False),
    (f"{FPR}:3:\n{FPR}:3:\n", False), (f"{FPR}:3:\n\n", False), (f"{FPR.lower()}:3:\n", False),
    (f"{FPR[:-1]}:3:\n", False), (f" {FPR}:3:\n", False), (f"{FPR}:3:\0\n", False), ("", False), (None, False)],
    ids=["never", "marginal", "unknown", "no-newline", "two-lines", "empty-line", "lower", "short", "blank", "nul",
         "empty", "missing"])
def test_pacman_trust_of_the_installed_key_is_never(tmp_path, content, passed):
    """Audit M3: orbitop-trusted des installierten Pakets ist genau eine Zeile <Fingerabdruck>:3: (Owner-Trust
    "never"), geprüft im Schritt install der Matrix auf Arch."""
    trusted = tmp_path / "orbitop-trusted"
    if content is not None:
        trusted.write_text(content)
    ok, out = call(tmp_path, f"TRUSTED={trusted}; never_introducer", "pacman.sh")
    assert ok is passed, out


def share(tmp_path, body):
    """Ein installierter Baum SHARE wie /usr/share/orbitop, dessen orbitop.actions.real_pkexec() BODY ausführt."""
    pkg = tmp_path / "share" / "orbitop"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "actions.py").write_text(f"def real_pkexec():\n    {body}\n")
    return pkg.parent


@pytest.mark.parametrize("body,passed", [("return True", True), ("return False", False), ("raise OSError", False)])
def test_real_pkexec_asks_the_installed_orbitop(tmp_path, body, passed):
    """Final review I2: der Schritt install verlangt, dass das installierte orbitop /usr/bin/pkexec mit seiner eigenen,
    strengeren Prüfung annimmt (actions.real_pkexec); sonst fehlte dort still das Beenden fremder Prozesse."""
    ok, out = call(tmp_path, f"real_pkexec {share(tmp_path, body)}")
    assert ok is passed, out


def test_real_pkexec_takes_orbitop_only_from_share(tmp_path):
    """Aus / mit python3 -I: weder der Arbeitsordner noch PYTHONPATH bringt ein anderes orbitop. Der Köder dort nimmt
    jedes pkexec an; SHARE hat kein orbitop, also muss die Prüfung scheitern (Plan 1, Audit Task 8)."""
    decoy = share(tmp_path / "decoy", "return True")
    (tmp_path / "share").mkdir()
    ok, out = call(tmp_path, f"cd {decoy} && real_pkexec {tmp_path / 'share'}", env={"PYTHONPATH": str(decoy)})
    assert not ok and "PKEXEC refused" in out, out


def test_real_pkexec_needs_no_arguments():  # real_pkexec in lib.sh ruft actions.real_pkexec() ohne Argumente
    assert all(p.default is not p.empty for p in inspect.signature(actions.real_pkexec).parameters.values())


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


def test_src_version_reads_the_tree(tmp_path):  # inside.sh (Schritt version) und counters.sh (upgrade_from_020)
    ok, out = call(tmp_path, f'[ "$(src_version {ROOT})" = {__version__} ] && [ -z "$(src_version {tmp_path} 2> /dev/null)" ]')
    assert ok, out
