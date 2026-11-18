# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Checks on the host the apt index that apt-inside.sh wrote in a container, before scripts/build-site.sh signs it.

Usage: python3 -I check-apt-index.py APTDIR SUITE COMPONENT POOLPATH…
APTDIR may hold only the debs POOLPATH… (already compared with --packages), dists/SUITE/Release, Packages,
Packages.gz and their by-hash copies. Each stanza of Packages must be the control file of one deb plus its true
Filename, Size and hashes. Release must list exactly Packages and Packages.gz with their true sizes and hashes, and
nothing but the fields apt-inside.sh writes. Any difference or error exits 1 with a message: nothing gets signed.
"""
import gzip
import hashlib
import io
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

PACKAGES_HASHES = {"MD5sum": "md5", "SHA1": "sha1", "SHA256": "sha256", "SHA512": "sha512"}
RELEASE_HASHES = {"MD5Sum": "md5", "SHA1": "sha1", "SHA256": "sha256", "SHA512": "sha512"}
BY_HASH = ("SHA256", "SHA512")  # the copies apt-ftparchive writes with DoByHash
RELEASE_FIXED = {"Origin": "orbitop", "Label": "orbitop", "Architectures": "all", "Acquire-By-Hash": "yes"}
RELEASE_DATE = "%a, %d %b %Y %H:%M:%S +0000"  # RFC 2822 in UTC, as apt-ftparchive writes it (C locale)
DATE_SLACK = timedelta(minutes=10)  # apt refuses a Release dated in the future as "not valid yet"


class Refused(Exception):
    pass


def paragraphs(text):
    """deb822 paragraphs as dicts; a continuation line is kept with its newline, a repeated field is refused.

    Only an empty line ends a paragraph: apt reads a line of blanks as a continuation line, so it is refused, and so is
    any character but printable ones, space and tab, which apt and this parser might split or strip differently."""
    paras, cur, key = [], {}, None
    for line in text.split("\n"):
        if not line:
            if cur:
                paras.append(cur)
            cur, key = {}, None
        elif not line.strip(" \t"):
            raise Refused(f"whitespace-only line {line!r}: apt does not end a paragraph there")
        elif not line.replace("\t", " ").isprintable():
            raise Refused(f"control character or other whitespace in {line!r}")
        elif line[0] in " \t":
            if key is None:
                raise Refused(f"continuation line without a field: {line!r}")
            cur[key] += "\n" + line
        else:
            key, sep, value = line.partition(":")
            if not sep or key in cur:
                raise Refused(f"bad or repeated field: {line!r}")
            cur[key] = value.strip(" \t")
    return paras + [cur] if cur else paras


def control(deb):
    """The control paragraph of a deb: the member control.tar.* of the ar archive, file ./control."""
    data = deb.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise Refused(f"not a deb: {deb}")
    pos = 8
    while pos + 60 <= len(data):
        name, size = data[pos:pos + 16].decode().strip().rstrip("/"), int(data[pos + 48:pos + 58])
        if name.startswith("control.tar"):
            with tarfile.open(fileobj=io.BytesIO(data[pos + 60:pos + 60 + size]), mode="r:*") as tar:
                names = [m.name for m in tar.getmembers() if m.isfile() and m.name.lstrip("./") == "control"]
                (para,) = paragraphs(tar.extractfile(names[0]).read().decode())
                return para
        pos += 60 + size + size % 2
    raise Refused(f"no control.tar in {deb}")


def digest(data, algo):
    return hashlib.new(algo, data).hexdigest()


def check_tree(apt, suite, component, debs):
    """(a) Exactly the expected files; returns the bytes of Packages and Packages.gz by their path."""
    index = f"dists/{suite}/{component}/binary-all"
    blobs = {p: (apt / p).read_bytes() for p in (f"{index}/Packages", f"{index}/Packages.gz")}
    if gzip.decompress(blobs[f"{index}/Packages.gz"]) != blobs[f"{index}/Packages"]:
        raise Refused("Packages.gz is not Packages")
    copies = {f"{index}/by-hash/{a}/{digest(b, a.lower())}": b for b in blobs.values() for a in BY_HASH}
    expected = {*debs, f"dists/{suite}/Release", *blobs, *copies}
    found = {str(p.relative_to(apt)) for p in apt.rglob("*") if not p.is_dir()}
    if found != expected:
        raise Refused(f"unexpected files {sorted(found - expected)}, missing {sorted(expected - found)}")
    for path, data in copies.items():
        if (apt / path).read_bytes() != data:
            raise Refused(f"{path} is no copy of the index it is named after")
    return blobs


def check_packages(apt, packages, debs):
    """(b) One stanza per deb, equal to its control file plus its Filename, Size and hashes, nothing else."""
    want = {}
    for path in debs:
        data = (apt / path).read_bytes()
        para = {**control(apt / path), "Filename": path, "Size": str(len(data)),
                **{field: digest(data, algo) for field, algo in PACKAGES_HASHES.items()}}
        if para["Package"] in want:
            raise Refused(f"two debs of {para['Package']}")
        want[para["Package"]] = para
    stanzas = paragraphs(packages.decode())
    if sorted(s.get("Package", "") for s in stanzas) != sorted(want):
        raise Refused(f"Packages lists {[s.get('Package') for s in stanzas]}, not {sorted(want)}")
    for stanza in stanzas:
        para = want[stanza["Package"]]
        if stanza != para:
            raise Refused(f"the stanza of {stanza['Package']} differs from its deb in "
                          f"{sorted(k for k in stanza.keys() | para.keys() if stanza.get(k) != para.get(k))}")


def check_release(apt, suite, component, blobs):
    """(c) The fixed fields, a Date not in the future, per hash exactly Packages and Packages.gz (true size, hash)."""
    (release,) = paragraphs((apt / f"dists/{suite}/Release").read_text(encoding="utf-8"))
    date = datetime.strptime(release.pop("Date", ""), RELEASE_DATE).replace(tzinfo=timezone.utc)
    if date > datetime.now(timezone.utc) + DATE_SLACK:
        raise Refused(f"Release Date {date} is in the future: apt would refuse the source as not valid yet")
    for field, algo in RELEASE_HASHES.items():
        listed = sorted(tuple(line.split()) for line in release.pop(field, "").split("\n") if line.strip())
        true = sorted((digest(b, algo), str(len(b)), path.split("/", 2)[2]) for path, b in blobs.items())
        if listed != true:
            raise Refused(f"Release {field} lists {listed}, not {true}")
    fixed = {**RELEASE_FIXED, "Suite": suite, "Codename": suite, "Components": component}
    if release != fixed:
        raise Refused(f"Release fields {release}, not {fixed}")


def main(argv):
    apt, suite, component, *debs = argv
    if not debs:
        raise Refused("no deb given")
    apt = Path(apt)
    blobs = check_tree(apt, suite, component, debs)
    check_packages(apt, blobs[f"dists/{suite}/{component}/binary-all/Packages"], debs)
    check_release(apt, suite, component, blobs)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:  # every error refuses: the host must not sign an index it could not check
        sys.exit(f"apt index: {error}")
