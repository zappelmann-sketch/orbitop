# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# zypper (openSUSE Tumbleweed) for scripts/matrix/inside.sh, which sources it after rpm.sh and provides point,
# quiet, flip, leftovers and PAGES.
# shellcheck shell=bash disable=SC2034,SC2154  # inside.sh reads NOISE and TAMPERED, and it sets PAGES

FAMILY=opensuse
NOISE='[Ww]arning|[Ee]rror|[Ff]ailed'
TAMPERED='Signature verification failed for repomd.xml'
REPO=/etc/zypp/repos.d/orbitop.repo
ZYPPER=(zypper --non-interactive)

refresh() { "${ZYPPER[@]}" refresh; }

# Without rpm --import first, zypper refuses the signed local package: "public key is not available".
keyring() {
    rpm_key "$1" && release_package "$1" && (cd /tmp && "${ZYPPER[@]}" install ./orbitop-release-opensuse.rpm) &&
        point "$REPO" "file://$1/"
}

# zypper checks the metadata and each package of the source: GPG Check (rp).
install() {
    "${ZYPPER[@]}" install orbitop && zypper lr orbitop | tee /tmp/repo &&
        grep -qE '^GPG Check +: \(rp\) Yes$' /tmp/repo
}

tools() { "${ZYPPER[@]}" install python3-pytest ShellCheck desktop-file-utils AppStream; }

update_from() { point "$REPO" "file://$1/" && "${ZYPPER[@]}" dup; }

remove() { files_of > /tmp/files && "${ZYPPER[@]}" remove orbitop && quiet "${ZYPPER[@]}" refresh; }

# The full uninstall: the .repo as packaged (rpm -V without mtime: zypper did not change it), zypper remove, the key
# out of the rpm database; zypper keeps no cache of the source.
purge() {
    point "$REPO" "$PAGES" && rpm -V --nomtime orbitop-release && "${ZYPPER[@]}" remove orbitop-release && drop_key &&
        leftovers /tmp/files && quiet "${ZYPPER[@]}" refresh && ! ls -d /var/cache/zypp/*/orbitop
}

refresh_index() { "${ZYPPER[@]}" refresh orbitop; }
