#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Signs the RPMs of one family with rpmsign and writes repodata/ with createrepo_c, inside a disposable container of
# the tool image rpm-tools.Dockerfile (Fedora or openSUSE), without network. The host signs repodata/repomd.xml
# afterwards (scripts/build-site.sh).
# Usage: bash rpm-inside.sh < KEY.pgp   only as root in the container that build-site.sh starts: the RPMs in /out,
#        the public key of ORBITOP_KEY (binary) on stdin, the host gpg-agent's extra socket at /gnupg/S.gpg-agent.
# The secret key never enters the container: gpg here only reaches the host agent through its restricted extra
# socket, which signs but never hands out a key. There is no other way; without the socket this script stops. The
# tools come with the image: nothing is installed while the socket is mounted.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../container-prologue.sh
. "$(dirname -- "$0")/../container-prologue.sh"  # $key from stdin, die; only as root in a container

[ $# -eq 0 ] || die "usage: $0 < KEY.pgp"
export GNUPGHOME=/gnupg  # holds only the public key and the mounted socket
[ -S "$GNUPGHOME/S.gpg-agent" ] || die "the host gpg-agent's extra socket is not mounted at $GNUPGHOME/S.gpg-agent"
chmod 700 "$GNUPGHOME"
echo no-autostart > "$GNUPGHOME/gpg.conf"  # never a local agent without the key in its place
[ "$(gpgconf --list-dirs agent-socket)" = "$GNUPGHOME/S.gpg-agent" ] ||
    die "gpg in this container does not look for its agent at $GNUPGHOME/S.gpg-agent"
gpg --batch --quiet --import "$key"
fpr=$(gpg --batch --with-colons --show-keys "$key" | awk -F: '$1 == "fpr" { print $10; exit }')
[[ $fpr =~ ^[0-9A-F]{40}$ ]] || die "no fingerprint in the key"

# orbitop-release installs this key; rpm and dnf or zypper verify the source with it.
release=(/out/orbitop-release-*.noarch.rpm)  # exactly one, build-site.sh checked
rpm2cpio "${release[0]}" | cpio -i --quiet --to-stdout ./etc/pki/rpm-gpg/RPM-GPG-KEY-orbitop | gpg --dearmor |
    cmp -s - "$key" || die "the key in ${release[0]#/out/} is not the public key of ORBITOP_KEY"

# The check a client does: the signature verifies with the public key alone. So the image's own keys leave the rpm
# database first (a loop of bash: Tumbleweed has no xargs), and rpm -K accepts no other key.
gpg --batch --armor --export "$fpr" > /tmp/key.asc
keys=$(rpmkeys --list)
while read -r k _; do [ -z "$k" ] || rpmkeys --delete "${k%:}"; done <<< "$keys"
[ -z "$(rpmkeys --list)" ] || die "the rpm database of the tool image still holds a key"
rpmkeys --import /tmp/key.asc
# An RPM that verifies already keeps its bytes: orbitop-release of an earlier release, which scripts/release.sh
# reuses after rpm -K. Every other one gets signed here.
unsigned=()
for rpm in /out/*.rpm; do
    [[ $(rpm -K "$rpm" 2>&1) == *": digests signatures OK" ]] || unsigned+=("$rpm")
done
[ ${#unsigned[@]} -eq 0 ] || rpmsign --addsign --define "_gpg_name $fpr!" "${unsigned[@]}" ||  # "!": the primary key
    die "rpmsign failed: the host gpg-agent (extra socket) must hold the secret key of $fpr"
for rpm in /out/*.rpm; do
    check=$(rpm -K "$rpm") || die "no valid signature: $check"
    echo "$check"
    [[ $check == *": digests signatures OK" ]] || die "no valid signature: $check"
done
createrepo_c --quiet /out
