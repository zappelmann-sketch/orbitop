# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# dnf (Fedora) for scripts/matrix/inside.sh, which sources it after lib.sh and rpm.sh.
# shellcheck shell=bash disable=SC2034,SC2154  # NOISE and TAMPERED are read elsewhere, PAGES and STATE come from lib.sh

FAMILY=fedora
NOISE='[Ww]arning|[Ee]rror|[Ff]ailed|[Ss]kipping'
TAMPERED='Bad PGP signature'
REPO=/etc/yum.repos.d/orbitop.repo

refresh() { net dnf makecache; }

# rpm -V before point: the .repo that point keeps is the one of the package.
keyring() {
    rpm_key "$1" && release_package "$1" && (cd "$STATE" && net dnf install ./orbitop-release-fedora.rpm -y) &&
        rpm -V -- orbitop-release && point "$REPO" "file://$1/"
}

# On the first use of the source, dnf asks once whether to import the key for its metadata (-y answers).
install_pkg() { net dnf install orbitop -y; }

tools() { net dnf install -y -- python3-pytest ShellCheck desktop-file-utils appstream util-linux; }  # runuser

update_from() { point "$REPO" "file://$1/" && net dnf upgrade -y; }

# --refresh: dnf makecache alone keeps metadata that has not expired and fetches nothing.
remove() { files_of > "$STATE/files" && dnf remove orbitop -y && quiet dnf makecache --refresh; }

# The full uninstall: the .repo back to the Pages address (point refuses if dnf changed it; rpm -V without mtime),
# dnf remove, the key out of the rpm database, and the cache of the source, where dnf5 keeps its copy of the key even
# after dnf clean all.
purge() {
    point "$REPO" "$PAGES" && rpm -V --nomtime -- orbitop-release && dnf remove orbitop-release -y && drop_key &&
        ls -d /var/cache/libdnf5/orbitop-*/pubring/* && rm -rf /var/cache/libdnf5/orbitop-* &&
        leftovers "$STATE/files" && quiet dnf makecache --refresh
}

# dnf5 skips a source that fails and exits 0 by default (docs/release.md); here the failure must show. -y imports
# the key for the metadata, so that the signature is checked at all.
refresh_index() { dnf makecache -y --setopt=skip_if_unavailable=False; }

# The counter release (scripts/matrix/counters.sh, rpm.sh). The owner of intel_gpu_top as in the security document
# 0.3.0, B2.4, and the package of /usr/bin/pkexec (polkit, 127 on Fedora 45). dnf5 names a scriptlet only when it
# prints something (">>> Running %triggerin scriptlet: …"), and sync without a marker prints nothing (probe on
# 2026-11-20), so TRIGGERED is empty.
OWNER=igt-gpu-tools
PKEXEC_PROVIDER=polkit
TRIGGERED=''
JOINT=(rpm_pair dnf_pair)  # B2.4, 6: rpm -U of both files, dnf upgrade of both
get_pkg() { dnf install -y -- "$@"; }
reget_pkg() { dnf reinstall -y -- "$@"; }
# Without the dependencies, which dnf removes along by default: install_file then needs no mirror.
remove_pkg() { dnf remove -y --setopt=clean_requirements_on_remove=False -- "$1"; }
install_new() { net dnf install -y -- "$1"; }  # dnf skips the OpenPGP check of a file given on the command line
dnf_pair() { dnf upgrade -y -- "$1" "$2"; }
