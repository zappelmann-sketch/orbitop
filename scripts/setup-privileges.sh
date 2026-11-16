#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Installs the runtime packages and grants the few privileges orbitop optionally uses.
# Usage: sudo bash setup-privileges.sh [--dry-run]
# Detection reads from ${ORBITOP_SYSROOT:-/} so it can be tested against fake trees.
set -euo pipefail

dry_run=0
case "${1:-}" in
    "") ;;
    --dry-run) dry_run=1 ;;
    *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac
[ $# -le 1 ] || { echo "usage: $0 [--dry-run]" >&2; exit 2; }

if [ "$dry_run" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    echo "This script must run as root (use: sudo bash $0), or pass --dry-run." >&2
    exit 1
fi

root=${ORBITOP_SYSROOT:-/}
root=${root%/}
tmpfiles_conf=/etc/tmpfiles.d/orbitop-rapl.conf

has_intel_gfx=0
for link in "$root"/sys/class/drm/card[0-9]*/device/driver; do
    [ -L "$link" ] || continue
    case "$(basename -- "$(readlink -- "$link")")" in
        i915|xe) has_intel_gfx=1 ;;
    esac
done

has_rapl=0
[ -d "$root/sys/class/powercap/intel-rapl:0" ] && has_rapl=1

# Runs a command, or only prints it with --dry-run.
run() {
    if [ "$dry_run" -eq 1 ]; then
        echo "WOULD: $*"
    else
        "$@"
    fi
}

write_tmpfiles_conf() {
    if [ "$dry_run" -eq 1 ]; then
        echo "WOULD: write $tmpfiles_conf"
        return
    fi
    printf '%s\n' \
        'z /sys/class/powercap/intel-rapl:*/energy_uj 0444 - - -' \
        'z /sys/class/powercap/intel-rapl:*/intel-rapl:*/energy_uj 0444 - - -' \
        > "$tmpfiles_conf"
    chmod 0644 -- "$tmpfiles_conf"
}

packages=(gir1.2-webkit-6.0)
[ "$has_intel_gfx" -eq 1 ] && packages+=(intel-gpu-tools)
run apt-get install -y "${packages[@]}"

if [ "$has_intel_gfx" -eq 1 ]; then
    igt=/usr/bin/intel_gpu_top
    if [ "$dry_run" -eq 0 ]; then
        igt=$(readlink -f -- "$(command -v intel_gpu_top)")
    fi
    run setcap cap_perfmon=ep "$igt"
fi

if [ "$has_rapl" -eq 1 ]; then
    write_tmpfiles_conf
    run systemd-tmpfiles --create "$tmpfiles_conf"
    echo "Note: RAPL energy counters are readable by root only because they allow a power side channel (CVE-2020-8694); on a single-user machine, making them world-readable is acceptable."
fi
