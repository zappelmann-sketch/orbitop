#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Writes the unsigned index of the apt source inside a disposable debian:trixie container: Packages, Packages.gz and
# Release (with Architectures: all, no Valid-Until). The host signs Release afterwards (scripts/build-site.sh).
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
apt-ftparchive packages pool > "$index/Packages"
gzip -9nk "$index/Packages"
# Origin and Label never change: apt asks the user to confirm a changed one.
apt-ftparchive -o APT::FTPArchive::Release::Origin=orbitop -o APT::FTPArchive::Release::Label=orbitop \
    -o APT::FTPArchive::Release::Suite="$suite" -o APT::FTPArchive::Release::Codename="$suite" \
    -o APT::FTPArchive::Release::Components="$component" -o APT::FTPArchive::Release::Architectures=all \
    release "dists/$suite" > /tmp/Release
mv /tmp/Release "dists/$suite/Release"  # written outside, so that Release does not list itself
cat "dists/$suite/Release"
