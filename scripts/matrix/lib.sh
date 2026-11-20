# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Helpers of scripts/matrix/inside.sh and the files of the package managers, sourced first. They need no root, so
# tests/test_matrix_lib.py sources them too. STATE is the directory for the matrix's own files (default
# /tmp/matrix); NOISE comes from the file of the package manager.
# shellcheck shell=bash disable=SC2153,SC2154  # NOISE comes from <manager>.sh

PAGES=https://zappelmann-sketch.github.io/orbitop/  # as in orbitop.sources, the .repo files and the README
STATE=${STATE:-/tmp/matrix}

# point FILE BASE: FILE as its package installed it (kept in STATE on the first call), with the Pages address
# replaced by BASE. It refuses when FILE is no longer what it wrote last (written).
point() {
    local name=${1//\//_}
    if [ -f "$STATE/written$name" ]; then
        written "$1" || return 1
    else
        cp -- "$1" "$STATE/pristine$name" || return 1
    fi
    sed "s|${PAGES//./\\.}|$2|g" "$STATE/pristine$name" > "$1" && cp -- "$1" "$STATE/written$name" &&
        grep -qF -- "$2" "$1"
}

# written FILE: FILE is still what point wrote to it last; otherwise the package manager changed it.
written() {
    local now was
    now=$(sha256sum < "$1") && was=$(sha256sum < "$STATE/written${1//\//_}") || return 1
    [ "$now" = "$was" ] || { echo "changed since the last point: $1" && return 1; }
}

# forget FILE: written FILE, and point starts over with it: its package goes, and a new one installs it anew.
forget() { written "$1" && rm -f -- "$STATE/written${1//\//_}" "$STATE/pristine${1//\//_}"; }

# A network hiccup at a mirror, not a fault of the packages, in the words the images print (tests/test_matrix_retry.py):
# curl's codes for resolve, connect, timeout, TLS handshake, empty reply and receive, as dnf ("Curl error (56):") and
# zypper ("Curl error 56") write them, not 60 (a certificate); the texts of libcurl after pacman's "failed retrieving
# file"; apt's own; those of the system. Never "Failed to connect to": systemd writes it in the scripts of packages.
HICCUP='Curl error \(?(6|7|28|35|52|56)\b|Timeout exceeded when accessing'  # dnf, zypper
HICCUP+="|Could not resolve host|Could(n't| not) connect to|Operation timed out|Operation too slow"  # libcurl
HICCUP+="|Empty reply from server|Connection timed out|Temporary failure resolving|Could not resolve '"  # and apt
HICCUP+='|Resolving timed out after|Connection timeout after'  # libcurl ("%s timed out after", "Resolving")
HICCUP+="|Failed to resolve '[^']*' with timeout after"  # libcurl 8 of Arch, Fedora and Tumbleweed
HICCUP+='|Connection reset by peer|Temporary failure in name resolution'  # libc

# real_pkexec [SHARE]: the installed orbitop (SHARE, default /usr/share/orbitop) accepts /usr/bin/pkexec with its own
# check, the one before every pkexec (actions._real_pkexec): a root-owned ELF with the setuid bit in a root-owned
# directory chain. From / with python3 -I, so that only SHARE provides orbitop.
real_pkexec() {
    (cd / && python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); from orbitop.actions import _real_pkexec
sys.exit(not _real_pkexec())' "${1:-/usr/share/orbitop}") ||
        { echo "PKEXEC refused by the check of the installed orbitop (actions._real_pkexec)"; return 1; }
}

# logged FILE COMMAND…: COMMAND, its output live on stdout and in FILE, with or without set -e and pipefail. Returns
# the exit code of COMMAND, or, if COMMAND succeeded, that of tee: without FILE, nothing may judge the output.
logged() {
    local status=()
    { "${@:2}" 2>&1 | tee -- "$1"; status=("${PIPESTATUS[@]}"); } || true
    [ "${status[0]}" -ne 0 ] || return "${status[1]}"
    return "${status[0]}"
}

# matching PATTERN FILE: the lines of FILE that match PATTERN, as text, with each NUL byte and each carriage return
# read as a line break, so that none hides the start of a line from an anchored pattern. Returns 0 on a match, 1 on
# none, 2 if FILE, tr or grep fails: a read error is never "no match".
matching() {
    local status=()
    # shellcheck disable=SC2020  # two characters, each to a line break
    { tr '\0\r' '\n\n' < "$2" | grep -aE -- "$1"; status=("${PIPESTATUS[@]}"); } || true
    [ "${status[0]}" -eq 0 ] || return 2
    return "${status[1]}"
}

# held: a fingerprint of the installed packages (packages, from the file of the package manager), never of an empty
# list; without stderr, where pacman warns about sync databases that the first refresh has not fetched yet.
held() {
    local list
    list=$(packages 2> /dev/null) && [ -n "$list" ] && sha256sum <<< "$list"
}

# net COMMAND…: COMMAND, for the commands that fetch from the mirrors. A run that fails, printed a network hiccup
# (HICCUP) and left the installed packages as they were (held) runs again after 10 s, up to three runs, and only the
# last one counts; any other failure counts at once. 10 s let a reset connection or a resolver hiccup pass and add at
# most 20 s to a step. COMMAND runs in a subshell. Never for the index refresh of the tamper step (refused).
net() {
    local rc run before after
    for run in 1 2 3; do
        before=$(held) || before=""
        rm -f -- "$STATE/net.out" || return 1  # no copy of an earlier run may decide
        rc=0
        logged "$STATE/net.out" "$@" || rc=$?
        [ "$rc" -ne 0 ] || return 0
        # matching fails with 2 if it cannot read the file: no hiccup either, so no retry.
        if [ "$run" -eq 3 ] || ! matching "$HICCUP" "$STATE/net.out" > /dev/null; then return "$rc"; fi
        after=$(held) || after=""
        if [ -z "$before" ] || [ "$before" != "$after" ]; then
            echo "NO RETRY: the installed packages changed or are unknown"
            return "$rc"
        fi
        echo "RETRY run $((run + 1)) of 3 in 10 s: network hiccup"
        sleep 10
    done
}

# clean COMMAND…: COMMAND succeeds and prints no line that matches NOISE (warnings, notices, errors).
clean() {
    local rc=0 noise found=0
    [ -n "${NOISE:-}" ] || { echo "NOISE is not set: nothing can judge the output"; return 1; }
    rm -f -- "$STATE/clean.out" || return 1  # no copy of an earlier run may decide
    logged "$STATE/clean.out" "$@" || rc=$?
    noise=$(matching "$NOISE" "$STATE/clean.out") || found=$?
    [ "$found" -le 1 ] || { echo "NOISE unknown: cannot read $STATE/clean.out"; return 1; }  # 1: no match
    [ -z "$noise" ] || printf 'NOISE %s\n' "$noise"
    [ "$rc" -eq 0 ] && [ -z "$noise" ]
}

# quiet COMMAND…: clean COMMAND with the retries of net; the callers are index refreshes, which may run again.
quiet() { net clean "$@"; }

# refused TEXT COMMAND…: COMMAND fails, and its output names the reason TEXT.
refused() {
    local out rc=0
    out=$("${@:2}" 2>&1) || rc=$?
    printf '%s\n' "$out"
    [ "$rc" -ne 0 ] && grep -qF -- "$1" <<< "$out"
}

# absent PATTERN…: no path matches any glob PATTERN; the ones that do are printed.
absent() {
    local pattern
    for pattern; do
        ! compgen -G "$pattern" || return 1
    done
}

# flip FILE [OFFSET]: the byte at OFFSET (default: in the middle of FILE) with its lowest bit inverted; a digit
# stays a digit.
flip() {
    local off=${2:-$(($(stat -c %s -- "$1") / 2))} byte
    byte=$(od -An -tu1 -j "$off" -N1 -- "$1") && [ -n "$byte" ] || return 1
    # shellcheck disable=SC2059  # the format is the octal escape of the new byte
    printf "$(printf '\\%03o' $((byte ^ 1)))" | dd of="$1" bs=1 seek="$off" conv=notrunc status=none
}

# leftovers LIST: no path of LIST (the file lists of the packages) is left, but directories another package owns
# (owned PATH, from the file of the package manager); and there is no /etc/orbitop.
leftovers() {
    local path left=()
    while IFS= read -r path; do
        [ -e "$path" ] || [ -L "$path" ] || continue
        if [ -d "$path" ] && [ ! -L "$path" ] && owned "$path" > /dev/null; then continue; fi
        left+=("$path")
    done < "$1"
    [ ! -e /etc/orbitop ] || left+=(/etc/orbitop)
    [ ${#left[@]} -eq 0 ] || { printf 'left behind: %s\n' "${left[@]}" && return 1; }
}
