# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Helpers of scripts/matrix/inside.sh and the files of the package managers, sourced first. They need no root, so
# tests/test_check_distros.py sources them too. STATE is the directory for the matrix's own files (default
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

# quiet COMMAND…: COMMAND succeeds and prints no line that matches NOISE (warnings, notices, errors).
quiet() {
    local out rc=0 noise
    out=$("$@" 2>&1) || rc=$?
    printf '%s\n' "$out"
    noise=$(grep -E -- "$NOISE" <<< "$out") || true
    [ -z "$noise" ] || printf 'NOISE %s\n' "$noise"
    [ "$rc" -eq 0 ] && [ -z "$noise" ]
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
