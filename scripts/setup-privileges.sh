#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Installs the runtime packages and the root-owned kill helper, and grants the few privileges orbitop optionally uses.
# Usage: sudo bash setup-privileges.sh [--dry-run] [--allow-rapl] [--allow-perfmon]
# With --dry-run, detection reads from ${ORBITOP_SYSROOT:-/} and ORBITOP_PKG_MANAGER overrides the package manager.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 022  # directories created on the way to the helper must stay readable for orbitop's trust check

usage() { echo "usage: $0 [--dry-run] [--allow-rapl] [--allow-perfmon]" >&2; exit 2; }

dry_run=0
allow_rapl=0
allow_perfmon=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=1 ;;
        --allow-rapl) allow_rapl=1 ;;
        --allow-perfmon) allow_perfmon=1 ;;
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

# The distribution decides, as package_manager in orbitop/app.py (tests/test_setup_script.py keeps them equal):
# ID, then each word of ID_LIKE from os-release(5), read line by line and never sourced.
os_release=$root/etc/os-release
[ -s "$os_release" ] || os_release=$root/usr/lib/os-release
id="" id_like=""
if [ -f "$os_release" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ID=*) id=${line#ID=} ;;
            ID_LIKE=*) id_like=${line#ID_LIKE=} ;;
        esac
    done < "$os_release"
fi
read -ra words <<< "$id $id_like"  # split without pathname expansion
manager=none
for word in "${words[@]}"; do
    case "${word//[\"\']/}" in
        debian|ubuntu) manager=apt-get ;;
        fedora|rhel|centos) manager=dnf ;;
        arch) manager=pacman ;;
        suse|opensuse|opensuse-*) manager=zypper ;;
        *) continue ;;
    esac
    break
done
# Another distribution's manager may be installed too (apt on Arch); without the named one, the first one found.
if [ "$manager" != none ] && ! command -v "$manager" >/dev/null; then
    echo "os-release names $manager, but it is not installed; looking for apt-get, dnf, pacman or zypper instead."
    manager=none
fi
if [ "$manager" = none ]; then
    for m in apt-get dnf pacman zypper; do
        if command -v "$m" >/dev/null; then
            manager=$m
            break
        fi
    done
fi
# The override is matched against the fixed list below and never reaches a command line.
[ "$dry_run" -eq 1 ] && manager=${ORBITOP_PKG_MANAGER:-$manager}

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

# Same lists as PACKAGES in orbitop/app.py; tests/test_setup_script.py keeps them equal.
case "$manager" in
    apt-get)
        install=(apt-get install -y)
        packages=(python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0)
        intel_tools="intel-gpu-tools" ;;
    dnf)
        install=(dnf install -y)
        packages=(python3-gobject gtk4 webkitgtk6.0)
        intel_tools="igt-gpu-tools" ;;
    pacman)
        install=(pacman -S --needed --noconfirm)
        packages=(python-gobject gtk4 webkitgtk-6.0)
        intel_tools="intel-gpu-tools" ;;
    zypper)
        install=(zypper --non-interactive install)
        packages=(python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-WebKit-6_0 python3-gobject-Gdk)
        intel_tools="igt-gpu-tools" ;;
    *)
        manager=none ;;
esac
if [ "$manager" = none ]; then
    echo "No supported package manager found (apt-get, dnf, pacman, zypper). Install PyGObject, GTK 4 and WebKitGTK 6.0 yourself (Debian names: python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0), see README.md."
else
    [ "$has_intel_gfx" -eq 1 ] && packages+=("$intel_tools")
    run "${install[@]}" "${packages[@]}"
fi

run install -d -o root -g root -m 0755 "$(dirname -- "$helper")"
run install -o root -g root -m 0755 "$helper_src" "$helper"
echo "Note: after updating orbitop/killhelper.py in the checkout, run this script again."
echo "Undo: sudo rm -r $(dirname -- "$helper")"

if [ "$has_intel_gfx" -eq 1 ] && [ "$allow_perfmon" -eq 1 ]; then
    if [ "$dry_run" -eq 0 ] && { [ -L "$igt" ] || [ ! -f "$igt" ] || [ "$(stat -c %u -- "$igt")" != 0 ]; }; then
        echo "$igt is not a regular root-owned file; refusing to set capabilities." >&2
        exit 1
    fi
    echo "WARNING: cap_perfmon lets every local account run $igt with GPU and package power counters (RAPL, CVE-2020-8694)."
    run setcap cap_perfmon=ep "$igt"
    echo "Note: upgrading intel-gpu-tools removes this capability; run this script with --allow-perfmon again afterwards."
    echo "Undo: sudo setcap -r $igt"
elif [ "$allow_perfmon" -eq 1 ]; then
    echo "No Intel GPU found; nothing to do for --allow-perfmon."
fi

if [ "$has_rapl" -eq 1 ] && [ "$allow_rapl" -eq 1 ]; then
    echo "WARNING: RAPL energy counters are root-only because of CVE-2020-8694 (power side channel)."
    echo "This rule makes them readable by every local account and every Flatpak app."
    echo "Undo: sudo rm $rapl_rules and reboot."
    if [ "$dry_run" -eq 1 ]; then
        echo "WOULD: write $rapl_rules:"
        echo "$rapl_rule"
    else
        printf '%s\n' "$rapl_rule" > "$rapl_rules"
    fi
    run udevadm control --reload
    run udevadm trigger --subsystem-match=powercap --action=add
elif [ "$allow_rapl" -eq 1 ]; then
    echo "No RAPL interface found; nothing to do for --allow-rapl."
fi
