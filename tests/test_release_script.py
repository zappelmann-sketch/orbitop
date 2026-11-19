# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/release.sh mit Stellvertretern (tests/release_stub.py): die Vorprüfung vor jedem Bau, der Trockenlauf
ohne gh und Push, die Pushes mit genannten Refs und die Anhänge des Releases. gh-pages, die Wiederverwendung
veröffentlichter Quellpakete und docs/distro-check.md: tests/test_release_pages.py."""
import re
import subprocess
import tarfile

import pytest

from tests.packaging_common import ROOT
from tests.release_stub import KV, VERSION, git, make_repo, run, sha256
from tests.site_stub import gpg, kill_agent, make_keys, needs_git

pytestmark = needs_git
ASSETS = sorted([f"orbitop-{VERSION}.tar.gz", f"orbitop_{VERSION}-1_all.deb", f"orbitop-{VERSION}-1.fedora.noarch.rpm",
                 f"orbitop-{VERSION}-1.opensuse.noarch.rpm", f"orbitop-{VERSION}-1-any.pkg.tar.zst",
                 "orbitop-apt-source.deb", "orbitop-release-fedora.rpm", "orbitop-release-opensuse.rpm"])
REFS = {"refs/heads/main:refs/heads/main", f"refs/tags/v{VERSION}:refs/tags/v{VERSION}",
        "refs/heads/gh-pages:refs/heads/gh-pages"}


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    """Zwei Wegwerfschlüssel (1 Jahr), dazu eine gpg.conf, die release.sh nie lesen darf (--no-options)."""
    k = make_keys(tmp_path_factory.mktemp("release-keys") / "gnupg",
                  uids=("Test Signing <test@example.com>", "Test Signing Two <test@example.com>"))
    yield k
    kill_agent(k["home"])


def one_key(tmp_path, expiry, *faked):
    home = tmp_path / "gnupg"
    home.mkdir(mode=0o700)
    gpg(home, *faked, "--passphrase", "", "--quick-gen-key", "Test Signing <test@example.com>", "ed25519", "sign",
        expiry)
    fpr = next(ln.split(":")[9] for ln in gpg(home, "--with-colons", "--list-keys").decode().splitlines()
               if ln.startswith("fpr:"))
    return {"home": home, "fpr": fpr}


@pytest.fixture
def repo(tmp_path, keys):
    """Ein Release-Stand: der README-Platzhalter durch den Fingerabdruck ersetzt (Task 9)."""
    return make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])


def pushes(calls):
    return [c[c.index("push") + 1:] for c in calls["git"] if "push" in c]


def refused_before_building(r, calls, text):
    assert r.returncode == 1 and text in r.stderr, r.stderr
    assert not calls["calls"] and not calls["gh"] and not pushes(calls)


@pytest.mark.parametrize("change", ["modified", "untracked"])
def test_refuses_dirty_tree(tmp_path, keys, repo, change):
    if change == "modified":
        (repo["repo"] / "README.md").write_text("changed\n")
    else:
        (repo["repo"] / "notes.txt").write_text("new\n")
    r, calls = run(tmp_path, repo, keys, VERSION, "--dry-run")
    refused_before_building(r, calls, "not clean")


def test_refuses_version_mismatch(tmp_path, keys, repo):
    r, calls = run(tmp_path, repo, keys, "9.9.9", "--dry-run")
    refused_before_building(r, calls, f"has the version {VERSION}, not 9.9.9")


@pytest.mark.parametrize("case,text", [
    ("branch", "only from the branch main"), ("tag", "exists already"), ("remote-tag", "exists on origin"),
    ("changelog", "newest <release>"), ("readme-other", "README names the fingerprint"),
    ("readme-placeholder", "placeholder <FINGERPRINT>"), ("bad-fpr", "40 hex digits"), ("no-secret", "no secret key"),
])
def test_refuses_before_building(tmp_path, keys, case, text):
    repo = make_repo(tmp_path, keys["fpr"], readme=None if case == "readme-placeholder" else
                     keys["fprs"][1] if case == "readme-other" else keys["fpr"])
    env = {"ORBITOP_KEY": {"bad-fpr": keys["fpr"][:39], "no-secret": "0" * 40}.get(case, keys["fpr"])}
    version = VERSION
    if case == "branch":
        git(repo["repo"], "checkout", "-q", "-b", "other")
    elif case in ("tag", "remote-tag"):
        git(repo["repo"], "tag", f"v{VERSION}")
        if case == "remote-tag":
            git(repo["repo"], "push", "-q", "origin", f"refs/tags/v{VERSION}")
            git(repo["repo"], "tag", "-d", f"v{VERSION}")
    elif case == "changelog":  # __version__ neuer als der oberste <release> der metainfo
        version = "9.9.9"
        init = repo["repo"] / "orbitop" / "__init__.py"
        init.write_text(init.read_text().replace(f'"{VERSION}"', '"9.9.9"'))
        git(repo["repo"], "commit", "-qam", "version")
    r, calls = run(tmp_path, repo, keys, version, *([] if case == "readme-placeholder" else ["--dry-run"]), env=env)
    refused_before_building(r, calls, text)


@pytest.mark.parametrize("args", [[], ["--dry-run"], [VERSION, "--force"], [f"v{VERSION}"], [VERSION, "--dry-run", "x"]])
def test_usage(tmp_path, keys, repo, args):
    r, calls = run(tmp_path, repo, keys, *args)
    assert r.returncode == 2 and "usage:" in r.stderr and not calls["calls"]


def test_refuses_expired_key(tmp_path):
    key = one_key(tmp_path, "1d", "--faked-system-time", "20200101T000000!")
    try:
        r, calls = run(tmp_path, make_repo(tmp_path, key["fpr"], readme=key["fpr"]), key, VERSION, "--dry-run")
    finally:
        kill_agent(key["home"])
    refused_before_building(r, calls, "expired on 2020-01-02")


def test_warns_key_under_180_days(tmp_path):
    key = one_key(tmp_path, "100d")
    try:
        r, calls = run(tmp_path, make_repo(tmp_path, key["fpr"], readme=key["fpr"]), key, VERSION, "--dry-run")
    finally:
        kill_agent(key["home"])
    assert re.search(r"warning: ORBITOP_KEY expires in (99|100) days", r.stderr), r.stderr
    assert r.returncode == 0 and calls["calls"], r.stderr  # nur eine Warnung: der Lauf baut weiter


def commit_key(repo, data):
    (repo["repo"] / "packaging" / "keys").mkdir()
    (repo["repo"] / "packaging" / "keys" / "orbitop-archive-keyring.asc").write_bytes(data)
    git(repo["repo"], "add", "packaging/keys")
    git(repo["repo"], "commit", "-qm", "key")


def test_refuses_key_not_matching_committed_file(tmp_path, keys, repo):
    commit_key(repo, gpg(keys["home"], "--armor", "--export", keys["fprs"][1]))
    r, calls = run(tmp_path, repo, keys, VERSION, "--dry-run")
    refused_before_building(r, calls, "packaging/keys/orbitop-archive-keyring.asc is not the key")


def test_dry_run_never_calls_gh_or_push(tmp_path, keys):
    repo = make_repo(tmp_path, keys["fpr"], readme=None)  # bis Task 9: nur eine Warnung im Trockenlauf
    commit_key(repo, gpg(keys["home"], "--armor", "--export", keys["fpr"]))  # der passende Schlüssel stört nicht
    r, calls = run(tmp_path, repo, keys, VERSION, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "warning: the README still has the placeholder <FINGERPRINT>" in r.stderr
    assert not calls["gh"] and not pushes(calls) and not calls["curl"]
    assert [c[0] for c in calls["calls"]] == ["build-packages", "build-site", "build-packages", "build-site",
                                              "check-distros"]
    assert f"dry run, would run: gh release create v{VERSION}" in r.stdout
    assert "push --atomic origin refs/heads/main:refs/heads/main" in r.stdout and "gh api -X POST" in r.stdout
    status = git(repo["repo"], "status", "--porcelain")
    assert status == " M docs/distro-check.md\n"  # geschrieben, nicht committet
    assert git(repo["repo"], "tag") == "" and git(repo["repo"], "worktree", "list").count("\n") == 1
    assert not list((tmp_path / "tmp").iterdir())  # kein Arbeitsordner bleibt


def test_build_gets_the_exported_public_key(tmp_path, keys, repo):
    r, calls = run(tmp_path, repo, keys, VERSION, "--dry-run")
    assert r.returncode == 0, r.stderr
    builds = [c for c in calls["calls"] if c[0] == "build-packages"]
    assert [c[-2:] for c in builds][1] == ["--suffix", "check1"]
    exported = gpg(keys["home"], "--no-options", "--armor", "--export", "--export-options", "export-minimal",
                   keys["fpr"])
    assert (tmp_path / "pubkey.asc").read_bytes() == exported  # nicht die armor-Option der gpg.conf
    assert all(c[c.index("--packages") + 1].endswith(("/pkgs", "/pkgs2")) for c in calls["calls"]
               if c[0] == "build-site")


def test_push_names_refs_explicitly(tmp_path, keys, repo):
    r, calls = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    done = pushes(calls)
    assert len(done) == 2, done
    for args in done:
        assert args[args.index("origin") + 1:] and set(args[args.index("origin") + 1:]) <= REFS, args
        assert not {"--all", "--mirror", "--force", "-f", "--tags"} & set(args)
        assert not any(a.startswith(("+", "--force")) for a in args)
    remote = repo["remote"]
    head = git(repo["repo"], "rev-parse", "HEAD").strip()
    assert git(remote, "rev-parse", "main").strip() == head
    assert git(remote, "cat-file", "-t", f"v{VERSION}").strip() == "tag"  # annotiert
    assert git(remote, "rev-parse", f"v{VERSION}^{{commit}}").strip() == head
    assert git(repo["repo"], "log", "-1", "--format=%s").strip() == f"docs: Distributionsprüfung für orbitop {VERSION}"
    assert git(repo["repo"], "show", "--name-only", "--format=", "HEAD").split() == ["docs/distro-check.md"]
    assert git(repo["repo"], "status", "--porcelain") == ""


def test_release_assets_list(tmp_path, keys, repo):
    r, calls = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    (create,) = [c for c in calls["gh"] if c[:2] == ["release", "create"]]
    files = [a for a in create if a.startswith("/")]
    assert create[:len(create) - len(files)] == ["release", "create", f"v{VERSION}", "--repo",
                                                 "zappelmann-sketch/orbitop", "--verify-tag", "--title",
                                                 f"orbitop {VERSION}", "--notes-from-tag"]
    assert sorted(f.rsplit("/", 1)[1] for f in files) == sorted([*ASSETS, "SHA256SUMS", "SHA256SUMS.asc"])
    assets = tmp_path / "assets"
    sums = (assets / "SHA256SUMS").read_text().splitlines()
    assert sorted(ln.split("  ")[1] for ln in sums) == ASSETS
    assert all(sha256((assets / n).read_bytes()) == h for h, n in (ln.split("  ") for ln in sums))
    # wie die README: gpgv mit dem Schlüsselbund der Paketquelle
    keyring = tmp_path / "keyring.pgp"
    keyring.write_bytes(subprocess.run(["git", "--git-dir", str(repo["remote"]), "cat-file", "blob",
                                        "gh-pages:orbitop-archive-keyring.pgp"], capture_output=True, check=True).stdout)
    v = subprocess.run(["gpgv", "--keyring", str(keyring), "SHA256SUMS.asc", "SHA256SUMS"], cwd=assets,
                       capture_output=True, text=True)
    assert v.returncode == 0 and f"using EDDSA key {keys['fpr']}" in v.stderr, v.stderr
    # die RPMs der Paketquelle (signiert), nicht die aus build-packages.sh
    served = subprocess.run(["git", "--git-dir", str(repo["remote"]), "cat-file", "blob",
                             f"gh-pages:rpm/fedora/orbitop-release-{KV}-1.noarch.rpm"], capture_output=True).stdout
    assert (assets / "orbitop-release-fedora.rpm").read_bytes() == served
    with tarfile.open(assets / f"orbitop-{VERSION}.tar.gz") as tar:  # git archive des Tags, mit dem Matrix-Ergebnis
        doc = tar.extractfile(f"orbitop-{VERSION}/docs/distro-check.md").read().decode()
    assert "debian@sha256:" + "1" * 64 in doc and f"orbitop-{VERSION}/CLAUDE.md" not in doc
    assert git(repo["remote"], "cat-file", "-p", f"v{VERSION}").count(f"orbitop {VERSION}") >= 1


def test_shellcheck_clean():
    scripts = [ROOT / "scripts" / "release.sh", *sorted((ROOT / "scripts" / "release").glob("*.sh"))]
    assert subprocess.run(["shellcheck", "-x", *map(str, scripts)], cwd=ROOT).returncode == 0
