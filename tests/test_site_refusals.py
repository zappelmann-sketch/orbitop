# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/build-site.sh bricht ab: falsche Umgebung, fremde Schlüssel im Agent, Fremdes aus einem Container."""
import shutil

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


@pytest.mark.parametrize("case", ["no-key", "bad-key", "foreign-key", "old-site", pytest.param("two-versions",
                                  marks=needs_git), "no-socket"])  # put kommt nach git archive HEAD
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


def test_build_site_fails_closed_when_the_key_comparison_fails(tmp_path, key):
    grep = f"""#!/bin/sh
case " $* " in *" -vxF "*) echo 'grep: broken' >&2; exit 2 ;; esac
exec {shutil.which("grep")} "$@"
"""
    r, calls = run(tmp_path, key, stubs={"grep": grep})
    assert (r.returncode, calls) == (1, []), r.stderr
    assert "could not be compared" in r.stderr


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
def test_put_refuses_a_symlinked_package_on_its_own(tmp_path, key):  # auch wenn only_plain ihn übersähe
    (tmp_path / "elsewhere").write_text("x")
    (tmp_path / "pkgs" / "arch").mkdir(parents=True)
    (tmp_path / "pkgs" / "arch" / "orbitop-0.2.0-1-any.pkg.tar.zst").symlink_to(tmp_path / "elsewhere")
    r, calls = run(tmp_path, key, stubs={"find": "#!/bin/sh\nexit 0\n"})
    assert (r.returncode, calls) == (1, []), r.stderr
    assert "not a regular file" in r.stderr


@pytest.mark.parametrize("getcap", ["#!/bin/sh\necho 'getcap: broken' >&2\nexit 1\n",
                                    "#!/bin/sh\necho '/x (No such file or directory)'\n"])  # Fehler mit Exit 0
def test_build_site_fails_closed_when_getcap_fails(tmp_path, key, getcap):
    r, calls = run(tmp_path, key, stubs={"getcap": getcap})
    assert (r.returncode, calls) == (1, []), r.stderr
    assert "refusing" in r.stderr and "getcap failed" in r.stderr


@needs_git
@pytest.mark.parametrize("plant", ["symlink", "fifo", "setgid", "cap"])
def test_build_site_refuses_odd_container_output(tmp_path, key, plant):
    victim = tmp_path / "victim.txt"
    victim.write_text("unchanged\n")
    r, calls = run(tmp_path, key, env={"PLANT": plant, "VICTIM": str(victim)})
    assert r.returncode == 1 and "refusing" in r.stderr, r.stderr
    assert victim.read_text() == "unchanged\n"  # nie durch einen Symlink des Containers geschrieben
    # Abbruch gleich nach dem Container, der es angelegt hat
    steps = [next(a for a in c if a.startswith("/src/packaging/site/")) for c in calls if c[0] == "run"]
    assert steps[-1].endswith("arch-inside.sh" if plant == "setgid" else "apt-inside.sh"), steps


@needs_git
@pytest.mark.parametrize("step", ["apt", "arch"])
def test_build_site_signs_no_package_a_container_changed(tmp_path, key, step):
    r, _ = run(tmp_path, key, env={"PLANT": f"changed-{step}"})
    assert r.returncode == 1 and "is not the one from --packages" in r.stderr, r.stderr
    site = tmp_path / "site"
    if step == "apt":  # der apt-Schritt ändert das Paket schon, bevor irgendetwas signiert ist
        assert not (site / "apt/dists/stable/InRelease").exists() and not list(site.rglob("*.sig"))
    assert not list(site.rglob("*.pkg.tar.zst.sig"))


@needs_git
def test_build_site_signs_only_the_package_from_packages(tmp_path, key):
    r, _ = run(tmp_path, key, env={"PLANT": "extra"})
    assert r.returncode == 0, r.stderr
    arch = tmp_path / "site" / "arch" / "x86_64"
    assert (arch / "orbitop-0.2.0-1-any.pkg.tar.zst.sig").exists()
    assert not (arch / "evil-1-1-any.pkg.tar.zst.sig").exists()


@needs_git
@pytest.mark.parametrize("plant", ["apt-extra", "apt-forged"])
def test_build_site_signs_no_apt_index_but_the_one_of_the_packages(tmp_path, key, plant):
    r, _ = run(tmp_path, key, env={"PLANT": plant})
    assert r.returncode == 1 and "apt index:" in r.stderr and "refusing apt" in r.stderr, r.stderr
    site = tmp_path / "site"
    assert not (site / "apt/dists/stable/InRelease").exists() and not list(site.rglob("*.sig"))
