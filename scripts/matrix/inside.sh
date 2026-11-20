#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# The container matrix of scripts/check-distros.sh (docs/distro-check.md), as root in a disposable container: the files
# of the commit the packages are built from at /src, the package source at /site and the one with the check version
# (plan K6) at /site2, all read-only.
# It installs, tests, updates and removes orbitop with the commands of the README. Only the installed copies of the
# source definitions under /etc point to file:// here (point); the packages keep the Pages address.
# Prints "STEP <name> ok|fail". The helpers are in scripts/matrix/lib.sh, the commands of each package manager in
# scripts/matrix/<manager>.sh; it provides NOISE and refresh, keyring ROOT, install_pkg, tools, installed, offered ROOT,
# update_from ROOT, files_of, owned PATH, packages (for net in lib.sh), remove, purge, tamper and refresh_index.
# shellcheck source-path=SCRIPTDIR disable=SC2317,SC2329  # step calls the functions
set -euo pipefail

if [ ! -e /.dockerenv ] || [ "$(id -u)" -ne 0 ]; then
    echo "$0 installs packages as root and runs only as root inside a disposable container." >&2
    exit 1
fi
export DEBIAN_FRONTEND=noninteractive  # tzdata would otherwise ask for a time zone
SITE=/site
SITE2=/site2
# shellcheck source=lib.sh
. /src/scripts/matrix/lib.sh
mkdir -p "$STATE"

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

# The installed starter names the version of /src: the packages are built from the same commit.
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

# tampered NAME TEXT CHANGE: a copy of SITE in STATE/tamper-NAME, changed by CHANGE ROOT and set up as the source
# again; the index refresh must refuse it with the reason TEXT.
tampered() {
    local copy=$STATE/tamper-$1
    rm -rf -- "$copy" && cp -a "$SITE" "$copy" && "$3" "$copy" && keyring "$copy" && refused "$2" refresh_index
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
step install install_pkg
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
