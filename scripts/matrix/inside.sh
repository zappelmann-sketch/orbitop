#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# The container matrix of scripts/check-distros.sh (docs/distro-check.md), as root in a disposable container: the files
# of HEAD at /src, the package source at /site and the one with the check version (plan K6) at /site2, all read-only.
# It installs, tests, updates and removes orbitop with the commands of the README. Only the installed copies of the
# source definitions under /etc point to file:// here (point); the packages keep the Pages address.
# Prints "STEP <name> ok|fail". The commands of each package manager are in scripts/matrix/<manager>.sh; it provides
# NOISE, TAMPERED and refresh, keyring ROOT, install, tools, installed, offered ROOT, update_from ROOT, files_of, owned
# PATH, remove, purge, tamper_index ROOT and refresh_index.
# shellcheck source-path=SCRIPTDIR disable=SC2153,SC2317,SC2329  # NOISE is in <manager>.sh; step calls the functions
set -euo pipefail

if [ ! -e /.dockerenv ] || [ "$(id -u)" -ne 0 ]; then
    echo "$0 installs packages as root and runs only as root inside a disposable container." >&2
    exit 1
fi
export DEBIAN_FRONTEND=noninteractive  # tzdata would otherwise ask for a time zone
PAGES=https://zappelmann-sketch.github.io/orbitop/
SITE=/site
SITE2=/site2

failed=0
# step NAME COMMAND…: prints "STEP NAME ok|fail"; later steps still run, so the log shows every result.
step() {
    local name=$1
    shift
    echo "=== $name"
    if "$@"; then
        echo "STEP $name ok"
    else
        echo "STEP $name fail"
        failed=1
    fi
}

# point FILE BASE: FILE as its package installed it (kept in /tmp on the first call), with the Pages address
# replaced by BASE.
point() {
    local pristine=/tmp/pristine${1//\//_}
    [ -f "$pristine" ] || cp -- "$1" "$pristine" || return 1
    sed "s|${PAGES//./\\.}|$2|g" "$pristine" > "$1" && grep -qF -- "$2" "$1"
}

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

# flip FILE [OFFSET]: the byte at OFFSET (default: in the middle of FILE) with its lowest bit inverted; a digit
# stays a digit.
flip() {
    local off=${2:-$(($(stat -c %s -- "$1") / 2))} byte
    byte=$(od -An -tu1 -j "$off" -N1 -- "$1") || return 1
    # shellcheck disable=SC2059  # the format is the octal escape of the new byte
    printf "$(printf '\\%03o' $((byte ^ 1)))" | dd of="$1" bs=1 seek="$off" conv=notrunc status=none
}

# leftovers LIST: no path of LIST (the file lists of the packages) is left, but directories another package owns;
# and there is no /etc/orbitop.
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

import_gi() {
    python3 -c '
import sys, gi
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gtk, WebKit
def v(m): return f"{m.get_major_version()}.{m.get_minor_version()}.{m.get_micro_version()}"
print("VERSIONS python", sys.version.split()[0], "pygobject", gi.__version__, "gtk", v(Gtk), "webkitgtk", v(WebKit))'
}

as_tester() { runuser -u tester -- "$@"; }

# As an ordinary user on a writable copy: the tests of the refusals without root skip themselves as root.
run_tests() {
    cp -r /src /home/tester/orbitop && chown -R tester: /home/tester/orbitop &&
        (cd /home/tester/orbitop && as_tester python3 -m pytest -q)
}

# The installed starter names the version of /src: the packages are built from the same HEAD.
version() {
    local want got
    want="orbitop $(sed -n 's/^__version__ = "\(.*\)"$/\1/p' /src/orbitop/__init__.py)"
    got=$(cd / && as_tester /usr/bin/orbitop --version) && echo "$got" && [ "$got" = "$want" ]
}

# SITE2 offers the check version; the regular update of the package manager installs it.
upgrade() {
    local before offered after
    before=$(installed) && offered=$(offered "$SITE2") && update_from "$SITE2" || return 1
    after=$(installed)
    echo "VERSION before $before, offered $offered, after $after"
    [ "$after" = "$offered" ] && [ "$after" != "$before" ]
}

# A copy of SITE with one changed byte in its signed index: the index refresh must refuse it, with its reason.
tamper() {
    rm -rf /tmp/tamper && cp -a "$SITE" /tmp/tamper && tamper_index /tmp/tamper && keyring /tmp/tamper &&
        refused "$TAMPERED" refresh_index
}

grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
for manager in apt-get dnf pacman zypper none; do
    command -v "$manager" > /dev/null && break
done
case $manager in
    apt-get) manager=apt ;;
    dnf | zypper)
        # shellcheck source=rpm.sh
        . /src/scripts/matrix/rpm.sh ;;
    none) echo "No supported package manager (apt-get, dnf, pacman, zypper)." >&2 && exit 1 ;;
esac
# shellcheck source=/dev/null  # one of apt.sh, dnf.sh, pacman.sh, zypper.sh
. "/src/scripts/matrix/$manager.sh"
useradd -m tester

step refresh refresh
step keyring keyring "$SITE"
step install install
[ "$failed" -eq 0 ] || exit 1  # without orbitop the remaining steps have nothing to check
step import import_gi
step tools tools
step pytest run_tests
step version version
step upgrade upgrade
step remove remove
step purge purge
step tamper tamper
exit "$failed"
