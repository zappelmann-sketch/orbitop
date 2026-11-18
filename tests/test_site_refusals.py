# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/build-site.sh bricht ab: falsche Umgebung, fremde Schlüssel im Agent, Fremdes aus einem Container."""
import pytest

from tests.site_stub import PACKAGES, kill_agent, make_keys, needs_git, run


@pytest.fixture(scope="module")
def key(tmp_path_factory):
    k = make_keys(tmp_path_factory.mktemp("refusal-key") / "gnupg")
    yield k
    kill_agent(k["home"])


@pytest.fixture(scope="module")
def two_keys(tmp_path_factory):
    k = make_keys(tmp_path_factory.mktemp("two-keys") / "gnupg",
                  ("Test Signing <test@example.com>", "Test Signing Two <test@example.com>"))
    yield k
    kill_agent(k["home"])


@pytest.mark.parametrize("case", ["no-key", "bad-key", "foreign-key", "old-site", "two-versions", "no-socket"])
def test_build_site_refuses_before_any_container(tmp_path, key, case):
    kwargs, expect = {
        "no-key": ({"fpr": ""}, "ORBITOP_KEY"),
        "bad-key": ({"fpr": "0x1234"}, "ORBITOP_KEY"),
        "foreign-key": ({"fpr": "A" * 40}, "no secret key"),
        "old-site": ({}, "--out"),
        "two-versions": ({"packages": [*PACKAGES, "deb/orbitop_0.1.0-1_all.deb"]}, "exactly one deb/orbitop_*"),
        "no-socket": ({"socket": tmp_path / "missing" / "S.gpg-agent.extra"}, "extra socket"),
    }[case]
    if case == "old-site":
        (tmp_path / "site").mkdir()
        (tmp_path / "site" / "index.html").write_text("")
    r, calls = run(tmp_path, key, **kwargs)
    assert (r.returncode, calls) == (1, []), r.stderr
    assert expect in r.stderr


def test_build_site_refuses_agent_with_other_keys(tmp_path, two_keys):
    # Über den Socket könnte der Container mit jedem Schlüssel des Agenten signieren und entschlüsseln
    r, calls = run(tmp_path, two_keys)
    assert (r.returncode, calls) == (1, []), r.stderr
    assert "no other key" in r.stderr


def test_build_site_never_reads_input_through_a_symlink(tmp_path, key):
    secret = tmp_path / "secret.txt"
    secret.write_text("not for the public site")
    (tmp_path / "pkgs" / "deb").mkdir(parents=True)
    (tmp_path / "pkgs" / "deb" / "orbitop_0.2.0-1_all.deb").symlink_to(secret)
    r, calls = run(tmp_path, key)
    assert (r.returncode, calls) == (1, []), r.stderr
    assert "refusing" in r.stderr
    site = tmp_path / "site"
    assert not [p for p in site.rglob("*") if p.is_file() and b"not for the public" in p.read_bytes()]


@needs_git
@pytest.mark.parametrize("plant", ["symlink", "fifo", "setgid"])
def test_build_site_refuses_odd_container_output(tmp_path, key, plant):
    victim = tmp_path / "victim.txt"
    victim.write_text("unchanged\n")
    r, calls = run(tmp_path, key, env={"PLANT": plant, "VICTIM": str(victim)})
    assert r.returncode == 1, r.stderr
    assert "refusing" in r.stderr and "plain files" in r.stderr
    assert victim.read_text() == "unchanged\n"  # nie durch einen Symlink des Containers geschrieben
    # Abbruch gleich nach dem Container, der es angelegt hat
    steps =[next(a for a in c if a.startswith("/src/packaging/site/")) for c in calls if c[0] == "run"]
    assert steps[-1].endswith("arch-inside.sh" if plant == "setgid" else "apt-inside.sh"), steps
