# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Steps 2 and 3 of scripts/release.sh and the release files: the small source packages the published source already
# has, the packages and the signed source, the container matrix with docs/distro-check.md, the release assets.
# Sourced by release.sh after checks.sh (gpg, $tmp/key.asc, $tmp/key.pgp, $pages_rev). Provides blob, signed_release,
# published, build, matrix and make_assets ($assets).
# shellcheck shell=bash disable=SC2154  # repo, version, dry, fpr, tmp, keyring_version, pages_rev and the images

# The paths of the source, as scripts/build-site.sh lays it out.
POOL=apt/pool/main/o
APT_INDEX=apt/dists/stable/main/binary-all/Packages
# The script of signed's container: the image's own keys leave the rpm database, so that rpm -K accepts ORBITOP_KEY
# (KEY) alone; then rpm -K of the RPM on stdin. A loop of bash: Tumbleweed has no xargs.
# shellcheck disable=SC2016  # the container expands it
RPM_K='set -e; cd "$(mktemp -d)"; printf "%s\n" "$KEY" > key.asc; cat > p.rpm
keys=$(rpmkeys --list); while read -r k _; do [ -z "$k" ] || rpmkeys --delete "${k%:}"; done <<< "$keys"
[ -z "$(rpmkeys --list)" ]; rpmkeys --import key.asc; rpm -K p.rpm'

# blob PATH FILE: PATH of the published gh-pages into FILE, read from git objects, never from a checkout; fails, and
# leaves no FILE, if PATH is no blob there (missing, or a directory).
blob() {
    [ "$(git -C "$repo" cat-file -t "$pages_rev:$1" 2> /dev/null)" = blob ] && mkdir -p -- "${2%/*}" || return 1
    if ! git -C "$repo" cat-file blob "$pages_rev:$1" > "$2"; then
        rm -f -- "$2"
        return 1
    fi
}

# signed_release: $tmp/published/Release is the Release of the published gh-pages, if its InRelease verifies with
# ORBITOP_KEY alone; fails otherwise.
signed_release() {
    local d=$tmp/published
    [ ! -f "$d/Release" ] || return 0
    mkdir -p "$d" && blob apt/dists/stable/InRelease "$d/InRelease" &&
        gpgv --keyring "$tmp/key.pgp" --output "$d/Release.new" "$d/InRelease" 2> /dev/null &&
        mv -- "$d/Release.new" "$d/Release"
}

# indexed FILE: the published apt index, which the verified InRelease lists, names a package with the sha256 of FILE.
indexed() {
    local d=$tmp/published hash
    signed_release && blob "$APT_INDEX" "$d/Packages" || return 1
    hash=$(sha256sum < "$d/Packages") && grep -qE "^ ${hash%% *} +[0-9]+ main/binary-all/Packages$" "$d/Release" &&
        hash=$(sha256sum < "$1") && grep -qxF "SHA256: ${hash%% *}" "$d/Packages"
}

# signed FAMILY FILE: rpm -K in a disposable container of FAMILY's image (RPM_K), which knows only the public key of
# ORBITOP_KEY, reports a valid signature for FILE. The container gets the key and FILE on stdin, nothing mounted,
# no network.
signed() {
    local image=$FEDORA_IMAGE checked
    [ "$1" = fedora ] || image=$SUSE_IMAGE
    checked=$(docker run --rm -i --network none --cap-drop MKNOD --cap-drop SETFCAP -e KEY="$(cat "$tmp/key.asc")" \
        "$image" bash -c "$RPM_K" < "$2") || return 1
    [ "${checked##*$'\n'}" = "p.rpm: digests signatures OK" ]
}

# published: the small source packages of packaging/keyring.version that gh-pages already serves go to $tmp/reuse, in
# the layout of build-packages.sh; build puts them in place of the rebuilt ones, so that one version keeps its bytes
# (the toolchain of the images is not pinned, and a signed RPM differs from build to build). Only bytes that the
# published source vouches for: the deb by its hash in the signed apt index, each RPM by its signature.
published() {
    local deb=$POOL/orbitop-apt-source/orbitop-apt-source_${keyring_version}_all.deb family rpm
    mkdir "$tmp/reuse"
    [ -n "$pages_rev" ] || return 0
    if blob "$deb" "$tmp/reuse/deb/${deb##*/}"; then
        indexed "$tmp/reuse/deb/${deb##*/}" ||
            die "refusing to reuse $deb: it is not in the signed apt index of gh-pages"
        echo "reusing the published $deb"
    fi
    for family in fedora opensuse; do
        rpm=rpm/$family/orbitop-release-$keyring_version-1.noarch.rpm
        blob "$rpm" "$tmp/reuse/rpm-$family/${rpm##*/}" || continue
        signed "$family" "$tmp/reuse/rpm-$family/${rpm##*/}" ||
            die "refusing to reuse $rpm of gh-pages: it has no valid signature of ORBITOP_KEY"
        echo "reusing the published $rpm"
    done
}

# build DIR SITE [SUFFIX]: build-packages.sh into DIR, the published small packages in place, build-site.sh into SITE.
build() {
    bash "$repo/scripts/build-packages.sh" --out "$1" --pubkey "$tmp/key.asc" ${3:+--suffix "$3"} ||
        die "build-packages.sh failed"
    cp -r -- "$tmp/reuse/." "$1/"
    bash "$repo/scripts/build-site.sh" --packages "$1" --out "$2" || die "build-site.sh failed"
}

# matrix: check-distros.sh with both trees must pass on every image and name ORBITOP_KEY. Its output becomes the
# results in docs/distro-check.md, which must still list every distribution of the README as passed; a release commits
# the file, a dry run only writes it.
matrix() {
    local key doc=docs/distro-check.md
    bash "$repo/scripts/check-distros.sh" --site "$tmp/site" --site2 "$tmp/site2" | tee "$tmp/matrix.log" ||
        die "the container matrix failed (RESULT lines above)"
    key=$(sed -n 's/^KEY //p' "$tmp/matrix.log" | sort -u)
    [ "$key" = "$fpr" ] || die "the matrix ran with the key ${key:-none}, not ORBITOP_KEY=$fpr"
    python3 -I "$repo/scripts/release/distro-check.py" "$repo/$doc" "$version" "$keyring_version" ${dry:+"--dry-run"} \
        < "$tmp/matrix.log" || die "cannot write the results to $doc"
    (cd "$repo" && env -u GNUPGHOME -u ORBITOP_KEY python3 -m pytest -q tests/test_readme.py) ||
        die "the README does not match the results in $doc"
    [ -z "$dry" ] || return 0
    git -C "$repo" diff --quiet -- "$doc" ||
        git -C "$repo" commit -q --no-gpg-sign -m "docs: Distributionsprüfung für orbitop $version" -- "$doc"
}

# make_assets: the files of the GitHub release in $tmp/assets, listed in $assets: the source archive of HEAD (step 4
# tags this commit), the four packages and the three small source packages under the fixed names of the README
# (plan K3), each as the signed source serves it (the RPMs with their signature), then SHA256SUMS of these eight and
# SHA256SUMS.asc, checked as the README tells users to.
make_assets() {
    local a=$tmp/assets s=$tmp/site p=$version-1 k=$keyring_version status
    mkdir "$a"
    git -C "$repo" archive --format=tar.gz --prefix="orbitop-$version/" -o "$a/orbitop-$version.tar.gz" HEAD
    cp -- "$s/$POOL/orbitop/orbitop_${p}_all.deb" "$s/arch/x86_64/orbitop-$p-any.pkg.tar.zst" "$a/"
    cp -- "$s/rpm/fedora/orbitop-$p.noarch.rpm" "$a/orbitop-$p.fedora.noarch.rpm"
    cp -- "$s/rpm/opensuse/orbitop-$p.noarch.rpm" "$a/orbitop-$p.opensuse.noarch.rpm"
    cp -- "$s/$POOL/orbitop-apt-source/orbitop-apt-source_${k}_all.deb" "$a/orbitop-apt-source.deb"
    cp -- "$s/rpm/fedora/orbitop-release-$k-1.noarch.rpm" "$a/orbitop-release-fedora.rpm"
    cp -- "$s/rpm/opensuse/orbitop-release-$k-1.noarch.rpm" "$a/orbitop-release-opensuse.rpm"
    (cd "$a" && export LC_ALL=C && sha256sum -- * > "$tmp/SHA256SUMS") && mv -- "$tmp/SHA256SUMS" "$a/"
    gpg --local-user "$fpr!" --armor --detach-sign -o "$a/SHA256SUMS.asc" "$a/SHA256SUMS"
    # As the README: gpgv with the keyring of the source, then sha256sum, in the directory of the files.
    status=$(cd "$a" && gpgv --status-fd 1 --keyring "$s/orbitop-archive-keyring.pgp" SHA256SUMS.asc SHA256SUMS \
        2> /dev/null) || die "SHA256SUMS.asc does not verify with the keyring of the source"
    grep -q "^\[GNUPG:\] VALIDSIG $fpr " <<< "$status" || die "SHA256SUMS.asc is not signed by ORBITOP_KEY=$fpr"
    (cd "$a" && sha256sum --strict --quiet -c SHA256SUMS) || die "SHA256SUMS does not match the release files"
    # shellcheck disable=SC2034  # read by release_github in publish.sh
    assets=("$a"/*)
    cat -- "$a/SHA256SUMS"
}
