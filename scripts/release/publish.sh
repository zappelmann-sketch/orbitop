# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Steps 4 to 8 of scripts/release.sh: tag, GitHub release as a draft, gh-pages, GitHub Pages, the wait for the new
# source, then the release published. Each push names its refs; nothing is pushed with --all, --mirror, --force or
# following tags. A dry run prints the commands (run) instead of running them. Sourced by release.sh after checks.sh
# and build.sh. Provides tag_release, release_github, pages_worktree, pages_tree, pages_on, wait_pages and
# publish_release.
# shellcheck shell=bash disable=SC2154  # repo, version, dry, tmp, pages_rev, release_rev, assets, APP, GH_REPO

PAGES=https://zappelmann-sketch.github.io/orbitop/
WAIT=600  # seconds: GitHub Pages caches each file for about 10 minutes (docs/release.md)
# What step 8 compares with the new source: the signed index of each format, each with its signature.
SERVED=(apt/dists/stable/InRelease rpm/fedora/repodata/repomd.xml rpm/fedora/repodata/repomd.xml.asc
    rpm/opensuse/repodata/repomd.xml rpm/opensuse/repodata/repomd.xml.asc arch/x86_64/orbitop.db
    arch/x86_64/orbitop.db.sig)

# tag_release: the annotated, unsigned tag v<version> of release_rev, the commit of the release files, once
# check_head found HEAD unmoved; its message, the changes of the metainfo, becomes the release notes.
tag_release() {
    check_head
    { echo "orbitop $version" && echo && python3 -I "$repo/packaging/changelog.py" notes \
        "$repo/data/$APP.metainfo.xml" "$version"; } > "$tmp/notes" || die "no release notes for $version"
    run git -C "$repo" tag -a --no-sign --cleanup=whitespace -F "$tmp/notes" "v$version" "$release_rev"
}

# release_github: main and the tag in one atomic push, then a draft release from the tag with exactly the assets; it
# is published once Pages serves the new source (publish_release).
release_github() {
    run git -C "$repo" push --atomic --no-follow-tags origin refs/heads/main:refs/heads/main \
        "refs/tags/v$version:refs/tags/v$version"
    # The notes are the tag message ($tmp/notes of tag_release); gh 2.104 refuses --notes-from-tag with --repo.
    run gh release create "v$version" --repo "$GH_REPO" --verify-tag --draft --title "orbitop $version" \
        --notes-file "$tmp/notes" "${assets[@]}"
}

# previous_by_hash KEEP: the by-hash copies of the apt index that the published gh-pages serves go to KEEP, so that a
# client with the previous InRelease still finds its index while the cache of Pages turns over. They come from git
# objects, never from a checkout (a symlink planted there could lead anywhere): only a file whose name is a hash that
# the previous InRelease, verified with ORBITOP_KEY, lists for Packages or Packages.gz, and whose content has it.
previous_by_hash() {
    local dir=apt/dists/stable/main/binary-all sum hash path
    if ! signed_release; then
        echo "warning: the published InRelease does not verify; no by-hash file is kept" >&2
        return
    fi
    for sum in SHA256 SHA512; do
        while read -r hash; do
            path=$dir/by-hash/$sum/$hash
            blob "$path" "$1/$path" || continue
            [ "$("${sum,,}sum" < "$1/$path" | cut -d' ' -f1)" = "$hash" ] || rm -f -- "$1/$path"
        done < <(awk -v s="$sum:" '/^[^ ]/ { on = ($1 == s) }
            on && NF == 3 && $1 ~ /^[0-9a-f]+$/ && $3 ~ /^main\/binary-all\/Packages(\.gz)?$/ { print $1 }' \
            "$tmp/published/Release")
    done
}

# pages_worktree (a release only): gh-pages, an orphan branch, in a worktree of its own at $tmp/pages, never checked
# out: the published branch, or a new one on the first release. It is made before anything is published, so that
# check_ident sees the identity git gives this worktree before step 4.
pages_worktree() {
    [ -z "$dry" ] || return 0
    if [ -n "$pages_rev" ]; then
        git -C "$repo" worktree add -q --no-checkout -B gh-pages "$tmp/pages" "$pages_rev"
    else
        if git -C "$repo" rev-parse -q --verify refs/heads/gh-pages > /dev/null; then
            git -C "$repo" branch -q -D gh-pages  # left by a failed first release; origin has none
        fi
        git -C "$repo" worktree add -q --orphan -b gh-pages "$tmp/pages"
    fi
    check_ident "$tmp/pages"
}

# pages_tree: the tree of the gh-pages worktree becomes the new source plus the verified by-hash files of the previous
# one, in one commit with IDENT (checked again right before it), and a push of this ref alone.
pages_tree() {
    local tree=$tmp/pages
    if [ -n "$dry" ]; then
        echo "dry run, would replace the content of gh-pages ${pages_rev:+($pages_rev) }with the new source in a" \
            "worktree, keep the verified apt by-hash files of the previous source and commit"
        run git -C "$repo" push --no-follow-tags origin refs/heads/gh-pages:refs/heads/gh-pages
        return
    fi
    [ -z "$pages_rev" ] || previous_by_hash "$tmp/keep"
    cp -a -- "$tmp/site/." "$tree/"
    [ ! -d "$tmp/keep" ] || cp -r -- "$tmp/keep/." "$tree/"  # the names are hashes: an equal name is an equal file
    git -C "$tree" add --all --force -- .  # the worktree holds the source alone; no excludes (*.deb) drop a file
    check_ident "$tree"
    git -C "$tree" commit -q --no-gpg-sign -m "chore: Paketquelle für orbitop $version"
    git -C "$repo" push --no-follow-tags origin refs/heads/gh-pages:refs/heads/gh-pages
}

# pages_on: GitHub Pages serves gh-pages at /; the first release turns it on (gh api answers 404 until then).
pages_on() {
    local source on=(gh api -X POST "repos/$GH_REPO/pages" -f 'source[branch]=gh-pages' -f 'source[path]=/')
    if [ -n "$dry" ]; then
        echo "dry run, would ask gh api repos/$GH_REPO/pages and, on HTTP 404 (the first release):"
        run "${on[@]}"
    elif source=$(gh api "repos/$GH_REPO/pages" --jq '.source.branch + " " + .source.path' 2> "$tmp/pages.err"); then
        [ "$source" = "gh-pages /" ] || die "GitHub Pages serves $source, not gh-pages /"
    elif grep -qF 'HTTP 404' "$tmp/pages.err"; then
        "${on[@]}" > /dev/null
    else
        die "gh api repos/$GH_REPO/pages: $(cat "$tmp/pages.err")"
    fi
}

# wait_pages: at most WAIT seconds until Pages serves each file of SERVED byte for byte as in the new source.
wait_pages() {
    local deadline=$((SECONDS + WAIT)) path stale
    if [ -n "$dry" ]; then
        echo "dry run, would wait up to $WAIT s until $PAGES serves the new ${SERVED[*]}"
        return
    fi
    while :; do
        stale=""
        for path in "${SERVED[@]}"; do
            curl -fsSL --proto =https --max-time 60 -o "$tmp/served" "$PAGES$path" &&
                cmp -s -- "$tmp/served" "$tmp/site/$path" || stale+=" $path"
        done
        [ -n "$stale" ] || { echo "GitHub Pages serves the new source" && return; }
        [ "$SECONDS" -lt "$deadline" ] ||
            die "after $WAIT s, GitHub Pages still serves an older$stale; the release stays a draft (docs/release.md)"
        sleep 20
    done
}

# publish_release: the draft becomes the latest release only now that Pages serves the new source, so that the
# downloads of the README (releases/latest) and the source agree.
publish_release() {
    run gh release edit "v$version" --repo "$GH_REPO" --draft=false
}
