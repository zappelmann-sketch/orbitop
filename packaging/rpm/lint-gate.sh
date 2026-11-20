#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Fails unless an rpmlint report is complete and has no E: line but the three accepted for openSUSE.
# Usage: bash lint-gate.sh fedora|opensuse REPORT   (packaging/rpm/build-inside.sh; tests/test_packaging_rpm.py)
# openSUSE's rpmlint reports every polkit action that the SUSE security team has not reviewed for a SUSE product and
# blocks filters for it (BlockedFilters in opensuse.toml). orbitop is no SUSE product, so exactly one line per action
# of its .policy is accepted, with that action's defaults (any:inactive:active); a weaker default fails
# (docs/release.md, "Lint notes"). The exit status of rpmlint depends on a badness threshold there, so every E: line
# counts. One awk over the file: no pipe that could end early.
set -euo pipefail

[ $# -eq 2 ] && [ -f "$2" ] || { echo "usage: $0 fedora|opensuse REPORT" >&2; exit 2; }
accepted=-  # a line rpmlint never prints
if [ "$1" = opensuse ]; then
    untracked="orbitop.noarch: E: polkit-untracked-privilege (Badness: 10) io.github.zappelmann-sketch.orbitop"
    accepted="$untracked.terminate (auth_admin:auth_admin:auth_admin)"
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
