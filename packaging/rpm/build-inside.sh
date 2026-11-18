#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds and lints orbitop and orbitop-release inside a disposable fedora:latest or opensuse/tumbleweed container.
# Usage: bash build-inside.sh VERSION RELEASE < KEY.pgp   only as root in the container that scripts/build-packages.sh
#        starts: the archive at /src (read-only), results to /out/rpm-<family> and /out/lint, the key
#        already checked by the host (binary).
set -euo pipefail

key=$(mktemp)
cat > "$key"  # first step: nothing else may read stdin

die() { echo "$*" >&2; exit 1; }
[ $# -eq 2 ] || die "usage: $0 VERSION RELEASE < KEY.pgp"
if [ ! -e /.dockerenv ] || [ "$(id -u)" -ne 0 ]; then
    die "$0 installs packages as root and runs only as root inside a disposable container."
fi
[[ ${OWNER:-} =~ ^[0-9]+:[0-9]+$ ]] || die "OWNER must be uid:gid"
trap 'chown -R "$OWNER" /out' EXIT  # the results belong to the caller, also after a failure
version=$1 release=$2

tools=(rpm-build desktop-file-utils rpmlint cpio)
# shellcheck source=/dev/null  # os-release(5) of the image
case "$(. /etc/os-release && echo "$ID")" in
    fedora)
        family=fedora
        dnf -y -q install "${tools[@]}" python3-devel libappstream-glib gnupg2 >/dev/null ;;
    opensuse-*)
        family=opensuse
        zypper -n -q refresh
        zypper -n -q install --no-recommends "${tools[@]}" python3 python-rpm-macros appstream-glib gpg2 >/dev/null ;;
    *) die "not a Fedora or openSUSE container" ;;
esac

# Sources: the archive as orbitop-VERSION.tar, the key armored (rpm --import and the .repo files need it so).
top=$(mktemp -d)
mkdir "$top/SOURCES" "$top/SPECS"
tar -C / -cf "$top/SOURCES/orbitop-$version.tar" --transform "s,^src,orbitop-$version," src
GNUPGHOME=$(mktemp -d) && export GNUPGHOME
gpg --batch --quiet --import "$key"
gpg --batch --armor --export > "$top/SOURCES/RPM-GPG-KEY-orbitop"
cp /src/packaging/keyring/orbitop-fedora.repo /src/packaging/keyring/orbitop-opensuse.repo /src/LICENSE "$top/SOURCES/"

# %changelog from the metainfo and from packaging/keyring.version; the repository holds none.
keyring=$(cat /src/packaging/keyring.version)
meta=/src/data/io.github.zappelmann_sketch.orbitop.metainfo.xml
{ cat /src/packaging/rpm/orbitop.spec; python3 -I /src/packaging/changelog.py rpm "$meta" "$version-$release"; } \
    > "$top/SPECS/orbitop.spec"
{ cat /src/packaging/rpm/orbitop-release.spec; python3 -I /src/packaging/changelog.py rpm-release "$keyring"; } \
    > "$top/SPECS/orbitop-release.spec"

# Time stamps only from %changelog and a neutral build host instead of the container's random name: the same inputs
# give the same orbitop-release, and no package names the machine it was built on.
rpmbuild() {
    command rpmbuild -bb --define "_topdir $top" --define "_buildhost build" \
        --define "source_date_epoch_from_changelog 1" --define "clamp_mtime_to_source_date_epoch 1" \
        --define "use_source_date_epoch_as_buildtime 1" "$@"
}
rpmbuild --define "orbitop_version $version" --define "orbitop_release $release" "$top/SPECS/orbitop.spec"
rpmbuild --define "keyring_version $keyring" "$top/SPECS/orbitop-release.spec"

# pkexec runs this file as root: no packaging tool may change it (Fedora mangles shebangs after %install).
rpm2cpio "$top/RPMS/noarch/orbitop-$version-$release.noarch.rpm" |
    cpio -i --quiet --to-stdout ./usr/lib/orbitop/killhelper |
    cmp - /src/orbitop/killhelper.py || die "the packaged helper differs from orbitop/killhelper.py"

mkdir -p "/out/rpm-$family" /out/lint
cp "$top"/RPMS/noarch/*.rpm "/out/rpm-$family/"
# openSUSE's rpmlint reports every polkit action that the SUSE security team has not reviewed for a SUSE product and
# blocks filters for it (BlockedFilters in opensuse.toml). orbitop is no SUSE product, so exactly this line is accepted;
# a weaker default than auth_admin fails (docs/release.md, "Lint notes"). The exit status of rpmlint depends on a
# badness threshold there, so every E: line counts.
accepted=-  # a line rpmlint never prints
if [ "$family" = opensuse ]; then
    accepted="orbitop.noarch: E: polkit-untracked-privilege (Badness: 10) io.github.zappelmann-sketch.orbitop.terminate"
    accepted+=" (auth_admin:auth_admin:auth_admin)"
fi
report=/out/lint/rpm-$family.txt
rpmlint "/out/rpm-$family"/*.rpm > "$report" 2>&1 || true
cat "$report"
grep -q ' packages and .* specfiles checked;' "$report" || die "rpmlint did not finish"
if grep ': E: ' "$report" | grep -qvxF -- "$accepted"; then
    die "rpmlint reports errors"
fi
