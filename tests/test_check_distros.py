# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/check-distros.sh mit einem Stellvertreter für docker: ein Container je Image, nur schreibgeschützte
Mounts, der Schlüssel beider Bäume, das Urteil aus den STEP-Zeilen. Die Schritte in scripts/matrix/ laufen nur im
Container (ihre Helfer: tests/test_matrix_lib.py)."""
import configparser
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.packaging_common import APT_SOURCE, PKG, ROOT, deb822
from tests.site_stub import GETCAP, gpg, kill_agent, make_keys, needs_git

SCRIPT = ROOT / "scripts" / "check-distros.sh"
MATRIX = ROOT / "scripts" / "matrix"
PAGES = "https://zappelmann-sketch.github.io/orbitop/"
DIGEST = "fake@sha256:" + "0" * 64
STEPS = ["refresh", "keyring", "install", "import", "tools", "pytest", "version", "upgrade", "remove", "purge",
         "counters", "tamper"]
REFUSED = """STEP refresh ok
STEP keyring ok
 orbitop : Depends: python3 (>= 3.12) but 3.11.2-1+b1 is to be installed
STEP install fail"""
# Schreibt die Argumente je Aufruf nach docker.log, die Dateien der Repo-Kopie nach files.txt, die Pakete unter /rev2
# und /v020 nach extras.txt und gibt OUTPUT aus. Ein Bau-Container (build-inside.sh von build-packages.sh) legt sein
# Format und einen Lint-Bericht an, unter deb/ das Paket orbitop der Version, und schreibt nach builds.log, ob /src
# den Helfer counterhelper.py hat (new) oder nicht (old, 0.2.0), und seine Argumente.
DOCKER = f"""#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/docker.log"
case $1 in
    image) echo "{DIGEST}" ;;
    run)
        build="" image=""
        for a; do case $a in *:/src:ro) src=${{a%:/src:ro}} ;; *:/out) out=${{a%:/out}} ;; */build-inside.sh) build=1 ;;
            *:/rev2:ro) rev2=${{a%:/rev2:ro}} ;; *:/v020:ro) v020=${{a%:/v020:ro}} ;; esac; done
        if [ -n "$build" ]; then
            for a; do [ "$a" = bash ] && break; image=$a; done
            case $image in debian:*) fmt=deb ;; fedora:*) fmt=rpm-fedora ;; opensuse/*) fmt=rpm-opensuse ;; *) fmt=arch ;; esac
            while [ "$1" != bash ]; do shift; done
            tree=old && [ ! -e "$src/orbitop/counterhelper.py" ] || tree=new
            echo "BUILD $fmt $tree $3 $4" >> "$LOG_DIR/builds.log"
            mkdir -p "$out/$fmt" "$out/lint" && echo ok > "$out/lint/$fmt.txt" && echo "$image" > "$out/$fmt/$fmt"
            [ "$fmt" != deb ] || touch "$out/deb/orbitop_$3_all.deb"
            cat > /dev/null
            exit 0
        fi
        echo "$src" > "$LOG_DIR/src.txt"
        (cd "$src" && tar -cf - . | tar -tf -) > "$LOG_DIR/files.txt"
        {{ ls "$rev2/deb"; ls "$v020/deb"; }} > "$LOG_DIR/extras.txt"
        printf '%s\\n' "$OUTPUT"
        exit "$RC" ;;
esac
"""


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    """Zwei Wegwerfschlüssel, je armored exportiert: der Schlüsselbund eines Seitenbaums."""
    k = make_keys(tmp_path_factory.mktemp("matrix-keys") / "gnupg",
                  uids=("Test Signing <test@example.com>", "Test Signing Two <test@example.com>"))
    yield {"fprs": k["fprs"], "asc": [gpg(k["home"], "--armor", "--export", fpr) for fpr in k["fprs"]]}
    kill_agent(k["home"])


def steps(failed=()):
    return "\n".join(f"STEP {s} {'fail' if s in failed else 'ok'}" for s in STEPS)


def sites(tmp_path, key=b"no key\n", key2=None):
    for name, data in (("site", key), ("site2", key if key2 is None else key2)):
        (tmp_path / name / "apt").mkdir(parents=True)
        (tmp_path / name / "orbitop-archive-keyring.asc").write_bytes(data)
    return tmp_path / "site", tmp_path / "site2"


def run(tmp_path, *args, output="", rc=0, env=()):
    """check-distros.sh mit docker-Stellvertreter; gibt das Ergebnis, die docker-Aufrufe (je Aufruf seine
    Argumente) und die RESULT-Zeilen zurück."""
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    for name, text in {"docker": DOCKER, "getcap": GETCAP}.items():
        (fake / name).write_text(text)
        (fake / name).chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "LOG_DIR": str(tmp_path), "OUTPUT": output,
           "RC": str(rc), **dict(env)}
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
def test_one_docker_run_per_image_with_ro_mounts(tmp_path, keys):
    site, site2 = sites(tmp_path, keys["asc"][0])
    r, calls, results = run(tmp_path, "--site", str(site), "--site2", str(site2), "fake:1", "fake/two:latest",
                            output=steps())
    assert r.returncode == 0, r.stderr
    assert results == [f"RESULT fake:1 {DIGEST} pass -", f"RESULT fake/two:latest {DIGEST} pass -"]
    assert f"KEY {keys['fprs'][0]}" in r.stdout.splitlines()
    runs = [c for c in calls if c[0] == "run" and DIGEST in c]
    src = (tmp_path / "src.txt").read_text().strip()
    work = Path(src).parent
    assert len(runs) == 2
    for call in runs:  # vom Digest, den das Ergebnis nennt, nicht vom Tag
        assert call[call.index(DIGEST):] == [DIGEST, "bash", "/src/scripts/matrix/inside.sh"]
        assert call[:call.index(DIGEST)] == ["run", "--rm", "-v", f"{src}:/src:ro", "-v", f"{site}:/site:ro", "-v",
                                             f"{site2}:/site2:ro", "-v", f"{work}/rev2:/rev2:ro", "-v",
                                             f"{work}/v020:/v020:ro"]
    files = {Path(ln) for ln in (tmp_path / "files.txt").read_text().splitlines()}
    assert {Path("scripts/check-distros.sh"), Path("orbitop/__init__.py")} <= files
    assert not {f for f in files if {"CLAUDE.md", ".superpowers", ".git", ".claude"} & set(f.parts)}
    assert Path(src).resolve() != ROOT and ROOT not in Path(src).resolve().parents
    assert not Path(src).exists()  # nach dem Lauf entfernt


@needs_git
def test_builds_revision_2_and_0_2_0_for_the_counter_cases(tmp_path, keys):
    """Vor den Images: derselbe Stand als Revision 2 und 0.2.0 aus den Dateien des Tags v0.2.0 (nie aus der
    veröffentlichten Quelle), je in allen vier Formaten, mit dem Schlüssel der Bäume; die Container sehen sie
    schreibgeschützt unter /rev2 und /v020. Ihr Protokoll geht nach stderr."""
    site, site2 = sites(tmp_path, keys["asc"][0])
    rev = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    r, calls, results = run(tmp_path, "--site", str(site), "--site2", str(site2), "fake:1", output=steps(),
                            env={"ORBITOP_REV": rev})
    assert r.returncode == 0 and results == [f"RESULT fake:1 {DIGEST} pass -"], r.stderr
    version = re.search(r'__version__ = "(.*)"', (ROOT / "orbitop" / "__init__.py").read_text()).group(1)
    assert (tmp_path / "builds.log").read_text().splitlines() == [
        f"BUILD deb new {version}-2 ", f"BUILD rpm-fedora new {version} 2", f"BUILD rpm-opensuse new {version} 2",
        f"BUILD arch new {version} 2", "BUILD deb old 0.2.0-1 ", "BUILD rpm-fedora old 0.2.0 1",
        "BUILD rpm-opensuse old 0.2.0 1", "BUILD arch old 0.2.0 1"]
    assert (tmp_path / "extras.txt").read_text().split() == ["deb", f"orbitop_{version}-2_all.deb", "deb",
                                                             "orbitop_0.2.0-1_all.deb"]
    assert "fpr:" not in r.stdout and "fpr:" in r.stderr  # build-packages.sh nennt den Schlüssel, aber nicht auf stdout


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


@pytest.mark.parametrize("case", ["no-key", "two-keys", "other-key"])
def test_sites_must_carry_one_and_the_same_key(tmp_path, keys, case):  # die Matrix vertraut dem Schlüssel der Bäume
    one, two = keys["asc"]
    key, key2, expect = {"no-key": (b"no key\n", one, "--site:"), "two-keys": (one + two, one + two, "--site:"),
                         "other-key": (one, two, "--site2 must carry the same key")}[case]
    site, site2 = sites(tmp_path, key, key2)
    r, calls, results = run(tmp_path, "--site", str(site), "--site2", str(site2), "fake:1", output=steps())
    assert (r.returncode, calls, results) == (1, [], []), r.stderr
    assert expect in r.stderr


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
def test_expected_refusal_counts_as_pass(tmp_path, keys, image, output, rc, result):
    site, site2 = sites(tmp_path, keys["asc"][0])
    r, _, results = run(tmp_path, "--site", str(site), "--site2", str(site2), image, output=output, rc=rc)
    assert results == [f"RESULT {image} {DIGEST} {result}"], r.stderr
    assert r.returncode == (0 if result.startswith("pass ") else 1)  # Exit 1, sobald ein Image nicht besteht


@needs_git
def test_one_failed_image_fails_the_run_after_all_images(tmp_path, keys):
    site, site2 = sites(tmp_path, keys["asc"][0])
    r, calls, results = run(tmp_path, "--site", str(site), "--site2", str(site2), "debian:trixie", "debian:bookworm",
                            output=steps())
    assert r.returncode == 1 and len([c for c in calls if c[0] == "run" and DIGEST in c]) == 2
    assert results == [f"RESULT debian:trixie {DIGEST} pass -", f"RESULT debian:bookworm {DIGEST} fail install"]


def tree_hash(d):
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*"))
            if p.is_file()}


@needs_git
def test_rewrite_only_inside_container(tmp_path, keys):
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
    lib = (MATRIX / "lib.sh").read_text(encoding="utf-8")
    assert f"\nPAGES={PAGES} " in lib  # dieselbe Adresse, sonst ersetzt point nichts
    matrix = "".join(f.read_text(encoding="utf-8") for f in sorted(MATRIX.glob("*.sh")))
    targets = re.findall(r"^[^#\n]*\bpoint (\S+) ", matrix, re.M)  # point nur auf installierte Dateien unter /etc
    assert targets and set(targets) == {'"$SOURCE"', '"$REPO"', '"$CONF"'}, targets
    assert set(re.findall(r"^(SOURCE|REPO|CONF)=(\S+)$", matrix, re.M)) == {
        ("SOURCE", "/etc/apt/sources.list.d/orbitop.sources"), ("REPO", "/etc/yum.repos.d/orbitop.repo"),
        ("REPO", "/etc/zypp/repos.d/orbitop.repo"), ("CONF", "/etc/pacman.conf")}
    assert "file://" not in SCRIPT.read_text(encoding="utf-8")
    site, site2 = sites(tmp_path, keys["asc"][0])
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
