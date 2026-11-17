#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Installs the runtime packages and the root-owned kill helper, and grants the few privileges orbitop optionally uses.
# Usage: sudo bash setup-privileges.sh [--dry-run] [--allow-rapl]
# With --dry-run, detection reads from ${ORBITOP_SYSROOT:-/} so it can be tested against fake trees.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 022  # directories created on the way to the helper must stay readable for orbitop's trust check

usage() { echo "usage: $0 [--dry-run] [--allow-rapl]" >&2; exit 2; }

dry_run=0
allow_rapl=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=1 ;;
        --allow-rapl) allow_rapl=1 ;;
        *) usage ;;
    esac
done

if [ "$dry_run" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    echo "This script must run as root (use: sudo bash $0), or pass --dry-run." >&2
    exit 1
fi

# Only the dry run may look at a fake tree; a real run always inspects the real system.
root=/
[ "$dry_run" -eq 1 ] && root=${ORBITOP_SYSROOT:-/}
root=${root%/}

rapl_rules=/etc/udev/rules.d/70-orbitop-rapl.rules
rapl_rule='ACTION=="add", SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", RUN+="/usr/bin/chmod 0444 /sys%p/energy_uj"'
igt=/usr/bin/intel_gpu_top
helper=/usr/local/libexec/orbitop/killhelper.py
helper_src="$(cd -- "$(dirname -- "$0")/.." && pwd -P)/orbitop/killhelper.py"

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

# orbitop runs pkexec only on a root-owned copy of the helper, never on the user-writable checkout.
if [ -L "$helper_src" ] || [ ! -f "$helper_src" ]; then
    echo "$helper_src is not a regular file; refusing to install the helper." >&2
    exit 1
fi

packages=(gir1.2-webkit-6.0)
[ "$has_intel_gfx" -eq 1 ] && packages+=(intel-gpu-tools)
run apt-get install -y "${packages[@]}"

run install -d -o root -g root -m 0755 "$(dirname -- "$helper")"
run install -o root -g root -m 0755 "$helper_src" "$helper"
echo "Note: after updating orbitop/killhelper.py in the checkout, run this script again."
echo "Undo: sudo rm -r $(dirname -- "$helper")"

if [ "$has_intel_gfx" -eq 1 ]; then
    if [ "$dry_run" -eq 0 ] && { [ -L "$igt" ] || [ ! -f "$igt" ] || [ "$(stat -c %u -- "$igt")" != 0 ]; }; then
        echo "$igt is not a regular root-owned file; refusing to set capabilities." >&2
        exit 1
    fi
    run setcap cap_perfmon=ep "$igt"
    echo "Note: upgrading intel-gpu-tools removes this capability; run this script again afterwards."
    echo "Undo: sudo setcap -r $igt"
fi

if [ "$has_rapl" -eq 1 ] && [ "$allow_rapl" -eq 1 ]; then
    echo "WARNING: RAPL energy counters are root-only because of CVE-2020-8694 (power side channel)."
    echo "This rule makes them readable by every local account and every Flatpak app."
    echo "Undo: sudo rm $rapl_rules and reboot."
    if [ "$dry_run" -eq 1 ]; then
        echo "WOULD: write $rapl_rules:"
        echo "$rapl_rule"
    else
        (umask 022 && printf '%s\n' "$rapl_rule" > "$rapl_rules")
    fi
    run udevadm control --reload
    run udevadm trigger --subsystem-match=powercap --action=add
elif [ "$allow_rapl" -eq 1 ]; then
    echo "No RAPL interface found; nothing to do for --allow-rapl."
fi
