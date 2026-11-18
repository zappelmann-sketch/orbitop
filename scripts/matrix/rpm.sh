# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# The rpm part of scripts/matrix/dnf.sh and zypper.sh, sourced by scripts/matrix/inside.sh before either of them;
# they set FAMILY (fedora, opensuse), the directory of their packages below rpm/ in the site.
# shellcheck shell=bash disable=SC2154  # FAMILY comes from dnf.sh or zypper.sh

installed() { rpm -q --qf '%{VERSION}-%{RELEASE}' orbitop; }
offered() { rpm -qp --qf '%{VERSION}-%{RELEASE}' "$1/rpm/$FAMILY"/orbitop-[0-9]*.noarch.rpm; }
files_of() { rpm -ql orbitop orbitop-release; }
owned() { rpm -qf -- "$1" > /dev/null 2>&1; }

# rpm_key ROOT: the key of the site into the rpm database, as the README does before the first package (no
# unknown key then for zypper, and dnf asks only for its copy for the metadata). Its name there goes to /tmp/rpmkey
# for rpmkeys --delete; every RPM of ROOT verifies with it.
rpm_key() {
    local before
    before=$(rpmkeys --list) && rpm --import "$1/orbitop-archive-keyring.asc" &&
        rpmkeys --list | grep -vxF -- "$before" | sed 's/[: ].*//' > /tmp/rpmkey &&  # Tumbleweed has no awk
        [ "$(wc -l < /tmp/rpmkey)" -eq 1 ] && rpm -K "$1/rpm/$FAMILY"/*.rpm
}

# release_package ROOT: orbitop-release of ROOT under the name of the release asset (plan K3), in /tmp.
release_package() { cp -- "$1/rpm/$FAMILY"/orbitop-release-*.noarch.rpm "/tmp/orbitop-release-$FAMILY.rpm"; }

# drop_key: the last command of the full uninstall in the README; afterwards the rpm database lacks the key.
drop_key() {
    local key
    key=$(cat /tmp/rpmkey) && rpmkeys --delete "$key" && ! rpmkeys --list | grep -F -- "$key"
}

# tamper_index ROOT: one digit of <revision> in repomd.xml changed; the XML stays well-formed, so the signature check
# has to refuse it (zypper parses repomd.xml before it checks the signature).
tamper_index() {
    local repomd=$1/rpm/$FAMILY/repodata/repomd.xml at
    at=$(grep -bo '<revision>[0-9]' "$repomd" | cut -d: -f1) && flip "$repomd" $((at + 10))
}
