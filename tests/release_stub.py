# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsames der Tests von scripts/release.sh: ein Wegwerf-Repository mit den Release-Skripten und einem
entfernten Repository (lokal, ohne Netz), Stellvertreter für die Bau-Skripte, git, gh, curl und docker."""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from tests.packaging_common import APP, ROOT

VERSION = next(ln.split('"')[1] for ln in (ROOT / "orbitop" / "__init__.py").read_text().splitlines()
               if ln.startswith("__version__"))
KV = (ROOT / "packaging" / "keyring.version").read_text().strip()
COPIED = [*(["scripts/release.sh"] if (ROOT / "scripts" / "release.sh").exists() else []), "scripts/container-common.sh", "packaging/changelog.py", "packaging/keyring.version",
          f"data/{APP}.metainfo.xml", "README.md", "README.de.md", "docs/distro-check.md", "orbitop/__init__.py",
          *(str(p.relative_to(ROOT)) for p in sorted((ROOT / "scripts" / "release").glob("*")) if p.is_file())]
REAL_GIT = shutil.which("git")
GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
# Die Bau-Skripte als Stellvertreter: Sie schreiben nur die Dateinamen, die release.sh liest.
BUILD_PACKAGES = f"""#!/bin/sh
printf '%s\\n' build-packages "$@" ---- >> "$LOG_DIR/calls.log"
while [ $# -gt 0 ]; do case $1 in --out) out=$2 ;; --pubkey) cp "$2" "$LOG_DIR/pubkey.asc" ;; --suffix) s=$2 ;; esac
    shift 2; done
mkdir -p "$out/deb" "$out/rpm-fedora" "$out/rpm-opensuse" "$out/arch" "$out/lint"
echo "rebuilt $out" > "$out/deb/orbitop_{VERSION}-1${{s:++$s}}_all.deb"
echo "rebuilt $out" > "$out/deb/orbitop-apt-source_{KV}_all.deb"
for f in fedora opensuse; do
    echo "rebuilt $out" > "$out/rpm-$f/orbitop-{VERSION}-1${{s:+.$s}}.noarch.rpm"
    echo "rebuilt $out" > "$out/rpm-$f/orbitop-release-{KV}-1.noarch.rpm"
done
echo "rebuilt $out" > "$out/arch/orbitop-{VERSION}-1${{s:+.1}}-any.pkg.tar.zst"
[ "$FAIL" != packages ]
"""
BUILD_SITE = """#!/bin/sh
printf '%s\\n' build-site "$@" ---- >> "$LOG_DIR/calls.log"
while [ $# -gt 0 ]; do case $1 in --packages) p=$2 ;; --out) out=$2 ;; esac; shift 2; done
apt=$out/apt/dists/stable/main/binary-all
mkdir -p "$out/apt/pool/main/o/orbitop" "$out/apt/pool/main/o/orbitop-apt-source" "$apt/by-hash/SHA256" \\
    "$out/arch/x86_64"
cp "$p"/deb/orbitop_*.deb "$out/apt/pool/main/o/orbitop/"
cp "$p"/deb/orbitop-apt-source_*.deb "$out/apt/pool/main/o/orbitop-apt-source/"
echo "Packages $out" > "$apt/Packages"
cp "$apt/Packages" "$apt/by-hash/SHA256/$(sha256sum < "$apt/Packages" | cut -d' ' -f1)"
echo "InRelease $out" > "$out/apt/dists/stable/InRelease"
[ "$FAIL" != site ] || exit 1
for f in fedora opensuse; do
    mkdir -p "$out/rpm/$f/repodata" && cp "$p"/rpm-$f/*.rpm "$out/rpm/$f/"
    echo "repomd $out" > "$out/rpm/$f/repodata/repomd.xml" && echo "asc $out" > "$out/rpm/$f/repodata/repomd.xml.asc"
done
cp "$p"/arch/*.zst "$out/arch/x86_64/"
echo "db $out" > "$out/arch/x86_64/orbitop.db" && echo "sig $out" > "$out/arch/x86_64/orbitop.db.sig"
gpg --no-options --batch --armor --export "$ORBITOP_KEY" > "$out/orbitop-archive-keyring.asc"
gpg --no-options --batch --export "$ORBITOP_KEY" > "$out/orbitop-archive-keyring.pgp"
: > "$out/.nojekyll"
"""
CHECK_DISTROS = """#!/bin/sh
printf '%s\\n' check-distros "$@" ---- >> "$LOG_DIR/calls.log"
cat "$LOG_DIR/matrix.txt"
exit "${MATRIX_RC:-0}"
"""
GIT = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/git.log"
exec "$REAL_GIT" "$@"
"""
# gh: release create nur mit dem Tag im entfernten Repository (--verify-tag), die Anhänge nach LOG_DIR/assets;
# GitHub Pages ist an, sobald LOG_DIR/pages-on da ist.
GH = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/gh.log"
case "$1 $2" in
    "release create")
        "$REAL_GIT" --git-dir "$REMOTE" rev-parse -q --verify "refs/tags/$3" > /dev/null || exit 1
        mkdir -p "$LOG_DIR/assets"
        for a; do [ ! -f "$a" ] || cp "$a" "$LOG_DIR/assets/"; done ;;
    "api -X") touch "$LOG_DIR/pages-on" ;;
    "api repos/zappelmann-sketch/orbitop/pages")
        [ -f "$LOG_DIR/pages-on" ] && echo "gh-pages /" && exit 0
        echo "gh: Not Found (HTTP 404)" >&2 && exit 1 ;;
esac
"""
# curl: GitHub Pages liefert den Zweig gh-pages des entfernten Repositorys aus.
CURL = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/curl.log"
while [ $# -gt 1 ]; do [ "$1" = -o ] && out=$2 && shift; shift; done
"$REAL_GIT" --git-dir "$REMOTE" cat-file blob "gh-pages:${1#https://zappelmann-sketch.github.io/orbitop/}" > "$out"
"""
# docker: rpm -K für ein veröffentlichtes RPM auf stdin; "TAMPERED" darin hat keine gültige Signatur.
DOCKER = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/docker.log"
if grep -q TAMPERED; then echo "/tmp/p.rpm: digests SIGNATURES NOT OK"; else echo "/tmp/p.rpm: digests signatures OK"; fi
"""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git(cwd, *args):
    return subprocess.run([REAL_GIT, *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV}).stdout


def matrix_output(fpr):
    """Was check-distros.sh ausgibt: je Image der Container-Lauf, dann KEY und die RESULT-Zeilen."""
    digest = "debian@sha256:" + "1" * 64
    return f"""KEY {fpr}
IMAGE debian:trixie
PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
VERSION_ID="13"
VERSIONS python 3.13.5 pygobject 3.50.0 gtk 4.18.6 webkitgtk 2.54.0
1000 passed, 50 skipped in 30.25s
VERSION before {VERSION}-1, offered {VERSION}-1+check1, after {VERSION}-1+check1
IMAGE debian:bookworm
VERSION_ID="12"
PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"
 orbitop : Depends: python3 (>= 3.12) but 3.11.2-1+b1 is to be installed
KEY {fpr}
RESULT debian:trixie {digest} pass -
RESULT debian:bookworm {digest.replace("1", "2")} pass install
"""


def make_repo(tmp_path, fpr, readme=None):
    """Wegwerf-Repository auf main mit den Release-Skripten und Stellvertretern für die Bau-Skripte, origin ein
    lokales bare-Repository; die Matrix meldet den Schlüssel FPR, die READMEs nennen README statt <FINGERPRINT>.
    Gibt die Pfade zurück."""
    repo, remote, bin_ = tmp_path / "repo", tmp_path / "remote.git", tmp_path / "bin"
    for name in COPIED:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, repo / name)
    for name, text in {"build-packages.sh": BUILD_PACKAGES, "build-site.sh": BUILD_SITE,
                       "check-distros.sh": CHECK_DISTROS}.items():
        (repo / "scripts" / name).write_text(text)
    for name in ("README.md", "README.de.md") if readme else ():
        (repo / name).write_text((repo / name).read_text().replace("<FINGERPRINT>", readme))
    (repo / "tests").mkdir()
    for name in ("test_ok.py", "test_readme.py"):  # die strenge Suite und der README-Abgleich nach der Matrix
        (repo / "tests" / name).write_text("def test_ok():\n    pass\n")
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    git(repo.parent, "init", "-q", "-b", "main", str(repo))
    for key, value in (("user.name", "Test"), ("user.email", "test@example.com"), ("remote.origin.url", str(remote)),
                       ("remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")):
        git(repo, "config", key, value)
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "push", "-q", "origin", "main")
    bin_.mkdir()
    for name, text in {"git": GIT, "gh": GH, "curl": CURL, "docker": DOCKER}.items():
        (bin_ / name).write_text(text)
        (bin_ / name).chmod(0o755)
    (tmp_path / "matrix.txt").write_text(matrix_output(fpr))
    (tmp_path / "tmp").mkdir()
    return {"repo": repo, "remote": remote, "bin": bin_}


def publish_pages(tmp_path, paths, files):
    """Ein früheres Release: der Zweig gh-pages im entfernten Repository mit FILES (Pfad -> Bytes)."""
    work = tmp_path / "old-pages"
    for name, data in files.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_bytes(data)
    git(tmp_path, "init", "-q", "-b", "gh-pages", str(work))
    git(work, "add", ".")
    git(work, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-q", "-m", "old")
    git(work, "push", "-q", str(paths["remote"]), "gh-pages")


def run(tmp_path, paths, key, *args, env=()):
    """release.sh mit den Stellvertretern; gibt das Ergebnis und die Aufrufe je Werkzeug zurück (je Aufruf seine
    Argumente)."""
    env = {**os.environ, **GIT_ENV, "PATH": f"{paths['bin']}:{os.environ['PATH']}", "LOG_DIR": str(tmp_path),
           "REAL_GIT": REAL_GIT, "REMOTE": str(paths["remote"]), "GNUPGHOME": str(key["home"]),
           "ORBITOP_KEY": key["fpr"], "TMPDIR": str(tmp_path / "tmp"), **dict(env)}
    r = subprocess.run(["bash", str(paths["repo"] / "scripts" / "release.sh"), *args], capture_output=True, text=True,
                       cwd=tmp_path, env=env, timeout=180)
    calls = {}
    for tool in ("calls", "git", "gh", "curl", "docker"):
        log = tmp_path / f"{tool}.log"
        calls[tool], cur = [], []
        for line in log.read_text().splitlines() if log.exists() else []:
            if line == "----":
                calls[tool], cur = [*calls[tool], cur], []
            else:
                cur.append(line)
    return r, calls
