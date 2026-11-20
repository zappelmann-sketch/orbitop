#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds and lints orbitop and orbitop-release inside a disposable fedora:latest or opensuse/tumbleweed container.
# Usage: bash build-inside.sh VERSION RELEASE < KEY.pgp   only as root in the container that scripts/build-packages.sh
#        starts: the archive at /src (read-only), results to /out/rpm-<family> and /out/lint, the key
#        already checked by the host (binary).
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../container-prologue.sh
. "$(dirname -- "$0")/../container-prologue.sh"  # $key from stdin, die, archive; only as root in a container

[ $# -eq 2 ] || die "usage: $0 VERSION RELEASE < KEY.pgp"
version=$1 release=$2

tools=(rpm-build desktop-file-utils rpmlint cpio gawk)
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
archive "$top/SOURCES" "$version"
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

# pkexec runs these files as root: no packaging tool may change them (Fedora mangles shebangs after %install).
for helper in killhelper counterhelper; do
    rpm2cpio "$top/RPMS/noarch/orbitop-$version-$release.noarch.rpm" |
        cpio -i --quiet --to-stdout "./usr/lib/orbitop/$helper" |
        cmp - "/src/orbitop/$helper.py" || die "the packaged helper differs from orbitop/$helper.py"
done

mkdir -p "/out/rpm-$family" /out/lint
cp "$top"/RPMS/noarch/*.rpm "/out/rpm-$family/"
report=/out/lint/rpm-$family.txt
rpmlint "/out/rpm-$family"/*.rpm > "$report" 2>&1 || true  # its exit status is no verdict (lint-gate.sh)
cat "$report"
bash /src/packaging/rpm/lint-gate.sh "$family" "$report" || die "rpmlint reports errors"
