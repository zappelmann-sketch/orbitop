# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Shared by scripts/build-packages.sh, scripts/build-site.sh, scripts/check-distros.sh and scripts/release.sh,
# sourced right after set -euo pipefail: the images, option parsing, a work directory with the tracked files, the
# disposable container whose output is checked, and the fingerprint of a key file.
# Provides $repo, die, usage (prints $USAGE), options, fresh_out, workdir ($tmp), tracked_files, only_plain, container,
# fingerprint.
# shellcheck shell=bash disable=SC2034  # the images are used by the scripts that source this file

DEB_IMAGE=debian:trixie
FEDORA_IMAGE=fedora:latest
SUSE_IMAGE=opensuse/tumbleweed
ARCH_IMAGE=archlinux:latest

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)

die() { echo "$*" >&2; exit 1; }
usage() { echo "usage: $USAGE" >&2; exit 2; }

# options NAME… -- ARG…: each pair "--NAME VALUE" in ARG sets the variable NAME; anything else is a usage error.
options() {
    local names=" "
    while [ "$1" != -- ]; do names+="$1 " && shift; done
    shift
    while [ $# -gt 0 ]; do
        [ $# -ge 2 ] && [[ $1 == --* && $names == *" ${1#--} "* ]] || usage
        printf -v "${1#--}" '%s' "$2"
        shift 2
    done
}

# fresh_out DIR WHY: DIR must be empty or missing.
fresh_out() {
    if [ -e "$1" ] && [ -n "$(ls -A -- "$1")" ]; then die "--out must be empty or missing, $2: $1"; fi
}

# workdir: sets $tmp, a new directory that is removed on exit, with the gpg-agent of $tmp/gnupg, if there is one, and
# the socket directory below /run/user/<uid>/gnupg that gpgconf --kill makes for it; a failure there keeps nothing.
workdir() {
    tmp=$(mktemp -d)
    trap '[ ! -d "$tmp/gnupg" ] || { gpgconf --homedir "$tmp/gnupg" --kill all
        gpgconf --homedir "$tmp/gnupg" --remove-socketdir; } 2>/dev/null || true; rm -rf -- "$tmp"' EXIT
}

# tracked_files: $tmp/src holds the files of the commit ORBITOP_REV, or of HEAD without it (git archive), never local
# ones such as CLAUDE.md. release.sh passes the HEAD of its step 1, so that a commit during the run changes no build.
tracked_files() {
    mkdir "$tmp/src"
    git -C "$repo" archive "${ORBITOP_REV:-HEAD}" | tar -C "$tmp/src" -xf -
}

# only_plain DIR: DIR comes from a container (as root); host tools may touch it only if it holds nothing but regular
# files and directories, none setuid or setgid and none with file capabilities. A planted symlink would make them read
# or write elsewhere, a FIFO would block them, a device would open the host's; setuid, setgid or a capability would
# give root's rights to whoever runs the file. Any error of find or getcap is a refusal too.
only_plain() {
    local odd getcap caps
    odd=$(find "$1" -mindepth 1 \( \( ! -type f ! -type d \) -o -perm /6000 \) -print -quit) ||
        die "refusing $1: find cannot check all of it"
    [ -z "$odd" ] || die "refusing $1: it holds something other than plain files and directories: $odd"
    getcap=$(PATH=$PATH:/usr/sbin:/sbin command -v getcap) ||
        die "refusing $1: getcap (libcap2-bin or libcap) is missing, so file capabilities cannot be checked"
    # getcap exits 0 even for errors and prints them; it prints nothing for a tree without capabilities.
    caps=$("$getcap" -r -- "$1" 2>&1) || die "refusing $1: getcap failed: $caps"
    [ -z "$caps" ] || die "refusing $1: file capabilities, or getcap failed: $caps"
}

# container DIR IMAGE [DOCKER-OPTION…] -- SCRIPT [ARG…]: one disposable container without the MKNOD and SETFCAP
# capabilities, the tracked files read-only at /src, DIR writable at /out and $tmp/key.pgp on stdin; afterwards DIR
# must be plain.
container() {
    local dir=$1 image=$2 opts=()
    shift 2
    while [ "$1" != -- ]; do opts+=("$1") && shift; done
    shift
    docker run --rm -i --cap-drop MKNOD --cap-drop SETFCAP -e OWNER="$(id -u):$(id -g)" -v "$tmp/src:/src:ro" \
        -v "$dir:/out" "${opts[@]}" "$image" bash "$@" < "$tmp/key.pgp"
    only_plain "$dir"
}

# fingerprint FILE: the fingerprint of the one primary key in the key file FILE, read in the empty keyring $tmp/gnupg
# (the caller makes it, never its GNUPGHOME); fails unless FILE holds exactly one primary key.
fingerprint() {
    command gpg --homedir "$tmp/gnupg" --no-options --batch --with-colons --show-keys -- "$1" 2> /dev/null |
        awk -F: '$1 == "pub" { n++ } $1 == "fpr" && !f { f = $10 }
            END { if (n != 1 || f !~ /^[0-9A-F]{40}$/) exit 1; print f }'
}
