# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""packaging/install-tree.sh: der Dateibaum des Hauptpakets, für alle Formate gleich."""
import os
import stat
import subprocess
import sys

import pytest

from orbitop import __version__, counterhelper
from tests.packaging_common import APP, PKG, ROOT

SHARE = "/usr/share/orbitop/"
RULE = "/usr/lib/udev/rules.d/70-orbitop-counters.rules"  # B2.3: unter /usr/lib, nie unter /etc/udev
HELPERS = {"/usr/lib/orbitop/killhelper": "killhelper.py", "/usr/lib/orbitop/counterhelper": "counterhelper.py"}


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
        *HELPERS,
        RULE,
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
    executables = {*HELPERS, SHARE + "bin/orbitop", *(SHARE + "orbitop/" + h for h in HELPERS.values())}
    for p in tree.rglob("*"):
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            continue
        name = "/" + str(p.relative_to(tree))
        want = 0o755 if stat.S_ISDIR(st.st_mode) or name in executables else 0o644
        want = 0o711 if name == "/etc/orbitop" else want  # B2.2: nur root darf ihn öffnen und das Lock halten
        assert stat.S_IMODE(st.st_mode) == want, name


def test_helper_copies_identical_and_executable(tree):
    for installed, source in HELPERS.items():
        helper = tree / installed.lstrip("/")
        assert helper.read_bytes() == (ROOT / "orbitop" / source).read_bytes(), source
        assert stat.S_IMODE(os.lstat(helper).st_mode) == 0o755
        assert helper.read_text().startswith("#!/usr/bin/python3 -IS\n")  # pkexec startet ihn direkt (K1)


def test_marker_directory_comes_empty_from_the_package(tree):  # B2.2: nur der Helfer legt die Merkdatei an
    etc = tree / "etc"
    assert sorted(p.relative_to(tree).as_posix() for p in etc.rglob("*")) == ["etc/orbitop"]
    assert os.path.dirname(counterhelper.MARKER) == "/etc/orbitop"
    assert stat.S_ISDIR(os.lstat(etc / "orbitop").st_mode) and not os.listdir(etc / "orbitop")
    assert stat.S_IMODE(os.lstat(etc / "orbitop").st_mode) == 0o711  # ohne g/o-Lesen kein fremdes flock (I-1)


def test_data_files_identical(tree):  # Starter, Vorlage, polkit-Datei und Regel unverändert aus data/ und bin/
    for src, dst in (("bin/orbitop", SHARE + "bin/orbitop"), ("data/autostart.desktop", SHARE + "autostart.desktop"),
                     ("data/io.github.zappelmann-sketch.orbitop.policy",
                      "/usr/share/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy"),
                     ("data/70-orbitop-counters.rules", RULE)):
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
