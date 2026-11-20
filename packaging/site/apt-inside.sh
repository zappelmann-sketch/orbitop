#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Writes the unsigned index of the apt source inside a disposable debian:trixie container: Packages, Packages.gz, their
# by-hash copies and Release (Architectures: all, Acquire-By-Hash, no Valid-Until, only SHA256 and SHA512). The host
# signs Release afterwards (scripts/build-site.sh).
# Usage: bash apt-inside.sh SUITE COMPONENT < KEY.pgp   only as root in the container that build-site.sh starts: the
#        debs already in /out/pool, the public key of ORBITOP_KEY (binary) on stdin.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../container-prologue.sh
. "$(dirname -- "$0")/../container-prologue.sh"  # $key from stdin, die; only as root in a container

[ $# -eq 2 ] || die "usage: $0 SUITE COMPONENT < KEY.pgp"
suite=$1 component=$2
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends apt-utils >/dev/null

# The source must sign with the key that orbitop-apt-source installs, or apt update fails on every client.
source_deb=(/out/pool/"$component"/o/orbitop-apt-source/orbitop-apt-source_*_all.deb)  # exactly one
dpkg-deb --fsys-tarfile "${source_deb[0]}" | tar -xO ./etc/apt/keyrings/orbitop-archive-keyring.pgp |
    cmp -s - "$key" || die "the key in ${source_deb[0]##*/} is not the public key of ORBITOP_KEY"

cd /out
index=dists/$suite/$component/binary-all
mkdir -p "$index"
# Only SHA256 and SHA512 in Packages and Release (apt-ftparchive(1)): apt counts MD5 and SHA1 as weak hashes.
hashes=(-o APT::FTPArchive::MD5=false -o APT::FTPArchive::SHA1=false)
apt-ftparchive "${hashes[@]}" packages pool > "$index/Packages"
# apt-ftparchive skips a file that is no package and still exits 0: the index must list exactly the two packages.
names=$(sed -n 's/^Package: //p' "$index/Packages" | sort | paste -sd ' ')
[ "$names" = "orbitop orbitop-apt-source" ] || die "Packages must list orbitop and orbitop-apt-source, not: $names"
gzip -9nk "$index/Packages"
# Origin and Label never change: apt asks the user to confirm a changed one. By-hash: GitHub Pages caches each file
# for itself, so a client may get a new InRelease with an old Packages; by-hash names cannot mix up.
apt-ftparchive "${hashes[@]}" -o APT::FTPArchive::Release::Origin=orbitop -o APT::FTPArchive::Release::Label=orbitop \
    -o APT::FTPArchive::Release::Suite="$suite" -o APT::FTPArchive::Release::Codename="$suite" \
    -o APT::FTPArchive::Release::Components="$component" -o APT::FTPArchive::Release::Architectures=all \
    -o APT::FTPArchive::Release::Acquire-By-Hash=yes -o APT::FTPArchive::DoByHash=true \
    release "dists/$suite" > /tmp/Release
mv /tmp/Release "dists/$suite/Release"  # written outside, so that Release does not list itself
cat "dists/$suite/Release"
