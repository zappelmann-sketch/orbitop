#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds and lints orbitop inside a disposable archlinux:latest container; makepkg runs as an unprivileged user.
# Usage: bash build-inside.sh VERSION PKGREL < KEY.pgp   only as root in the container that scripts/build-packages.sh
#        starts: the archive at /src (read-only), results to /out/arch, the key already checked by the host (binary).
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../container-prologue.sh
. "$(dirname -- "$0")/../container-prologue.sh"  # $key from stdin, die, archive; only as root in a container

[ $# -eq 2 ] || die "usage: $0 VERSION PKGREL < KEY.pgp"
version=$1 pkgrel=$2

pacman -Syu --noconfirm --needed base-devel namcap python >/dev/null
useradd --create-home builder  # makepkg refuses to run as root

# The build directory: PKGBUILD with version, the archive as orbitop-VERSION.tar, the keyring files of pacman-key(8).
work=$(mktemp -d)
cp /src/packaging/arch/orbitop.install "$work/"
{ printf 'pkgver=%s\npkgrel=%s\n' "$version" "$pkgrel"; cat /src/packaging/arch/PKGBUILD; } > "$work/PKGBUILD"
archive "$work" "$version"
cp "$key" "$work/orbitop.gpg"
GNUPGHOME=$(mktemp -d) && export GNUPGHOME
fpr=$(gpg --batch --with-colons --show-keys "$key" | awk -F: '$1 == "fpr" { print $10; exit }')
[[ $fpr =~ ^[0-9A-F]{40}$ ]] || die "no fingerprint in the key"
# Owner trust 3 ("never"): pacman's local signature makes the key valid, but it never helps to validate another key.
printf '%s:3:\n' "$fpr" > "$work/orbitop-trusted"
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

# pkexec runs these files as root: no packaging tool may change them.
for helper in killhelper counterhelper; do
    bsdtar -xOf "$pkg" "usr/lib/orbitop/$helper" | cmp - "/src/orbitop/$helper.py" ||
        die "the packaged helper differs from orbitop/$helper.py"
done
# Only root may open /etc/orbitop, where counterhelper takes its lock (packaging/install-tree.sh).
mode=$(bsdtar -tvf "$pkg" | awk '$NF == "etc/orbitop/" || $NF == "etc/orbitop" { print $1 }')
[ "$mode" = drwx--x--x ] || die "/etc/orbitop is '$mode' in the package, not drwx--x--x"

mkdir -p /out/arch /out/lint
cp "$pkg" /out/arch/
report=/out/lint/arch-orbitop.txt
namcap PKGBUILD "$pkg" > "$report" 2>&1
cat "$report"
if grep -q ' E: ' "$report"; then die "namcap reports errors"; fi
