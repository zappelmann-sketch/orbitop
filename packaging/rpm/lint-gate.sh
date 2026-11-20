#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Fails unless an rpmlint report is complete and has no E: line but the accepted ones: the mode 0711 of /etc/orbitop
# in both families, and one line per polkit action for openSUSE.
# Usage: bash lint-gate.sh fedora|opensuse REPORT   (packaging/rpm/build-inside.sh; tests/test_packaging_rpm.py)
# openSUSE's rpmlint reports every polkit action that the SUSE security team has not reviewed for a SUSE product and
# blocks filters for it (BlockedFilters in opensuse.toml). orbitop is no SUSE product, so exactly one line per action
# of its .policy is accepted, with that action's defaults (any:inactive:active); a weaker default fails
# (docs/release.md, "Lint notes"). The exit status of rpmlint depends on a badness threshold there, so every E: line
# counts. /etc/orbitop is 0711 on purpose, so that no other account can hold counterhelper's lock on it; rpmlint
# reports every directory mode but 0755 as an error. One awk over the file: no pipe that could end early.
set -euo pipefail

[ $# -eq 2 ] && [ -f "$2" ] || { echo "usage: $0 fedora|opensuse REPORT" >&2; exit 2; }
accepted="orbitop.noarch: E: non-standard-dir-perm /etc/orbitop 711"
if [ "$1" = opensuse ]; then
    untracked="orbitop.noarch: E: polkit-untracked-privilege (Badness: 10) io.github.zappelmann-sketch.orbitop"
    accepted+=$'\n'"$untracked.terminate (auth_admin:auth_admin:auth_admin)"
    for action in counters-release counters-lock; do
        accepted+=$'\n'"$untracked.$action (no:no:auth_admin)"
    done
fi
ACCEPTED=$accepted awk '
    BEGIN { n = split(ENVIRON["ACCEPTED"], lines, "\n"); for (i = 1; i <= n; i++) ok[lines[i]] = 1 }
    / packages and .* specfiles checked;/ { finished = 1 }
    /: E: / && !($0 in ok) { print "rpmlint error: " $0 > "/dev/stderr"; bad = 1 }
    END {
        if (!finished) print "rpmlint did not finish" > "/dev/stderr"
        exit bad || !finished
    }' "$2"
