#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds the signed package source for GitHub Pages from the output of build-packages.sh (spec 2, docs/release.md).
# Usage: ORBITOP_KEY=FINGERPRINT [GNUPGHOME=DIR] bash build-site.sh --packages DIR --out SITE
#        SITE is empty or missing. GNUPGHOME (by default the caller's keyring) holds the secret key of ORBITOP_KEY.
# Only gpg on this host signs. The containers in packaging/site/*-inside.sh index the packages; they get the public
# key, and the one for rpmsign also the gpg-agent's restricted extra socket, never a secret key.
set -euo pipefail

# Below https://zappelmann-sketch.github.io/orbitop/ as orbitop.sources, the .repo files and the README's pacman.conf
# section name them (tests/test_site.py).
APT_DIR=apt
APT_SUITE=stable
APT_COMPONENT=main
FEDORA_DIR=rpm/fedora
OPENSUSE_DIR=rpm/opensuse
ARCH_DIR=arch/x86_64
DEB_IMAGE=debian:trixie
FEDORA_IMAGE=fedora:latest
SUSE_IMAGE=opensuse/tumbleweed
ARCH_IMAGE=archlinux:latest

usage() { echo "usage: ORBITOP_KEY=FINGERPRINT $0 --packages DIR --out SITE" >&2; exit 2; }
die() { echo "$*" >&2; exit 1; }

packages="" out=""
while [ $# -gt 0 ]; do
    [ $# -ge 2 ] || usage
    case "$1" in
        --packages) packages=$2 ;;
        --out) out=$2 ;;
        *) usage ;;
    esac
    shift 2
done
[ -n "$packages" ] && [ -n "$out" ] || usage
[ -d "$packages" ] || die "--packages must be the output directory of build-packages.sh: $packages"
if [ -e "$out" ] && [ -n "$(ls -A -- "$out")" ]; then
    die "--out must be empty or missing, so that the source holds only the newest packages: $out"
fi
fpr=${ORBITOP_KEY:-}
fpr=${fpr^^}
[[ $fpr =~ ^[0-9A-F]{40}$ ]] || die "ORBITOP_KEY must be the fingerprint of the signing key (40 hex digits)"

gpg() { command gpg --batch "$@"; }
# The secret key of exactly this primary key; the fingerprint of a subkey or of a foreign key stops here.
primary=$(gpg --with-colons --list-secret-keys -- "$fpr" 2>/dev/null | awk -F: '$1 == "fpr" { print $10; exit }') ||
    true
[ "$primary" = "$fpr" ] || die "GNUPGHOME has no secret key with the fingerprint ORBITOP_KEY=$fpr"
gpgconf --launch gpg-agent
socket=$(gpgconf --list-dirs agent-extra-socket)
[ -S "$socket" ] || die "rpmsign needs the gpg-agent's extra socket, and there is none at $socket (extra-socket none?)"

tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
gpg --export -- "$fpr" > "$tmp/key.pgp"
gpg --armor --export -- "$fpr" > "$tmp/key.asc"
repo=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
mkdir -p "$tmp/src/packaging/site"
cp -- "$repo/packaging/container-prologue.sh" "$tmp/src/packaging/"
cp -- "$repo"/packaging/site/*-inside.sh "$tmp/src/packaging/site/"
mkdir -p -- "$out"
out=$(cd -- "$out" && pwd -P)

shopt -s nullglob
put() {  # put PATTERN DIR: exactly one file per package, so that the source holds only the newest version (spec 2)
    # shellcheck disable=SC2206  # PATTERN is a glob
    local found=("$packages"/$1)
    [ ${#found[@]} -eq 1 ] || die "--packages must hold exactly one $1, not ${#found[@]}"
    mkdir -p -- "$out/$2"
    cp -- "${found[0]}" "$out/$2/"
}
put 'deb/orbitop_*_all.deb' "$APT_DIR/pool/$APT_COMPONENT/o/orbitop"
put 'deb/orbitop-apt-source_*_all.deb' "$APT_DIR/pool/$APT_COMPONENT/o/orbitop-apt-source"
put 'rpm-fedora/orbitop-[0-9]*.noarch.rpm' "$FEDORA_DIR"
put 'rpm-fedora/orbitop-release-*.noarch.rpm' "$FEDORA_DIR"
put 'rpm-opensuse/orbitop-[0-9]*.noarch.rpm' "$OPENSUSE_DIR"
put 'rpm-opensuse/orbitop-release-*.noarch.rpm' "$OPENSUSE_DIR"
put 'arch/orbitop-*-any.pkg.tar.zst' "$ARCH_DIR"

# One disposable container per step: its scripts read-only, only its part of SITE writable, the public key on stdin.
container() {  # container IMAGE DIR SCRIPT [ARG…]
    local image=$1 dir=$2 script=$3
    shift 3
    local mounts=(-v "$tmp/src:/src:ro" -v "$out/$dir:/out")
    # rpmsign alone needs a signature from inside; it gets the agent's socket, which signs but never exports a key.
    [ "$script" != rpm-inside.sh ] || mounts+=(-v "$socket:/gnupg/S.gpg-agent")
    docker run --rm -i -e OWNER="$(id -u):$(id -g)" "${mounts[@]}" "$image" bash "/src/packaging/site/$script" "$@" \
        < "$tmp/key.pgp"
}
sign() { gpg --yes --local-user "$fpr!" "$@"; }  # "!": exactly the primary key, never a subkey
# Every signature must verify with the public key alone, the one the packages install.
verify() { gpgv --keyring "$tmp/key.pgp" "$@" 2>/dev/null || die "the signature does not verify with ORBITOP_KEY: $1"; }

# apt: Packages and Release from the container, InRelease and Release.gpg from here.
container "$DEB_IMAGE" "$APT_DIR" apt-inside.sh "$APT_SUITE" "$APT_COMPONENT"
dists=$out/$APT_DIR/dists/$APT_SUITE
sign --clearsign -o "$dists/InRelease" "$dists/Release"
sign --armor --detach-sign -o "$dists/Release.gpg" "$dists/Release"
verify "$dists/InRelease"
verify "$dists/Release.gpg" "$dists/Release"

# RPM: rpmsign and createrepo_c in the container of each family, then repomd.xml signed here.
container "$FEDORA_IMAGE" "$FEDORA_DIR" rpm-inside.sh
container "$SUSE_IMAGE" "$OPENSUSE_DIR" rpm-inside.sh
for dir in "$FEDORA_DIR" "$OPENSUSE_DIR"; do
    repomd=$out/$dir/repodata/repomd.xml
    sign --armor --detach-sign -o "$repomd.asc" "$repomd"
    verify "$repomd.asc" "$repomd"
    cp -- "$tmp/key.asc" "$repomd.key"
done

# Arch: repo-add in the container, then a binary .sig beside the package and both databases; pacman fetches each one
# from the server (repo-add embeds no package signature without --include-sigs, and pacman 7 does not need it).
container "$ARCH_IMAGE" "$ARCH_DIR" arch-inside.sh
for file in "$out/$ARCH_DIR"/*.pkg.tar.zst "$out/$ARCH_DIR/orbitop.db" "$out/$ARCH_DIR/orbitop.files"; do
    sign --no-armor --detach-sign -o "$file.sig" "$file"
    verify "$file.sig" "$file"
done

cp -- "$tmp/key.asc" "$out/orbitop-archive-keyring.asc"
cp -- "$tmp/key.pgp" "$out/orbitop-archive-keyring.pgp"
: > "$out/.nojekyll"  # GitHub Pages serves the tree as it is
grouped=$(sed -E 's/.{4}/& /g; s/ $//; s/^.{25}/& /' <<< "$fpr")  # as gpg --fingerprint prints it
sed "s/<FINGERPRINT>/$grouped/" "$repo/packaging/site/index.html" > "$out/index.html"
(cd -- "$out" && find . -type f | sort)
