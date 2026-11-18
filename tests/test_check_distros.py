# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/check-distros.sh mit einem Stellvertreter für docker: ein Container je Image, nur schreibgeschützte
Mounts, das Urteil aus den STEP-Zeilen. Die Schritte in scripts/matrix/ laufen nur im Container."""
import configparser
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.packaging_common import APT_SOURCE, PKG, ROOT, deb822

SCRIPT = ROOT / "scripts" / "check-distros.sh"
MATRIX = ROOT / "scripts" / "matrix"
PAGES = "https://zappelmann-sketch.github.io/orbitop/"
STEPS = ["refresh", "keyring", "install", "import", "tools", "pytest", "version", "upgrade", "remove", "purge",
         "tamper"]
REFUSED = """STEP refresh ok
STEP keyring ok
 orbitop : Depends: python3 (>= 3.12) but 3.11.2-1+b1 is to be installed
STEP install fail"""
needs_git = pytest.mark.skipif(not (ROOT / ".git").exists(), reason="kopiert git archive HEAD")
# Schreibt die Argumente je Aufruf nach docker.log, die Dateien der Repo-Kopie nach files.txt und gibt OUTPUT aus.
DOCKER = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/docker.log"
case $1 in
    image) echo "fake@sha256:0" ;;
    run)
        for a; do case $a in *:/src:ro) src=${a%:/src:ro} ;; esac; done
        echo "$src" > "$LOG_DIR/src.txt"
        (cd "$src" && tar -cf - . | tar -tf -) > "$LOG_DIR/files.txt"
        printf '%s\\n' "$OUTPUT"
        exit "$RC" ;;
esac
"""


def steps(failed=()):
    return "\n".join(f"STEP {s} {'fail' if s in failed else 'ok'}" for s in STEPS)


def sites(tmp_path):
    for name in ("site", "site2"):
        (tmp_path / name / "apt").mkdir(parents=True)
        (tmp_path / name / "orbitop-archive-keyring.asc").write_text(f"{PAGES} {name}\n")
    return tmp_path / "site", tmp_path / "site2"


def run(tmp_path, *args, output="", rc=0):
    """check-distros.sh mit docker-Stellvertreter; gibt das Ergebnis, die docker-Aufrufe (je Aufruf seine
    Argumente) und die RESULT-Zeilen zurück."""
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "docker").write_text(DOCKER)
    (fake / "docker").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "LOG_DIR": str(tmp_path), "OUTPUT": output,
           "RC": str(rc)}
    r = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, cwd=tmp_path, env=env,
                       timeout=60)
    log = tmp_path / "docker.log"
    calls, cur = [], []
    for line in log.read_text().splitlines() if log.exists() else []:
        if line == "----":
            calls, cur = [*calls, cur], []
        else:
            cur.append(line)
    return r, calls, [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT ")]


@needs_git
def test_one_docker_run_per_image_with_ro_mounts(tmp_path):
    site, site2 = sites(tmp_path)
    r, calls, results = run(tmp_path, "--site", str(site), "--site2", str(site2), "fake:1", "fake/two:latest",
                            output=steps())
    assert r.returncode == 0, r.stderr
    assert results == ["RESULT fake:1 fake@sha256:0 pass -", "RESULT fake/two:latest fake@sha256:0 pass -"]
    runs = [c for c in calls if c[0] == "run"]
    src = (tmp_path / "src.txt").read_text().strip()
    for call, image in zip(runs, ["fake:1", "fake/two:latest"], strict=True):
        opts = call[:call.index(image)]
        assert call[call.index(image):] == [image, "bash", "/src/scripts/matrix/inside.sh"]
        assert opts == ["run", "--rm", "-v", f"{src}:/src:ro", "-v", f"{site}:/site:ro", "-v", f"{site2}:/site2:ro"]
    files = {Path(ln) for ln in (tmp_path / "files.txt").read_text().splitlines()}
    assert {Path("scripts/check-distros.sh"), Path("orbitop/__init__.py")} <= files
    assert not {f for f in files if {"CLAUDE.md", ".superpowers", ".git", ".claude"} & set(f.parts)}
    assert Path(src).resolve() != ROOT and ROOT not in Path(src).resolve().parents
    assert not Path(src).exists()  # nach dem Lauf entfernt


@pytest.mark.parametrize("args", [
    [], ["--site", "S"], ["--site2", "T", "fake:1"], ["--site", "S", "--site2"], ["--site", "S", "--site2", "T", "-v"],
    ["--site", "S", "--site2", "T", "--privileged"], ["--site", "S", "--site2", "T", "--network=host"],
    ["--site", "S", "--site2", "T", ""], ["--site", "S", "--site2", "T", "fake:1", "--rm"],
    ["--site", "S", "--site2", "T", "fake:1 --privileged"], ["--site", "S", "--site2", "T", "$(id)"],
    ["--bogus", "x", "--site", "S", "--site2", "T"], ["--site", "S", "--site2", "T", "--site", "S"],
])
def test_options_never_reach_docker(tmp_path, args):
    site, site2 = sites(tmp_path)
    args = [{"S": str(site), "T": str(site2)}.get(a, a) for a in args]
    r, calls, results = run(tmp_path, *args, output=steps())
    assert (r.returncode, calls, results) == (2, [], []), r.stderr
    assert "usage:" in r.stderr


def test_sites_must_be_trees_of_build_site(tmp_path):
    site, site2 = sites(tmp_path)
    (site2 / "orbitop-archive-keyring.asc").unlink()
    for args in (["--site", str(tmp_path / "missing"), "--site2", str(site2)], ["--site", str(site), "--site2",
                                                                                   str(site2)]):
        r, calls, _ = run(tmp_path, *args, "fake:1", output=steps())
        assert (r.returncode, calls) == (1, []) and "build-site.sh" in r.stderr, r.stderr


@needs_git
@pytest.mark.parametrize("image,output,rc,result", [
    ("debian:bookworm", REFUSED, 1, "pass install"),
    ("ubuntu:22.04", REFUSED, 1, "pass install"),
    ("debian:trixie", REFUSED, 1, "fail install"),  # nur die zwei alten dürfen ablehnen
    ("debian:bookworm", REFUSED.replace("Depends: python3 (>= 3.12)", "Depends: pkexec"), 1, "fail install"),
    ("debian:bookworm", steps(), 0, "fail install"),  # installiert trotz Python 3.11
    ("ubuntu:22.04", REFUSED.replace("keyring ok", "keyring fail"), 1, "fail keyring"),
    ("debian:trixie", steps(failed=["pytest", "purge"]), 1, "fail pytest"),
    ("debian:trixie", steps(), 1, "fail run"),  # Abbruch ohne fehlgeschlagenen Schritt
    ("debian:trixie", steps(), 0, "pass -"),
], ids=["bookworm", "jammy", "trixie-refused", "other-reason", "installs", "keyring", "pytest", "aborted", "pass"])
def test_expected_refusal_counts_as_pass(tmp_path, image, output, rc, result):
    site, site2 = sites(tmp_path)
    r, _, results = run(tmp_path, "--site", str(site), "--site2", str(site2), image, output=output, rc=rc)
    assert results == [f"RESULT {image} fake@sha256:0 {result}"], r.stderr


def tree_hash(d):
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*"))
            if p.is_file()}


@needs_git
def test_rewrite_only_inside_container(tmp_path):
    """Die Pakete tragen die echte Pages-Adresse; nur die installierten Kopien unter /etc im Container zeigen auf
    file://, und der Rechner ändert die Bäume nie."""
    (source,) = deb822(APT_SOURCE / "orbitop.sources")
    assert source["URIs"] == PAGES + "apt"
    for family in ("fedora", "opensuse"):
        repo = configparser.ConfigParser(interpolation=None)
        repo.read(PKG / "keyring" / f"orbitop-{family}.repo", encoding="utf-8")
        assert repo["orbitop"]["baseurl"] == f"{PAGES}rpm/{family}"
    packaged = [APT_SOURCE / "orbitop.sources", *(PKG / "keyring").glob("*.repo")]
    assert all("file:///site" not in f.read_text(encoding="utf-8") for f in packaged)
    inside = (MATRIX / "inside.sh").read_text(encoding="utf-8")
    assert f"PAGES={PAGES}\n" in inside  # dieselbe Adresse, sonst ersetzt point nichts
    matrix = "".join(f.read_text(encoding="utf-8") for f in sorted(MATRIX.glob("*.sh")))
    targets = re.findall(r"^[^#\n]*\bpoint (\S+) ", matrix, re.M)  # point nur auf installierte Dateien unter /etc
    assert targets and set(targets) == {'"$SOURCE"', '"$REPO"', '"$CONF"'}, targets
    assert set(re.findall(r"^(SOURCE|REPO|CONF)=(\S+)$", matrix, re.M)) == {
        ("SOURCE", "/etc/apt/sources.list.d/orbitop.sources"), ("REPO", "/etc/yum.repos.d/orbitop.repo"),
        ("REPO", "/etc/zypp/repos.d/orbitop.repo"), ("CONF", "/etc/pacman.conf")}
    assert "file://" not in SCRIPT.read_text(encoding="utf-8")
    site, site2 = sites(tmp_path)
    before = tree_hash(site), tree_hash(site2)
    r, _, results = run(tmp_path, "--site", str(site), "--site2", str(site2), "fake:1", output=steps())
    assert results and (tree_hash(site), tree_hash(site2)) == before, r.stderr


def test_matrix_refuses_outside_container(tmp_path):  # installiert echt als root, also nur im Wegwerf-Container
    if os.geteuid() == 0:
        pytest.skip("running as root")
    r = subprocess.run(["bash", str(MATRIX / "inside.sh")], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 1 and "container" in r.stderr and "STEP" not in r.stdout


def test_shellcheck_clean():
    assert subprocess.run(["shellcheck", "-x", str(SCRIPT), *map(str, sorted(MATRIX.glob("*.sh")))],
                          cwd=ROOT).returncode == 0
