# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# apt (Debian, Ubuntu) for scripts/matrix/inside.sh, which sources it and provides point, quiet, flip, leftovers,
# and PAGES. With a file:// source the pin of orbitop-apt-source does not apply (no origin, priority 500); the
# upgrade therefore serves SITE2 over http under the host name of Pages, where it applies.
# shellcheck shell=bash disable=SC2034,SC2154  # inside.sh reads NOISE and TAMPERED, and it sets PAGES

NOISE='^(W|E|N|Err|Warning|Error|Notice):'  # apt-get and apt 2 abbreviate, apt 3 does not
TAMPERED='Hash Sum mismatch'
SOURCE=/etc/apt/sources.list.d/orbitop.sources
INDEX=apt/dists/stable/main/binary-all
SERVED=http://${PAGES#https://}  # the Pages address over http, served by serve

refresh() { apt-get update; }

# keyring ROOT: orbitop-apt-source from the file, as the README downloads it from the release; the Release of ROOT
# has Architectures all, by-hash and no Valid-Until (spec 2).
keyring() {
    local release=$1/apt/dists/stable/Release
    cp -- "$1"/apt/pool/main/o/orbitop-apt-source/orbitop-apt-source_*_all.deb /tmp/orbitop-apt-source.deb &&
        (cd /tmp && apt install ./orbitop-apt-source.deb -y) && point "$SOURCE" "file://$1/" &&
        grep -qx 'Architectures: all' "$release" && grep -qx 'Acquire-By-Hash: yes' "$release" &&
        ! grep -q '^Valid-Until:' "$release"
}

install() { quiet apt update && apt install orbitop -y && apt-cache policy orbitop; }

tools() { apt-get install -y python3-pytest shellcheck desktop-file-utils appstream; }

installed() { dpkg-query -W -f '${Version}' orbitop; }
offered() { dpkg-deb -f "$1"/apt/pool/main/o/orbitop/orbitop_*_all.deb Version; }

# serve ROOT: ROOT at $SERVED on 127.0.0.1:80, in the background as $server (python3 comes with orbitop).
serve() {
    local _
    mkdir -p /tmp/pages && ln -sfn -- "$1" /tmp/pages/orbitop || return 1
    grep -q ' zappelmann-sketch.github.io$' /etc/hosts || echo '127.0.0.1 zappelmann-sketch.github.io' >> /etc/hosts
    python3 -m http.server 80 --bind 127.0.0.1 --directory /tmp/pages > /tmp/http.log 2>&1 &
    server=$!
    for _ in $(seq 50); do
        (exec 3<> /dev/tcp/127.0.0.1/80) 2> /dev/null && return 0
        sleep 0.1
    done
    return 1
}

# update_from ROOT: apt update and apt upgrade with ROOT served like Pages; the pin gives the source priority 100,
# and apt fetches the index by hash. Afterwards the source points to ROOT as file:// again.
update_from() {
    local rc=0
    serve "$1" || return 1
    { point "$SOURCE" "$SERVED" && quiet apt update && apt-cache policy orbitop | tee /tmp/policy &&
        grep -qE "^ +100 ${SERVED//./\\.}apt stable/main all Packages$" /tmp/policy && apt upgrade -y &&
        grep -F "GET /orbitop/$INDEX/by-hash/SHA" /tmp/http.log; } || rc=1
    kill "$server"
    point "$SOURCE" "file://$1/" && return "$rc"
}

files_of() { dpkg -L orbitop orbitop-apt-source | grep -vx '/\.'; }
owned() { dpkg -S -- "$1" > /dev/null 2>&1; }

# apt remove orbitop, then orbitop-apt-source: its conffiles keep a working source with its key.
remove() {
    files_of > /tmp/files && apt remove orbitop -y && quiet apt update && apt remove orbitop-apt-source -y &&
        quiet apt update && apt-cache policy orbitop | grep -E '^  Candidate: [0-9]'
}

# apt purge of both: nothing of their files lists is left, and apt keeps no index of the source.
purge() {
    apt purge orbitop orbitop-apt-source -y && leftovers /tmp/files && quiet apt update &&
        ! find /var/lib/apt/lists \( -name '_site*' -o -name '*zappelmann-sketch*' \) | grep .
}

# tamper_index ROOT: Packages.gz with a changed byte, also at its by-hash paths, from where apt fetches it.
tamper_index() {
    local f
    cp -- "$1/$INDEX/Packages.gz" /tmp/Packages.gz && flip "$1/$INDEX/Packages.gz" || return 1
    for f in "$1/$INDEX"/by-hash/*/*; do
        if cmp -s -- "$f" /tmp/Packages.gz; then cp -- "$1/$INDEX/Packages.gz" "$f" || return 1; fi
    done
}

refresh_index() { apt update; }
