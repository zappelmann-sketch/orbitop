#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds the packages from `git archive` of the commit ORBITOP_REV (default HEAD) in disposable containers and lints
# them (docs/release.md).
# Usage: bash build-packages.sh --out DIR --pubkey FILE [--suffix SUFFIX] [--revision N] [--lint fatal|report]
#        DIR is empty or missing and receives deb/, rpm-fedora/, rpm-opensuse/, arch/ and lint/; FILE is the armored
#        public key of the package source. --suffix marks a check build that is never published (K6): Debian revision
#        1+SUFFIX, RPM release 1.SUFFIX, Arch pkgrel 1.1 (pacman allows only digits there). --revision N (default 1)
#        is the package revision, for the next one of the same tree in the container matrix (check-distros.sh).
#        --lint report (default fatal) only reports lint findings, for a tree that can no longer change (0.2.0 in
#        check-distros.sh): a newer lintian, rpmlint or namcap must not stop every matrix run there.
# The builds run in packaging/{debian,rpm,arch}/build-inside.sh; this script only checks, prepares and starts them.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=container-common.sh
. "$(dirname -- "$0")/container-common.sh"  # images, die, usage, options, fresh_out, workdir, container

USAGE="$0 --out DIR --pubkey FILE [--suffix SUFFIX] [--revision N] [--lint fatal|report]"

out="" pubkey="" suffix="" revision=1 lint=fatal
options out pubkey suffix revision lint -- "$@"
[ -n "$out" ] && [ -n "$pubkey" ] || usage
[[ -z $suffix || $suffix =~ ^[a-z0-9]+$ ]] || die "--suffix: only a-z and 0-9"
[[ $revision =~ ^[1-9][0-9]*$ ]] || die "--revision: a number from 1"
[[ $lint == fatal || $lint == report ]] || die "--lint: fatal or report"
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
# build FORMAT IMAGE SCRIPT [ARG…]: one disposable container, the archive read-only, the checked key on stdin and a
# new, empty output directory of its own writable, never DIR: no image can touch the packages of another one. That
# directory may then hold only FORMAT/ and lint/ with files, which go to DIR/FORMAT and DIR/lint, never over a file
# that is there already. A failed container stops the build; with --lint report not if it left packages and a lint
# report: lint is the last step of every build-inside.sh (also of 0.2.0), after the copy to /out, so it failed there.
# A failure before (the build, a cmp or mode guard) leaves neither and stays fatal.
build() {
    local format=$1 image=$2 work odd file files=() rc=0
    shift 2
    work=$(mktemp -d -p "$tmp")
    container "$work" "$image" -- "$@" || rc=$?
    if [ "$rc" -ne 0 ]; then
        if ! { [ "$lint" = report ] && compgen -G "$work/$format/*" > /dev/null &&
            compgen -G "$work/lint/*" > /dev/null; }; then
            die "the container of $image failed (exit $rc)"
        fi
        echo "WARNING: the lint findings of $image (above) are not fatal for this build (--lint report)" >&2
    fi
    odd=$(cd -- "$work" && find . -mindepth 1 ! \( -type d -regex "\./\($format\|lint\)" \) \
        ! \( -type f -regex "\./\($format\|lint\)/[^/]+" \) -print -quit) || die "refusing the output of $image"
    [ -z "$odd" ] || die "refusing the output of $image: ${odd#./} is not a file in $format/ or lint/"
    while IFS= read -r -d '' file; do
        [ ! -e "$out/$file" ] || die "refusing the output of $image: $file is in DIR already"
        files+=("$file")
    done < <(cd -- "$work" && find . -mindepth 2 -type f -printf '%P\0')
    mkdir -p -- "$out/$format" "$out/lint"
    for file in "${files[@]}"; do mv -- "$work/$file" "$out/$file"; done
}
build deb "$DEB_IMAGE" /src/packaging/debian/build-inside.sh "$version-$revision${suffix:++$suffix}"
build rpm-fedora "$FEDORA_IMAGE" /src/packaging/rpm/build-inside.sh "$version" "$revision${suffix:+.$suffix}"
build rpm-opensuse "$SUSE_IMAGE" /src/packaging/rpm/build-inside.sh "$version" "$revision${suffix:+.$suffix}"
build arch "$ARCH_IMAGE" /src/packaging/arch/build-inside.sh "$version" "$revision${suffix:+.1}"
ls -lR -- "$out"
