#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds and lints orbitop and orbitop-apt-source inside a disposable debian:trixie container.
# Usage: bash build-inside.sh DEBIAN-VERSION < KEY.pgp   only as root in the container that scripts/build-packages.sh
#        starts: the archive at /src (read-only), results to /out, the key already checked by the host (binary).
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../container-prologue.sh
. "$(dirname -- "$0")/../container-prologue.sh"  # $key from stdin, die; only as root in a container

[ $# -eq 1 ] || die "usage: $0 DEBIAN-VERSION < KEY.pgp"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends build-essential debhelper dh-python python3 lintian >/dev/null
work=$(mktemp -d)

# orbitop: a writable copy of the archive, changelog from the metainfo.
cp -a /src "$work/orbitop"
cd "$work/orbitop"
cp -a packaging/debian debian
python3 -I packaging/changelog.py debian data/io.github.zappelmann_sketch.orbitop.metainfo.xml "$1" > debian/changelog
dpkg-buildpackage -b -us -uc
# pkexec runs these files as root: no packaging tool may change them (dh_python3 once dropped "-I" from a shebang).
for helper in killhelper counterhelper; do
    dpkg-deb --fsys-tarfile "$work"/orbitop_*_all.deb | tar -xO "./usr/lib/orbitop/$helper" |
        cmp - "/src/orbitop/$helper.py" || die "the packaged helper differs from orbitop/$helper.py"
done
# Only root may open /etc/orbitop, where counterhelper takes its lock (packaging/install-tree.sh).
mode=$(dpkg-deb --fsys-tarfile "$work"/orbitop_*_all.deb | tar -tvf - | awk '$NF == "./etc/orbitop/" { print $1 }')
[ "$mode" = drwx--x--x ] || die "/etc/orbitop is '$mode' in the package, not drwx--x--x"

# orbitop-apt-source: its own source tree with only its inputs, so that nothing of orbitop reaches it.
apt=$work/orbitop-apt-source
cp -a packaging/apt-source "$apt"
cp "$key" "$apt/orbitop-archive-keyring.pgp"
python3 -I packaging/changelog.py apt-source "$(cat packaging/keyring.version)" > "$apt/debian/changelog"
(cd "$apt" && dpkg-buildpackage -b -us -uc)

mkdir -p /out/deb /out/lint
cp "$work"/*.deb /out/deb/
rc=0
for deb in /out/deb/*.deb; do
    report=/out/lint/$(basename "$deb" .deb).txt
    lintian --display-info --show-overrides --fail-on error --tag-display-limit 0 "$deb" > "$report" || rc=1
    cat "$report"
done
exit "$rc"
