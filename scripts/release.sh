#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds, checks and publishes a release of orbitop (spec 5, docs/release.md "Release").
# Usage: GNUPGHOME=DIR ORBITOP_KEY=FINGERPRINT bash release.sh VERSION [--dry-run]
#        On a clean main whose orbitop/__init__.py has VERSION; GNUPGHOME holds the archive key and nothing else.
#        --dry-run runs steps 1 to 3 (docs/distro-check.md is written, not committed) and only prints steps 4 to 8.
# Steps: 1 checks (release/checks.sh); 2 packages and signed source, twice (the second with --suffix check1), in a
#        work directory that is removed on exit (release/build.sh); 3 container matrix and docs/distro-check.md;
#        4 annotated tag; 5 push of main and tag, GitHub release (assets: release/build.sh); 6 gh-pages; 7 GitHub
#        Pages on the first release; 8 wait until Pages serves the new source (release/publish.sh).
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=container-common.sh
. "$(dirname -- "$0")/container-common.sh"  # $repo, die, usage, the images
# shellcheck source-path=SCRIPTDIR source=release/checks.sh
. "$repo/scripts/release/checks.sh"
# shellcheck source-path=SCRIPTDIR source=release/build.sh
. "$repo/scripts/release/build.sh"
# shellcheck source-path=SCRIPTDIR source=release/publish.sh
. "$repo/scripts/release/publish.sh"

USAGE="GNUPGHOME=DIR ORBITOP_KEY=FINGERPRINT $0 VERSION [--dry-run]"
if [[ $# -lt 1 || $# -gt 2 || ! $1 =~ ^[0-9]+(\.[0-9]+)*$ || ${2---dry-run} != --dry-run ]]; then usage; fi
version=$1
dry=${2:+1}
fpr=${ORBITOP_KEY:-}
fpr=${fpr^^}
keyring_version=$(cat -- "$repo/packaging/keyring.version")
[[ $keyring_version =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}$ ]] || die "packaging/keyring.version must be YYYY.MM.DD"

# run COMMAND…: steps 4 to 8 run COMMAND; a dry run only prints it.
run() {
    if [ -n "$dry" ]; then
        printf 'dry run, would run:' && printf ' %q' "$@" && echo
    else
        "$@"
    fi
}

# On every exit: no work directory (packages, sites, the gh-pages worktree) is left for a later run to find, and the
# gpg-agent of GNUPGHOME forgets the passphrase.
finish() {
    gpgconf --homedir "$tmp/gnupg" --kill all 2> /dev/null || true
    rm -rf -- "$tmp"
    git -C "$repo" worktree prune
    gpgconf --kill gpg-agent 2> /dev/null || true
}
tmp=$(mktemp -d)
trap finish EXIT
mkdir -m 700 "$tmp/gnupg"  # an empty keyring for reading key files, never GNUPGHOME

echo "== 1 checks"
check_tree
check_key
check_readme
remote_state
published
run_tests
echo "== 2 packages and signed source"
build "$tmp/pkgs" "$tmp/site"
build "$tmp/pkgs2" "$tmp/site2" check1
echo "== 3 container matrix"
matrix
echo "== 4 tag"
tag_release
echo "== 5 GitHub release"
if [ -n "$dry" ]; then make_assets HEAD; else make_assets "v$version"; fi
release_github
echo "== 6 gh-pages"
pages_tree
echo "== 7 GitHub Pages"
pages_on
echo "== 8 published source"
wait_pages
