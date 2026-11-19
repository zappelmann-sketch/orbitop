# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# The rpm part of scripts/matrix/dnf.sh and zypper.sh, sourced by scripts/matrix/inside.sh after lib.sh and before
# either of them; they set FAMILY (fedora, opensuse), the directory of their packages below rpm/ in the site, and
# TAMPERED, the reason their index refresh names for a changed repomd.xml.
# shellcheck shell=bash disable=SC2154  # FAMILY and TAMPERED come from dnf.sh or zypper.sh, STATE from lib.sh

installed() { rpm -q --qf '%{VERSION}-%{RELEASE}' orbitop; }
offered() { rpm -qp --qf '%{VERSION}-%{RELEASE}' "$1/rpm/$FAMILY"/orbitop-[0-9]*.noarch.rpm; }
files_of() { rpm -ql orbitop orbitop-release; }
owned() { rpm -qf -- "$1" > /dev/null 2>&1; }

# rpm_key ROOT: the key of the site into the rpm database, as the README does before the first package (no
# unknown key then for zypper, and dnf asks only for its copy for the metadata); exactly one key is new there. Then
# every RPM of ROOT must carry a signature that verifies: rpm -K reports "digests OK" with exit 0 for an RPM without
# one.
rpm_key() {
    local before after checked
    before=$(rpmkeys --list) && rpm --import "$1/orbitop-archive-keyring.asc" && after=$(rpmkeys --list) || return 1
    [ "$(grep -cvxF -- "$before" <<< "$after")" -eq 1 ] && checked=$(rpm -K "$1/rpm/$FAMILY"/*.rpm) || return 1
    printf '%s\n' "$checked"
    ! grep -v -- ': digests signatures OK$' <<< "$checked"
}

# release_package ROOT: orbitop-release of ROOT under the name of the release asset (plan K3), in STATE.
release_package() { cp -- "$1/rpm/$FAMILY"/orbitop-release-*.noarch.rpm "$STATE/orbitop-release-$FAMILY.rpm"; }

# drop_key: the line of the README's full uninstall that deletes every key named like the archive key from the rpm
# database (without sudo); afterwards it lists none.
drop_key() {
    local keys
    rpmkeys --list | grep -F 'orbitop archive signing key' | sed 's/[: ].*//' | xargs -r -n1 rpmkeys --delete &&
        keys=$(rpmkeys --list) && ! grep -F 'orbitop archive signing key' <<< "$keys"
}

# tamper_index ROOT: one digit of <revision> in repomd.xml changed; the XML stays well-formed, so the signature check
# has to refuse it (zypper parses repomd.xml before it checks the signature).
tamper_index() {
    local repomd=$1/rpm/$FAMILY/repodata/repomd.xml at
    at=$(grep -bo '<revision>[0-9]' "$repomd" | cut -d: -f1) && flip "$repomd" $((at + 10))
}

tamper() { tampered repomd "$TAMPERED" tamper_index; }
