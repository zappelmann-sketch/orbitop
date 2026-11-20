# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Start ohne Fenster: snapshot_path, check_runtime, Paketverwaltung, main und bin/orbitop."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from orbitop import app
from orbitop.app import check_runtime, snapshot_path
from orbitop.i18n import load_texts

REPO = Path(__file__).resolve().parent.parent


# ---- snapshot_path ----
def test_snapshot_path(tmp_path):
    good = str(tmp_path / "shot.png")
    assert snapshot_path(good) == good
    assert snapshot_path(None) is None and snapshot_path("") is None
    assert snapshot_path(str(tmp_path / "shot.jpg")) is None
    assert snapshot_path(str(tmp_path / "missing" / "shot.png")) is None
    assert snapshot_path(str(tmp_path)) is None


# ---- check_runtime / main / bin ----
def _clear_lang(monkeypatch, lang):
    for k in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LANG", lang)


@pytest.mark.parametrize("missing,package", [("WebKit", "gir1.2-webkit-6.0"), ("Gtk", "gir1.2-gtk-4.0")])
def test_check_runtime_reports_missing_package(tmp_path, monkeypatch, missing, package):  # Review Focus 5
    _clear_lang(monkeypatch, "en_US.UTF-8")
    calls = []

    def req(ns, v):
        calls.append((ns, v))
        if ns == missing:
            raise ValueError(f"Namespace {ns} not available")
    msg = check_runtime(req, root=str(tmp_path))
    assert package in msg
    assert msg == load_texts("en")["error.runtime_missing"].format(package=package,
                                                                   command=f"sudo apt install {package}")
    assert ("Gtk", "4.0") in calls


def test_check_runtime_speaks_german(tmp_path, monkeypatch):
    _clear_lang(monkeypatch, "de_DE.UTF-8")

    def req(ns, v):
        if ns == "WebKit":
            raise ValueError("Namespace WebKit not available")
    msg = check_runtime(req, root=str(tmp_path))
    fmt = {"package": "gir1.2-webkit-6.0", "command": "sudo apt install gir1.2-webkit-6.0"}
    assert msg == load_texts("de")["error.runtime_missing"].format(**fmt)
    assert msg != load_texts("en")["error.runtime_missing"].format(**fmt)


def test_check_runtime_ok():
    calls = []
    assert check_runtime(lambda ns, v: calls.append((ns, v))) is None
    assert calls == [("Gtk", "4.0"), ("WebKit", "6.0")]


def test_check_runtime_reports_missing_pygobject(tmp_path, monkeypatch):
    _clear_lang(monkeypatch, "en_US.UTF-8")
    monkeypatch.setitem(sys.modules, "gi", None)  # import gi wirft dann ImportError
    assert check_runtime(root=str(tmp_path)) == load_texts("en")["error.runtime_missing"].format(
        package="python3-gi", command="sudo apt install python3-gi")


@pytest.mark.parametrize("text,where,manager", [
    ('ID=ubuntu\nID_LIKE=debian\n', "etc", "apt-get"), ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', "etc", "apt-get"),
    ('ID=fedora\n', "etc", "dnf"), ('ID=arch\n', "etc", "pacman"), ("ID='manjaro'\nID_LIKE=arch\n", "etc", "pacman"),
    ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n', "etc", "zypper"), ('ID=gentoo\n', "etc", "apt-get"),
    ('ID=fedora\n', "usr/lib", "dnf"), (None, None, "apt-get")])
def test_package_manager_from_os_release(tmp_path, text, where, manager):
    if text is not None:
        (tmp_path / where).mkdir(parents=True)
        (tmp_path / where / "os-release").write_text(text, encoding="utf-8")
    assert app.package_manager(str(tmp_path)) == manager


def test_package_manager_prefers_etc_over_usr_lib(tmp_path):  # os-release(5): /etc zuerst
    for where, text in (("etc", "ID=arch\n"), ("usr/lib", "ID=fedora\n")):
        (tmp_path / where).mkdir(parents=True)
        (tmp_path / where / "os-release").write_text(text, encoding="utf-8")
    assert app.package_manager(str(tmp_path)) == "pacman"


def test_check_runtime_names_package_of_running_distro(tmp_path, monkeypatch):
    _clear_lang(monkeypatch, "en_US.UTF-8")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "os-release").write_text("ID=fedora\n", encoding="utf-8")

    def req(ns, v):
        if ns == "WebKit":
            raise ValueError("Namespace WebKit not available")
    assert check_runtime(req, root=str(tmp_path)) == load_texts("en")["error.runtime_missing"].format(
        package="webkitgtk6.0", command="sudo dnf install webkitgtk6.0")


def test_check_runtime_python_too_old(tmp_path, monkeypatch):  # Review Focus 5
    _clear_lang(monkeypatch, "en_US.UTF-8")
    assert check_runtime(lambda *a: None, root=str(tmp_path), version=(3, 11, 2)) == \
        load_texts("en")["error.python_old"].format(version="3.11.2")


PY311 = shutil.which("python3.11", path="/usr/bin:/bin")  # im selben PATH wie der Aufruf


@pytest.mark.skipif(not PY311, reason="kein Python 3.11")
def test_python_3_11_gets_clear_message(tmp_path):  # Review Focus 5 (Debian 12)
    code = f"import sys; sys.path.insert(0, {str(REPO)!r}); from orbitop.app import main; sys.exit(main([]))"
    r = subprocess.run([PY311, "-I", "-B", "-c", code], capture_output=True, text=True, cwd=tmp_path,
                       env={"LANG": "en_US.UTF-8", "PATH": "/usr/bin:/bin"})
    assert (r.returncode, "3.12" in r.stderr, "Traceback" in r.stderr) == (2, True, False), r.stderr


@pytest.mark.parametrize("args,rc,out", [(["--version"], 0, "orbitop 0.2.0"), ([], 2, None)])
def test_without_pygobject_no_traceback(tmp_path, args, rc, out):
    out = out or app.PACKAGES[app.package_manager()][0]  # main liest das echte /etc/os-release
    code = (f"import sys; sys.path.insert(0, {str(REPO)!r}); sys.modules['gi'] = None; import orbitop.sampler; "
            "from orbitop.app import main; sys.exit(main(sys.argv[1:]))")
    r = subprocess.run([sys.executable, "-I", "-c", code, *args], capture_output=True, text=True, cwd=tmp_path)
    assert (r.returncode, out in r.stdout + r.stderr, "Traceback" in r.stderr) == (rc, True, False), r.stderr


def test_main_exit_2_without_webkit(monkeypatch, capsys):
    monkeypatch.setattr(app, "check_runtime", lambda *a: "Paket fehlt: x")
    assert app.main([]) == 2
    assert "Paket fehlt: x" in capsys.readouterr().err


def test_main_version_skips_runtime_check(monkeypatch, capsys):
    monkeypatch.setattr(app, "check_runtime", lambda *a: pytest.fail("kein Laufzeit-Check für --version"))
    assert app.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "orbitop 0.2.0"


def test_version_flag(tmp_path):
    r = subprocess.run([sys.executable, str(REPO / "bin" / "orbitop"), "--version"], capture_output=True, text=True,
                       cwd=tmp_path)
    assert r.stdout.strip() == "orbitop 0.2.0" and r.returncode == 0


def test_launcher_is_executable():
    assert os.access(REPO / "bin" / "orbitop", os.X_OK)
