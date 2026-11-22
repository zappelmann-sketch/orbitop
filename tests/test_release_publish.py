# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/release.sh, die Veröffentlichung mit Stellvertretern (tests/release_stub.py): Pushes mit genannten Refs,
ohne Signatur- und Tag-Folge-Überraschungen, die Anhänge des Releases, der Entwurf, der erst nach Pages
veröffentlicht wird, die Identität im Worktree von gh-pages, ein liegengebliebener Zweig gh-pages und der
Stellvertreter für gh."""
import os
import subprocess
import tarfile

import pytest

from tests.release_stub import GH, KV, NAME, NOREPLY, REAL, VERSION, environ, git, make_repo, run, sha256, stub
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
    tags = [c for c in calls["git"] if "tag" in c and "-s" in c]  # Format, Programm und Schlüssel nie aus der Konfig
    assert len(tags) == 1 and {"gpg.format=ssh", "gpg.ssh.program=ssh-keygen",
                               f"user.signingKey={tmp_path / 'tag-key'}"} <= set(tags[0])
    verify = [i for i, c in enumerate(calls["git"]) if "tag" in c and "-v" in c]
    assert len(verify) == 1 and verify[0] < next(i for i, c in enumerate(calls["git"]) if "push" in c)
    commits = [c for c in calls["git"] if "commit" in c]
    assert len(commits) == 2 and all("--no-gpg-sign" in c for c in commits)
    remote = repo["remote"]
    head = git(repo["repo"], "rev-parse", "HEAD").strip()
    assert git(remote, "rev-parse", "main").strip() == head
    assert git(remote, "cat-file", "-t", f"v{VERSION}").strip() == "tag"  # annotiert
    assert git(remote, "rev-parse", f"v{VERSION}^{{commit}}").strip() == head
    signers = repo["repo"] / ".github" / "allowed_signers"  # so prüft jeder mit dem Repository den Tag
    v = subprocess.run([REAL["git"], "-c", f"gpg.ssh.allowedSignersFile={signers}", "tag", "-v", f"v{VERSION}"],
                       cwd=remote, capture_output=True, text=True, env=environ())
    assert v.returncode == 0 and f'Good "git" signature for {NOREPLY}' in v.stderr, v.stderr
    subject = git(repo["repo"], "log", "-1", "--format=%s").strip()
    assert subject == f"docs: Distributionsprüfung für orbitop {VERSION}"
    assert git(repo["repo"], "show", "--name-only", "--format=", "HEAD").split() == ["docs/distro-check.md"]
    assert git(repo["repo"], "status", "--porcelain") == ""


def test_release_assets_list(tmp_path, keys, repo):
    r, calls = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    (create,) = [c for c in calls["gh"] if c[:2] == ["release", "create"]]
    i = create.index("--notes-file")  # gh 2.104 lehnt --notes-from-tag mit --repo ab
    files = create[i + 2:]
    assert create[:i + 1] == ["release", "create", f"v{VERSION}", "--repo", "zappelmann-sketch/orbitop",
                              "--verify-tag", "--draft", "--title", f"orbitop {VERSION}", "--notes-file"]
    tag_message = git(repo["remote"], "tag", "-l", "--format=%(contents:subject)%0a%0a%(contents:body)", f"v{VERSION}")
    assert (tmp_path / "notes").read_text().strip() == tag_message.strip() != ""
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


def test_pages_commit_ignores_the_excludes_of_git(tmp_path, keys, repo):
    """Ein globales core.excludesFile mit *.deb und *.rpm darf keine Datei der Quelle aus dem Commit lassen."""
    excludes = tmp_path / "excludes"
    excludes.write_text("*.deb\n*.rpm\n*.zst\n")
    git(repo["repo"], "config", "core.excludesFile", str(excludes))
    r, _ = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    names = git(repo["remote"], "ls-tree", "-r", "--name-only", "gh-pages").split()
    assert f"apt/pool/main/o/orbitop/orbitop_{VERSION}-1_all.deb" in names
    assert f"rpm/fedora/orbitop-release-{KV}-1.noarch.rpm" in names
    assert f"arch/x86_64/orbitop-{VERSION}-1-any.pkg.tar.zst" in names


def identity_only_on_main(tmp_path, repo):
    """includeIf onbranch:main gibt nur main die Identität des Projekts, sonst gilt die globale (etwa eine private);
    gibt die Umgebung dafür zurück."""
    project = tmp_path / "project.gitconfig"
    project.write_text(f"[user]\n\tname = {NAME}\n\temail = {NOREPLY}\n")
    config = tmp_path / "global.gitconfig"
    config.write_text(f'[user]\n\tname = Alice\n\temail = alice@example.com\n[includeIf "onbranch:main"]\n'
                      f"\tpath = {project}\n")
    for key in ("user.name", "user.email"):
        git(repo["repo"], "config", "--unset", key)
    return {"GIT_CONFIG_GLOBAL": str(config)}


def test_refuses_an_identity_that_only_the_gh_pages_worktree_gets(tmp_path, keys, repo):
    """Re-Review: Der Worktree auf gh-pages bekäme die globale Identität. Der Lauf hält an, bevor etwas
    veröffentlicht ist."""
    r, calls = run(tmp_path, repo, keys, VERSION, env=identity_only_on_main(tmp_path, repo))
    assert r.returncode == 1 and "GIT_AUTHOR_IDENT must be exactly zappelmann-sketch <" in r.stderr, r.stderr
    assert "/pages (git config" in r.stderr  # im Worktree, nicht im Repository
    assert not [c for c in calls["git"] if "push" in c or "tag" in c]
    assert not [c for c in calls["gh"] if c[0] == "release"]
    assert "gh-pages" not in git(repo["remote"], "branch")


@pytest.mark.parametrize("local", [False, True], ids=["first", "local-gh-pages"])
def test_dry_run_checks_the_pages_identity(tmp_path, keys, repo, local):
    """Plan 2026-11-19, Task 9: Der Trockenlauf prüft die Identität im Worktree von gh-pages wie der echte Lauf und
    ändert dabei keinen Zweig, auch keinen lokalen gh-pages, den ein früherer Lauf ließ."""
    if local:
        git(repo["repo"], "branch", "gh-pages")
    refs = git(repo["repo"], "for-each-ref")
    r, calls = run(tmp_path, repo, keys, VERSION, "--dry-run", env=identity_only_on_main(tmp_path, repo))
    assert r.returncode == 1 and "GIT_AUTHOR_IDENT must be exactly zappelmann-sketch <" in r.stderr, r.stderr
    assert "/pages (git config" in r.stderr
    assert not calls["gh"] and not [c for c in calls["git"] if "push" in c]
    assert git(repo["repo"], "for-each-ref") == refs
    assert git(repo["repo"], "worktree", "list").count("\n") == 1


def test_first_release_replaces_a_leftover_local_gh_pages(tmp_path, keys, repo):
    """D: ein abgebrochener erster Release ließ den Zweig gh-pages zurück; origin hat keinen."""
    git(repo["repo"], "branch", "gh-pages")
    r, _ = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    remote = repo["remote"]
    assert git(remote, "rev-list", "--count", "gh-pages").strip() == "1"  # verwaist, ohne den alten Zweig
    assert "orbitop/__init__.py" not in git(remote, "ls-tree", "-r", "--name-only", "gh-pages")


TRUE = ["1", "t", "T", "TRUE", "True"]  # die übrigen wahren Werte von pflag (strconv.ParseBool) neben "true"


@pytest.mark.parametrize("args", [["--repo", "o/r", "--notes-from-tag"], ["--notes-from-tag", "--repo", "o/r"],
                                  ["--notes-from-tag", "-R", "o/r"], ["--notes-from-tag=true", "--repo", "o/r"],
                                  *[[f"--notes-from-tag={v}", "-R", "o/r"] for v in TRUE]],
                         ids=["repo-first", "repo-after", "short", "equals", *[f"equals-{v}" for v in TRUE]])
def test_gh_stub_refuses_notes_from_tag_with_repo(tmp_path, args):
    """Plan 2026-11-19, Task 9: Der Stellvertreter lehnt wie gh 2.104 --notes-from-tag mit --repo oder -R ab, in
    jeder Reihenfolge und mit jedem wahren Wert; --notes-file mit --repo nicht (dort scheitert nur der fehlende
    Tag)."""
    stub(tmp_path, "gh", GH)
    git(tmp_path, "init", "-q", "--bare", str(tmp_path / "remote.git"))
    env = {**os.environ, "LOG_DIR": str(tmp_path), "REAL_GIT": REAL["git"], "REMOTE": str(tmp_path / "remote.git")}
    text = "using `--notes-from-tag` with `--repo` is not supported"
    for notes, refused in ((args, True), ([a for a in args if "notes" not in a] + ["--notes-file", "n"], False)):
        r = subprocess.run([str(tmp_path / "gh"), "release", "create", "v1", "--verify-tag", *notes],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 1 and (text in r.stderr) == refused, (notes, r.stderr)


def test_source_archive_ignores_replace_refs_and_attribute_files(tmp_path, keys, repo):
    """Audit M3 (Plan 2026-11-19, Task 9): Das Quellarchiv des Release (make_assets) enthält README.md, wie der
    Commit sie hat, auch mit einem Ersatz für ihren Blob (refs/replace) und export-ignore in core.attributesFile;
    gzip packt es, auch wenn tar.tar.gz.command der git-Konfiguration einen anderen Befehl nennt, und tar.umask 0
    macht keinen Eintrag für alle schreibbar (Audit M2): nur 0644 und 0755."""
    readme = (repo["repo"] / "README.md").read_bytes()
    planted = subprocess.run(["git", "-C", str(repo["repo"]), "hash-object", "-w", "--stdin"], input=b"planted\n",
                             capture_output=True, check=True).stdout.decode().strip()
    git(repo["repo"], "replace", git(repo["repo"], "rev-parse", "HEAD:README.md").strip(), planted)
    (tmp_path / "attributes").write_text("README.md export-ignore\n")
    git(repo["repo"], "config", "core.attributesFile", str(tmp_path / "attributes"))
    git(repo["repo"], "config", "tar.tar.gz.command", "cat > /dev/null; echo planted")
    git(repo["repo"], "config", "tar.umask", "0")
    r, _ = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    with tarfile.open(tmp_path / "assets" / f"orbitop-{VERSION}.tar.gz", "r:gz") as tar:
        assert tar.extractfile(f"orbitop-{VERSION}/README.md").read() == readme
        modes = {m.name: oct(m.mode) for m in tar.getmembers() if not m.issym()}  # Linux ignoriert die eines Symlinks
    assert modes and set(modes.values()) <= {"0o644", "0o755"}, modes
