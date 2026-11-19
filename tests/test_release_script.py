# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/release.sh mit Stellvertretern (tests/release_stub.py): die Vorprüfung vor jedem Bau, der gpg-agent mit
einer Passphrase je Release und der Trockenlauf ohne gh und Push. Die Veröffentlichung: tests/test_release_publish.py;
gh-pages, Wiederverwendung und docs/distro-check.md: tests/test_release_pages.py."""
import re
import subprocess

import pytest

from tests.packaging_common import ROOT
from tests.release_stub import VERSION, git, make_repo, run
from tests.site_stub import gpg, kill_agent, make_keys, needs_git

pytestmark = needs_git


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
    assert not calls["calls"] and not pushes(calls)
    assert not [c for c in calls["gh"] if c[0] == "release" or "POST" in c]


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


CASES = {  # Fall: (README, Trockenlauf, Umgebung, erwarteter Text)
    "branch": ("fpr", True, {}, "only from the branch main"),
    "tag": ("fpr", True, {}, "exists already"),
    "remote-tag": ("fpr", True, {}, "exists on origin"),
    "changelog": ("fpr", True, {}, "newest <release>"),
    "identity-mail": ("fpr", True, {}, "GIT_AUTHOR_IDENT must be exactly zappelmann-sketch <"),
    "identity-name": ("fpr", True, {}, "GIT_AUTHOR_IDENT must be exactly zappelmann-sketch <"),
    "committer": ("fpr", True, {"GIT_COMMITTER_NAME": "Alice"}, "GIT_COMMITTER_IDENT must be exactly"),
    "readme-other": ("other", True, {}, "README names the fingerprint"),
    "readme-placeholder": (None, False, {}, "README still has the placeholder <FINGERPRINT>"),
    "readme-none": ("no fingerprint", False, {}, "README names no fingerprint of the archive key"),
    "bad-fpr": ("fpr", True, {"ORBITOP_KEY": "bad"}, "40 hex digits"),
    "no-secret": ("fpr", True, {"ORBITOP_KEY": "0" * 40}, "no secret key"),
    "no-gnupghome": ("fpr", True, {"GNUPGHOME": ""}, "GNUPGHOME must be the GnuPG directory"),
    "gh-login": ("fpr", False, {"GH_AUTH_RC": "1"}, "gh is not logged in"),
    "gh-admin": ("fpr", False, {"GH_ADMIN": "false"}, "no admin rights on zappelmann-sketch/orbitop"),
}


@pytest.mark.parametrize("case", CASES)
def test_refuses_before_building(tmp_path, keys, case):
    readme, dry, env, text = CASES[case]
    readme = {"fpr": keys["fpr"], "other": keys["fprs"][1]}.get(readme, readme)
    repo = make_repo(tmp_path, keys["fpr"], readme=readme,
                     **{"identity-mail": {"email": "alice@example.com"},  # die Adresse oder der Name allein
                        "identity-name": {"user": "Alice"}}.get(case, {}))
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
    r, calls = run(tmp_path, repo, keys, version, *(["--dry-run"] if dry else []), env=env)
    refused_before_building(r, calls, text)


@pytest.mark.parametrize("args", [[], ["--dry-run"], [VERSION, "--force"], [f"v{VERSION}"], [VERSION, "--dry-run", "x"],
                                  [VERSION, ""]])
def test_usage(tmp_path, keys, repo, args):
    r, calls = run(tmp_path, repo, keys, *args)
    assert r.returncode == 2 and "usage:" in r.stderr and not calls["calls"] and not calls["gpgconf"]


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


def test_agent_keeps_the_passphrase_for_the_whole_release(tmp_path, keys, repo):
    """Spec 4: eine Eingabe je Release. Der Agent von GNUPGHOME startet neu mit 2 Stunden und stoppt am Ende."""
    r, calls = run(tmp_path, repo, keys, VERSION, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert calls["gpg-agent"] == [["--homedir", str(keys["home"]), "--daemon", "--disable-scdaemon",
                                   "--default-cache-ttl", "7200", "--max-cache-ttl", "7200"]]
    assert calls["gpgconf"][0] == calls["gpgconf"][-1] == ["--kill", "gpg-agent"]  # vor dem Start und am Ende
    assert not (keys["home"] / "gpg-agent.conf").exists()  # keine Datei im GnuPG-Ordner geändert


def test_agent_stops_even_when_the_cleanup_fails(tmp_path, keys, repo):
    """set -e gilt auch im EXIT-Trap: ein scheiterndes rm (root-eigene Reste) darf das Beenden nicht verhindern."""
    r, calls = run(tmp_path, repo, keys, VERSION, "--dry-run", env={"RM_FAILS": "1"})
    assert calls["gpgconf"].count(["--kill", "gpg-agent"]) == 2, calls["gpgconf"]  # beim Start und am Ende
    assert calls["gpgconf"][-1] == ["--kill", "gpg-agent"]
    assert git(repo["repo"], "worktree", "list").count("\n") == 1  # auch prune lief


def test_dry_run_never_calls_gh_or_push(tmp_path, keys):
    repo = make_repo(tmp_path, keys["fpr"], readme=None)  # bis Task 9: nur eine Warnung im Trockenlauf
    commit_key(repo, gpg(keys["home"], "--armor", "--export", keys["fpr"]))  # der passende Schlüssel stört nicht
    r, calls = run(tmp_path, repo, keys, VERSION, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "warning: the README still has the placeholder <FINGERPRINT>" in r.stderr
    assert not calls["gh"] and not pushes(calls) and not calls["curl"]
    assert [c[0] for c in calls["calls"]] == ["build-packages", "build-site", "build-packages", "build-site",
                                              "check-distros"]
    assert f"dry run, would run: gh release create v{VERSION}" in r.stdout and " --draft " in r.stdout
    assert "push --atomic --no-follow-tags origin refs/heads/main:refs/heads/main" in r.stdout
    assert "gh api -X POST" in r.stdout and f"gh release edit v{VERSION}" in r.stdout
    assert git(repo["repo"], "status", "--porcelain") == " M docs/distro-check.md\n"  # geschrieben, nicht committet
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


def test_shellcheck_clean():
    scripts = [ROOT / "scripts" / "release.sh", *sorted((ROOT / "scripts" / "release").glob("*.sh"))]
    assert subprocess.run(["shellcheck", "-x", *map(str, scripts)], cwd=ROOT).returncode == 0
