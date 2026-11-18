#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds the packages from `git archive HEAD` in disposable containers and lints them (docs/release.md).
# Usage: bash build-packages.sh --out DIR --pubkey FILE [--suffix SUFFIX]
#        DIR is empty or missing and receives deb/ and lint/; FILE is the armored public key of the package source.
#        --suffix marks a check build that is never published: Debian revision 1+SUFFIX (K6).
#        bash build-packages.sh --inside-deb VERSION   only as root inside such a container, key on stdin
set -euo pipefail

DEB_IMAGE=debian:trixie
REVISION=1
METAINFO=data/io.github.zappelmann_sketch.orbitop.metainfo.xml

usage() { echo "usage: $0 --out DIR --pubkey FILE [--suffix SUFFIX]" >&2; exit 2; }
die() { echo "$*" >&2; exit 1; }

inside_deb() {
    local version=$1 work apt deb report rc=0
    if [ ! -e /.dockerenv ] || [ "$(id -u)" -ne 0 ]; then
        die "--inside-deb installs packages as root and runs only as root inside a disposable container."
    fi
    [[ ${OWNER:-} =~ ^[0-9]+:[0-9]+$ ]] || die "OWNER must be uid:gid"
    trap 'chown -R "$OWNER" /out' EXIT  # the results belong to the caller, also after a failure
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends build-essential debhelper dh-python python3 lintian gpg >/dev/null
    work=$(mktemp -d)
    cp -a /src "$work/orbitop"
    cd "$work/orbitop"
    cp -a packaging/debian debian
    python3 -I packaging/changelog.py debian "$METAINFO" "$version" > debian/changelog
    # orbitop-apt-source: its own source tree with only its inputs, so that nothing of orbitop reaches it.
    apt=$work/orbitop-apt-source
    mkdir "$apt"
    cp -a packaging/apt-source/debian "$apt/debian"
    cp packaging/keyring/orbitop.sources "$apt/"
    python3 -I packaging/changelog.py apt-source "$(cat packaging/keyring.version)" > "$apt/debian/changelog"
    export GNUPGHOME=$work/gnupg
    mkdir -m 700 "$GNUPGHOME"
    gpg --batch --dearmor > "$apt/orbitop-archive-keyring.pgp"
    # Only a public key goes into the package, never a secret one.
    gpg --batch --show-keys --with-colons "$apt/orbitop-archive-keyring.pgp" > "$work/key.txt"
    if ! grep -q '^pub:' "$work/key.txt" || grep -qE '^(sec|ssb):' "$work/key.txt"; then
        die "--pubkey is not a public key"
    fi
    grep -m 1 '^fpr:' "$work/key.txt"
    dpkg-buildpackage -b -us -uc
    (cd "$apt" && dpkg-buildpackage -b -us -uc)
    # pkexec runs this file as root: no packaging tool may change it (dh_python3 once dropped "-I" from its shebang).
    dpkg-deb --fsys-tarfile "$work"/orbitop_*_all.deb | tar -xO ./usr/lib/orbitop/killhelper |
        cmp - orbitop/killhelper.py || die "the packaged helper differs from orbitop/killhelper.py"
    mkdir -p /out/deb /out/lint
    cp "$work"/*.deb /out/deb/
    for deb in /out/deb/*.deb; do
        report=/out/lint/$(basename "$deb" .deb).txt
        lintian --display-info --show-overrides --fail-on error --tag-display-limit 0 "$deb" > "$report" || rc=1
        cat "$report"
    done
    exit "$rc"
}

host() {
    local out="" pubkey="" suffix="" repo version
    while [ $# -gt 0 ]; do
        [ $# -ge 2 ] || usage
        case "$1" in
            --out) out=$2 ;;
            --pubkey) pubkey=$2 ;;
            --suffix) suffix=$2 ;;
            *) usage ;;
        esac
        shift 2
    done
    [ -n "$out" ] && [ -n "$pubkey" ] || usage
    [[ -z $suffix || $suffix =~ ^[a-z0-9]+$ ]] || die "--suffix: only a-z and 0-9"
    # A secret key never reaches a container.
    if [ ! -f "$pubkey" ] || [ "$(head -n 1 -- "$pubkey")" != "-----BEGIN PGP PUBLIC KEY BLOCK-----" ] ||
        grep -q 'PRIVATE KEY' -- "$pubkey"; then
        die "--pubkey must be an armored public key: $pubkey"
    fi
    if [ -e "$out" ] && [ -n "$(ls -A -- "$out")" ]; then
        die "--out must be empty or missing, so that no old package is mistaken for a new one: $out"
    fi
    mkdir -p -- "$out"
    out=$(cd -- "$out" && pwd -P)
    repo=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
    copy=$(mktemp -d)
    trap 'rm -rf -- "$copy"' EXIT
    git -C "$repo" archive HEAD | tar -C "$copy" -xf -  # only committed files, never local ones such as CLAUDE.md
    version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$copy/orbitop/__init__.py")
    [[ $version =~ ^[0-9]+(\.[0-9]+)*$ ]] || die "no version in orbitop/__init__.py"
    docker run --rm -i -e OWNER="$(id -u):$(id -g)" -v "$copy:/src:ro" -v "$out:/out" "$DEB_IMAGE" \
        bash /src/scripts/build-packages.sh --inside-deb "$version-$REVISION${suffix:++$suffix}" < "$pubkey"
    ls -l -- "$out/deb"
}

if [ "${1:-}" = --inside-deb ]; then
    [ $# -eq 2 ] || usage
    inside_deb "$2"
fi
host "$@"
