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
owned() { dpkg -S -- "$1" 2> /dev/null; }
# packages: with the status, so that a removal that keeps the conffiles changes the list too.
# shellcheck disable=SC2016  # the format of dpkg-query
packages() { dpkg-query -W -f '${db:Status-Abbrev} ${binary:Package} ${Version}\n'; }

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

# The counter release (scripts/matrix/counters.sh). The owner of intel_gpu_top as in the security document 0.3.0,
# B2.4: igt-gpu-tools on Ubuntu 26.04, where intel-gpu-tools is a metapackage that depends on it with an exact version
# (a newer igt-gpu-tools would break it); install_owner checks it with dpkg -S.
COUNTER_CASES=(orbitop_install_manual_cap file_list reinstall_owner_off on_off reinstall_owner_on owner_remove
    owner_first_install_on rev2_upgrade_on remove_on remove_broken_helper purge manual_rule_untouched upgrade_from_020
    joint_upgrade)
OWNER=intel-gpu-tools
if grep -qx 'ID=ubuntu' /etc/os-release && grep -qx 'VERSION_ID="26.04"' /etc/os-release; then OWNER=igt-gpu-tools; fi
JOINT=(install_pair dpkg_pair dpkg_pair_reversed)  # B2.4, 6: apt-get install of both files, dpkg -i in both orders
TRIGGERED='^Processing triggers for orbitop '
REVOKE_FAILED='^orbitop: counter release not revoked$'  # prerm, when off cannot run

install_owner() { net apt-get install -y "$OWNER" && [ "$(owned "$TOOL")" = "$OWNER: $TOOL" ]; }
reinstall_owner() { net apt-get install --reinstall -y "$OWNER"; }
remove_owner() { apt-get remove -y "$OWNER"; }

# fake_owner N: OWNER as the next version, <installed version>+fakeN, built here; its intel_gpu_top is a copy of the
# installed program (an ELF file; cp takes no capability along). Prints the file.
fake_owner() {
    local dir=$STATE/owner-$1 version
    version=$(dpkg-query -W -f '${Version}' "$OWNER") && rm -rf -- "$dir" && mkdir -p "$dir/DEBIAN" "$dir/usr/bin" &&
        cp -- "$TOOL" "$dir/usr/bin/" && [ "$(head -c 4 -- "$TOOL" | od -An -c | tr -d ' ')" = 177ELF ] &&
        printf '%s\n' "Package: $OWNER" "Version: $version+fake$1" "Architecture: $(dpkg --print-architecture)" \
            "Maintainer: orbitop matrix <matrix@example.com>" "Description: the next version of $OWNER, for the matrix" \
            > "$dir/DEBIAN/control" && dpkg-deb --root-owner-group --build "$dir" "$dir.deb" > /dev/null && echo "$dir.deb"
}

install_file() { dpkg -i "$1"; }  # also over the same or a higher version, where apt would keep what is installed
install_pair() { apt-get install -y "$1" "$2"; }  # one apt transaction for both files
dpkg_pair() { dpkg -i "$1" "$2"; }
dpkg_pair_reversed() { dpkg -i "$2" "$1"; }
remove_pkg() { apt-get remove -y "$1"; }
purge_pkg() { apt-get purge -y "$1"; }
pkg_files() { dpkg -L orbitop; }

# orbitop_file rev1|rev2|v020: orbitop of SITE, or the one check-distros.sh built of the same tree as revision 2
# (REV2) or of the tag v0.2.0 (V020).
orbitop_file() {
    local files
    case $1 in
        rev1) files=("$SITE"/apt/pool/main/o/orbitop/orbitop_*_all.deb) ;;
        rev2) files=("$REV2"/deb/orbitop_*_all.deb) ;;
        v020) files=("$V020"/deb/orbitop_*_all.deb) ;;
        *) return 1 ;;
    esac
    [ ${#files[@]} -eq 1 ] && [ -f "${files[0]}" ] && echo "${files[0]}"
}
