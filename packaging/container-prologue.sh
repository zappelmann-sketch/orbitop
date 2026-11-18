# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Common start of packaging/{debian,rpm,arch}/build-inside.sh and packaging/site/*-inside.sh, which source it right
# after set -euo pipefail (bash).
# It keeps the key from stdin, refuses to run anywhere but as root in a disposable container, and hands the results
# in /out to the caller. Provides $key (the key the host checked, binary), die MESSAGE and archive DIR VERSION.
# shellcheck shell=bash

key=$(mktemp)
cat > "$key"  # first step: nothing else may read stdin

die() { echo "$*" >&2; exit 1; }
if [ ! -e /.dockerenv ] || [ "$(id -u)" -ne 0 ]; then
    die "$0 installs packages as root and runs only as root inside a disposable container."
fi
[[ ${OWNER:-} =~ ^[0-9]+:[0-9]+$ ]] || die "OWNER must be uid:gid"
trap 'chown -R "$OWNER" /out' EXIT  # the results belong to the caller, also after a failure

# The archive at /src as DIR/orbitop-VERSION.tar, top directory orbitop-VERSION (RPM Source0, Arch source).
archive() { tar -C / -cf "$1/orbitop-$2.tar" --transform "s,^src,orbitop-$2," src; }
