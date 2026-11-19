# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsames der Tests von scripts/release.sh: ein Wegwerf-Repository mit den Release-Skripten und einem
entfernten Repository (lokal, ohne Netz), Stellvertreter für die Bau-Skripte, git, gh, curl, docker, gpg-agent und
gpgconf."""
import hashlib
import os
import re
import shutil
import subprocess
import time

from tests.packaging_common import APP, ROOT

VERSION = next(ln.split('"')[1] for ln in (ROOT / "orbitop" / "__init__.py").read_text().splitlines()
               if ln.startswith("__version__"))
KV = (ROOT / "packaging" / "keyring.version").read_text().strip()
COPIED = ["scripts/release.sh", "scripts/container-common.sh", "packaging/changelog.py", "packaging/keyring.version",
          f"data/{APP}.metainfo.xml", "README.md", "README.de.md", "docs/distro-check.md", "orbitop/__init__.py",
          *(str(p.relative_to(ROOT)) for p in sorted((ROOT / "scripts" / "release").glob("*")) if p.is_file())]
REAL = {tool: shutil.which(tool) for tool in ("git", "gpg-agent", "gpgconf", "rm")}
GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
# Die Identität des Projekts (öffentlich, in jedem Commit); release.sh verlangt genau sie.
NAME, NOREPLY = "zappelmann-sketch", "235797375+zappelmann-sketch@users.noreply.github.com"
TOOLS = ("calls", "git", "gh", "curl", "docker", "gpg-agent", "gpgconf")
# Die Bau-Skripte als Stellvertreter: Sie schreiben nur die Dateinamen, die release.sh liest.
BUILD_PACKAGES = f"""#!/bin/sh
printf '%s\\n' build-packages "$@" ---- >> "$LOG_DIR/calls.log"
while [ $# -gt 0 ]; do
    case $1 in --out) out=$2 ;; --pubkey) cp "$2" "$LOG_DIR/pubkey.asc" ;; --suffix) s=$2 ;; esac
    shift 2
done
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
sha256sum "$p"/deb/*.deb >> "$LOG_DIR/site-inputs.txt"  # was build-site.sh bekam
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
# MATRIX_COMMIT: während der Matrix committet ein anderer Prozess (eine andere Sitzung) im Repository.
CHECK_DISTROS = """#!/bin/sh
printf '%s\\n' check-distros "$@" ---- >> "$LOG_DIR/calls.log"
[ -z "$MATRIX_COMMIT" ] || "$REAL_GIT" -C "$REPO" commit -q --allow-empty -m other
cat "$LOG_DIR/matrix.txt"
exit "${MATRIX_RC:-0}"
"""
LOGGED = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/{tool}.log"
exec {real} "$@"
"""
# git: wie LOGGED; die Push-Adressen von origin sind die von GitHub (ORIGIN_PUSH), gepusht wird ins lokale Remote.
GIT = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/git.log"
case " $* " in *" remote get-url --all --push origin "*)
    printf '%s\\n' "${{ORIGIN_PUSH-https://github.com/zappelmann-sketch/orbitop.git}}"; exit 0 ;;
esac
exec {real} "$@"
"""
# gh: angemeldet (GH_AUTH_RC), Admin (GH_ADMIN); release create nur mit dem Tag im entfernten Repository
# (--verify-tag), die Anhänge nach LOG_DIR/assets; GitHub Pages ist an, sobald LOG_DIR/pages-on da ist. order.log
# hält die Reihenfolge von gh und curl fest.
GH = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/gh.log"
echo "gh $1 $2" >> "$LOG_DIR/order.log"
case "$1 $2" in
    "auth status") exit "${GH_AUTH_RC:-0}" ;;
    "api repos/zappelmann-sketch/orbitop") echo "${GH_ADMIN:-true}" ;;
    "release create")
        "$REAL_GIT" --git-dir "$REMOTE" rev-parse -q --verify "refs/tags/$3" > /dev/null || exit 1
        mkdir -p "$LOG_DIR/assets"
        for a; do [ ! -f "$a" ] || cp "$a" "$LOG_DIR/assets/"; done ;;
    "api -X") touch "$LOG_DIR/pages-on" ;;
    "api repos/zappelmann-sketch/orbitop/pages")
        [ -f "$LOG_DIR/pages-on" ] && echo "gh-pages /" && exit 0
        echo "gh: Not Found (HTTP 404)" >&2 && exit 1 ;;
esac
exit 0
"""
# rm: scheitert mit RM_FAILS, wie an root-eigenen Resten eines abgebrochenen Containers.
RM = f"""#!/bin/sh
[ -z "$RM_FAILS" ] || exit 1
exec {REAL["rm"]} "$@"
"""
# curl: GitHub Pages liefert den Zweig gh-pages des entfernten Repositorys aus.
CURL = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/curl.log"
echo curl >> "$LOG_DIR/order.log"
while [ $# -gt 1 ]; do [ "$1" = -o ] && out=$2 && shift; shift; done
"$REAL_GIT" --git-dir "$REMOTE" cat-file blob "gh-pages:${1#https://zappelmann-sketch.github.io/orbitop/}" > "$out"
"""
# docker: führt das Skript des Containers (bash -c, letztes Argument) hier aus, mit dem Schlüssel aus -e KEY=… und
# Stellvertretern für rpmkeys und rpm in RPM_BIN; die rpm-Datenbank hat schon den Schlüssel des Image ("distro").
DOCKER = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/docker.log"
for a; do case $a in KEY=*) KEY=${a#KEY=} ;; esac; done
export TMPDIR=$LOG_DIR/container  # the container's own /tmp, not the TMPDIR of release.sh
mkdir -p "$TMPDIR" && RPMDB=$(mktemp -d) && echo "distro-key: Distro <distro@example.com> public key" > "$RPMDB/keys"
export KEY RPMDB PATH="$RPM_BIN:$PATH"
shift $(($# - 1))
exec bash -c "$1"
"""
RPMKEYS = """#!/bin/sh
case $1 in
    --list) cat "$RPMDB/keys" ;;
    --delete) grep -v "^$2[: ]" "$RPMDB/keys" > "$RPMDB/new"; mv "$RPMDB/new" "$RPMDB/keys" ;;
    --import) grep -q "BEGIN PGP PUBLIC KEY" "$2" && echo "orbitop-key: orbitop archive signing key" >> "$RPMDB/keys" ;;
esac
"""
# rpm -K: gültig, wenn das RPM "signed-by:NAME" trägt und NAME-key in der rpm-Datenbank liegt.
RPM = """#!/bin/sh
signer=$(sed -n 's/^signed-by://p' "$2")
if [ -n "$signer" ] && grep -q "^$signer-key:" "$RPMDB/keys"; then echo "$2: digests signatures OK"
else echo "$2: digests SIGNATURES NOT OK" && exit 1; fi
"""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git(cwd, *args):
    return subprocess.run([REAL["git"], *args], cwd=cwd, check=True, capture_output=True, text=True,
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


def stub(directory, name, text):
    (directory / name).write_text(text)
    (directory / name).chmod(0o755)


def make_repo(tmp_path, fpr, readme=None, user=NAME, email=NOREPLY, date=None):
    """Wegwerf-Repository auf main mit den Release-Skripten und Stellvertretern für die Bau-Skripte, origin ein
    lokales bare-Repository, Identität USER <EMAIL>; die Matrix meldet den Schlüssel FPR, die READMEs nennen README
    statt des Fingerabdrucks des Archivschlüssels (None: den Platzhalter <FINGERPRINT>), der neueste <release> der
    metainfo trägt DATE (None: heute, UTC). Gibt die Pfade zurück."""
    repo, remote, bin_, rpm_bin = (tmp_path / n for n in ("repo", "remote.git", "bin", "rpm-bin"))
    for name in COPIED:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, repo / name)
    for name, text in {"build-packages.sh": BUILD_PACKAGES, "build-site.sh": BUILD_SITE,
                       "check-distros.sh": CHECK_DISTROS}.items():
        (repo / "scripts" / name).write_text(text)
    for name in ("README.md", "README.de.md"):
        (repo / name).write_text(re.sub(r"\b[0-9A-F]{40}\b", readme or "<FINGERPRINT>", (repo / name).read_text()))
    metainfo = repo / "data" / f"{APP}.metainfo.xml"
    date = date or time.strftime("%Y-%m-%d", time.gmtime())
    metainfo.write_text(re.sub(r'(<release version="[^"]+" date=")[0-9-]+', rf"\g<1>{date}", metainfo.read_text(),
                               count=1))
    (repo / "tests").mkdir()
    for name in ("test_ok.py", "test_readme.py"):  # die strenge Suite und der README-Abgleich nach der Matrix
        (repo / "tests" / name).write_text("def test_ok():\n    pass\n")
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    git(repo.parent, "init", "-q", "-b", "main", str(repo))
    for key, value in (("user.name", user), ("user.email", email), ("remote.origin.url", str(remote)),
                       ("remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")):
        git(repo, "config", key, value)
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "push", "-q", "origin", "main")
    bin_.mkdir()
    rpm_bin.mkdir()
    for tool, text in {"gh": GH, "curl": CURL, "docker": DOCKER, "rm": RM, "git": GIT.format(real=REAL["git"]),
                       **{t: LOGGED.format(tool=t, real=REAL[t]) for t in ("gpg-agent", "gpgconf")}}.items():
        stub(bin_, tool, text)
    stub(rpm_bin, "rpmkeys", RPMKEYS)
    stub(rpm_bin, "rpm", RPM)
    (tmp_path / "matrix.txt").write_text(matrix_output(fpr))
    (tmp_path / "tmp").mkdir()
    return {"repo": repo, "remote": remote, "bin": bin_, "rpm_bin": rpm_bin}


def publish_pages(tmp_path, paths, files, links=()):
    """Ein früheres Release: der Zweig gh-pages im entfernten Repository mit FILES (Pfad -> Bytes) und LINKS (Pfad ->
    Ziel eines Symlinks)."""
    work = tmp_path / "old-pages"
    for name, data in [*files.items(), *dict(links).items()]:
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            (work / name).write_bytes(data)
        else:
            (work / name).symlink_to(data)
    git(tmp_path, "init", "-q", "-b", "gh-pages", str(work))
    git(work, "add", ".")
    git(work, "-c", "user.name=Test", "-c", f"user.email={NOREPLY}", "commit", "-q", "-m", "old")
    git(work, "push", "-q", str(paths["remote"]), "gh-pages")


def run(tmp_path, paths, key, *args, env=()):
    """release.sh mit den Stellvertretern; gibt das Ergebnis und die Aufrufe je Werkzeug zurück (je Aufruf seine
    Argumente)."""
    env = {**os.environ, **GIT_ENV, "PATH": f"{paths['bin']}:{os.environ['PATH']}", "LOG_DIR": str(tmp_path),
           "REAL_GIT": REAL["git"], "REMOTE": str(paths["remote"]), "RPM_BIN": str(paths["rpm_bin"]),
           "REPO": str(paths["repo"]),
           "GNUPGHOME": str(key["home"]), "ORBITOP_KEY": key["fpr"], "TMPDIR": str(tmp_path / "tmp"), **dict(env)}
    r = subprocess.run(["bash", str(paths["repo"] / "scripts" / "release.sh"), *args], capture_output=True,
                       text=True, cwd=tmp_path, env=env, timeout=180)
    calls = {}
    for tool in TOOLS:
        log = tmp_path / f"{tool}.log"
        calls[tool], cur = [], []
        for line in log.read_text().splitlines() if log.exists() else []:
            if line == "----":
                calls[tool], cur = [*calls[tool], cur], []
            else:
                cur.append(line)
    order = tmp_path / "order.log"
    calls["order"] = order.read_text().splitlines() if order.exists() else []
    return r, calls
