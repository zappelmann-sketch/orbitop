# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""packaging/site/check-apt-index.py: der Rechner signiert den apt-Index nur, wenn er genau die debs beschreibt."""
import re
import subprocess
import sys

import pytest

from tests.apt_tree import make_deb, stanza, write_index
from tests.packaging_common import PKG

CHECK = PKG / "site" / "check-apt-index.py"
DEBS = ["pool/main/o/orbitop/orbitop_0.2.0-1_all.deb",
        "pool/main/o/orbitop-apt-source/orbitop-apt-source_2026.11.18_all.deb"]
INDEX = "dists/stable/main/binary-all"


@pytest.fixture
def apt(tmp_path):
    apt = tmp_path / "apt"
    make_deb(apt / DEBS[0], "orbitop", "0.2.0-1", "Depends: python3\n")
    make_deb(apt / DEBS[1], "orbitop-apt-source", "2026.11.18")
    write_index(apt, "stable", "main")
    return apt


def check(apt):
    return subprocess.run([sys.executable, "-I", str(CHECK), str(apt), "stable", "main", *DEBS],
                          capture_output=True, text=True)


def packages(apt):
    return "\n".join(stanza(apt, d) for d in DEBS)


def test_accepts_the_index_of_the_debs(apt):
    r = check(apt)
    assert (r.returncode, r.stderr) == (0, "")


def forge(apt, case):
    text, release = packages(apt), apt / "dists/stable/Release"
    sha = text.split("SHA256: ", 1)[1].split("\n", 1)[0]
    if case == "extra-file":
        (apt / "dists/stable/notes.txt").write_text("x")
    elif case == "extra-deb":  # ein weiteres Paket, im Index richtig eingetragen
        make_deb(apt / "pool/main/e/evil/evil_1_all.deb", "evil", "1")
        write_index(apt, "stable", "main")
    elif case == "filename":
        write_index(apt, "stable", "main", text.replace(f"Filename: {DEBS[0]}", "Filename: pool/evil.deb"))
    elif case == "sha256":
        write_index(apt, "stable", "main", text.replace(sha, "0" * 64, 1))
    elif case == "conflicts":  # Felder, die apt beim Auflösen nutzt, kommen nur aus dem deb
        write_index(apt, "stable", "main", text.replace("Package: orbitop\n", "Package: orbitop\nConflicts: sudo\n"))
    elif case == "third-stanza":
        write_index(apt, "stable", "main", text + "\nPackage: evil\nVersion: 1\nFilename: pool/x.deb\n")
    elif case == "by-hash":
        next((apt / INDEX / "by-hash/SHA256").iterdir()).write_text("other")
    elif case == "missing-by-hash":
        next((apt / INDEX / "by-hash/SHA512").iterdir()).unlink()
    elif case == "gz":
        (apt / INDEX / "Packages.gz").write_bytes(b"\x1f\x8b" + b"0" * 20)
    elif case == "release-entry":
        release.write_text(release.read_text().replace(
            "SHA256:\n", f"SHA256:\n {'0' * 64} 1 main/binary-all/Packages.xz\n"))
    elif case == "release-size":
        release.write_text(re.sub(r"(SHA256:\n \S+\s+)(\d+)", lambda m: m[1] + str(int(m[2]) + 1),
                                  release.read_text(), count=1))
    elif case == "release-field":
        release.write_text("Signed-By: 0000000000000000000000000000000000000000\n" + release.read_text())
    elif case in ("space-line", "tab-line"):  # apt liest die Zeile als Folgezeile und verschmilzt beide Stanzas
        blank = " " if case == "space-line" else "\t"
        write_index(apt, "stable", "main", f"{blank}\n".join(stanza(apt, d) for d in DEBS))
    elif case == "control-char":  # apt behält \x1c im Hash, str.strip() hätte es entfernt
        write_index(apt, "stable", "main", text.replace(sha, sha + "\x1c", 1))
    elif case in ("future-date", "bad-date"):
        date = "Fri, 01 Jan 2100 00:00:00 +0000" if case == "future-date" else "01 Jan 2026 00:00:00 +0000"
        release.write_text(re.sub(r"(?m)^Date: .*$", f"Date: {date}", release.read_text()))
    elif case in ("release-cr", "release-crlf"):  # apt liest \r als Teil des Werts, read_text() machte \n daraus
        old, new = (b"\nOrigin", b"\rOrigin") if case == "release-cr" else (b"\n", b"\r\n")
        release.write_bytes(release.read_bytes().replace(old, new))


@pytest.mark.parametrize("case, reason", [
    ("extra-file", "unexpected files"), ("extra-deb", "unexpected files"),
    ("filename", "differs from its deb in ['Filename']"), ("sha256", "differs from its deb in ['SHA256']"),
    ("conflicts", "differs from its deb in ['Conflicts']"), ("third-stanza", "Packages lists"),
    ("by-hash", "is no copy"), ("missing-by-hash", "missing"), ("gz", "apt index:"),
    ("release-entry", "Release SHA256 lists"), ("release-size", "Release SHA256 lists"),
    ("release-field", "Release fields"), ("space-line", "whitespace-only line"),
    ("tab-line", "whitespace-only line"), ("control-char", "control character"),
    ("future-date", "is in the future"), ("bad-date", "does not match format"),
    ("release-cr", "control character"), ("release-crlf", "control character")])
def test_refuses_a_forged_index(apt, case, reason):
    forge(apt, case)
    r = check(apt)
    assert r.returncode == 1 and r.stderr.startswith("apt index:") and reason in r.stderr, r.stderr


def test_release_fields_match_apt_inside():  # was der Container schreiben soll, verlangt die Prüfung
    inside = (PKG / "site" / "apt-inside.sh").read_text(encoding="utf-8")
    for option in ("Release::Origin=orbitop", "Release::Label=orbitop", "Release::Architectures=all",
                   "Release::Acquire-By-Hash=yes"):
        assert option in inside
