#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Copies a fixed list of /proc and /sys files of the running machine into <target>.
# Never copies serials, MAC addresses (address) or anything outside the list.
set -euo pipefail

[ $# -eq 1 ] || { echo "usage: $0 <target-dir>" >&2; exit 2; }
target=$(realpath -m -- "$1")
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

# Expands "<dir-glob>" x "<file> ..." without recursion.
copy_glob() {
    local dir=$1 f d
    shift
    for d in $dir; do
        for f in "$@"; do copy_file "$d/$f"; done
    done
}

copy_file proc/stat
copy_file proc/meminfo
copy_file proc/net/dev
copy_file proc/diskstats
copy_file proc/cpuinfo
# Mounts under home/media dirs can reveal user names; snap loop mounts reveal installed software.
if [ -r proc/mounts ]; then
    mkdir -p -- "$target/proc"
    timeout 1 grep -Ev '^/dev/loop| /(home|media|run/media|run/user|mnt|snap|run/snapd)(/| )' proc/mounts > "$target/proc/mounts" || true
fi

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
copy_glob "sys/class/net/*" operstate type

# hwmon behind drm devices (amdgpu keeps its hwmon there).
copy_glob "sys/class/drm/card[0-9]/device/hwmon/hwmon*" name 'temp*_input' 'power*_average' 'power*_input'

# Driver symlinks stay symlinks, but only their relative target is recorded.
for l in sys/class/drm/card[0-9]/device/driver; do
    [ -L "$l" ] || continue
    mkdir -p -- "$target/${l%/*}"
    ln -sfn -- "../../../bus/pci/drivers/$(basename -- "$(readlink -- "$l")")" "$target/$l"
done

# A NIC counts as physical when its "device" entry exists: record an empty directory.
for n in sys/class/net/*; do
    [ -e "$n/device" ] && mkdir -p -- "$target/$n/device"
done
exit 0
