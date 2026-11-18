#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Checks setup-privileges.sh, the runtime and the tests in disposable distribution containers (docs/distro-check.md).
# Usage: bash check-distros.sh [image …]   one "docker run --rm" per image, a copy of the tracked files at /src (ro)
#        bash check-distros.sh --inside    only as root inside such a container: installs packages for real
set -euo pipefail

usage() { echo "usage: $0 [image …] | --inside" >&2; exit 2; }

failed=0
# Prints "STEP <name> ok|fail"; later steps still run, so the log shows every result.
step() {
    local name=$1
    shift
    if "$@"; then
        echo "STEP $name ok"
    else
        echo "STEP $name fail"
        failed=1
    fi
}

as_tester() { (cd /home/tester/orbitop && runuser -u tester -- "$@"); }

# As an ordinary user on a writable copy: the tests of the refusals without root skip themselves as root.
run_tests() {
    useradd -m tester && cp -r /src /home/tester/orbitop && chown -R tester: /home/tester/orbitop &&
        as_tester python3 -m pytest -q
}

inside() {
    if [ ! -e /.dockerenv ] || [ "$(id -u)" -ne 0 ]; then
        echo "--inside installs packages as root and runs only as root inside a disposable container." >&2
        exit 1
    fi
    export DEBIAN_FRONTEND=noninteractive  # tzdata would otherwise ask for a time zone
    grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
    local m manager=none refresh=(true) tools=()
    for m in apt-get dnf pacman zypper; do  # same order as setup-privileges.sh
        if command -v "$m" >/dev/null; then
            manager=$m
            break
        fi
    done
    # Index refresh as in the README; dnf and zypper refresh on their own.
    case "$manager" in
        apt-get)
            refresh=(apt-get update)
            tools=(apt-get install -y python3-pytest shellcheck desktop-file-utils appstream) ;;
        dnf)  # util-linux: runuser, missing from the Fedora image
            tools=(dnf install -y python3-pytest ShellCheck desktop-file-utils appstream util-linux) ;;
        pacman)
            refresh=(pacman -Syu --noconfirm)
            tools=(pacman -S --needed --noconfirm python-pytest shellcheck desktop-file-utils appstream) ;;
        zypper)
            tools=(zypper --non-interactive install python3-pytest ShellCheck desktop-file-utils AppStream) ;;
        *)
            echo "No supported package manager (apt-get, dnf, pacman, zypper)." >&2
            exit 1 ;;
    esac
    step refresh "${refresh[@]}"
    step setup bash /src/scripts/setup-privileges.sh
    step import python3 -c '
import sys, gi
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gtk, WebKit
def v(m): return f"{m.get_major_version()}.{m.get_minor_version()}.{m.get_micro_version()}"
print("VERSIONS python", sys.version.split()[0], "pygobject", gi.__version__, "gtk", v(Gtk), "webkitgtk", v(WebKit))'
    step tools "${tools[@]}"
    step pytest run_tests
    step dry-run as_tester bash scripts/setup-privileges.sh --dry-run
    step version as_tester python3 bin/orbitop --version
    echo "PYTHON $(python3 --version 2>&1)"
    exit "$failed"
}

host() {
    local image repo digest rc first results=()
    for image in "$@"; do
        case "$image" in -*|"") usage ;; esac  # never an option for docker run
    done
    repo=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
    log=$(mktemp)
    copy=$(mktemp -d)
    trap 'rm -rf -- "$log" "$copy"' EXIT
    # A container sees only the tracked files, never local ones such as CLAUDE.md or .git; a release tree has no others.
    if [ -e "$repo/.git" ]; then
        git -C "$repo" ls-files -z | tar -C "$repo" --null -T - -cf - | tar -C "$copy" -xf -
    else
        cp -a -- "$repo/." "$copy"
    fi
    for image in "$@"; do
        if ! docker pull "$image"; then
            results+=("RESULT $image - fail pull")
            continue
        fi
        digest=$(docker image inspect --format '{{index .RepoDigests 0}}' "$image")
        rc=0
        docker run --rm -v "$copy:/src:ro" "$image" bash /src/scripts/check-distros.sh --inside 2>&1 |
            tee "$log" || rc=$?
        first=$(sed -n '/^STEP .* fail$/{s/^STEP //;s/ fail$//;p;q}' "$log")
        if [ "$rc" -eq 0 ] && [ -z "$first" ]; then
            results+=("RESULT $image $digest pass -")
        else
            results+=("RESULT $image $digest fail ${first:-run}")
        fi
    done
    printf '%s\n' "${results[@]}"
}

if [ "${1:-}" = --inside ]; then
    [ $# -eq 1 ] || usage
    inside
fi
[ $# -gt 0 ] || set -- ubuntu:24.04 debian:trixie fedora:latest archlinux:latest opensuse/tumbleweed debian:bookworm \
    ubuntu:22.04
host "$@"
