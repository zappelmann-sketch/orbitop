#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Copies a fixed list of /proc and /sys files of the running machine into <target>.
# <target> must not exist or be empty: capture into a fresh directory, then swap it in.
# Never copies serials, MAC addresses (address), host or user names. Dropped on purpose:
#   - cpuinfo lines starting with "Serial"
#   - interfaces named enx*/wlx* and power supplies named hid-* (MAC in the name)
#   - mounts of type nfs, nfs4, cifs, smb3, smbfs or fuse.sshfs (host/user in the source),
#     /dev/loop* sources, and mount points under /home, /media, /run/media, /run/user,
#     /mnt, /snap and /run/snapd
set -euo pipefail

# Reads /proc/mounts on stdin, writes the lines that are safe to keep.
filter_mounts() {
    awk '$3 !~ /^(nfs|nfs4|cifs|smb3|smbfs|fuse\.sshfs)$/ && $1 !~ /^\/dev\/loop/ &&
        $2 !~ /^\/(home|media|run\/media|run\/user|mnt|snap|run\/snapd)(\/|$)/'
}
if [ "${1:-}" = --filter-mounts ]; then
    filter_mounts
    exit
fi

# Names that embed a MAC address.
private_name() {
    case $1 in enx*|wlx*|hid-*) return 0 ;; esac
    return 1
}

self=$(realpath -- "$0")
[ $# -eq 1 ] || { echo "usage: $0 <target-dir>" >&2; exit 2; }
target=$(realpath -m -- "$1")
if [ -e "$target" ] && [ -n "$(ls -A -- "$target")" ]; then
    echo "$target is not empty; capture into a fresh directory and swap it in." >&2
    exit 1
fi
mkdir -p -- "$target"
cd /
shopt -s nullglob

# Regular readable files only; vanished, unreadable or blocking files are skipped quietly.
copy_file() {
    local src=$1 dst
    [ -f "$src" ] && [ ! -L "$src" ] && [ -r "$src" ] || return 0
    dst=$target/$src
    mkdir -p -- "${dst%/*}"
    timeout 1 cat -- "$src" > "$dst" 2>/dev/null || rm -f -- "$dst"
}

# Copies every <dir-glob>/<file-glob> match, no recursion.
copy_glob() {
    local dir=$1 f d p
    shift
    for d in $dir; do
        ! private_name "${d##*/}" || continue
        for f in "$@"; do
            for p in "$d"/$f; do copy_file "$p"; done
        done
    done
}

# Writes a filtered copy of a file (stdin filter given as command).
filter_file() {
    local src=$1 dst=$target/$1
    shift
    [ -r "$src" ] || return 0
    mkdir -p -- "${dst%/*}"
    timeout 1 "$@" < "$src" > "$dst" 2>/dev/null || rm -f -- "$dst"
}

copy_file proc/stat
copy_file proc/meminfo
copy_file proc/diskstats
filter_file proc/cpuinfo grep -vi '^serial'
filter_file proc/net/dev grep -Ev '^ *(enx|wlx)'
filter_file proc/mounts bash "$self" --filter-mounts

copy_glob "sys/devices/system/cpu/cpu[0-9]*/cpufreq" scaling_cur_freq cpuinfo_max_freq
copy_glob "sys/class/hwmon/hwmon*" name 'temp*_input' 'temp*_label' 'temp*_crit' \
    'fan*_input' 'fan*_label' 'fan*_max' 'power*_input' 'power*_average' 'power*_label'
copy_glob "sys/class/thermal/thermal_zone*" type temp
copy_glob "sys/class/powercap/intel-rapl*" name energy_uj max_energy_range_uj
copy_glob "sys/class/power_supply/*" type status online capacity power_now current_now voltage_now
copy_glob "sys/class/drm/card[0-9]" gt_act_freq_mhz gt_max_freq_mhz
copy_glob "sys/class/drm/card[0-9]/device" vendor device product_name gpu_busy_percent \
    mem_info_vram_used mem_info_vram_total pp_dpm_sclk
copy_glob "sys/class/devfreq/*" cur_freq max_freq
copy_glob "sys/block/*" size stat
copy_glob "sys/block/*/device" model
copy_glob "sys/block/*/*" partition
copy_glob "sys/class/net/*" operstate type

# Driver symlinks stay symlinks, but only their relative target is recorded.
for l in sys/class/drm/card[0-9]/device/driver; do
    [ -L "$l" ] || continue
    mkdir -p -- "$target/${l%/*}"
    ln -sfn -- "../../../bus/pci/drivers/$(basename -- "$(readlink -- "$l")")" "$target/$l"
done

# "device" entries mark physical NICs and disks: record an empty directory (.keep, git drops empty dirs).
for d in sys/class/net/*/device sys/block/*/device; do
    [ -e "$d" ] || continue
    ! private_name "$(basename -- "${d%/device}")" || continue
    mkdir -p -- "$target/$d"
    : > "$target/$d/.keep"
done
exit 0
