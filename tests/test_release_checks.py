# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/release.sh, Prüfungen des Schlussreviews: das Datum des neuesten <release> der metainfo, die Push- und die
Fetch-Adresse von origin, ein HEAD, der sich während des Laufs nicht bewegen darf, Bauten aus dem festen Commit und
die Identität ohne Einfluss der Shell (Stellvertreter: tests/release_stub.py)."""
import os
import shutil
import subprocess

import pytest

from tests.packaging_common import ROOT
from tests.release_stub import GIT_ENV, NOREPLY, REAL, VERSION, git, make_repo, run
from tests.site_stub import kill_agent, make_keys, needs_git

pytestmark = needs_git
GITHUB = "https://github.com/zappelmann-sketch/orbitop.git"


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    k = make_keys(tmp_path_factory.mktemp("check-keys") / "gnupg")
    yield k
    kill_agent(k["home"])


def published_nothing(r, calls, repo, text):
    assert r.returncode == 1 and text in r.stderr, r.stderr
    assert git(repo["repo"], "tag") == "" and git(repo["remote"], "tag") == ""
    assert not [c for c in calls["git"] if "push" in c]
    assert not [c for c in calls["gh"] if c[0] == "release" or "POST" in c]


@pytest.mark.parametrize("dry", [False, True], ids=["release", "dry-run"])
def test_release_date_must_be_today(tmp_path, keys, dry):
    """Review M1: Der neueste <release> der metainfo nennt das Datum des Release (UTC); ein Trockenlauf warnt nur."""
    repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"], date="2026-01-01")
    r, calls = run(tmp_path, repo, keys, VERSION, *(["--dry-run"] if dry else []))
    text = "the newest <release> of the metainfo has the date 2026-01-01, not today ("
    if dry:
        assert r.returncode == 0 and f"warning: {text}" in r.stderr, r.stderr
    else:
        assert r.returncode == 1 and text in r.stderr and not calls["calls"], r.stderr


@pytest.mark.parametrize("dry", [False, True], ids=["release", "dry-run"])
def test_origin_must_push_to_the_project(tmp_path, keys, dry):
    """Audit H1: Jeder Push geht an origin; dessen Push-Adresse muss das Repository des Projekts sein."""
    repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])
    r, calls = run(tmp_path, repo, keys, VERSION, *(["--dry-run"] if dry else []),
                   env={"ORIGIN_PUSH": "https://github.com/alice/orbitop.git"})
    text = ("origin pushes to https://github.com/alice/orbitop.git, not to zappelmann-sketch/orbitop on GitHub (git"
            " remote get-url --all --push origin: url, pushurl, insteadOf)")  # die ganze Meldung
    if dry:
        assert r.returncode == 0 and f"warning: {text}" in r.stderr, r.stderr
    else:
        assert r.returncode == 1 and text in r.stderr and not calls["calls"], r.stderr


@pytest.mark.parametrize("dry", [False, True], ids=["release", "dry-run"])
def test_origin_must_fetch_from_the_project(tmp_path, keys, dry):
    """Plan 2026-11-19, Task 9: remote_state liest Tag und gh-pages von origin; auch dessen Fetch-Adresse muss das
    Repository des Projekts sein, sonst entscheidet ein Spiegel über den Stand von GitHub."""
    repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])
    r, calls = run(tmp_path, repo, keys, VERSION, *(["--dry-run"] if dry else []),
                   env={"ORIGIN_FETCH": "/srv/mirror.git"})
    text = ("origin fetches from /srv/mirror.git, not from zappelmann-sketch/orbitop on GitHub (git remote get-url"
            " --all origin: url, insteadOf)")
    if dry:
        assert r.returncode == 0 and f"warning: {text}" in r.stderr, r.stderr
    else:
        assert r.returncode == 1 and text in r.stderr and not calls["calls"], r.stderr


CONFIGS = {  # Konfiguration von origin: je Meldung der Anfang vor dem Repository, erst Push, dann Fetch
    "https": ([("remote.origin.url", GITHUB)], ()),
    "https-short": ([("remote.origin.url", GITHUB.removesuffix(".git"))], ()),
    "scp": ([("remote.origin.url", "git@github.com:zappelmann-sketch/orbitop.git")], ()),
    "ssh": ([("remote.origin.url", "ssh://git@github.com/zappelmann-sketch/orbitop.git")], ()),
    "fetch-mirror": ([("remote.origin.url", "/srv/mirror.git"), ("remote.origin.pushurl", GITHUB)], ("not from",)),
    "fetch-pushinsteadof": ([("remote.origin.url", "/srv/mirror.git"),
                             (f"url.{GITHUB}.pushInsteadOf", "/srv/mirror.git")], ("not from",)),
    "fetch-two-urls": ([("remote.origin.url", GITHUB), ("remote.origin.url", "/srv/mirror.git"),
                        ("remote.origin.pushurl", GITHUB)], ("not from",)),
    "fork": ([("remote.origin.url", "https://github.com/alice/orbitop.git")], ("not to", "not from")),
    "http": ([("remote.origin.url", "http://github.com/zappelmann-sketch/orbitop.git")], ("not to", "not from")),
    "longer": ([("remote.origin.url", GITHUB + "x")], ("not to", "not from")),
    "other-pushurl": ([("remote.origin.url", GITHUB), ("remote.origin.pushurl", "/srv/mirror.git")], ("not to",)),
    "two-pushurls": ([("remote.origin.url", GITHUB), ("remote.origin.pushurl", GITHUB),
                      ("remote.origin.pushurl", "/srv/mirror.git")], ("not to",)),
    "insteadof": ([("remote.origin.url", GITHUB), ("url./srv/mirror.git.insteadOf", GITHUB)], ("not to", "not from")),
    "pushinsteadof": ([("remote.origin.url", GITHUB), ("url./srv/mirror.git.pushInsteadOf", GITHUB)], ("not to",)),
    "none": ([], ("not to", "not from")),
}


@pytest.mark.parametrize("case", CONFIGS)
def test_check_origin(tmp_path, case):
    """check_origin mit echtem git: git remote get-url --all --push origin nennt jede Adresse, an die ein Push geht,
    nach pushurl, insteadOf und pushInsteadOf, git remote get-url --all origin jede, von der remote_state liest; je
    genau eine, und die des Projekts. Ein Release bricht bei der ersten ab, ein Trockenlauf warnt bei jeder."""
    config, problems = CONFIGS[case]
    subprocess.run([REAL["git"], "init", "-q", str(tmp_path / "r")], check=True, env={**os.environ, **GIT_ENV})
    for key, value in config:
        subprocess.run([REAL["git"], "-C", str(tmp_path / "r"), "config", "--add", key, value], check=True,
                       env={**os.environ, **GIT_ENV})
    script = '. scripts/container-common.sh; . scripts/release/checks.sh; repo=$R; check_origin'
    for dry in ("", "1"):
        r = subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, **GIT_ENV, "R": str(tmp_path / "r"), "dry": dry})
        assert r.returncode == (1 if problems and not dry else 0), r.stderr
        found = [m for m in ("not to", "not from") if f"{m} zappelmann-sketch/orbitop on GitHub" in r.stderr]
        assert found == list(problems[:1] if not dry else problems), r.stderr
        assert not dry or r.stderr.count("warning: origin ") == len(problems), r.stderr


@pytest.mark.parametrize("dry", [False, True], ids=["release", "dry-run"])
def test_refuses_a_head_that_moved_during_the_run(tmp_path, keys, dry):
    """Audit H2: Während der Matrix committet ein anderer Prozess. Getaggt wird nur der Stand von Schritt 1 oder der
    eine Commit von Schritt 3 darauf, sonst hält der Lauf vor dem Tag an."""
    repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])
    pinned = git(repo["repo"], "rev-parse", "HEAD").strip()
    r, calls = run(tmp_path, repo, keys, VERSION, *(["--dry-run"] if dry else []), env={"MATRIX_COMMIT": "1"})
    text = "HEAD moved during the run" if dry else f"is neither the HEAD of step 1 ({pinned})"
    published_nothing(r, calls, repo, text)


def test_tags_the_commit_of_the_release_files(tmp_path, keys):
    """Audit H2: Tag und Quellarchiv nennen den Commit von Schritt 3, dessen Elter der Stand von Schritt 1 ist."""
    repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])
    pinned = git(repo["repo"], "rev-parse", "HEAD").strip()
    r, calls = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    tagged = git(repo["remote"], "rev-parse", f"v{VERSION}^{{commit}}").strip()
    assert git(repo["remote"], "rev-parse", f"{tagged}^").strip() == pinned
    (tag,) = [c for c in calls["git"] if "tag" in c and "-a" in c]
    assert tag[-2:] == [f"v{VERSION}", tagged]  # der Commit selbst, nicht HEAD


def test_builds_use_the_pinned_commit(tmp_path, keys):
    """Plan 2026-11-19, Task 9: Nach Schritt 1 committet ein anderer Prozess. Beide Bauten und die Matrix bekommen
    trotzdem den Baum des festen Commits (ORBITOP_REV für tracked_files), und vor dem Tag hält der Lauf an."""
    repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])
    pinned = git(repo["repo"], "rev-parse", "HEAD").strip()
    r, calls = run(tmp_path, repo, keys, VERSION, env={"MOVE_HEAD": "1"})
    assert "moved.txt" in git(repo["repo"], "ls-tree", "--name-only", "HEAD")  # HEAD ist gewandert
    assert (tmp_path / "trees.log").read_text().splitlines() == [
        "build-packages.sh pinned", "build-site.sh pinned", "build-packages.sh pinned", "build-site.sh pinned",
        "check-distros.sh pinned"]
    published_nothing(r, calls, repo, f"is neither the HEAD of step 1 ({pinned})")


def test_identity_of_the_shell_never_reaches_the_run(tmp_path, keys, monkeypatch):
    """Plan 2026-11-19, Task 9: GIT_AUTHOR_* und GIT_COMMITTER_* der Shell, die pytest startet, gehen nicht an
    release.sh durch (release_stub.run); Commits und Tag tragen weiter die noreply-Adresse."""
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "Alice")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "alice@example.com")
    repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])
    r, _ = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    for ref in (f"v{VERSION}", "gh-pages"):
        assert git(repo["remote"], "log", "-1", "--format=%an <%ae> %cn <%ce>", ref).strip() == (
            f"zappelmann-sketch <{NOREPLY}> zappelmann-sketch <{NOREPLY}>")
    assert NOREPLY in git(repo["remote"], "cat-file", "-p", f"v{VERSION}").split("\n")[3]  # tagger


@pytest.mark.parametrize("dry", [False, True], ids=["release", "dry-run"])
def test_refuses_a_script_changed_during_the_run(tmp_path, keys, dry):
    """Audit M2 (Plan 2026-11-19, Task 9): Die Skripte des Laufs kommen aus dem Arbeitsbaum. Ändert ein anderer
    Prozess eines davon ohne Commit, hält der Lauf vor dem Tag an; nur docs/distro-check.md des Trockenlaufs darf
    geändert sein."""
    repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])
    r, calls = run(tmp_path, repo, keys, VERSION, *(["--dry-run"] if dry else []), env={"CHANGE_SCRIPT": "1"})
    published_nothing(r, calls, repo, "the working tree changed during the run (git status):\n")
    assert "\n M scripts/container-common.sh" in r.stderr, r.stderr
    assert "dry run, would run: git" not in r.stdout  # kein Tag, auch nicht gedruckt


def test_suite_never_sees_orbitop_rev(tmp_path, keys):
    """Audit M1 (Plan 2026-11-19, Task 9): Ein ORBITOP_REV der Shell erreicht die strenge Suite und den
    README-Abgleich nicht (die Tests des Wegwerf-Repositorys prüfen ihre Umgebung, release_stub.SUITE)."""
    repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])
    r, _ = run(tmp_path, repo, keys, VERSION, "--dry-run", env={"ORBITOP_REV": "a" * 40})
    assert r.returncode == 0, r.stderr


def archive_repo(tmp_path):
    """Ein Repository mit zwei Commits von README.md ("one", dann "two"); gibt Pfad und Hashes zurück."""
    r = tmp_path / "r"
    git(tmp_path, "init", "-q", str(r))
    revs = []
    for text in ("one", "two"):
        (r / "README.md").write_text(f"{text}\n")
        git(r, "add", "README.md")
        git(r, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", text)
        revs.append(git(r, "rev-parse", "HEAD").strip())
    return r, revs


def tracked(tmp_path, repo, rev=None):
    """tracked_files wie in den Bau-Skripten (set -euo pipefail), REV als ORBITOP_REV; gibt das Ergebnis und
    README.md aus $tmp/src zurück (None, wenn sie fehlt)."""
    script = ('. scripts/container-common.sh; repo=$R; tmp=$T; tracked_files; '
              'cat "$tmp/src/README.md" 2> /dev/null || echo none')
    (tmp_path / "t").mkdir()
    env = {k: v for k, v in os.environ.items() if k != "ORBITOP_REV"}
    r = subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=ROOT, capture_output=True, text=True,
                       env={**env, **GIT_ENV, "R": str(repo), "T": str(tmp_path / "t"),
                            **({} if rev is None else {"ORBITOP_REV": rev})})
    return r, r.stdout.strip()


@pytest.mark.parametrize("rev", ["unset", "first", "HEAD", "main", "short", "upper", "option"])
def test_tracked_files_takes_only_a_full_hash(tmp_path, rev):
    """Audit M1 (Plan 2026-11-19, Task 9): tracked_files nimmt ORBITOP_REV nur als vollen Hash (SHA-1 oder
    SHA-256), ohne ihn HEAD; jeder andere Wert, auch eine Option für git archive, bricht ab."""
    repo, (first, _) = archive_repo(tmp_path)
    value = {"unset": None, "first": first, "HEAD": "HEAD", "main": "main", "short": first[:12], "upper": first.upper(),
             "option": f"--output={tmp_path / 'x'}"}[rev]
    r, readme = tracked(tmp_path, repo, value)
    if rev in ("unset", "first"):
        assert r.returncode == 0 and readme == ("two" if rev == "unset" else "one"), r.stderr
    else:
        assert r.returncode == 1 and f"ORBITOP_REV must be the full hash of a commit, not {value}" in r.stderr
        assert not (tmp_path / "t" / "src").exists() and not (tmp_path / "x").exists()


@pytest.mark.parametrize("case", ["replace", "attributes-file"])
def test_tracked_files_ignores_replace_refs_and_attribute_files(tmp_path, case):
    """Audit M3 (Plan 2026-11-19, Task 9): git archive folgt refs/replace (git-replace(1)) und liest export-ignore
    und export-subst aus core.attributesFile (git-archive(1), ATTRIBUTES); beides darf nicht ändern, was der Bau
    bekommt."""
    repo, (_, second) = archive_repo(tmp_path)
    if case == "replace":
        planted = subprocess.run([REAL["git"], "-C", str(repo), "hash-object", "-w", "--stdin"], input="planted\n",
                                 capture_output=True, text=True, check=True).stdout.strip()
        git(repo, "replace", git(repo, "rev-parse", "HEAD:README.md").strip(), planted)
        assert git(repo, "show", "HEAD:README.md") == "planted\n"  # git folgt dem Ersatz sonst
    else:
        (tmp_path / "attributes").write_text("README.md export-ignore\n")
        git(repo, "config", "core.attributesFile", str(tmp_path / "attributes"))
    for rev in (None, second):
        r, readme = tracked(tmp_path, repo, rev)
        assert r.returncode == 0 and readme == "two", r.stderr
        shutil.rmtree(tmp_path / "t")
