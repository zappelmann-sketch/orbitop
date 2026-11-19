# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Steps 4 to 8 of scripts/release.sh: tag, GitHub release, gh-pages, GitHub Pages, and the wait for the new source.
# Each push names its refs; nothing is ever pushed with --all, --mirror or --force. A dry run prints the commands
# (run) instead of running them. Sourced by release.sh after checks.sh and build.sh. Provides tag_release,
# release_github, pages_tree, pages_on and wait_pages.
# shellcheck shell=bash disable=SC2154  # repo, version, dry, tmp, pages_rev, assets and APP come from the others

GH_REPO=zappelmann-sketch/orbitop
PAGES=https://zappelmann-sketch.github.io/orbitop/
WAIT=600  # seconds: GitHub Pages caches each file for about 10 minutes (docs/release.md)
# What step 8 compares with the new source: the signed index of each format, each with its signature.
SERVED=(apt/dists/stable/InRelease rpm/fedora/repodata/repomd.xml rpm/fedora/repodata/repomd.xml.asc
    rpm/opensuse/repodata/repomd.xml rpm/opensuse/repodata/repomd.xml.asc arch/x86_64/orbitop.db
    arch/x86_64/orbitop.db.sig)

# tag_release: the annotated tag v<version>; its message, the changes of the metainfo, becomes the release notes.
tag_release() {
    { echo "orbitop $version" && echo && python3 -I "$repo/packaging/changelog.py" notes \
        "$repo/data/$APP.metainfo.xml" "$version"; } > "$tmp/notes" || die "no release notes for $version"
    run git -C "$repo" tag -a --cleanup=whitespace -F "$tmp/notes" "v$version"
}

# release_github: main and the tag in one atomic push, then the release from the tag with exactly the assets.
release_github() {
    run git -C "$repo" push --atomic origin refs/heads/main:refs/heads/main "refs/tags/v$version:refs/tags/v$version"
    run gh release create "v$version" --repo "$GH_REPO" --verify-tag --title "orbitop $version" --notes-from-tag \
        "${assets[@]}"
}

# previous_by_hash TREE KEEP: the by-hash copies of the apt index that TREE (the published gh-pages) serves go to KEEP,
# so that a client with the previous InRelease still finds its index while the cache of Pages turns over.
previous_by_hash() {
    local dir=apt/dists/stable/main/binary-all file sum hash
    for file in Packages Packages.gz; do
        [ -f "$1/$dir/$file" ] || continue
        for sum in SHA256 SHA512; do
            hash=$("${sum,,}sum" < "$1/$dir/$file")
            hash=$dir/by-hash/$sum/${hash%% *}
            [ ! -f "$1/$hash" ] || install -D -m 644 -- "$1/$hash" "$2/$hash"
        done
    done
}

# pages_tree: gh-pages, an orphan branch, in a worktree of its own below $tmp: the content replaced by the new
# source plus the by-hash files of the previous one, one commit, and a push of this ref alone.
pages_tree() {
    local tree=$tmp/pages
    if [ -n "$dry" ]; then
        echo "dry run, would replace the content of gh-pages ${pages_rev:+($pages_rev) }with the new source in a" \
            "worktree, keep the apt by-hash files of the previous source and commit"
        run git -C "$repo" push origin refs/heads/gh-pages:refs/heads/gh-pages
        return
    fi
    if [ -n "$pages_rev" ]; then
        git -C "$repo" worktree add -q -B gh-pages "$tree" "$pages_rev"
        previous_by_hash "$tree" "$tmp/keep"
        git -C "$tree" rm -rqf -- .
    else
        git -C "$repo" worktree add -q --orphan -b gh-pages "$tree"
    fi
    cp -a -- "$tmp/site/." "$tree/"
    [ ! -d "$tmp/keep" ] || cp -r -- "$tmp/keep/." "$tree/"  # the names are hashes: an equal name is an equal file
    git -C "$tree" add --all -- .  # the worktree holds the source and nothing else
    git -C "$tree" commit -q -m "chore: Paketquelle für orbitop $version"
    git -C "$repo" push origin refs/heads/gh-pages:refs/heads/gh-pages
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
            die "after $WAIT s, GitHub Pages still serves an older$stale; check again later (docs/release.md, Release)"
        sleep 20
    done
}
