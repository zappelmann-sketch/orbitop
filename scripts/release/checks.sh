# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Step 1 of scripts/release.sh, before anything is built: the tree, the versions, the key, the README and GitHub.
# Sourced by release.sh after container-common.sh (die, fingerprint), which sets repo, version, dry, fpr (ORBITOP_KEY
# in upper case) and tmp. Provides APP, GH_REPO, gpg, check_tree ($pinned), check_date, check_origin, check_key
# ($tmp/key.asc and $tmp/key.pgp), check_committed, check_readme, check_github, remote_state ($pages_rev), run_tests
# and check_head.
# shellcheck shell=bash disable=SC2154  # repo, version, dry, fpr and tmp come from release.sh

APP=io.github.zappelmann_sketch.orbitop
GH_REPO=zappelmann-sketch/orbitop
IDENT="zappelmann-sketch <235797375+zappelmann-sketch@users.noreply.github.com>"  # of every commit and tag
WARN_DAYS=180  # spec 4: the key's remaining time
# The push and the fetch URL of origin, the one repository a release pushes to and reads from: GH_REPO on GitHub, over
# https or ssh.
ORIGIN_URL='(https://github\.com/|git@github\.com:|ssh://git@github\.com/)zappelmann-sketch/orbitop(\.git)?'

gpg() { command gpg --no-options --batch "$@"; }  # never a gpg.conf: its options would reach the release

# check_ident DIR: git in DIR writes commits and tags as the account's name and noreply address and nothing else (git
# var prints IDENT, then time and zone). DIR is the repository or the gh-pages worktree: an includeIf of the git
# configuration (onbranch, gitdir) can give a worktree another identity than the repository.
check_ident() {
    local ident who
    for ident in GIT_AUTHOR_IDENT GIT_COMMITTER_IDENT; do
        who=$(git -C "$1" var "$ident") || die "git var $ident failed in $1"
        [ "${who% * *}" = "$IDENT" ] ||
            die "$ident must be exactly $IDENT in $1 (git config user.name, user.email, also under includeIf)"
    done
}

# check_tree: a clean main at VERSION, without the tag, whose commits and tag carry IDENT; the Debian and the RPM
# changelog of this version come from the one source, the <release> entries of the metainfo (packaging/changelog.py).
# pinned is this HEAD: the builds and the matrix take its files (build.sh), the release files and the tag are of it or
# of the one commit of step 3 on top (check_head). git archive would take export-ignore and export-subst from
# info/attributes, which no commit shows and git_archive cannot turn off, so it must be empty.
check_tree() {
    local branch status have kind attributes
    check_ident "$repo"
    branch=$(git -C "$repo" symbolic-ref --short -q HEAD) || true
    [ "$branch" = main ] || die "release only from the branch main, not ${branch:-a detached HEAD}"
    status=$(git -C "$repo" status --porcelain) || die "git status failed"
    [ -z "$status" ] || die "the working tree is not clean (git status):"$'\n'"$status"
    attributes=$(git -C "$repo" rev-parse --path-format=absolute --git-path info/attributes) ||
        die "git rev-parse --git-path info/attributes failed"
    [ ! -s "$attributes" ] || die "$attributes is not empty: git archive would apply it to the release files" \
        "(git-archive(1), ATTRIBUTES); empty or remove it"
    have=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$repo/orbitop/__init__.py")
    [ "$have" = "$version" ] || die "orbitop/__init__.py has the version ${have:-none}, not $version"
    ! git -C "$repo" rev-parse -q --verify "refs/tags/v$version" > /dev/null || die "the tag v$version exists already"
    for kind in debian rpm; do
        python3 -I "$repo/packaging/changelog.py" "$kind" "$repo/data/$APP.metainfo.xml" "$version-1" > /dev/null ||
            die "packaging/changelog.py $kind: the metainfo must name $version as its newest <release>"
    done
    pinned=$(git -C "$repo" rev-parse --verify HEAD) || die "git rev-parse HEAD failed"
}

# warn_or_die MESSAGE…: a release stops; a dry run, which publishes nothing, only warns.
warn_or_die() {
    [ -n "$dry" ] || die "$*"
    echo "warning: $*; a release refuses that" >&2
}

# check_date: the newest <release> of the metainfo, which becomes the changelogs and the release notes, has today's
# date (UTC).
check_date() {
    local released today
    released=$(python3 -I -c 'import sys, xml.etree.ElementTree as E
print(E.parse(sys.argv[1]).find("releases/release").get("date"))' "$repo/data/$APP.metainfo.xml") ||
        die "cannot read the date of the newest <release> of the metainfo"
    today=$(date -u +%F)
    [ "$released" = "$today" ] ||
        warn_or_die "the newest <release> of the metainfo has the date $released, not today ($today, UTC)"
}

# check_origin: every URL that git push origin pushes to, and every URL that remote_state reads the tag and gh-pages
# from, is one, the repository GH_REPO on GitHub, so that no mirror stands in for it. git remote get-url --all
# [--push] names them after pushurl, insteadOf and pushInsteadOf of the git configuration.
check_origin() {
    local urls re="^${ORIGIN_URL}\$"
    urls=$(git -C "$repo" remote get-url --all --push origin 2> /dev/null) || urls=""
    [[ $urls =~ $re ]] || warn_or_die "origin pushes to ${urls:-nowhere}, not to $GH_REPO on GitHub (git remote" \
        "get-url --all --push origin: url, pushurl, insteadOf)"
    urls=$(git -C "$repo" remote get-url --all origin 2> /dev/null) || urls=""
    [[ $urls =~ $re ]] || warn_or_die "origin fetches from ${urls:-nowhere}, not from $GH_REPO on GitHub (git" \
        "remote get-url --all origin: url, insteadOf)"
}

# check_key: ORBITOP_KEY is the primary key of a secret key in GNUPGHOME and has not expired (a warning when less than
# WARN_DAYS are left). Its public key, exported with export-minimal, goes to $tmp/key.asc for build-packages.sh and to
# $tmp/key.pgp. A committed packaging/keys/orbitop-archive-keyring.asc must be that export (check_committed).
check_key() {
    local primary expires now days
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
    check_committed
}

# check_committed: a committed packaging/keys/orbitop-archive-keyring.asc is ORBITOP_KEY and, packet for packet, its
# current export $tmp/key.pgp. A renewal (new expiry, another user ID) keeps the fingerprint but changes the key, and
# the tests pin that file per packaging/keyring.version.
check_committed() {
    local committed=$repo/packaging/keys/orbitop-archive-keyring.asc
    [ -e "$committed" ] || return 0
    [ "$(fingerprint "$committed" || true)" = "$fpr" ] ||
        die "packaging/keys/orbitop-archive-keyring.asc is not the key ORBITOP_KEY=$fpr"
    gpg --homedir "$tmp/gnupg" --dearmor < "$committed" | cmp -s - "$tmp/key.pgp" ||
        die "packaging/keys/orbitop-archive-keyring.asc is not the current export of ORBITOP_KEY; export it again" \
            "and raise packaging/keyring.version (docs/release.md, Renewal)"
}

# check_readme: every fingerprint in README.md and README.de.md, in one piece or grouped as gpg prints it, is
# ORBITOP_KEY. A README without the fingerprint, or with the placeholder <FINGERPRINT>, stops a release; a dry run
# only warns.
check_readme() {
    local readmes=("$repo/README.md" "$repo/README.de.md") found problem=""
    found=$(grep -ohE '\b[0-9A-F]{4}( {0,2}[0-9A-F]{4}){9}\b' -- "${readmes[@]}" | tr -d ' ' | sort -u) || true
    [ -z "$found" ] || [ "$found" = "$fpr" ] ||
        die "the README names the fingerprint ${found//$'\n'/ and }, not ORBITOP_KEY=$fpr"
    [ -n "$found" ] || problem="names no fingerprint of the archive key"
    ! grep -qF '<FINGERPRINT>' -- "${readmes[@]}" || problem="still has the placeholder <FINGERPRINT>"
    [ -n "$problem" ] || return 0
    warn_or_die "the README $problem"
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
# ORBITOP_KEY, so that no test reaches the archive key, and without ORBITOP_REV, so that every test builds its own
# files.
run_tests() {
    (cd "$repo" && env -u GNUPGHOME -u ORBITOP_KEY -u ORBITOP_REV python3 -m pytest -q -W error::ResourceWarning \
        -W error::DeprecationWarning) || die "the strict test suite failed"
}

# check_head (before the tag): HEAD is still release_rev, the commit of the release files (step 3), and that is the
# pinned HEAD of step 1 or the commit of step 3 right on top of it; the working tree is still clean, apart from the
# docs/distro-check.md that a dry run writes and does not commit. A commit of another process during the run (another
# session, an agent with a shell), or a change of a script that runs from the working tree (release.sh, the build
# scripts, container-common.sh), stops the release before anything is tagged or pushed.
check_head() {
    local head parent="" status
    head=$(git -C "$repo" rev-parse --verify HEAD) || die "git rev-parse HEAD failed"
    [ "$head" = "$release_rev" ] || die "HEAD moved during the run: it is $head, the release files are of $release_rev"
    [ "$head" = "$pinned" ] || parent=$(git -C "$repo" rev-parse -q --verify "$head^") || true
    [ "$head" = "$pinned" ] || [ "$parent" = "$pinned" ] ||
        die "HEAD $head is neither the HEAD of step 1 ($pinned) nor the commit of step 3 on top of it"
    status=$(git -C "$repo" status --porcelain) || die "git status failed"
    [ -z "$status" ] || { [ -n "$dry" ] && [ "$status" = " M docs/distro-check.md" ]; } ||
        die "the working tree changed during the run (git status):"$'\n'"$status"
}
