#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds, checks and publishes a release of orbitop (spec 5, docs/release.md "Release").
# Usage: GNUPGHOME=DIR ORBITOP_KEY=FINGERPRINT ORBITOP_TAG_KEY=FILE bash release.sh VERSION [--dry-run]
#        On a clean main whose orbitop/__init__.py has VERSION; GNUPGHOME holds the archive key and nothing else;
#        ORBITOP_TAG_KEY is the private SSH key of the tags, whose public half .github/allowed_signers lists.
#        --dry-run runs steps 1 to 3, the release files (docs/distro-check.md is written, not committed) and the
#        identity check of the gh-pages worktree, and only prints the commands of steps 4 to 8.
# Steps: 1 checks (release/checks.sh), HEAD pinned; 2 packages and signed source of the pinned HEAD, twice (the
#        second with --suffix check1), in a work directory that is removed on exit; 3 container matrix with the files
#        of the pinned HEAD and docs/distro-check.md; the release files from its commit (release/build.sh) and the
#        gh-pages worktree with its identity checked;
#        4 annotated tag of that commit, if HEAD has not moved since step 1, signed with ORBITOP_TAG_KEY and checked;
#        5 push of main and tag, GitHub release as a draft;
#        6 gh-pages; 7 GitHub Pages on the first release; 8 wait until Pages serves the new source, then publish
#        the release (release/publish.sh).
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=container-common.sh
. "$(dirname -- "$0")/container-common.sh"  # $repo, die, usage, the images
# shellcheck source-path=SCRIPTDIR source=release/checks.sh
. "$repo/scripts/release/checks.sh"
# shellcheck source-path=SCRIPTDIR source=release/build.sh
. "$repo/scripts/release/build.sh"
# shellcheck source-path=SCRIPTDIR source=release/publish.sh
. "$repo/scripts/release/publish.sh"

USAGE="GNUPGHOME=DIR ORBITOP_KEY=FINGERPRINT ORBITOP_TAG_KEY=FILE $0 VERSION [--dry-run]"
if [[ $# -lt 1 || $# -gt 2 || ! $1 =~ ^[0-9]+(\.[0-9]+)*$ || ${2---dry-run} != --dry-run ]]; then usage; fi
version=$1
dry=${2:+1}
fpr=${ORBITOP_KEY:-}
fpr=${fpr^^}
tag_key=${ORBITOP_TAG_KEY:-}
keyring_version=$(cat -- "$repo/packaging/keyring.version")
[[ $keyring_version =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}$ ]] || die "packaging/keyring.version must be YYYY.MM.DD"
# The script stops and starts the agent of GNUPGHOME, so it must be the archive key's directory of its own.
[[ -n ${GNUPGHOME:-} && -d $GNUPGHOME ]] ||
    die "GNUPGHOME must be the GnuPG directory of the archive key (docs/release.md, Key)"
[ "$(cd -- "$GNUPGHOME" && pwd -P)" != "$(cd -- "${HOME:-/nonexistent}/.gnupg" 2> /dev/null && pwd -P)" ] ||
    die "GNUPGHOME must not be ~/.gnupg: the archive key has a directory of its own (docs/release.md, Key)"

# run COMMAND…: steps 4 to 8 run COMMAND; a dry run only prints it.
run() {
    if [ -n "$dry" ]; then
        printf 'dry run, would run:' && printf ' %q' "$@" && echo
    else
        "$@"
    fi
}

# On every exit: the gpg-agent of GNUPGHOME stops first, so the passphrase is no longer cached, and no work directory
# (packages, sites, the gh-pages worktree) is left for a later run to find. set -e holds in this trap too, so no step
# may stop the others, not even an rm that root-owned leftovers of a container make fail.
finish() {
    gpgconf --kill gpg-agent 2> /dev/null || true
    rm -rf -- "$tmp" || echo "warning: could not remove all of $tmp (root-owned files of a container?);" \
        "remove it by hand" >&2
    git -C "$repo" worktree prune || true
}
tmp=$(mktemp -d)
trap finish EXIT
mkdir -m 700 "$tmp/gnupg"  # an empty keyring for reading key files, never GNUPGHOME
# Two passphrase prompts per run, both naming the archive key: one from the host (build-site.sh, first signature),
# one "Note: Request from a remote site." for rpmsign through the extra socket, which gpg-agent caches apart; any
# further prompt is suspicious (docs/release.md, Release). The matrix lies between the first signature and the last
# (SHA256SUMS.asc), longer than the 10 minutes gpg-agent keeps a passphrase by default. So the agent of GNUPGHOME
# starts anew for this run and keeps it for 2 hours; no file of GNUPGHOME changes. No scdaemon: no token's key is
# reachable through the agent's socket (docs/release.md, Site).
gpgconf --kill gpg-agent
gpg-agent --homedir "$GNUPGHOME" --daemon --disable-scdaemon --default-cache-ttl 7200 --max-cache-ttl 7200 > /dev/null

echo "== 1 checks"
check_tree
check_date
check_origin
check_key
check_tag_key
check_readme
[ -n "$dry" ] || check_github
remote_state
published
run_tests
echo "== 2 packages and signed source"
build "$tmp/pkgs" "$tmp/site"
build "$tmp/pkgs2" "$tmp/site2" check1
echo "== 3 container matrix"
matrix
echo "== release files and the gh-pages worktree"
make_assets
pages_worktree
echo "== 4 tag"
tag_release
echo "== 5 GitHub release, a draft"
release_github
echo "== 6 gh-pages"
pages_tree
echo "== 7 GitHub Pages"
pages_on
echo "== 8 published source, then the release"
wait_pages
publish_release
