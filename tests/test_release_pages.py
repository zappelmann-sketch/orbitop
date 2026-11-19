# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/release.sh, Schritte 2, 3 und 6 bis 8 mit Stellvertretern (tests/release_stub.py): gh-pages als eigener
Worktree, GitHub Pages beim ersten Release, das Warten auf Pages, die Wiederverwendung veröffentlichter Quellpakete,
die Matrix und docs/distro-check.md."""
import subprocess

import pytest

from tests.release_stub import KV, VERSION, git, make_repo, matrix_output, publish_pages, run, sha256
from tests.site_stub import kill_agent, make_keys, needs_git

pytestmark = needs_git
BIN = "apt/dists/stable/main/binary-all"
DEB = f"apt/pool/main/o/orbitop-apt-source/orbitop-apt-source_{KV}_all.deb"
RPMS = [f"rpm/{f}/orbitop-release-{KV}-1.noarch.rpm" for f in ("fedora", "opensuse")]
SERVED = ["apt/dists/stable/InRelease", "rpm/fedora/repodata/repomd.xml", "rpm/fedora/repodata/repomd.xml.asc",
          "rpm/opensuse/repodata/repomd.xml", "rpm/opensuse/repodata/repomd.xml.asc", "arch/x86_64/orbitop.db",
          "arch/x86_64/orbitop.db.sig"]


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    k = make_keys(tmp_path_factory.mktemp("pages-keys") / "gnupg",
                  uids=("Test Signing <test@example.com>", "Test Signing Two <test@example.com>"))
    yield k
    kill_agent(k["home"])


@pytest.fixture
def repo(tmp_path, keys):
    return make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])


def clearsign(keys, text, signer=0):
    return subprocess.run(["gpg", "--homedir", str(keys["home"]), "--no-options", "--batch", "--local-user",
                           keys["fprs"][signer] + "!", "--clearsign"], input=text.encode(), capture_output=True,
                          check=True).stdout


def published(keys, deb=b"published deb\n", listed=None, rpm=b"published rpm\n", signer=0):
    """Der Baum eines früheren Releases: Quellpakete dieser keyring.version, ein von KEYS signierter apt-Index, der
    das deb (oder LISTED) nennt, by-hash dieses Index und eines Releases davor."""
    packages = f"Package: orbitop-apt-source\nVersion: {KV}\nFilename: {DEB[4:]}\nSHA256: {listed or sha256(deb)}\n"
    release = f"Origin: orbitop\nSHA256:\n {sha256(packages.encode())} {len(packages)} main/binary-all/Packages\n"
    return {DEB: deb, **{p: rpm for p in RPMS}, f"{BIN}/Packages": packages.encode(),
            f"{BIN}/by-hash/SHA256/{sha256(packages.encode())}": packages.encode(),
            f"{BIN}/by-hash/SHA256/{'f' * 64}": b"index of the release before\n",
            "apt/dists/stable/InRelease": clearsign(keys, release, signer),
            "rpm/fedora/orbitop-0.1.0-1.noarch.rpm": b"old\n"}


def tree(remote, ref="gh-pages"):
    return set(git(remote, "ls-tree", "-r", "--name-only", ref).split())


def blob(remote, path):
    return subprocess.run(["git", "--git-dir", str(remote), "cat-file", "blob", f"gh-pages:{path}"],
                          capture_output=True, check=True).stdout


def test_first_release_makes_orphan_pages_and_enables_them(tmp_path, keys, repo):
    r, calls = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    remote = repo["remote"]
    assert git(remote, "rev-list", "--count", "gh-pages").strip() == "1"  # verwaist, ein Commit
    assert not tree(remote) & tree(remote, "main")
    assert {".nojekyll", "orbitop-archive-keyring.asc", f"apt/pool/main/o/orbitop/orbitop_{VERSION}-1_all.deb",
            DEB, *RPMS, *SERVED} <= tree(remote)
    api = [c for c in calls["gh"] if c[0] == "api"]
    assert api == [["api", "repos/zappelmann-sketch/orbitop/pages", "--jq", '.source.branch + " " + .source.path'],
                   ["api", "-X", "POST", "repos/zappelmann-sketch/orbitop/pages", "-f", "source[branch]=gh-pages",
                    "-f", "source[path]=/"]]
    fetched = [c[-1] for c in calls["curl"]]
    assert sorted(fetched) == sorted(f"https://zappelmann-sketch.github.io/orbitop/{p}" for p in SERVED)
    assert all("--proto" in c and "=https" in c for c in calls["curl"])
    assert not list((tmp_path / "tmp").iterdir()) and git(repo["repo"], "worktree", "list").count("\n") == 1


def test_second_release_reuses_published_packages_and_keeps_by_hash(tmp_path, keys, repo):
    old = published(keys)
    publish_pages(tmp_path, repo, old)
    before = git(repo["remote"], "rev-parse", "gh-pages").strip()
    (tmp_path / "pages-on").touch()  # GitHub Pages ist schon an
    r, calls = run(tmp_path, repo, keys, VERSION)
    assert r.returncode == 0, r.stderr
    assets = tmp_path / "assets"
    assert (assets / "orbitop-apt-source.deb").read_bytes() == old[DEB]
    assert (assets / "orbitop-release-fedora.rpm").read_bytes() == (assets / "orbitop-release-opensuse.rpm").read_bytes() \
        == old[RPMS[0]]
    assert blob(repo["remote"], DEB) == old[DEB] and blob(repo["remote"], RPMS[1]) == old[RPMS[1]]
    remote = repo["remote"]
    assert git(remote, "rev-parse", "gh-pages^").strip() == before  # ein Commit auf dem veröffentlichten Stand
    names = tree(remote)
    kept = f"{BIN}/by-hash/SHA256/{sha256(old[f'{BIN}/Packages'])}"
    assert kept in names and f"{BIN}/by-hash/SHA256/{'f' * 64}" not in names  # nur der vorige Index bleibt
    assert blob(remote, f"{BIN}/Packages") != old[f"{BIN}/Packages"]  # sonst der neue Baum
    assert "rpm/fedora/orbitop-0.1.0-1.noarch.rpm" not in names
    assert not [c for c in calls["gh"] if "POST" in c]
    runs = calls["docker"]  # rpm -K der veröffentlichten RPMs: ohne Netz, die Datei auf stdin
    assert len(runs) == 2 and all(c[:4] == ["run", "--rm", "-i", "--network"] and c[4] == "none" for c in runs)


@pytest.mark.parametrize("case,text", [("unlisted", "not in the signed apt index"),
                                       ("foreign-index", "not in the signed apt index"),
                                       ("tampered-rpm", "no valid signature of ORBITOP_KEY")])
def test_refuses_published_package_it_cannot_vouch_for(tmp_path, keys, repo, case, text):
    publish_pages(tmp_path, repo, published(keys, listed="0" * 64 if case == "unlisted" else None,
                                            rpm=b"TAMPERED\n" if case == "tampered-rpm" else b"rpm\n",
                                            signer=1 if case == "foreign-index" else 0))
    r, calls = run(tmp_path, repo, keys, VERSION, "--dry-run")
    assert r.returncode == 1 and text in r.stderr, r.stderr
    assert not calls["calls"]  # vor dem Bau


@pytest.mark.parametrize("case,text", [("fail", "the container matrix failed"), ("key", "matrix ran with the key")])
def test_matrix_must_pass_with_the_key(tmp_path, keys, repo, case, text):
    if case == "key":
        (tmp_path / "matrix.txt").write_text(matrix_output(keys["fprs"][1]))
    r, calls = run(tmp_path, repo, keys, VERSION, env={"MATRIX_RC": "1" if case == "fail" else "0"})
    assert r.returncode == 1 and text in r.stderr, r.stderr
    assert git(repo["repo"], "tag") == "" and git(repo["repo"], "rev-list", "--count", "HEAD").strip() == "1"
    assert not calls["gh"] and not [c for c in calls["git"] if "push" in c]


@pytest.mark.parametrize("fail", ["packages", "site"])
def test_failed_build_leaves_nothing_behind(tmp_path, keys, repo, fail):
    r, calls = run(tmp_path, repo, keys, VERSION, env={"FAIL": fail})
    assert r.returncode == 1 and not calls["gh"]
    assert not list((tmp_path / "tmp").iterdir())  # kein halber Baum, den ein späterer Lauf fände
    assert git(repo["repo"], "status", "--porcelain") == ""


def test_distro_check_gets_the_results(tmp_path, keys, repo):
    r, _ = run(tmp_path, repo, keys, VERSION, "--dry-run")
    assert r.returncode == 0, r.stderr
    doc = (repo["repo"] / "docs" / "distro-check.md").read_text()
    block = doc[doc.index("<!-- matrix:start"):doc.index("<!-- matrix:end -->")]
    assert f"`scripts/release.sh {VERSION} --dry-run`" in block and f"`KEY {keys['fpr']}`" in block
    assert "throwaway key" in block
    assert (f"| Debian 13 | `debian:trixie` | `debian@sha256:{'1' * 64}` | `orbitop {VERSION}-1` → "
            f"`{VERSION}-1+check1`: Python 3.13.5, PyGObject 3.50.0, GTK 4.18.6, WebKitGTK 2.54.0 | "
            "1000 passed, 50 skipped | pass |") in block
    assert (f"| Debian 12 | `debian:bookworm` | `debian@sha256:{'2' * 64}` | `orbitop {VERSION}-1` refused | – | "
            'pass (expected refusal): step `install`, "orbitop : Depends: python3 (>= 3.12) but 3.11.2-1+b1 is to '
            'be installed" |') in block
    rest = doc.replace(block, "")
    assert "| Distribution |" not in rest  # nur die Tabelle im geschriebenen Teil
