# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/build-site.sh und packaging/site/: Seitenbaum, Signaturen nur auf dem Rechner, Vorlage index.html."""
import configparser
import os
import re
import shutil
import subprocess

import pytest

from tests.packaging_common import APT_SOURCE, PKG, ROOT, deb822

SCRIPT = ROOT / "scripts" / "build-site.sh"
INDEX = PKG / "site" / "index.html"
PAGES = "https://zappelmann-sketch.github.io/orbitop/"
README = {"https://github.com/zappelmann-sketch/orbitop/blob/main/README.md",
          "https://github.com/zappelmann-sketch/orbitop/blob/main/README.de.md"}
PACKAGES = ["deb/orbitop_0.2.0-1_all.deb", "deb/orbitop-apt-source_2026.11.18_all.deb",
            "rpm-fedora/orbitop-0.2.0-1.noarch.rpm", "rpm-fedora/orbitop-release-2026.11.18-1.noarch.rpm",
            "rpm-opensuse/orbitop-0.2.0-1.noarch.rpm", "rpm-opensuse/orbitop-release-2026.11.18-1.noarch.rpm",
            "arch/orbitop-0.2.0-1-any.pkg.tar.zst", "lint/orbitop_0.2.0-1_all.txt"]


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
    """Wegwerfschlüssel ohne Passphrase in einem eigenen GNUPGHOME, sein Agent wird am Ende beendet."""
    if not (shutil.which("gpg") and shutil.which("gpgv")):
        pytest.skip("gpg fehlt")
    home = tmp_path_factory.mktemp("site-key") / "gnupg"
    home.mkdir(mode=0o700)

    def gpg(*args):
        return subprocess.run(["gpg", "--homedir", str(home), "--batch", *args], check=True,
                              capture_output=True).stdout

    gpg("--passphrase", "", "--quick-gen-key", "Test Signing <test@example.com>", "ed25519", "sign", "1y")
    fpr = next(ln.split(":")[9] for ln in gpg("--with-colons", "--list-keys").decode().splitlines()
               if ln.startswith("fpr:"))
    (home.parent / "pub.pgp").write_bytes(gpg("--export", fpr))
    yield {"home": home, "fpr": fpr, "pub": home.parent / "pub.pgp"}
    subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "all"], capture_output=True)


def run(tmp_path, key, *, packages=PACKAGES, fpr=None, socket=None):
    """build-site.sh mit docker-Stellvertreter, der nur die Dateien der Container-Schritte anlegt."""
    pkgs = tmp_path / "pkgs"
    for name in packages:
        (pkgs / name).parent.mkdir(parents=True, exist_ok=True)
        (pkgs / name).write_bytes(name.encode())
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "docker").write_text(f"""#!/bin/sh
printf '%s\\n' "$@" >> {tmp_path}/docker.log
for a; do case $a in *:/out) out=${{a%:/out}} ;; /src/packaging/site/*) step=${{a##*/}} ;; esac; done
cat >> {tmp_path}/stdin.bin
case $step in
    apt-inside.sh) mkdir -p "$out/dists/stable" && echo 'Suite: stable' > "$out/dists/stable/Release" ;;
    rpm-inside.sh) mkdir -p "$out/repodata" && echo '<repomd/>' > "$out/repodata/repomd.xml" ;;
    arch-inside.sh) echo db > "$out/orbitop.db" && echo files > "$out/orbitop.files" ;;
esac
""")
    if socket:  # gpgconf meldet einen anderen Ort des extra-socket
        (fake / "gpgconf").write_text(f"""#!/bin/sh
[ "$1 $2" = "--list-dirs agent-extra-socket" ] && {{ echo {socket}; exit 0; }}
exec {shutil.which("gpgconf")} "$@"
""")
    for f in fake.iterdir():
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "GNUPGHOME": str(key["home"]),
           "ORBITOP_KEY": key["fpr"] if fpr is None else fpr}
    r = subprocess.run(["bash", str(SCRIPT), "--packages", str(pkgs), "--out", str(tmp_path / "site")],
                       capture_output=True, text=True, env=env)
    log = tmp_path / "docker.log"
    return r, log.read_text().splitlines() if log.exists() else []


def test_build_site_signs_on_host_with_public_key_only_in_containers(tmp_path, key):
    r, calls = run(tmp_path, key)
    assert r.returncode == 0, r.stderr
    site = tmp_path / "site"
    assert sorted(str(p.relative_to(site)) for p in site.rglob("*") if p.is_file()) == sorted([
        ".nojekyll", "index.html", "orbitop-archive-keyring.asc", "orbitop-archive-keyring.pgp",
        "apt/dists/stable/InRelease", "apt/dists/stable/Release", "apt/dists/stable/Release.gpg",
        "apt/pool/main/o/orbitop/orbitop_0.2.0-1_all.deb",
        "apt/pool/main/o/orbitop-apt-source/orbitop-apt-source_2026.11.18_all.deb",
        *(f"rpm/{fam}/{name}" for fam in ("fedora", "opensuse") for name in (
            "orbitop-0.2.0-1.noarch.rpm", "orbitop-release-2026.11.18-1.noarch.rpm",
            "repodata/repomd.xml", "repodata/repomd.xml.asc", "repodata/repomd.xml.key")),
        *(f"arch/x86_64/{name}" for name in ("orbitop-0.2.0-1-any.pkg.tar.zst", "orbitop-0.2.0-1-any.pkg.tar.zst.sig",
                                             "orbitop.db", "orbitop.db.sig", "orbitop.files", "orbitop.files.sig"))])
    # Jede Signatur gilt mit dem öffentlichen Schlüssel allein; pacman will sie binär, apt und RPM armored
    arch, dists, signed = site / "arch/x86_64", site / "apt/dists/stable", [(site / "apt/dists/stable/InRelease",)]
    signed += [(dists / "Release.gpg", dists / "Release")]
    signed += [(site / f"rpm/{fam}/repodata/repomd.xml.asc", site / f"rpm/{fam}/repodata/repomd.xml")
               for fam in ("fedora", "opensuse")]
    signed += [(arch / f"{name}.sig", arch / name)
               for name in ("orbitop-0.2.0-1-any.pkg.tar.zst", "orbitop.db", "orbitop.files")]
    for files in signed:
        v = subprocess.run(["gpgv", "--keyring", str(key["pub"]), *map(str, files)], capture_output=True)
        assert v.returncode == 0, (files, v.stderr)
        assert files[0].read_bytes().startswith(b"-----BEGIN PGP") == (files[0].parent != arch), files[0]
    assert (site / "orbitop-archive-keyring.pgp").read_bytes() == key["pub"].read_bytes()
    html = (site / "index.html").read_text(encoding="utf-8")
    fpr = key["fpr"]
    grouped = " ".join(fpr[i:i + 4] for i in range(0, 20, 4)) + "  " + " ".join(fpr[i:i + 4] for i in range(20, 40, 4))
    assert "<FINGERPRINT>" not in html and html.count(grouped) == 2

    starts = [i for i, a in enumerate(calls) if a == "run"]
    runs = [calls[i + 1:j] for i, j in zip(starts, [*starts[1:], len(calls)])]
    socket = subprocess.run(["gpgconf", "--list-dirs", "agent-extra-socket"], capture_output=True, text=True,
                            env={**os.environ, "GNUPGHOME": str(key["home"])}).stdout.strip()
    steps = []
    for args in runs:
        assert args[:2] == ["--rm", "-i"], args
        assert not [a for a in args if a in ("--privileged", "--cap-add", "--network=host")]
        mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
        step = args[args.index("bash") + 1].rsplit("/", 1)[-1]
        steps.append((args[args.index("bash") - 1], step))
        # Nur rpmsign bekommt etwas vom Agenten, und dann nur dessen eingeschränkten Socket
        agent = [f"{socket}:/gnupg/S.gpg-agent"] if step == "rpm-inside.sh" else []
        assert [m.rsplit(":", 1)[-1] for m in mounts[:2]] == ["ro", "/out"] and mounts[2:] == agent, mounts
    assert steps == [("debian:trixie", "apt-inside.sh"), ("fedora:latest", "rpm-inside.sh"),
                     ("opensuse/tumbleweed", "rpm-inside.sh"), ("archlinux:latest", "arch-inside.sh")]
    assert (tmp_path / "stdin.bin").read_bytes() == key["pub"].read_bytes() * 4  # nie ein geheimer Schlüssel


@pytest.mark.parametrize("case", ["no-key", "bad-key", "foreign-key", "old-site", "two-versions", "no-socket"])
def test_build_site_refuses_before_any_container(tmp_path, key, case):
    kwargs, expect = {
        "no-key": ({"fpr": ""}, "ORBITOP_KEY"),
        "bad-key": ({"fpr": "0x1234"}, "ORBITOP_KEY"),
        "foreign-key": ({"fpr": "A" * 40}, "no secret key"),
        "old-site": ({}, "--out"),
        "two-versions": ({"packages": [*PACKAGES, "deb/orbitop_0.1.0-1_all.deb"]}, "exactly one deb/orbitop_*"),
        "no-socket": ({"socket": tmp_path / "missing" / "S.gpg-agent.extra"}, "extra socket"),
    }[case]
    if case == "old-site":
        (tmp_path / "site").mkdir()
        (tmp_path / "site" / "index.html").write_text("")
    r, calls = run(tmp_path, key, **kwargs)
    assert (r.returncode, calls) == (1, []), r.stderr
    assert expect in r.stderr
