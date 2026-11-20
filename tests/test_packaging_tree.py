# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""packaging/install-tree.sh: der Dateibaum des Hauptpakets, für alle Formate gleich."""
import os
import stat
import subprocess
import sys

import pytest

from orbitop import __version__
from tests.packaging_common import APP, PKG, ROOT

SHARE = "/usr/share/orbitop/"


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    dest = tmp_path_factory.mktemp("destdir")
    # umask 077: Die Rechte im Baum dürfen nicht von der umask des Aufrufers abhängen
    subprocess.run(["bash", str(PKG / "install-tree.sh"), str(dest)], check=True, umask=0o077)
    return dest


def listing(dest):
    return sorted("/" + str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_symlink() or not p.is_dir())


def test_install_tree_file_list(tree):
    code = sorted(SHARE + str(p.relative_to(ROOT)) for p in (ROOT / "orbitop").rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts)
    assert listing(tree) == sorted([
        "/usr/bin/orbitop",
        "/usr/lib/orbitop/killhelper",
        f"/usr/share/applications/{APP}.desktop",
        f"/usr/share/icons/hicolor/scalable/apps/{APP}.svg",
        f"/usr/share/metainfo/{APP}.metainfo.xml",
        "/usr/share/orbitop/autostart.desktop",
        "/usr/share/orbitop/bin/orbitop",
        "/usr/share/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy",
        *code])
    assert SHARE + "orbitop/ui/fonts/Orbitron.ttf" in code and SHARE + "orbitop/locale/de.json" in code
    assert not [p for p in listing(tree) if p.startswith("/usr/local") or "__pycache__" in p or "/tests/" in p]


def test_modes_independent_of_umask(tree):
    executables = {"/usr/lib/orbitop/killhelper", SHARE + "bin/orbitop", SHARE + "orbitop/killhelper.py"}
    for p in tree.rglob("*"):
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            continue
        name = "/" + str(p.relative_to(tree))
        want = 0o755 if stat.S_ISDIR(st.st_mode) or name in executables else 0o644
        assert stat.S_IMODE(st.st_mode) == want, name


def test_helper_copy_identical_and_executable(tree):
    helper = tree / "usr/lib/orbitop/killhelper"
    assert helper.read_bytes() == (ROOT / "orbitop" / "killhelper.py").read_bytes()
    assert stat.S_IMODE(os.lstat(helper).st_mode) == 0o755
    assert helper.read_text().startswith("#!/usr/bin/python3 -IS\n")  # pkexec startet ihn direkt (K1)


def test_data_files_identical(tree):  # Starter, Vorlage und polkit-Datei unverändert aus data/ und bin/
    for src, dst in (("bin/orbitop", SHARE + "bin/orbitop"), ("data/autostart.desktop", SHARE + "autostart.desktop"),
                     ("data/io.github.zappelmann-sketch.orbitop.policy",
                      "/usr/share/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy")):
        assert (tree / dst.lstrip("/")).read_bytes() == (ROOT / src).read_bytes(), src


def test_symlink_target_relative(tree):
    link = tree / "usr/bin/orbitop"
    assert os.readlink(link) == "../share/orbitop/bin/orbitop"
    assert link.resolve() == tree / "usr/share/orbitop/bin/orbitop"


def test_installed_starter_runs_from_its_tree(tree):  # K2: realpath im Starter findet /usr/share/orbitop
    r = subprocess.run([sys.executable, "-I", "-B", str(tree / "usr/bin/orbitop"), "--version"],
                       capture_output=True, text=True, cwd=tree)
    assert (r.returncode, r.stdout) == (0, f"orbitop {__version__}\n"), r.stderr


def test_install_tree_refuses_root_and_missing_destdir(tmp_path):
    for args in ([], [""], ["/"], ["//"], ["/usr/.."], [str(tmp_path), "extra"]):
        r = subprocess.run(["bash", str(PKG / "install-tree.sh"), *args], capture_output=True, text=True)
        assert r.returncode == 2, args
