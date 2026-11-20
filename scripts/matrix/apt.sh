# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# apt (Debian, Ubuntu) for scripts/matrix/inside.sh, which sources it after lib.sh. With a file:// source the pin of
# orbitop-apt-source does not apply (no origin, priority 500); the upgrade therefore serves SITE2 over http under the
# host name of Pages, where it applies.
# shellcheck shell=bash disable=SC2034,SC2154  # NOISE is read by lib.sh, PAGES and STATE come from it

NOISE='^(W|E|N|Err|Warning|Error|Notice):'  # apt-get and apt 2 abbreviate, apt 3 does not
SOURCE=/etc/apt/sources.list.d/orbitop.sources
DISTS=apt/dists/stable
INDEX=$DISTS/main/binary-all
SERVED=http://${PAGES#https://}  # the Pages address over http, served by serve

refresh() { net apt-get update; }

# keyring ROOT: orbitop-apt-source from the file, as the README downloads it from the release; the Release of ROOT
# has Architectures all, by-hash and no Valid-Until (spec 2).
keyring() {
    local release
    release=$(cat "$1/$DISTS/Release") || return 1
    cp -- "$1"/apt/pool/main/o/orbitop-apt-source/orbitop-apt-source_*_all.deb "$STATE/orbitop-apt-source.deb" &&
        (cd "$STATE" && apt install ./orbitop-apt-source.deb -y) && point "$SOURCE" "file://$1/" &&
        grep -qx 'Architectures: all' <<< "$release" && grep -qx 'Acquire-By-Hash: yes' <<< "$release" &&
        ! grep '^Valid-Until:' <<< "$release"
}

install_pkg() { quiet apt update && net apt install orbitop -y && apt-cache policy orbitop; }

tools() { net apt-get install -y python3-pytest shellcheck desktop-file-utils appstream; }

installed() { dpkg-query -W -f '${Version}' orbitop; }
offered() { dpkg-deb -f "$1"/apt/pool/main/o/orbitop/orbitop_*_all.deb Version; }

# serve ROOT: ROOT at $SERVED on 127.0.0.1:80, in the background as $server (python3 comes with orbitop).
serve() {
    local _
    mkdir -p "$STATE/pages" && ln -sfn -- "$1" "$STATE/pages/orbitop" || return 1
    grep -q ' zappelmann-sketch.github.io$' /etc/hosts || echo '127.0.0.1 zappelmann-sketch.github.io' >> /etc/hosts
    python3 -m http.server 80 --bind 127.0.0.1 --directory "$STATE/pages" > "$STATE/http.log" 2>&1 &
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
    local rc=0 policy
    serve "$1" || return 1
    { point "$SOURCE" "$SERVED" && quiet apt update && policy=$(apt-cache policy orbitop) && echo "$policy" &&
        grep -qE "^ +100 ${SERVED//./\\.}apt stable/main all Packages$" <<< "$policy" && net apt upgrade -y &&
        grep -F "GET /orbitop/$INDEX/by-hash/SHA" "$STATE/http.log"; } || rc=1
    kill "$server"
    point "$SOURCE" "file://$1/" && return "$rc"
}

files_of() { dpkg -L orbitop orbitop-apt-source | grep -vx '/\.'; }
owned() { dpkg -S -- "$1" > /dev/null 2>&1; }
packages() { dpkg-query -W; }

# apt remove orbitop, then orbitop-apt-source: its conffiles keep a working source with its key.
remove() {
    local policy
    files_of > "$STATE/files" && apt remove orbitop -y && quiet apt update && apt remove orbitop-apt-source -y &&
        quiet apt update && policy=$(apt-cache policy orbitop) && grep -E '^  Candidate: [0-9]' <<< "$policy"
}

# apt purge of both (first forget: apt did not change the source; it keeps pointing to SITE2, so that apt still
# knows orbitop): nothing of their file lists is left, and apt keeps no index of the source.
purge() {
    forget "$SOURCE" && apt purge orbitop orbitop-apt-source -y && leftovers "$STATE/files" &&
        quiet apt update && absent '/var/lib/apt/lists/*_site*' '/var/lib/apt/lists/*zappelmann-sketch*'
}

# change_index ROOT: Packages.gz with a changed byte, also at its by-hash paths (named after its SHA256 and SHA512),
# from where apt fetches it. This tests the hashes in the signed InRelease.
change_index() {
    local gz=$1/$INDEX/Packages.gz by=$1/$INDEX/by-hash sha256 sha512
    sha256=$(sha256sum < "$gz") && sha512=$(sha512sum < "$gz") || return 1
    sha256=$by/SHA256/${sha256%% *} sha512=$by/SHA512/${sha512%% *}
    [ -f "$sha256" ] && [ -f "$sha512" ] && flip "$gz" && cp -- "$gz" "$sha256" && cp -- "$gz" "$sha512"
}

# change_release ROOT: the last digit of the seconds in the signed Date of InRelease changed; the format stays valid,
# so only the signature can refuse it.
change_release() {
    local inrelease=$1/$DISTS/InRelease found match
    found=$(grep -bo '^Date: [^:]*:[0-9][0-9]:[0-9][0-9]' "$inrelease") && [ "$(wc -l <<< "$found")" -eq 1 ] || return 1
    match=${found#*:}  # grep -bo prints OFFSET:MATCH
    flip "$inrelease" $((${found%%:*} + ${#match} - 1))
}

tamper() {
    tampered index 'Hash Sum mismatch' change_index && tampered release 'is not signed' change_release
}

refresh_index() { apt update; }
