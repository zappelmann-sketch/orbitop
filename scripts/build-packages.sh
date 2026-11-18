#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds the packages from `git archive HEAD` in disposable containers and lints them (docs/release.md).
# Usage: bash build-packages.sh --out DIR --pubkey FILE [--suffix SUFFIX]
#        DIR is empty or missing and receives deb/ and lint/; FILE is the armored public key of the package source.
#        --suffix marks a check build that is never published: Debian revision 1+SUFFIX (K6).
# The build itself runs in packaging/debian/build-inside.sh; this script only checks, prepares and starts it.
set -euo pipefail

DEB_IMAGE=debian:trixie
REVISION=1

usage() { echo "usage: $0 --out DIR --pubkey FILE [--suffix SUFFIX]" >&2; exit 2; }
die() { echo "$*" >&2; exit 1; }

out="" pubkey="" suffix=""
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
if [ -e "$out" ] && [ -n "$(ls -A -- "$out")" ]; then
    die "--out must be empty or missing, so that no old package is mistaken for a new one: $out"
fi

tmp=$(mktemp -d)
trap 'gpgconf --homedir "$tmp/gnupg" --kill all 2>/dev/null; rm -rf -- "$tmp"' EXIT
mkdir -m 700 "$tmp/gnupg"  # a fresh keyring: the check never reads or changes the caller's GNUPGHOME
gpg() { command gpg --homedir "$tmp/gnupg" --batch "$@"; }
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

mkdir -p -- "$out"
out=$(cd -- "$out" && pwd -P)
repo=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
mkdir "$tmp/src"
git -C "$repo" archive HEAD | tar -C "$tmp/src" -xf -  # only committed files, never local ones such as CLAUDE.md
version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$tmp/src/orbitop/__init__.py")
[[ $version =~ ^[0-9]+(\.[0-9]+)*$ ]] || die "no version in orbitop/__init__.py"
docker run --rm -i -e OWNER="$(id -u):$(id -g)" -v "$tmp/src:/src:ro" -v "$out:/out" "$DEB_IMAGE" \
    bash /src/packaging/debian/build-inside.sh "$version-$REVISION${suffix:++$suffix}" < "$tmp/key.pgp"
ls -l -- "$out/deb"
