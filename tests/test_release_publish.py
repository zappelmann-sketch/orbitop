# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/release.sh, die Veröffentlichung mit Stellvertretern (tests/release_stub.py): Pushes mit genannten Refs,
ohne Signatur- und Tag-Folge-Überraschungen, die Anhänge des Releases, der Entwurf, der erst nach Pages
veröffentlicht wird, und ein liegengebliebener Zweig gh-pages."""
import subprocess
import tarfile

import pytest

from tests.release_stub import KV, VERSION, git, make_repo, run, sha256
from tests.site_stub import kill_agent, make_keys, needs_git

pytestmark = needs_git
ASSETS = sorted([f"orbitop-{VERSION}.tar.gz", f"orbitop_{VERSION}-1_all.deb",
                 f"orbitop-{VERSION}-1.fedora.noarch.rpm", f"orbitop-{VERSION}-1.opensuse.noarch.rpm",
                 f"orbitop-{VERSION}-1-any.pkg.tar.zst", "orbitop-apt-source.deb", "orbitop-release-fedora.rpm",
                 "orbitop-release-opensuse.rpm"])
REFS = {"refs/heads/main:refs/heads/main", f"refs/tags/v{VERSION}:refs/tags/v{VERSION}",
        "refs/heads/gh-pages:refs/heads/gh-pages"}


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    k = make_keys(tmp_path_factory.mktemp("publish-keys") / "gnupg")
    yield k
    kill_agent(k["home"])


@pytest.fixture
def repo(tmp_path, keys):
    return make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])


def blob(remote, path):
    return subprocess.run(["git", "--git-dir", str(remote), "cat-file", "blob", f"gh-pages:{path}"],
                          capture_output=True, check=True).stdout


def test_push_names_refs_explicitly(tmp_path, keys, repo):
    r, calls = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    done = [c[c.index("push") + 1:] for c in calls["git"] if "push" in c]
    assert len(done) == 2, done
    for args in done:
        assert "--no-follow-tags" in args  # push.followTags schiebt sonst jeden annotierten Tag mit
        assert args[args.index("origin") + 1:] and set(args[args.index("origin") + 1:]) <= REFS, args
        assert not {"--all", "--mirror", "--force", "-f", "--tags", "--follow-tags"} & set(args)
        assert not any(a.startswith(("+", "--force")) for a in args)
    tags = [c for c in calls["git"] if "tag" in c and "-a" in c]
    assert len(tags) == 1 and "--no-sign" in tags[0]  # tag.gpgSign signierte sonst mit einem anderen Schlüssel
    commits = [c for c in calls["git"] if "commit" in c]
    assert len(commits) == 2 and all("--no-gpg-sign" in c for c in commits)
    remote = repo["remote"]
    head = git(repo["repo"], "rev-parse", "HEAD").strip()
    assert git(remote, "rev-parse", "main").strip() == head
    assert git(remote, "cat-file", "-t", f"v{VERSION}").strip() == "tag"  # annotiert
    assert git(remote, "rev-parse", f"v{VERSION}^{{commit}}").strip() == head
    subject = git(repo["repo"], "log", "-1", "--format=%s").strip()
    assert subject == f"docs: Distributionsprüfung für orbitop {VERSION}"
    assert git(repo["repo"], "show", "--name-only", "--format=", "HEAD").split() == ["docs/distro-check.md"]
    assert git(repo["repo"], "status", "--porcelain") == ""


def test_release_assets_list(tmp_path, keys, repo):
    r, calls = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    (create,) = [c for c in calls["gh"] if c[:2] == ["release", "create"]]
    files = [a for a in create if a.startswith("/")]
    assert create[:len(create) - len(files)] == ["release", "create", f"v{VERSION}", "--repo",
                                                 "zappelmann-sketch/orbitop", "--verify-tag", "--draft", "--title",
                                                 f"orbitop {VERSION}", "--notes-from-tag"]
    assert sorted(f.rsplit("/", 1)[1] for f in files) == sorted([*ASSETS, "SHA256SUMS", "SHA256SUMS.asc"])
    assets = tmp_path / "assets"
    sums = (assets / "SHA256SUMS").read_text().splitlines()
    assert sorted(ln.split("  ")[1] for ln in sums) == ASSETS
    assert all(sha256((assets / n).read_bytes()) == h for h, n in (ln.split("  ") for ln in sums))
    keyring = tmp_path / "keyring.pgp"  # wie die README: gpgv mit dem Schlüsselbund der Paketquelle
    keyring.write_bytes(blob(repo["remote"], "orbitop-archive-keyring.pgp"))
    v = subprocess.run(["gpgv", "--keyring", str(keyring), "SHA256SUMS.asc", "SHA256SUMS"], cwd=assets,
                       capture_output=True, text=True)
    assert v.returncode == 0 and f"using EDDSA key {keys['fpr']}" in v.stderr, v.stderr
    # die RPMs der Paketquelle (signiert), nicht die aus build-packages.sh
    served = blob(repo["remote"], f"rpm/fedora/orbitop-release-{KV}-1.noarch.rpm")
    assert (assets / "orbitop-release-fedora.rpm").read_bytes() == served
    with tarfile.open(assets / f"orbitop-{VERSION}.tar.gz") as tar:  # git archive des getaggten Commits
        names = {m.name for m in tar.getmembers() if m.isfile()}
        doc = tar.extractfile(f"orbitop-{VERSION}/docs/distro-check.md").read().decode()
    tagged = git(repo["remote"], "ls-tree", "-r", "--name-only", f"v{VERSION}").split()
    assert names == {f"orbitop-{VERSION}/{n}" for n in tagged}  # genau der Baum des Tags
    assert "debian@sha256:" + "1" * 64 in doc  # mit dem Ergebnis der Matrix
    assert git(repo["remote"], "cat-file", "-p", f"v{VERSION}").count(f"orbitop {VERSION}") >= 1


def test_draft_is_published_only_after_pages_serve_the_source(tmp_path, keys, repo):
    r, calls = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    assert calls["gh"][-1] == ["release", "edit", f"v{VERSION}", "--repo", "zappelmann-sketch/orbitop",
                               "--draft=false"]
    order = calls["order"]
    assert order.index("gh release create") < order.index("curl")
    assert max(i for i, step in enumerate(order) if step == "curl") < order.index("gh release edit")


def test_first_release_replaces_a_leftover_local_gh_pages(tmp_path, keys, repo):
    """D: ein abgebrochener erster Release ließ den Zweig gh-pages zurück; origin hat keinen."""
    git(repo["repo"], "branch", "gh-pages")
    r, _ = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    remote = repo["remote"]
    assert git(remote, "rev-list", "--count", "gh-pages").strip() == "1"  # verwaist, ohne den alten Zweig
    assert "orbitop/__init__.py" not in git(remote, "ls-tree", "-r", "--name-only", "gh-pages")
