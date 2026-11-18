#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds and lints orbitop inside a disposable archlinux:latest container; makepkg runs as an unprivileged user.
# Usage: bash build-inside.sh VERSION PKGREL < KEY.pgp   only as root in the container that scripts/build-packages.sh
#        starts: the archive at /src (read-only), results to /out/arch, the key already checked by the host (binary).
set -euo pipefail

key=$(mktemp)
cat > "$key"  # first step: nothing else may read stdin

die() { echo "$*" >&2; exit 1; }
[ $# -eq 2 ] || die "usage: $0 VERSION PKGREL < KEY.pgp"
if [ ! -e /.dockerenv ] || [ "$(id -u)" -ne 0 ]; then
    die "$0 installs packages as root and runs only as root inside a disposable container."
fi
[[ ${OWNER:-} =~ ^[0-9]+:[0-9]+$ ]] || die "OWNER must be uid:gid"
trap 'chown -R "$OWNER" /out' EXIT  # the results belong to the caller, also after a failure
version=$1 pkgrel=$2

pacman -Syu --noconfirm --needed base-devel namcap python >/dev/null
useradd --create-home builder  # makepkg refuses to run as root

# The build directory: PKGBUILD with version, the archive as orbitop-VERSION.tar, the keyring files of pacman-key(8).
work=$(mktemp -d)
cp /src/packaging/arch/orbitop.install "$work/"
{ printf 'pkgver=%s\npkgrel=%s\n' "$version" "$pkgrel"; cat /src/packaging/arch/PKGBUILD; } > "$work/PKGBUILD"
tar -C / -cf "$work/orbitop-$version.tar" --transform "s,^src,orbitop-$version," src
cp "$key" "$work/orbitop.gpg"
GNUPGHOME=$(mktemp -d) && export GNUPGHOME
fpr=$(gpg --batch --with-colons --show-keys "$key" | awk -F: '$1 == "fpr" { print $10; exit }')
[[ $fpr =~ ^[0-9A-F]{40}$ ]] || die "no fingerprint in the key"
printf '%s:4:\n' "$fpr" > "$work/orbitop-trusted"  # ownertrust "marginal", as in archlinux-trusted
chown -R builder "$work"

cd "$work"
packager="zappelmann-sketch <235797375+zappelmann-sketch@users.noreply.github.com>"
as_builder() { runuser -u builder -- env PACKAGER="$packager" "$@"; }
as_builder makepkg --geninteg >> PKGBUILD
# The runtime dependencies from the repositories: pacman checks every name, and namcap sees the packages it checks.
mapfile -t depends < <(bash -c 'source ./PKGBUILD && printf "%s\n" "${depends[@]}"')
pacman -S --noconfirm --needed --asdeps "${depends[@]}" >/dev/null
as_builder makepkg --noconfirm
pkg=$work/orbitop-$version-$pkgrel-any.pkg.tar.zst

# pkexec runs this file as root: no packaging tool may change it.
bsdtar -xOf "$pkg" usr/lib/orbitop/killhelper | cmp - /src/orbitop/killhelper.py ||
    die "the packaged helper differs from orbitop/killhelper.py"

mkdir -p /out/arch /out/lint
cp "$pkg" /out/arch/
report=/out/lint/arch-orbitop.txt
namcap PKGBUILD "$pkg" > "$report" 2>&1
cat "$report"
if grep -q ' E: ' "$report"; then exit 1; fi
