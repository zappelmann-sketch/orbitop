# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# The cases of the counter release for the step counters of scripts/matrix/inside.sh (docs/distro-check.md), the same
# for every format: the container matrix of the security document 0.3.0, B2.1, B2.2, B2.3, B2.4, B2.8 and B2.9. Sourced
# after lib.sh and the file of the package manager, which provides COUNTER_CASES (its cases, in the order they run:
# each starts from the state the one before left), OWNER (the package of intel_gpu_top), JOINT (the ways to update
# orbitop and OWNER in one transaction, each called as WAY ORBITOP-FILE OWNER-FILE), TRIGGERED (a pattern for the line
# its log prints when orbitop's trigger runs, or empty if it prints none), REMOVE_TRIGGERED (the same when OWNER goes,
# empty where no trigger runs then), REVOKE_FAILED (a pattern for what a removal prints when the helper cannot run;
# never empty), install_owner, reinstall_owner and remove_owner (OWNER from the mirrors), fake_owner N (OWNER of a
# higher version, built here; prints the file), install_file FILE (orbitop from a file, also of the same or a lower
# version), orbitop_file rev1|rev2|v020, pkg_files (orbitop's file list), remove_pkg NAME, purge_pkg NAME, installed
# and owned PATH. A format may add cases of its own (case_<name>).
# As root, without polkit. Docker masks the RAPL zones (/sys/devices/virtual/powercap), so the helper finds none and
# exits 0 for that part (ruling of Task 2): the cases check the capability, the marker and the exit codes.
# shellcheck shell=bash disable=SC2154  # STATE comes from lib.sh, the rest from the file of the package manager

HELPER=/usr/lib/orbitop/counterhelper
MARKER=/etc/orbitop/counters-released  # counterhelper.MARKER
TOOL=/usr/bin/intel_gpu_top
CAP=0100000200000000000000004000000000000000  # cap_perfmon=ep, the 20 bytes setcap writes (B2.1)
# What the package scripts print if the helper failed: the lines of postinst and prerm (deb), and the helper's own
# message or the shell's if it cannot start, as RPM and Arch scripts print nothing of their own; and any Python
# traceback in the output (the helper's if it crashed; one of another package fails the case as well, fail closed).
NOT_APPLIED='orbitop: counter release not (applied|revoked)|counterhelper: |Traceback \(most recent call last\):'
MANUAL_RULE=/etc/udev/rules.d/70-orbitop-rapl.rules  # the rule of the README of 0.2.0 (B2.9)
MANUAL_LINE='ACTION=="add", SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", RUN+="/usr/bin/chmod 0444 /sys%p/energy_uj"'

# cap: the security.capability of TOOL in hex, "none" without one; fails without TOOL.
cap() {
    python3 -I -c 'import errno, os, sys
try:
    print(os.getxattr(sys.argv[1], "security.capability", follow_symlinks=False).hex())
except OSError as e:
    if e.errno != errno.ENODATA:
        raise
    print("none")' "$TOOL"
}
has_cap() { local c; c=$(cap) && echo "CAP $c" && [ "$c" = "$CAP" ]; }
no_cap() { local c; c=$(cap) && echo "CAP $c" && [ "$c" = none ]; }

# set_cap HEX|none: the capability on TOOL set or taken by hand, as setcap and setcap -r would.
set_cap() {
    python3 -I -c 'import errno, os, sys
try:
    if sys.argv[2] == "none":
        os.removexattr(sys.argv[1], "security.capability")
    else:
        os.setxattr(sys.argv[1], "security.capability", bytes.fromhex(sys.argv[2]))
except OSError as e:
    if e.errno != errno.ENODATA:
        raise' "$TOOL" "$1"
}

# marker_on: the marker is an empty regular file, root 0644; marker_off: there is none.
marker_on() { [ -f "$MARKER" ] && [ ! -L "$MARKER" ] && [ "$(stat -c '%u %g %a %s' -- "$MARKER")" = "0 0 644 0" ]; }
marker_off() { [ ! -e "$MARKER" ] && [ ! -L "$MARKER" ]; }

# closed: /etc/orbitop, the directory of the marker, is root 0711, and another account (nobody) cannot open it, so none
# can hold the helper's lock on it (B2.2).
closed() {
    local dir=${MARKER%/*}
    [ -d "$dir" ] && [ ! -L "$dir" ] && [ "$(stat -c '%u %g %a' -- "$dir")" = "0 0 711" ] &&
        runuser -u nobody -- python3 -I -c 'import os, sys
try:
    os.open(sys.argv[1], os.O_RDONLY | os.O_DIRECTORY)
except PermissionError:
    raise SystemExit(0)
raise SystemExit("nobody can open " + sys.argv[1])' "$dir"
}

# helper WORD CODE: counterhelper WORD exits with CODE.
helper() {
    local rc=0
    "$HELPER" "$1" || rc=$?
    echo "counterhelper $1: exit $rc"
    [ "$rc" -eq "$2" ]
}

# scripted COMMAND…: COMMAND succeeds and no package script reported a failed helper; its log stays in STATE/op.out.
scripted() {
    local found=0
    logged "$STATE/op.out" "$@" || return 1
    matching "$NOT_APPLIED" "$STATE/op.out" || found=$?
    [ "$found" -eq 1 ]  # 1: no such line; 2: the log cannot be read
}

# triggered [PATTERN]: the last scripted command ran orbitop's trigger (PATTERN, default TRIGGERED), if the format
# logs that.
triggered() { local pattern=${1-$TRIGGERED}; [ -z "$pattern" ] || matching "$pattern" "$STATE/op.out"; }

inode() { stat -c %i -- "$TOOL"; }
# stamp: inode and change time of TOOL. A reinstall changes it also where rpm keeps an unchanged file and only sets
# its metadata anew, which takes the capability as well (%_minimize_writes on openSUSE, probe on 2026-11-20).
stamp() { stat -c '%i %z' -- "$TOOL"; }

# For the files of the formats. only_file FILE…: prints FILE if it is the one regular file given (a glob that matched
# exactly one); elf FILE: FILE starts with the magic bytes of an ELF program.
only_file() { [ $# -eq 1 ] && [ -f "$1" ] && echo "$1"; }
elf() { [ "$(head -c 4 -- "$1" | od -An -c | tr -d ' ')" = 177ELF ]; }

# B2.4, 5: with a capability set by hand, the first installation of orbitop creates no marker and leaves it.
case_orbitop_install_manual_cap() {
    install_owner && set_cap "$CAP" && scripted install_file "$(orbitop_file rev1)" && marker_off && has_cap &&
        set_cap none
}

# B2.2 and B2.3: the package brings /etc/orbitop (root 0711, empty) and its udev rule only below /usr/lib/udev/rules.d.
case_file_list() {
    local list
    list=$(pkg_files | sed 's|/$||') && printf '%s\n' "$list" | grep -E '^/etc|rules' &&
        grep -qx /etc/orbitop <<< "$list" && ! grep -qE '^/etc/(orbitop/|udev)' <<< "$list" &&
        [ "$(grep -E '\.rules$' <<< "$list")" = /usr/lib/udev/rules.d/70-orbitop-counters.rules ] &&
        closed && [ -z "$(ls -A -- "${MARKER%/*}")" ]
}

# B2.4, 1 and B2.2: without a marker, reinstalling the Intel tools runs the trigger and releases nothing. The
# capability set by hand before shows that a reinstall takes it in this format, which reinstall_owner_on builds on.
case_reinstall_owner_off() {
    helper off 0 && set_cap "$CAP" && scripted reinstall_owner && triggered && no_cap && marker_off
}

# B2.1 and B2.2: on sets cap_perfmon=ep and the marker; no other account can open /etc/orbitop; off takes both back.
case_on_off() { helper on 0 && has_cap && marker_on && closed && helper off 0 && no_cap && marker_off; }

# B2.4, 2: after on, the file of a reinstalled Intel package (new, or with its metadata set anew) has the capability
# again.
case_reinstall_owner_on() {
    local was
    helper on 0 && was=$(stamp) && scripted reinstall_owner && triggered && [ "$(stamp)" != "$was" ] && has_cap &&
        marker_on
}

# B2.4, 3: removing the Intel tools runs the trigger where the format has one then (deb), and the helper ends with 0,
# as it does on its own.
case_owner_remove() {
    helper on 0 && scripted remove_owner && triggered "$REMOVE_TRIGGERED" && [ ! -e "$TOOL" ] && helper sync 0 &&
        marker_on
}

# B2.4, 4: after on, the first installation of the Intel tools brings the capability.
case_owner_first_install_on() { [ ! -e "$TOOL" ] && helper on 0 && scripted install_owner && triggered && has_cap; }

# B2.8, 4: with on, the update to the next revision of orbitop keeps the marker and the capability.
case_rev2_upgrade_on() {
    helper on 0 && has_cap && scripted install_file "$(orbitop_file rev2)" && [[ $(installed) == *-2 ]] &&
        marker_on && has_cap
}

# B2.8, 1 and 2: with on, removing orbitop takes the marker and the capability back; installing orbitop and the Intel
# tools again then releases nothing. /etc/orbitop goes on purge at the latest (case purge).
case_remove_on() {
    helper on 0 && has_cap && scripted remove_pkg orbitop && marker_off && no_cap &&
        { ls -ld -- "${MARKER%/*}" 2> /dev/null || echo "no /etc/orbitop after the removal"; } &&
        scripted install_file "$(orbitop_file rev1)" && marker_off && no_cap && scripted reinstall_owner && no_cap &&
        marker_off
}

# B2.8, 6 (M-3): with on and a helper that cannot run, removing orbitop still succeeds, its log shows that the helper
# failed (REVOKE_FAILED), and the marker goes. The capability stays, as expected (README.Debian names setcap -r);
# purge then leaves no /etc/orbitop.
case_remove_broken_helper() {
    helper on 0 && has_cap && chmod -x "$HELPER" && logged "$STATE/op.out" remove_pkg orbitop &&
        matching "$REVOKE_FAILED" "$STATE/op.out" && marker_off && has_cap &&
        echo "M-3: the capability stays after a removal with a broken helper, as expected" && set_cap none &&
        scripted purge_pkg orbitop && [ ! -e "${MARKER%/*}" ]
}

# B2.8, 7: with on, purging orbitop leaves nothing below /etc/orbitop, and no /etc/orbitop.
case_purge() {
    scripted install_file "$(orbitop_file rev1)" && helper on 0 && has_cap && scripted purge_pkg orbitop &&
        marker_off && no_cap && [ ! -e "${MARKER%/*}" ]
}

# B2.9: the udev rule of the README of 0.2.0 stays as it is through install, on, off, remove and purge.
case_manual_rule_untouched() {
    local before
    mkdir -p "${MANUAL_RULE%/*}" && printf '%s\n' "$MANUAL_LINE" > "$MANUAL_RULE" &&
        before=$(sha256sum < "$MANUAL_RULE") && scripted install_file "$(orbitop_file rev1)" && helper on 0 &&
        helper off 0 && scripted remove_pkg orbitop && scripted purge_pkg orbitop &&
        [ "$(sha256sum < "$MANUAL_RULE")" = "$before" ] && rm -- "$MANUAL_RULE"
}

# from_020: 0.2.0, then the update to revision 1 of /src, which must change the installed version from 0.2.0-1 to
# <version of /src>-1: while /src was 0.2.0, the case only reinstalled the same version (review of Tasks 3 and 4).
from_020() {
    local before after
    scripted install_file "$(orbitop_file v020)" && before=$(installed) && [ ! -e "$HELPER" ] &&
        scripted install_file "$(orbitop_file rev1)" && after=$(installed) || return 1
    echo "FROM_020 $before to $after"
    [ "$before" = 0.2.0-1 ] && [ "$after" = "$(src_version /src)-1" ] && [ "$after" != "$before" ] && [ -x "$HELPER" ]
}

# B2.8, 3 and review focus 1: the update from 0.2.0 releases nothing, and a capability set by hand stays. pkexec is
# checked only after the update: 0.2.0 has no actions.real_pkexec (plan 1, audit of Task 1, M2).
case_upgrade_from_020() {
    from_020 && marker_off && no_cap && real_pkexec /usr/share/orbitop && scripted purge_pkg orbitop &&
        set_cap "$CAP" && from_020 && marker_off && has_cap && set_cap none
}

# B2.4, 6, B2.8, 5 (I-1): with on, orbitop (from revision 1) and the Intel tools updated in one transaction, in each
# way of JOINT; afterwards the new intel_gpu_top has the capability.
case_joint_upgrade() {
    local way n=0 owner ino
    helper on 0 || return 1
    for way in "${JOINT[@]}"; do
        n=$((n + 1))
        echo "--- joint_upgrade: $way"
        owner=$(fake_owner "$n") && scripted install_file "$(orbitop_file rev1)" && has_cap && ino=$(inode) &&
            scripted "$way" "$(orbitop_file rev2)" "$owner" && [[ $(installed) == *-2 ]] &&
            [ "$(inode)" != "$ino" ] && has_cap || return 1
    done
}

# counters: every case of COUNTER_CASES in turn, a line "COUNTERS <case> ok|FAIL" each; fails if one failed. A format
# without cases says so in a line "COUNTERS none" and fails: every format has them.
counters() {
    local name failed=0
    [ ${#COUNTER_CASES[@]} -gt 0 ] || { echo "COUNTERS none" && return 1; }
    for name in "${COUNTER_CASES[@]}"; do
        echo "--- $name"
        if "case_$name"; then
            echo "COUNTERS $name ok"
        else
            echo "COUNTERS $name FAIL"
            failed=1
        fi
    done
    [ "$failed" -eq 0 ]
}
