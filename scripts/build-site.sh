#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Builds the signed package source for GitHub Pages from the output of build-packages.sh (spec 2, docs/release.md).
# Usage: ORBITOP_KEY=FINGERPRINT GNUPGHOME=DIR bash build-site.sh --packages DIR --out SITE
#        SITE is empty or missing. GNUPGHOME holds the secret key of ORBITOP_KEY and nothing else (its own gpg-agent).
# Only gpg on this host signs. The containers in packaging/site/*-inside.sh index the packages; they get the public
# key, and the ones for rpmsign also the gpg-agent's restricted extra socket, never a secret key.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=container-common.sh
. "$(dirname -- "$0")/container-common.sh"  # images, die, usage, options, fresh_out, workdir, container

# Below https://zappelmann-sketch.github.io/orbitop/ as orbitop.sources, the .repo files and the README's pacman.conf
# section name them (tests/test_site.py).
APT_DIR=apt
APT_SUITE=stable
APT_COMPONENT=main
FEDORA_DIR=rpm/fedora
OPENSUSE_DIR=rpm/opensuse
ARCH_DIR=arch/x86_64
# Local tool images for rpmsign (packaging/site/rpm-tools.Dockerfile).
FEDORA_TOOLS=orbitop-site-rpm-fedora:local
SUSE_TOOLS=orbitop-site-rpm-opensuse:local
USAGE="ORBITOP_KEY=FINGERPRINT $0 --packages DIR --out SITE"

packages="" out=""
options packages out -- "$@"
[ -n "$packages" ] && [ -n "$out" ] || usage
[ -d "$packages" ] || die "--packages must be the output directory of build-packages.sh: $packages"
packages=$(cd -- "$packages" && pwd -P)
only_plain "$packages"  # written by root in containers; no symlink there may lead the copies below elsewhere
fresh_out "$out" "so that the source holds only the newest packages"
fpr=${ORBITOP_KEY:-}
fpr=${fpr^^}
[[ $fpr =~ ^[0-9A-F]{40}$ ]] || die "ORBITOP_KEY must be the fingerprint of the signing key (40 hex digits)"

gpg() { command gpg --no-options --batch "$@"; }  # no gpg.conf: its comment or sig-notation would reach the site
# The secret key of exactly this primary key; the fingerprint of a subkey or of a foreign key stops here.
primary=$(gpg --with-colons --list-secret-keys -- "$fpr" 2>/dev/null | awk -F: '$1 == "fpr" { print $10; exit }') ||
    true
[ "$primary" = "$fpr" ] || die "GNUPGHOME has no secret key with the fingerprint ORBITOP_KEY=$fpr"
gpgconf --launch gpg-agent
# Through the socket the agent signs and decrypts with every key it holds, so it may hold only this one. Its listing
# must show the primary key (or the listing failed) and no keygrip of another key.
mine=$(gpg --with-colons --with-keygrip --list-secret-keys -- "$fpr" | awk -F: '$1 == "grp" { print $10 }')
held=$(gpg-connect-agent --no-autostart 'KEYINFO --list' /bye | awk '$2 == "KEYINFO" { print $3 }')
grip=${mine%%$'\n'*}
if [[ ! $grip =~ ^[0-9A-F]{40}$ ]] || ! grep -qxF -- "$grip" <<< "$held"; then
    die "the gpg-agent of GNUPGHOME does not list ORBITOP_KEY (KEYINFO --list)"
fi
# grep exits 1 when every keygrip is one of ours and 2 on an error: only 0 and 1 are answers.
others=$(grep -vxF -f <(printf '%s\n' "$mine") <<< "$held" || [ $? -eq 1 ]) ||
    die "the keys of the gpg-agent of GNUPGHOME could not be compared"
[ -z "$others" ] || die "the gpg-agent of GNUPGHOME must hold ORBITOP_KEY and no other key; use a GNUPGHOME of" \
    "its own (docs/release.md, Site)"
socket=$(gpgconf --list-dirs agent-extra-socket)
[ -S "$socket" ] || die "rpmsign needs the gpg-agent's extra socket, and there is none at $socket (extra-socket none?)"

workdir
tracked_files
gpg --export --export-options export-minimal -- "$fpr" > "$tmp/key.pgp"
gpg --armor --export --export-options export-minimal -- "$fpr" > "$tmp/key.asc"
mkdir -p -- "$out"
out=$(cd -- "$out" && pwd -P)

shopt -s nullglob
put() {  # put PATTERN DIR: exactly one file per package, so that the source holds only the newest version (spec 2)
    # shellcheck disable=SC2206  # PATTERN is a glob
    local found=("$packages"/$1)
    [ ${#found[@]} -eq 1 ] || die "--packages must hold exactly one $1, not ${#found[@]}"
    [ -f "${found[0]}" ] && [ ! -L "${found[0]}" ] || die "--packages: not a regular file: ${found[0]}"
    mkdir -p -- "$out/$2"
    cp -- "${found[0]}" "$out/$2/"
    (cd -- "$out" && sha256sum -- "$2/${found[0]##*/}") >> "$tmp/inputs.sha256"
}
# inputs DIR: the names of the packages put into DIR, one per line.
inputs() { grep -F "  $1/" "$tmp/inputs.sha256" | awk -v d="$1/" '{ print substr($2, length(d) + 1) }'; }
# unchanged DIR: after its container, the packages in DIR are still byte for byte those from --packages, so that the
# host signs no package a container replaced.
unchanged() {
    (cd -- "$out" && grep -F "  $1/" "$tmp/inputs.sha256" | sha256sum --check --quiet --strict -) ||
        die "refusing $1: a package there is not the one from --packages any more"
}
# exactly DIR PATTERN…: after its container, DIR holds exactly one file per PATTERN (an extended regular expression of
# its path below DIR) and no other file, so that the host signs and publishes nothing a container added.
exactly() {
    local dir=$1 files pattern
    shift
    files=$(cd -- "$out/$dir" && find . -type f -printf '%P\n' | LC_ALL=C sort) || die "refusing $dir: find failed"
    for pattern; do
        [ "$(grep -cxE -- "$pattern" <<< "$files")" -eq 1 ] || die "refusing $dir: not exactly one file like $pattern"
        files=$(grep -vxE -- "$pattern" <<< "$files") || true
    done
    [ -z "$files" ] || die "refusing $dir: files that no step writes: ${files//$'\n'/ }"
}
# shellcheck disable=SC2001  # ${var//…} has no back reference in every bash
literal() { sed 's/[][\.*^$+?(){}|]/\\&/g' <<< "$1"; }  # a file name as an extended regular expression
# signed_only DIR FAMILY: after rpm-inside.sh, DIR holds the RPMs from --packages and the repodata/ of createrepo_c,
# and each RPM is its input byte for byte from the main header on: rpmsign changed only its signature header.
signed_only() {
    local name names=() patterns=()
    mapfile -t names < <(inputs "$1")
    for name in "${names[@]}"; do patterns+=("$(literal "$name")"); done
    exactly "$1" "${patterns[@]}" 'repodata/repomd\.xml' 'repodata/[0-9a-f]{64}-primary\.xml\.(zst|gz|xz)' \
        'repodata/[0-9a-f]{64}-filelists\.xml\.(zst|gz|xz)' 'repodata/[0-9a-f]{64}-other\.xml\.(zst|gz|xz)'
    for name in "${names[@]}"; do
        python3 -I "$tmp/src/packaging/site/rpm-same.py" "$out/$1/$name" "$packages/rpm-$2/$name" ||
            die "refusing $1: $name is not the package from --packages with a new signature"
    done
}
put 'deb/orbitop_*_all.deb' "$APT_DIR/pool/$APT_COMPONENT/o/orbitop"
put 'deb/orbitop-apt-source_*_all.deb' "$APT_DIR/pool/$APT_COMPONENT/o/orbitop-apt-source"
put 'rpm-fedora/orbitop-[0-9]*.noarch.rpm' "$FEDORA_DIR"
put 'rpm-fedora/orbitop-release-*.noarch.rpm' "$FEDORA_DIR"
put 'rpm-opensuse/orbitop-[0-9]*.noarch.rpm' "$OPENSUSE_DIR"
put 'rpm-opensuse/orbitop-release-*.noarch.rpm' "$OPENSUSE_DIR"
put 'arch/orbitop-*-any.pkg.tar.zst' "$ARCH_DIR"

sign() { gpg --yes --local-user "$fpr!" "$@"; }  # "!": exactly the primary key, never a subkey
# Every signature must verify with the public key alone, the one the packages install.
verify() { gpgv --keyring "$tmp/key.pgp" "$@" 2>/dev/null || die "the signature does not verify with ORBITOP_KEY: $1"; }
# The RPM tools go into local images first, with network but without the socket. The containers that get the socket
# run from them without network, so no installation, scriptlet or download runs next to it.
tools() { docker build -q -t "$1" --build-arg BASE="$2" - < "$tmp/src/packaging/site/rpm-tools.Dockerfile" >/dev/null; }
tools "$FEDORA_TOOLS" "$FEDORA_IMAGE"
tools "$SUSE_TOOLS" "$SUSE_IMAGE"

# apt: Packages, by-hash and Release from the container, InRelease and Release.gpg from here.
container "$out/$APT_DIR" "$DEB_IMAGE" -- /src/packaging/site/apt-inside.sh "$APT_SUITE" "$APT_COMPONENT"
unchanged "$APT_DIR"
# The container wrote the index; the host signs it only if it lists exactly these debs, true to the byte.
mapfile -t debs < <(inputs "$APT_DIR")
python3 -I "$tmp/src/packaging/site/check-apt-index.py" "$out/$APT_DIR" "$APT_SUITE" "$APT_COMPONENT" "${debs[@]}" ||
    die "refusing $APT_DIR: its index is not exactly the one of the packages from --packages"
dists=$out/$APT_DIR/dists/$APT_SUITE
sign --clearsign -o "$dists/InRelease" "$dists/Release"
sign --armor --detach-sign -o "$dists/Release.gpg" "$dists/Release"
verify "$dists/InRelease"
verify "$dists/Release.gpg" "$dists/Release"

# RPM: rpmsign through the agent's socket and createrepo_c in the tool image of each family, then repomd.xml here.
agent=(--network none --mount "type=bind,source=$socket,target=/gnupg/S.gpg-agent")
container "$out/$FEDORA_DIR" "$FEDORA_TOOLS" "${agent[@]}" -- /src/packaging/site/rpm-inside.sh
signed_only "$FEDORA_DIR" fedora
container "$out/$OPENSUSE_DIR" "$SUSE_TOOLS" "${agent[@]}" -- /src/packaging/site/rpm-inside.sh
signed_only "$OPENSUSE_DIR" opensuse
for dir in "$FEDORA_DIR" "$OPENSUSE_DIR"; do
    repomd=$out/$dir/repodata/repomd.xml
    sign --armor --detach-sign -o "$repomd.asc" "$repomd"
    verify "$repomd.asc" "$repomd"
    cp -- "$tmp/key.asc" "$repomd.key"
done

# Arch: repo-add in the container, then a binary .sig beside the package and both databases; pacman fetches each one
# from the server (repo-add embeds no package signature without --include-sigs, and pacman 7 does not need it).
container "$out/$ARCH_DIR" "$ARCH_IMAGE" --network none -- /src/packaging/site/arch-inside.sh
unchanged "$ARCH_DIR"
pkg=$(inputs "$ARCH_DIR")  # only the package from --packages
exactly "$ARCH_DIR" "$(literal "$pkg")" 'orbitop\.db' 'orbitop\.files'
for file in "$out/$ARCH_DIR/$pkg" "$out/$ARCH_DIR/orbitop.db" "$out/$ARCH_DIR/orbitop.files"; do
    sign --no-armor --detach-sign -o "$file.sig" "$file"
    verify "$file.sig" "$file"
done

cp -- "$tmp/key.asc" "$out/orbitop-archive-keyring.asc"
cp -- "$tmp/key.pgp" "$out/orbitop-archive-keyring.pgp"
: > "$out/.nojekyll"  # GitHub Pages serves the tree as it is
grouped=$(sed -E 's/.{4}/& /g; s/ $//; s/^.{25}/& /' <<< "$fpr")  # as gpg --fingerprint prints it
sed "s/<FINGERPRINT>/$grouped/" "$tmp/src/packaging/site/index.html" > "$out/index.html"
(cd -- "$out" && find . -type f | sort)
