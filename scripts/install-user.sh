#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Per-user install of launcher, icon and autostart (--hidden). Writes only under $HOME.
# Usage: install-user.sh [--uninstall]
set -euo pipefail

APP_ID="io.github.zappelmann_sketch.orbitop"
[ "$(id -u)" -ne 0 ] || { echo "refusing to run as root" >&2; exit 1; }
[[ "${HOME:-}" = /* ]] || { echo "HOME must be an absolute path" >&2; exit 1; }
case "$*" in "" | "--uninstall") ;; *) echo "usage: $0 [--uninstall]" >&2; exit 2 ;; esac

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# a newline/CR in the path would inject extra keys into the .desktop file
case "$repo" in *$'\n'* | *$'\r'*) echo "repo path contains a newline" >&2; exit 1 ;; esac
apps="$HOME/.local/share/applications"
icons="$HOME/.local/share/icons/hicolor/scalable/apps"
auto="$HOME/.config/autostart"
targets=("$apps/$APP_ID.desktop" "$icons/$APP_ID.svg" "$auto/$APP_ID.desktop")

refresh() {
    command -v update-desktop-database >/dev/null 2>&1 &&
        { update-desktop-database "$apps" >/dev/null 2>&1 || true; }
    return 0
}

if [ "${1:-}" = "--uninstall" ]; then
    rm -f -- "${targets[@]}"
    refresh
    exit 0
fi
[ -x "$repo/bin/orbitop" ] || { echo "missing or not executable: $repo/bin/orbitop" >&2; exit 1; }

# Desktop Entry spec: double-quote the path, backslash-escape " ` $ \, then double
# every backslash again (string-value escaping); % must be %%.
q="${repo//\\/\\\\\\\\}"
q="${q//\"/\\\\\"}"
q="${q//\`/\\\\\`}"
q="${q//\$/\\\\\$}"
q="${q//%/%%}"
exec_line="\"$q/bin/orbitop\""

tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
src="$repo/data/$APP_ID.desktop"
# Exec is written via awk's ENVIRON so no backslash is reinterpreted.
EXEC_VAL="$exec_line" awk '/^Exec=/{print "Exec=" ENVIRON["EXEC_VAL"]; next} {print}' "$src" > "$tmp/app.desktop"
EXEC_VAL="$exec_line --hidden" awk '/^Exec=/{print "Exec=" ENVIRON["EXEC_VAL"]; next} {print}
    /^Terminal=/{print "X-GNOME-Autostart-enabled=true"; print "NoDisplay=true"}' "$src" > "$tmp/auto.desktop"

mkdir -p "$apps" "$icons" "$auto"
install -m 644 "$tmp/app.desktop" "${targets[0]}"
install -m 644 "$repo/data/icons/$APP_ID.svg" "${targets[1]}"
install -m 644 "$tmp/auto.desktop" "${targets[2]}"
refresh
echo "installed: ${targets[*]}"
