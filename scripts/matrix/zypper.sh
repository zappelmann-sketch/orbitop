# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# zypper (openSUSE Tumbleweed) for scripts/matrix/inside.sh, which sources it after lib.sh and rpm.sh.
# shellcheck shell=bash disable=SC2034,SC2154  # NOISE and TAMPERED are read elsewhere, PAGES and STATE come from lib.sh

FAMILY=opensuse
NOISE='[Ww]arning|[Ee]rror|[Ff]ailed'
TAMPERED='Signature verification failed for repomd.xml'
REPO=/etc/zypp/repos.d/orbitop.repo
ZYPPER=(zypper --non-interactive)

refresh() { "${ZYPPER[@]}" refresh; }

# Without rpm --import first, zypper refuses the signed local package: "public key is not available". rpm -V before
# point: the .repo that point keeps is the one of the package. findutils first, as in the README: the image has no
# xargs, which the full uninstall needs.
keyring() {
    "${ZYPPER[@]}" install findutils && rpm_key "$1" && release_package "$1" &&
        (cd "$STATE" && "${ZYPPER[@]}" install ./orbitop-release-opensuse.rpm) && rpm -V orbitop-release &&
        point "$REPO" "file://$1/"
}

# zypper checks the metadata and each package of the source: GPG Check (rp).
install_pkg() {
    "${ZYPPER[@]}" install orbitop && zypper lr orbitop | tee "$STATE/repo" &&
        grep -qE '^GPG Check +: \(rp\) Yes$' "$STATE/repo"
}

tools() { "${ZYPPER[@]}" install python3-pytest ShellCheck desktop-file-utils AppStream; }

update_from() { point "$REPO" "file://$1/" && "${ZYPPER[@]}" dup; }

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
