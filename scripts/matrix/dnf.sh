# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# dnf (Fedora) for scripts/matrix/inside.sh, which sources it after rpm.sh and provides point, quiet, flip, leftovers
# and PAGES.
# shellcheck shell=bash disable=SC2034,SC2154  # inside.sh reads NOISE and TAMPERED, and it sets PAGES

FAMILY=fedora
NOISE='[Ww]arning|[Ee]rror|[Ff]ailed|[Ss]kipping'
TAMPERED='Bad PGP signature'
REPO=/etc/yum.repos.d/orbitop.repo

refresh() { dnf makecache; }

keyring() {
    rpm_key "$1" && release_package "$1" && (cd /tmp && dnf install ./orbitop-release-fedora.rpm -y) &&
        point "$REPO" "file://$1/"
}

# On the first use of the source, dnf asks once whether to import the key for its metadata (-y answers).
install() { dnf install orbitop -y; }

tools() { dnf install -y python3-pytest ShellCheck desktop-file-utils appstream util-linux; }  # runuser

update_from() { point "$REPO" "file://$1/" && dnf upgrade -y; }

remove() { files_of > /tmp/files && dnf remove orbitop -y && quiet dnf makecache; }

# The full uninstall: the .repo as packaged (rpm -V without mtime: dnf did not change it), dnf remove, the key out
# of the rpm database, and the cache of the source, where dnf5 keeps its copy of the key even after dnf clean all.
purge() {
    point "$REPO" "$PAGES" && rpm -V --nomtime orbitop-release && dnf remove orbitop-release -y && drop_key &&
        ls -d /var/cache/libdnf5/orbitop-*/pubring/* && rm -rf /var/cache/libdnf5/orbitop-* && leftovers /tmp/files &&
        quiet dnf makecache
}

# dnf5 skips a source that fails and exits 0 by default (docs/release.md); here the failure must show. -y imports
# the key for the metadata, so that the signature is checked at all.
refresh_index() { dnf makecache -y --setopt=skip_if_unavailable=False; }
