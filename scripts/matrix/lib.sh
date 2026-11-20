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

# A network hiccup at a mirror, not a fault of the packages: curl's codes for resolve, connect, timeout, TLS
# handshake, empty reply and receive, and the same failures in the words of the system.
HICCUP='Curl error \((6|7|28|35|52|56)\)|Connection reset by peer|Could not resolve host'
HICCUP+='|Temporary failure in name resolution|Operation timed out'

# quiet COMMAND…: COMMAND succeeds and prints no line that matches NOISE (warnings, notices, errors). A run that fails
# so and printed a network hiccup (HICCUP) runs again after 10 s, up to three runs, and only the last one counts; any
# other failure counts at once. The callers are index refreshes, which may run again; the tamper step uses refused.
quiet() {
    local out rc noise run
    for run in 1 2 3; do
        rc=0
        out=$("$@" 2>&1) || rc=$?
        printf '%s\n' "$out"
        noise=$(grep -E -- "$NOISE" <<< "$out") || true
        [ -z "$noise" ] || printf 'NOISE %s\n' "$noise"
        [ "$rc" -ne 0 ] || [ -n "$noise" ] || return 0
        if [ "$run" -eq 3 ] || ! grep -qE -- "$HICCUP" <<< "$out"; then return 1; fi
        echo "RETRY run $((run + 1)) of 3 in 10 s: network hiccup"
        sleep 10
    done
}

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
        if [ -d "$path" ] && [ ! -L "$path" ] && owned "$path"; then continue; fi
        left+=("$path")
    done < "$1"
    [ ! -e /etc/orbitop ] || left+=(/etc/orbitop)
    [ ${#left[@]} -eq 0 ] || { printf 'left behind: %s\n' "${left[@]}" && return 1; }
}
