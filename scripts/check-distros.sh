#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Installs, tests, updates and removes the packages from the signed package source in disposable containers, one
# "docker run --rm" per image (docs/distro-check.md). The steps run in scripts/matrix/inside.sh.
# Usage: bash check-distros.sh --site SITE --site2 SITE2 [image …]
#        SITE and SITE2 come from build-site.sh, SITE2 from packages built with --suffix (plan K6). Each container gets
#        them read-only at /site and /site2 and the files of HEAD read-only at /src, nothing writable.
#        Prints "KEY <fingerprint>" (the key both trees carry), "IMAGE <image>" before the log of each image and at the
#        end "RESULT <image> <digest> pass|fail <step>" per image; exits 1 unless every image passed.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=container-common.sh
. "$(dirname -- "$0")/container-common.sh"  # die, usage, workdir, tracked_files

IMAGES=(debian:trixie ubuntu:24.04 ubuntu:26.04 fedora:latest opensuse/tumbleweed archlinux:latest debian:bookworm
    ubuntu:22.04)
# Python older than 3.12: they pass only if exactly the step install fails, with apt's reason.
REFUSING=" debian:bookworm ubuntu:22.04 "
REFUSAL="orbitop : Depends: python3 (>= 3.12)"
USAGE="$0 --site SITE --site2 SITE2 [image …]"

site="" site2=""
while [ $# -gt 0 ] && [[ $1 == --* ]]; do
    case $1 in --site | --site2) name=${1#--} ;; *) usage ;; esac
    [[ $# -ge 2 && -z ${!name} ]] || usage  # each option once
    printf -v "$name" '%s' "$2"
    shift 2
done
[[ -n $site && -n $site2 ]] || usage
for image in "$@"; do
    [[ $image =~ ^[a-z0-9][A-Za-z0-9._/:@-]*$ ]] || usage  # an image, never an option for docker run
done
[ $# -gt 0 ] || set -- "${IMAGES[@]}"
for dir in "$site" "$site2"; do
    [[ -d $dir && -f $dir/orbitop-archive-keyring.asc ]] ||
        die "--site and --site2 must be trees from build-site.sh: $dir"
done
site=$(cd -- "$site" && pwd -P)
site2=$(cd -- "$site2" && pwd -P)

# fingerprint SITE: the fingerprint of the one primary key in the keyring of SITE, read in an empty keyring.
fingerprint() {
    gpg --homedir "$tmp/gnupg" --no-options --batch --with-colons --show-keys -- \
        "$1/orbitop-archive-keyring.asc" 2> /dev/null |
        awk -F: '$1 == "pub" { n++ } $1 == "fpr" && !f { f = $10 }
            END { if (n != 1 || f !~ /^[0-9A-F]{40}$/) exit 1; print f }'
}

# verdict IMAGE RC: "pass -", "pass install" for an expected refusal, or "fail <first failed step>".
verdict() {
    local failed first
    failed=$(sed -n 's/^STEP \(.*\) fail$/\1/p' "$tmp/log")
    first=${failed%%$'\n'*}
    if [[ $REFUSING == *" $1 "* ]]; then
        if [ "$failed" = install ] && grep -qF -- "$REFUSAL" "$tmp/log"; then
            echo "pass install"
        else
            echo "fail ${first:-install}"
        fi
    elif [ "$2" -eq 0 ] && [ -z "$failed" ]; then
        echo "pass -"
    else
        echo "fail ${first:-run}"
    fi
}

workdir
mkdir -m 700 "$tmp/gnupg"  # never the caller's GNUPGHOME
# The containers trust whatever key the sites carry; the run names it, and Task 10 compares it with ORBITOP_KEY.
key=$(fingerprint "$site") || die "--site: orbitop-archive-keyring.asc must hold exactly one key"
[ "$(fingerprint "$site2" || true)" = "$key" ] || die "--site2 must carry the same key as --site ($key)"
echo "KEY $key"
tracked_files  # a container sees only the files of HEAD, never local ones such as CLAUDE.md or .git
results=()
for image in "$@"; do
    echo "IMAGE $image"  # scripts/release/distro-check.py finds the log of each image by this line
    if ! docker pull "$image"; then
        results+=("RESULT $image - fail pull")
        continue
    fi
    # The container runs from the digest the result names, even if the tag moves meanwhile.
    digest=$(docker image inspect --format '{{index .RepoDigests 0}}' "$image") || digest=""
    if [[ ! $digest =~ ^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$ ]]; then
        results+=("RESULT $image - fail digest")
        continue
    fi
    rc=0
    # Nothing is writable for the container, so unlike the builds it keeps SETFCAP: rpm sets file capabilities.
    docker run --rm -v "$tmp/src:/src:ro" -v "$site:/site:ro" -v "$site2:/site2:ro" "$digest" \
        bash /src/scripts/matrix/inside.sh 2>&1 | tee "$tmp/log" || rc=$?
    results+=("RESULT $image $digest $(verdict "$image" "$rc")")
done
printf '%s\n' "KEY $key" "${results[@]}"
passed='^RESULT [^ ]+ [^ ]+ pass '
for result in "${results[@]}"; do
    [[ $result =~ $passed ]] || exit 1  # an expected refusal counts as passed
done
