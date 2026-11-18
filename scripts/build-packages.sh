#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds the packages from `git archive HEAD` in disposable containers and lints them (docs/release.md).
# Usage: bash build-packages.sh --out DIR --pubkey FILE [--suffix SUFFIX]
#        DIR is empty or missing and receives deb/, rpm-fedora/, rpm-opensuse/, arch/ and lint/; FILE is the armored
#        public key of the package source. --suffix marks a check build that is never published (K6): Debian revision
#        1+SUFFIX, RPM release 1.SUFFIX, Arch pkgrel 1.1 (pacman allows only digits there).
# The builds run in packaging/{debian,rpm,arch}/build-inside.sh; this script only checks, prepares and starts them.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=container-common.sh
. "$(dirname -- "$0")/container-common.sh"  # images, die, usage, options, fresh_out, workdir, container

REVISION=1
USAGE="$0 --out DIR --pubkey FILE [--suffix SUFFIX]"

out="" pubkey="" suffix=""
options out pubkey suffix -- "$@"
[ -n "$out" ] && [ -n "$pubkey" ] || usage
[[ -z $suffix || $suffix =~ ^[a-z0-9]+$ ]] || die "--suffix: only a-z and 0-9"
fresh_out "$out" "so that no old package is mistaken for a new one"

workdir
mkdir -m 700 "$tmp/gnupg"  # a fresh keyring: the check never reads or changes the caller's GNUPGHOME
gpg() { command gpg --homedir "$tmp/gnupg" --no-options --batch "$@"; }
# Exactly one public key: it becomes the trust anchor of the source, and nothing else (a second key, a secret
# key under a PUBLIC header) ever reaches the container, which gets only the checked binary form.
if [ ! -f "$pubkey" ] || [ "$(head -n 1 -- "$pubkey")" != "-----BEGIN PGP PUBLIC KEY BLOCK-----" ] ||
    ! gpg --quiet --dearmor < "$pubkey" > "$tmp/key.pgp" 2>/dev/null; then
    die "--pubkey must be an armored public key: $pubkey"
fi
gpg --show-keys --with-colons -- "$tmp/key.pgp" > "$tmp/key.txt" 2>/dev/null || true
if [ "$(grep -c '^pub:' "$tmp/key.txt")" -ne 1 ] || grep -qE '^(sec|ssb):' "$tmp/key.txt"; then
    die "--pubkey must hold exactly one public key and no secret key: $pubkey"
fi
grep -m 1 '^fpr:' "$tmp/key.txt"
# The minimal form, as build-site.sh exports it: the source containers compare the packaged key byte by byte.
gpg --quiet --import "$tmp/key.pgp"
gpg --export --export-options export-minimal > "$tmp/key.pgp"

mkdir -p -- "$out"
out=$(cd -- "$out" && pwd -P)
tracked_files
version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$tmp/src/orbitop/__init__.py")
[[ $version =~ ^[0-9]+(\.[0-9]+)*$ ]] || die "no version in orbitop/__init__.py"
# One disposable container per build: the archive read-only, only DIR writable, the checked key on stdin.
container "$out" "$DEB_IMAGE" -- /src/packaging/debian/build-inside.sh "$version-$REVISION${suffix:++$suffix}"
for image in "$FEDORA_IMAGE" "$SUSE_IMAGE"; do
    container "$out" "$image" -- /src/packaging/rpm/build-inside.sh "$version" "$REVISION${suffix:+.$suffix}"
done
container "$out" "$ARCH_IMAGE" -- /src/packaging/arch/build-inside.sh "$version" "$REVISION${suffix:+.1}"
ls -lR -- "$out"
