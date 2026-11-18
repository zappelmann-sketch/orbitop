#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Installs the file tree of the orbitop package below DESTDIR (locations: docs/release.md, "Sources").
# Usage: bash install-tree.sh DESTDIR   shared by every package format; each format adds license and copyright itself
set -euo pipefail
umask 022  # modes in the tree never depend on the caller

usage() { echo "usage: $0 DESTDIR (not /)" >&2; exit 2; }
[ $# -eq 1 ] && [ -n "$1" ] || usage
mkdir -p -- "$1"
dest=$(cd -- "$1" && pwd -P)
[ ! "$dest" -ef / ] || usage  # never into the running system, past the package manager
src=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
app=io.github.zappelmann_sketch.orbitop
share=$dest/usr/share

# The program: starter and Python package in a private directory (K2), without byte code.
install -D -m 0755 -- "$src/bin/orbitop" "$share/orbitop/bin/orbitop"
while IFS= read -r -d '' f; do
    mode=0644
    [ -x "$src/$f" ] && mode=0755
    install -D -m "$mode" -- "$src/$f" "$share/orbitop/$f"
done < <(cd -- "$src" && find orbitop -name __pycache__ -prune -o -type f -print0)
install -d -m 0755 -- "$dest/usr/bin"
ln -sfn ../share/orbitop/bin/orbitop "$dest/usr/bin/orbitop"

# The root helper, started directly by pkexec (K1), and its polkit action.
install -D -m 0755 -- "$src/orbitop/killhelper.py" "$dest/usr/lib/orbitop/killhelper"
install -D -m 0644 -- "$src/data/io.github.zappelmann-sketch.orbitop.policy" \
    "$share/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy"

# Desktop integration and the inactive autostart template (K5).
install -D -m 0644 -- "$src/data/$app.desktop" "$share/applications/$app.desktop"
install -D -m 0644 -- "$src/data/icons/$app.svg" "$share/icons/hicolor/scalable/apps/$app.svg"
install -D -m 0644 -- "$src/data/$app.metainfo.xml" "$share/metainfo/$app.metainfo.xml"
install -D -m 0644 -- "$src/data/autostart.desktop" "$share/orbitop/autostart.desktop"
