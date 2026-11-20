# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""packaging/site/rpm-same.py: build-site.sh nimmt ein von rpmsign signiertes RPM nur an, wenn es ab dem Haupt-Header
byte-gleich mit dem unsignierten aus build-packages.sh ist. Die Paare in tests/fixtures/rpm/ sind echt: dasselbe
orbitop-release, einmal aus build-packages.sh und einmal von build-site.sh mit einem Wegwerfschlüssel signiert, aus
Fedora (rpm 6, Platz für die Signatur reserviert, gleiche Größe) und Tumbleweed (rpm 4.20, der Signatur-Header
wächst)."""
import subprocess
import sys

import pytest

from tests.packaging_common import PKG, ROOT

SCRIPT = PKG / "site" / "rpm-same.py"
RPMS = ROOT / "tests" / "fixtures" / "rpm"
LEAD = 96


def same(tmp_path, signed, unsigned):
    paths = []
    for name, data in (("signed.rpm", signed), ("unsigned.rpm", unsigned)):
        (tmp_path / name).write_bytes(data)
        paths.append(str(tmp_path / name))
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *paths], capture_output=True, text=True)


def fixture(name):
    return (RPMS / f"{name}.rpm").read_bytes()


def main_header(data):
    """Wo der Haupt-Header beginnt: nach Lead und Signatur-Header samt Auffüllung auf 8 Bytes."""
    count, size = int.from_bytes(data[LEAD + 8:LEAD + 12], "big"), int.from_bytes(data[LEAD + 12:LEAD + 16], "big")
    end = LEAD + 16 + 16 * count + size
    return end + -end % 8


@pytest.mark.parametrize("family", ["fedora", "opensuse"])
def test_accepts_the_signed_package_of_its_input(tmp_path, family):
    signed, unsigned = fixture(f"{family}-signed"), fixture(f"{family}-unsigned")
    assert signed != unsigned
    r = same(tmp_path, signed, unsigned)
    assert r.returncode == 0, r.stderr
    # dieselben Bytes auf beiden Seiten, hier die unsignierten: so kommt ein RPM, das schon gültig signiert war (das
    # wiederverwendete orbitop-release), unverändert aus rpm-inside.sh zurück
    assert same(tmp_path, unsigned, unsigned).returncode == 0


def test_refuses_another_package(tmp_path):
    r = same(tmp_path, fixture("opensuse-signed"), fixture("fedora-unsigned"))
    assert r.returncode == 1 and "header or payload differ" in r.stderr, r.stderr


@pytest.mark.parametrize("where", ["header", "payload"])
def test_refuses_a_changed_byte_after_the_signature(tmp_path, where):
    signed = bytearray(fixture("fedora-signed"))
    pos = main_header(signed) + 40 if where == "header" else len(signed) - 10
    signed[pos] ^= 0xFF
    r = same(tmp_path, bytes(signed), fixture("fedora-unsigned"))
    assert r.returncode == 1, r.stderr


def test_ignores_the_signature_header(tmp_path):  # dort schreibt rpmsign; geprüft wird sie mit rpm -K
    signed = bytearray(fixture("fedora-signed"))
    signed[main_header(signed) - 20] ^= 0xFF
    assert same(tmp_path, bytes(signed), fixture("fedora-unsigned")).returncode == 0


@pytest.mark.parametrize("data", [b"", b"not an rpm\n" * 20, fixture("fedora-signed")[:LEAD + 16],
                                  fixture("fedora-signed")[:LEAD] + b"\0" * 64],
                         ids=["empty", "text", "cut", "no-signature-header"])
def test_refuses_what_is_no_rpm(tmp_path, data):
    r = same(tmp_path, data, fixture("fedora-unsigned"))
    assert r.returncode == 1 and r.stderr, r.stderr


def test_usage():
    r = subprocess.run([sys.executable, "-I", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 2 and "usage:" in r.stderr
