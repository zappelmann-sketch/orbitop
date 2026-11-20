# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# zypper (openSUSE Tumbleweed) for scripts/matrix/inside.sh, which sources it after lib.sh and rpm.sh.
# shellcheck shell=bash disable=SC2034,SC2154  # NOISE and TAMPERED are read elsewhere, PAGES and STATE come from lib.sh

FAMILY=opensuse
NOISE='[Ww]arning|[Ee]rror|[Ff]ailed'
TAMPERED='Signature verification failed for repomd.xml'
REPO=/etc/zypp/repos.d/orbitop.repo
ZYPPER=(zypper --non-interactive)

refresh() { net "${ZYPPER[@]}" refresh; }

# Without rpm --import first, zypper refuses the signed local package: "public key is not available". rpm -V before
# point: the .repo that point keeps is the one of the package. findutils first, as in the README: the image has no
# xargs, which the full uninstall needs.
keyring() {
    net "${ZYPPER[@]}" install findutils && rpm_key "$1" && release_package "$1" &&
        (cd "$STATE" && net "${ZYPPER[@]}" install ./orbitop-release-opensuse.rpm) && rpm -V orbitop-release &&
        point "$REPO" "file://$1/"
}

# zypper checks the metadata and each package of the source: GPG Check (rp).
install_pkg() {
    net "${ZYPPER[@]}" install orbitop && zypper lr orbitop | tee "$STATE/repo" &&
        grep -qE '^GPG Check +: \(rp\) Yes$' "$STATE/repo"
}

tools() { net "${ZYPPER[@]}" install python3-pytest ShellCheck desktop-file-utils AppStream; }

update_from() { point "$REPO" "file://$1/" && net "${ZYPPER[@]}" dup; }

# --force: without it, zypper only compares repomd.xml and reports "up to date".
remove() {
    files_of > "$STATE/files" && "${ZYPPER[@]}" remove orbitop && quiet "${ZYPPER[@]}" refresh --force orbitop
}

# The full uninstall: the .repo back to the Pages address (point refuses if zypper changed it; rpm -V without
# mtime), zypper remove, the key out of the rpm database; zypper keeps no cache of the source.
purge() {
    point "$REPO" "$PAGES" && rpm -V --nomtime orbitop-release && "${ZYPPER[@]}" remove orbitop-release && drop_key &&
        leftovers "$STATE/files" && quiet "${ZYPPER[@]}" refresh && absent '/var/cache/zypp/*/orbitop'
}

refresh_index() { "${ZYPPER[@]}" refresh orbitop; }

# The counter release (scripts/matrix/counters.sh, rpm.sh). The owner of intel_gpu_top as in the security document
# 0.3.0, B2.4 (igt-gpu-tools is only a Provides there), and the package of /usr/bin/pkexec, which orbitop requires as
# a file. zypper prints no line for a trigger whose scriptlet prints nothing (probe on 2026-11-20), so TRIGGERED is
# empty.
OWNER=intel-gpu-tools
PKEXEC_PROVIDER=pkexec
TRIGGERED=''
JOINT=(rpm_pair zypper_pair)  # B2.4, 6: rpm -U of both files, zypper up of both
get_pkg() { "${ZYPPER[@]}" install "$@"; }
reget_pkg() { "${ZYPPER[@]}" install --force "$@"; }
remove_pkg() { "${ZYPPER[@]}" remove "$1"; }  # zypper removes no dependencies along by default

# install_new FILE: zypper refuses an unsigned file and one whose key is not in the rpm database (/rev2 and /v020 are
# unsigned, the key of SITE left the database in the step purge).
install_new() { net "${ZYPPER[@]}" --no-gpg-checks install --allow-unsigned-rpm "$1"; }

# zypper_pair ORBITOP OWNER: zypper up takes no files, so both go into a repository of their own (plaindir, without
# signatures, like the files themselves), and zypper up updates both from it in one transaction; the repository goes
# afterwards.
zypper_pair() {
    local dir=$STATE/joint rc=0
    rm -rf -- "$dir" && mkdir -p "$dir" && cp -- "$1" "$2" "$dir/" &&
        "${ZYPPER[@]}" addrepo --no-gpgcheck --type plaindir "$dir" joint || return 1
    "${ZYPPER[@]}" update --repo joint orbitop "$OWNER" || rc=$?
    "${ZYPPER[@]}" removerepo joint && return "$rc"
}
