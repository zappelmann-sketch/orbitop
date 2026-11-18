# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Kleine apt-Bäume für die Tests: minimale debs und ein Index wie von apt-ftparchive (Packages, Packages.gz,
by-hash, Release). Auch als Programm für den docker-Stellvertreter:
python3 -I apt_tree.py index APTDIR SUITE COMP [forge]   (forge: SHA256 von orbitop in Packages gefälscht)."""
import gzip
import hashlib
import io
import shutil
import sys
import tarfile
from pathlib import Path

HASHES = (("MD5sum", "MD5Sum", "md5"), ("SHA1", "SHA1", "sha1"), ("SHA256", "SHA256", "sha256"),
          ("SHA512", "SHA512", "sha512"))


def _ar_member(name, data):
    head = f"{name:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n".encode()
    return head + data + (b"\n" if len(data) % 2 else b"")


def _tar_xz(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def make_deb(path, package, version, extra=""):
    """Ein deb mit control-Datei und leerem Datenteil, gebaut wie von dpkg-deb (ar, control.tar.xz)."""
    control = (f"Package: {package}\nVersion: {version}\nArchitecture: all\nMaintainer: user <user@example.com>\n"
               f"{extra}Description: test package\n a test package for the apt index check\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"!<arch>\n" + _ar_member("debian-binary", b"2.0\n")
                     + _ar_member("control.tar.xz", _tar_xz({"./control": control.encode()}))
                     + _ar_member("data.tar.xz", _tar_xz({})))


def stanza(apt, path):
    """Die Stanza eines debs, wie apt-ftparchive sie schreibt: control plus Filename, Size und Hashes."""
    data = (apt / path).read_bytes()
    pos = data.index(b"control.tar.xz")
    member = data[pos + 60:pos + 60 + int(data[pos + 48:pos + 58])]
    with tarfile.open(fileobj=io.BytesIO(member), mode="r:xz") as tar:
        text = tar.extractfile("./control").read().decode()
    fields = "".join(f"{field}: {hashlib.new(algo, data).hexdigest()}\n" for field, _, algo in HASHES)
    return text + f"Filename: {path}\nSize: {len(data)}\n" + fields


def write_index(apt, suite, component, packages=None):
    """Packages (sonst aus den debs unter pool/), Packages.gz, by-hash und Release, passend zueinander."""
    apt = Path(apt)
    debs = sorted(str(p.relative_to(apt)) for p in (apt / "pool").rglob("*.deb"))
    packages = "\n".join(stanza(apt, d) for d in debs) if packages is None else packages
    index = apt / "dists" / suite / component / "binary-all"
    index.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(index / "by-hash", ignore_errors=True)  # nur die Kopien des neuen Index
    blobs = {"Packages": packages.encode(), "Packages.gz": gzip.compress(packages.encode(), mtime=0)}
    lines = {field: "" for _, field, _ in HASHES}
    for name, data in blobs.items():
        (index / name).write_bytes(data)
        for _, field, algo in HASHES:
            h = hashlib.new(algo, data).hexdigest()
            lines[field] += f"\n {h} {len(data):>16} {component}/binary-all/{name}"
            if field in ("SHA256", "SHA512"):
                (index / "by-hash" / field).mkdir(parents=True, exist_ok=True)
                (index / "by-hash" / field / h).write_bytes(data)
    head = (f"Acquire-By-Hash: yes\nArchitectures: all\nCodename: {suite}\nComponents: {component}\n"
            f"Date: Thu, 01 Jan 2026 00:00:00 +0000\nLabel: orbitop\nOrigin: orbitop\nSuite: {suite}\n")
    (apt / "dists" / suite / "Release").write_text(head + "".join(f"{f}:{v}\n" for f, v in lines.items()))


def forged(apt):
    """Packages, dessen SHA256 des ersten Pakets auf ein anderes zeigt; Packages.gz und Release passen dazu."""
    apt = Path(apt)
    debs = sorted(str(p.relative_to(apt)) for p in (apt / "pool").rglob("*.deb"))
    text = "\n".join(stanza(apt, d) for d in debs)
    old = text.split("SHA256: ", 1)[1].split("\n", 1)[0]
    return text.replace(old, "0" * 64, 1)


if __name__ == "__main__":
    _, command, apt, suite, component, *mode = sys.argv
    if command == "index":
        write_index(apt, suite, component, forged(apt) if mode == ["forge"] else None)
