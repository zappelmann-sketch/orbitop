# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/build-site.sh und packaging/site/: Seitenbaum, Signaturen nur auf dem Rechner, Vorlage index.html."""
import configparser
import hashlib
import os
import re
import subprocess

import pytest

from tests.packaging_common import APT_SOURCE, PKG, deb822
from tests.site_stub import LEAK, REPODATA, RPMS, SCRIPT, kill_agent, make_keys, needs_git, run

INDEX = PKG / "site" / "index.html"
PAGES = "https://zappelmann-sketch.github.io/orbitop/"
README = {"https://github.com/zappelmann-sketch/orbitop/blob/main/README.md",
          "https://github.com/zappelmann-sketch/orbitop/blob/main/README.de.md"}
VERSIONED = ("orbitop-0.2.0-1.noarch.rpm", "orbitop-release-2026.11.18-1.noarch.rpm")
ARCH_FILES = ("orbitop-0.2.0-1-any.pkg.tar.zst", "orbitop.db", "orbitop.files")


def constants():
    """Die Konstanten am Anfang von build-site.sh (NAME=wert)."""
    return dict(re.findall(r"^([A-Z_]+)=(\S+)$", SCRIPT.read_text(encoding="utf-8"), re.M))


def test_index_has_fingerprint_placeholder_and_no_external_urls():
    html = INDEX.read_text(encoding="utf-8")
    assert html.splitlines()[1:3] == ["<!-- SPDX-License-Identifier: GPL-3.0-or-later -->",
                                      "<!-- Copyright © 2026 zappelmann-sketch -->"]
    assert html.count("<FINGERPRINT>") == 2  # Englisch und Deutsch
    assert '<section lang="de">' in html
    targets = re.findall(r"""\b(?:src|href)\s*=\s*["']?([^"'\s>]+)""", html, re.I)
    assert targets and set(targets) <= README, targets
    assert not re.search(r"<script|<link|<iframe|<img|<object|@import|url\(", html, re.I)


def test_sources_template_matches_site_layout():
    c = constants()
    (source,) = deb822(APT_SOURCE / "orbitop.sources")
    assert source["URIs"] == PAGES + c["APT_DIR"]
    assert (source["Suites"], source["Components"]) == (c["APT_SUITE"], c["APT_COMPONENT"])
    for family in ("fedora", "opensuse"):
        repo = configparser.ConfigParser(interpolation=None)
        repo.read(PKG / "keyring" / f"orbitop-{family}.repo", encoding="utf-8")
        assert repo["orbitop"]["baseurl"] == PAGES + c[f"{family.upper()}_DIR"]
    assert c["ARCH_DIR"] == "arch/x86_64"  # Server = …/arch/$arch in pacman.conf (Spec 2)


@pytest.fixture(scope="module")
def key(tmp_path_factory):
    k = make_keys(tmp_path_factory.mktemp("site-key") / "gnupg")
    yield k
    kill_agent(k["home"])


def site_files(site):
    return sorted(str(p.relative_to(site)) for p in site.rglob("*") if p.is_file())


@needs_git
def test_build_site_tree_and_signatures(tmp_path, key):
    r, _ = run(tmp_path, key)
    assert r.returncode == 0, r.stderr
    site = tmp_path / "site"
    index = "apt/dists/stable/main/binary-all"
    blobs = [(site / index / name).read_bytes() for name in ("Packages", "Packages.gz")]
    assert site_files(site) == sorted([
        ".nojekyll", "index.html", "orbitop-archive-keyring.asc", "orbitop-archive-keyring.pgp",
        "apt/dists/stable/InRelease", "apt/dists/stable/Release", "apt/dists/stable/Release.gpg",
        f"{index}/Packages", f"{index}/Packages.gz",
        *(f"{index}/by-hash/{a}/{hashlib.new(a.lower(), b).hexdigest()}" for b in blobs for a in ("SHA256", "SHA512")),
        "apt/pool/main/o/orbitop/orbitop_0.2.0-1_all.deb",
        "apt/pool/main/o/orbitop-apt-source/orbitop-apt-source_2026.11.18_all.deb",
        *(f"rpm/{fam}/{name}" for fam in ("fedora", "opensuse") for name in (
            *VERSIONED, "repodata/repomd.xml", "repodata/repomd.xml.asc", "repodata/repomd.xml.key", *REPODATA)),
        *(f"arch/x86_64/{name}{sig}" for name in ARCH_FILES for sig in ("", ".sig"))])
    # Jede Signatur gilt mit dem öffentlichen Schlüssel allein; pacman will sie binär, apt und RPM armored
    arch, dists = site / "arch/x86_64", site / "apt/dists/stable"
    signed = [(dists / "InRelease",), (dists / "Release.gpg", dists / "Release")]
    signed += [(site / f"rpm/{fam}/repodata/repomd.xml.asc", site / f"rpm/{fam}/repodata/repomd.xml")
               for fam in ("fedora", "opensuse")]
    signed += [(arch / f"{name}.sig", arch / name) for name in ARCH_FILES]
    for files in signed:
        v = subprocess.run(["gpgv", "--keyring", str(key["pub"]), *map(str, files)], capture_output=True,
                           env={**os.environ, "GNUPGHOME": str(key["home"])})
        assert v.returncode == 0, (files, v.stderr)
        assert files[0].read_bytes().startswith(b"-----BEGIN PGP") == (files[0].parent != arch), files[0]
    assert (site / "orbitop-archive-keyring.pgp").read_bytes() == key["pub"].read_bytes()
    for fam in ("fedora", "opensuse"):  # die RPMs, wie rpmsign sie im Container signiert hat
        signed = (RPMS / f"{fam}-signed.rpm").read_bytes()
        assert {(site / f"rpm/{fam}/{n}").read_bytes() for n in VERSIONED} == {signed}
    # Nichts aus der gpg.conf des GNUPGHOME (comment, sig-notation, armor) erreicht die Seite
    assert not [p for p in site.rglob("*") if p.is_file() and LEAK.encode() in p.read_bytes()]
    html = (site / "index.html").read_text(encoding="utf-8")
    fpr = key["fpr"]
    grouped = " ".join(fpr[i:i + 4] for i in range(0, 20, 4)) + "  " + " ".join(fpr[i:i + 4] for i in range(20, 40, 4))
    assert "<FINGERPRINT>" not in html and html.count(grouped) == 2


@needs_git
def test_build_site_gives_containers_public_key_and_socket_only_for_rpmsign(tmp_path, key):
    r, calls = run(tmp_path, key)
    assert r.returncode == 0, r.stderr
    # Zuerst die Werkzeug-Images, gebaut ohne Socket; nur sie erhalten ihn später, dann ohne Netz
    assert [c[0] for c in calls] == ["build", "build", "run", "run", "run", "run"]
    assert [(c[c.index("-t") + 1], c[c.index("--build-arg") + 1]) for c in calls[:2]] == [
        ("orbitop-site-rpm-fedora:local", "BASE=fedora:latest"),
        ("orbitop-site-rpm-opensuse:local", "BASE=opensuse/tumbleweed")]
    socket = subprocess.run(["gpgconf", "--list-dirs", "agent-extra-socket"], capture_output=True, text=True,
                            env={**os.environ, "GNUPGHOME": str(key["home"])}).stdout.strip()
    agent = [f"type=bind,source={socket},target=/gnupg/S.gpg-agent"]
    steps = []
    for args in (c[1:] for c in calls[2:]):
        assert args[:6] == ["--rm", "-i", "--cap-drop", "MKNOD", "--cap-drop", "SETFCAP"], args
        assert not [a for a in args if a in ("--privileged", "--cap-add", "--network=host")]
        volumes = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
        assert [v.rsplit(":", 1)[-1] for v in volumes] == ["ro", "/out"], volumes
        offline = "--network" in args and args[args.index("--network") + 1] == "none"
        mounts = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
        steps.append((args[args.index("bash") - 1], args[args.index("bash") + 1].rsplit("/", 1)[-1], offline, mounts))
    assert steps == [("debian:trixie", "apt-inside.sh", False, []),
                     ("orbitop-site-rpm-fedora:local", "rpm-inside.sh", True, agent),
                     ("orbitop-site-rpm-opensuse:local", "rpm-inside.sh", True, agent),
                     ("archlinux:latest", "arch-inside.sh", True, [])]
    assert (tmp_path / "stdin.bin").read_bytes() == key["pub"].read_bytes() * 4  # nie ein geheimer Schlüssel
