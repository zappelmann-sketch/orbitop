#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Writes the pacman database orbitop.db and orbitop.files with repo-add inside a disposable archlinux:latest
# container, without any key. The host signs the package and both databases afterwards (scripts/build-site.sh).
# Usage: bash arch-inside.sh < KEY.pgp   only as root in the container that build-site.sh starts: the package in
#        /out, the public key of ORBITOP_KEY (binary) on stdin.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../container-prologue.sh
. "$(dirname -- "$0")/../container-prologue.sh"  # $key from stdin, die; only as root in a container

[ $# -eq 0 ] || die "usage: $0 < KEY.pgp"
cd /out
pkg=(orbitop-*-any.pkg.tar.zst)  # exactly one, build-site.sh checked
# pacman-key --populate orbitop trusts this key; pacman verifies the database and the package with it.
# The image has no cmp; sha256sum from coreutils compares as well.
[ "$(bsdtar -xOf "${pkg[0]}" usr/share/pacman/keyrings/orbitop.gpg | sha256sum)" = "$(sha256sum < "$key")" ] ||
    die "the key in ${pkg[0]} is not the public key of ORBITOP_KEY"

repo-add --quiet orbitop.db.tar.gz "${pkg[0]}"
# GitHub Pages serves files, not the symlinks orbitop.db and orbitop.files that repo-add makes.
for db in orbitop.db orbitop.files; do
    rm "$db"
    mv "$db.tar.gz" "$db"
done
