# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Step 1 of scripts/release.sh, before anything is built: the tree, the versions, the key, the README and GitHub.
# Sourced by release.sh, which sets repo, version, dry, fpr (ORBITOP_KEY in upper case) and tmp. Provides APP,
# GH_REPO, gpg, fingerprint, check_tree, check_key ($tmp/key.asc and $tmp/key.pgp), check_readme, check_github,
# remote_state ($pages_rev) and run_tests.
# shellcheck shell=bash disable=SC2154  # repo, version, dry, fpr and tmp come from release.sh

APP=io.github.zappelmann_sketch.orbitop
GH_REPO=zappelmann-sketch/orbitop
WARN_DAYS=180  # spec 4: the key's remaining time

gpg() { command gpg --no-options --batch "$@"; }  # never a gpg.conf: its options would reach the release

# fingerprint FILE: the fingerprint of the one primary key in FILE, read in the empty keyring $tmp/gnupg.
fingerprint() {
    gpg --homedir "$tmp/gnupg" --with-colons --show-keys -- "$1" 2> /dev/null |
        awk -F: '$1 == "pub" { n++ } $1 == "fpr" && !f { f = $10 }
            END { if (n != 1 || f !~ /^[0-9A-F]{40}$/) exit 1; print f }'
}

# check_tree: a clean main at VERSION, without the tag; the Debian and the RPM changelog of this version come from the
# one source, the <release> entries of the metainfo (packaging/changelog.py). The commits and the tag of the release
# carry only the noreply address of the GitHub account.
check_tree() {
    local branch status have kind ident who
    for ident in GIT_AUTHOR_IDENT GIT_COMMITTER_IDENT; do
        who=$(git -C "$repo" var "$ident") || die "git var $ident failed"
        [[ $who == *"@users.noreply.github.com> "* ]] ||
            die "$ident must be the noreply address of the GitHub account (git config user.email)"
    done
    branch=$(git -C "$repo" symbolic-ref --short -q HEAD) || true
    [ "$branch" = main ] || die "release only from the branch main, not ${branch:-a detached HEAD}"
    status=$(git -C "$repo" status --porcelain) || die "git status failed"
    [ -z "$status" ] || die "the working tree is not clean (git status):"$'\n'"$status"
    have=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$repo/orbitop/__init__.py")
    [ "$have" = "$version" ] || die "orbitop/__init__.py has the version ${have:-none}, not $version"
    ! git -C "$repo" rev-parse -q --verify "refs/tags/v$version" > /dev/null || die "the tag v$version exists already"
    for kind in debian rpm; do
        python3 -I "$repo/packaging/changelog.py" "$kind" "$repo/data/$APP.metainfo.xml" "$version-1" > /dev/null ||
            die "packaging/changelog.py $kind: the metainfo must name $version as its newest <release>"
    done
}

# check_key: ORBITOP_KEY is the primary key of a secret key in GNUPGHOME and has not expired (a warning when less than
# WARN_DAYS are left). Its public key, exported with export-minimal, goes to $tmp/key.asc for build-packages.sh and to
# $tmp/key.pgp. A committed packaging/keys/orbitop-archive-keyring.asc must hold the same key.
check_key() {
    local primary expires now days committed=$repo/packaging/keys/orbitop-archive-keyring.asc
    [[ $fpr =~ ^[0-9A-F]{40}$ ]] || die "ORBITOP_KEY must be the fingerprint of the archive key (40 hex digits)"
    primary=$(gpg --with-colons --list-secret-keys -- "$fpr" 2> /dev/null |
        awk -F: '$1 == "fpr" { print $10; exit }') || true
    [ "$primary" = "$fpr" ] || die "GNUPGHOME has no secret key with the fingerprint ORBITOP_KEY=$fpr"
    expires=$(gpg --with-colons --list-keys -- "$fpr" | awk -F: '$1 == "pub" { print $7; exit }')
    now=$(date +%s)
    if [ -n "$expires" ]; then
        [[ $expires =~ ^[0-9]+$ ]] || die "gpg reports no expiry date for ORBITOP_KEY: $expires"
        [ "$expires" -gt "$now" ] ||
            die "ORBITOP_KEY expired on $(date -u -d "@$expires" +%F); renew it first (docs/release.md, Renewal)"
        days=$(((expires - now) / 86400))
        [ "$days" -ge "$WARN_DAYS" ] || echo "warning: ORBITOP_KEY expires in $days days," \
            "on $(date -u -d "@$expires" +%F); renew it soon (docs/release.md, Renewal)" >&2
    fi
    gpg --armor --export --export-options export-minimal -- "$fpr" > "$tmp/key.asc"
    gpg --export --export-options export-minimal -- "$fpr" > "$tmp/key.pgp"
    [ ! -e "$committed" ] || [ "$(fingerprint "$committed" || true)" = "$fpr" ] ||
        die "packaging/keys/orbitop-archive-keyring.asc is not the key ORBITOP_KEY=$fpr"
}

# check_readme: every fingerprint in README.md and README.de.md, in one piece or grouped as gpg prints it, is
# ORBITOP_KEY. A README without the fingerprint, or with the placeholder <FINGERPRINT> (until Task 9), stops a
# release; a dry run only warns.
check_readme() {
    local readmes=("$repo/README.md" "$repo/README.de.md") found problem=""
    found=$(grep -ohE '\b[0-9A-F]{4}( {0,2}[0-9A-F]{4}){9}\b' -- "${readmes[@]}" | tr -d ' ' | sort -u) || true
    [ -z "$found" ] || [ "$found" = "$fpr" ] ||
        die "the README names the fingerprint ${found//$'\n'/ and }, not ORBITOP_KEY=$fpr"
    [ -n "$found" ] || problem="names no fingerprint of the archive key"
    ! grep -qF '<FINGERPRINT>' -- "${readmes[@]}" || problem="still has the placeholder <FINGERPRINT>"
    [ -n "$problem" ] || return 0
    [ -n "$dry" ] || die "the README $problem"
    echo "warning: the README $problem; a release refuses that" >&2
}

# check_github (a release only): gh is logged in and may change the repository (admin: the release, GitHub Pages),
# before anything is built. A dry run never calls gh.
check_github() {
    local admin
    gh auth status > /dev/null 2>&1 || die "gh is not logged in (gh auth login)"
    admin=$(gh api "repos/$GH_REPO" --jq .permissions.admin 2> /dev/null) || die "gh api repos/$GH_REPO failed"
    [ "$admin" = true ] || die "the login of gh has no admin rights on $GH_REPO (release, GitHub Pages)"
}

# remote_state: the tag is not on origin either. pages_rev is the published gh-pages, fetched as
# refs/remotes/origin/gh-pages, or empty before the first release.
remote_state() {
    local refs
    refs=$(git -C "$repo" ls-remote origin "refs/tags/v$version" refs/heads/gh-pages) ||
        die "cannot read the refs of origin"
    ! grep -q "refs/tags/v$version$" <<< "$refs" || die "the tag v$version exists on origin already"
    pages_rev=""
    grep -q 'refs/heads/gh-pages$' <<< "$refs" || return 0
    git -C "$repo" fetch -q origin +refs/heads/gh-pages:refs/remotes/origin/gh-pages
    # shellcheck disable=SC2034  # read by build.sh and publish.sh
    pages_rev=refs/remotes/origin/gh-pages
}

# run_tests: the strict test suite (CLAUDE.md), with the environment of an ordinary run: without GNUPGHOME and
# ORBITOP_KEY, so that no test reaches the archive key.
run_tests() {
    (cd "$repo" && env -u GNUPGHOME -u ORBITOP_KEY python3 -m pytest -q -W error::ResourceWarning \
        -W error::DeprecationWarning) || die "the strict test suite failed"
}
