# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Autostart je Benutzer: Vorrang der Benutzerdatei, Hidden, seltsame Dateien, atomares Schreiben (Review Focus 2, 3)."""
import os
import threading
from pathlib import Path

import pytest

from orbitop import APP_ID, autostart, userfile
from orbitop.autostart import FILE, OVERRIDE, TEMPLATE, set_enabled, state, system_paths, user_path

REPO = Path(__file__).resolve().parent.parent
not_root = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")


def which(name):
    return "/usr/bin/" + name if name == "orbitop" else None


def nowhere(_name):
    return None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # selbst ein Fehler führt nie in den echten Autostart-Ordner
    return {"XDG_CONFIG_HOME": str(tmp_path / "cfg"), "XDG_CONFIG_DIRS": f"{tmp_path / 'xdg1'}:{tmp_path / 'xdg2'}"}


def user(env) -> Path:
    return Path(env["XDG_CONFIG_HOME"]) / "autostart" / FILE


def system(env, i, text) -> Path:
    p = Path(env["XDG_CONFIG_DIRS"].split(":")[i]) / "autostart" / FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def put_user(env, text) -> Path:
    p = user(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_template_matches_data_file():  # K5
    assert (REPO / "data" / "autostart.desktop").read_bytes() == TEMPLATE.encode("utf-8")
    lines = TEMPLATE.splitlines()
    assert lines[:2] == ["# SPDX-License-Identifier: GPL-3.0-or-later", "# Copyright © 2026 zappelmann-sketch"]
    assert {"[Desktop Entry]", "Type=Application", "Name=orbitop", "Exec=orbitop --hidden", "TryExec=orbitop",
            f"Icon={APP_ID}", "X-GNOME-Autostart-enabled=true", "NoDisplay=true"} <= set(lines)
    assert OVERRIDE == "[Desktop Entry]\nType=Application\nName=orbitop\nHidden=true\n"
    assert FILE == APP_ID + ".desktop"


def test_state_none_without_command(env):  # Review Focus 3: Checkout ohne Paket
    put_user(env, TEMPLATE)
    system(env, 0, TEMPLATE)
    assert state(env, nowhere) is None
    assert set_enabled(False, env, nowhere) is None and user(env).read_text() == TEMPLATE  # nichts geschrieben


def test_on_writes_template(env):
    assert state(env, which) is False
    assert set_enabled(True, env, which) is True
    assert user(env).read_text() == TEMPLATE and os.listdir(user(env).parent) == [FILE]  # keine tmp-Datei
    assert state(env, which) is True


def test_off_removes_user_file(env):
    set_enabled(True, env, which)
    assert set_enabled(False, env, which) is False and os.listdir(user(env).parent) == []
    assert set_enabled(False, env, which) is False  # fehlt sie schon, ist das kein Fehler


def test_off_with_system_entry_writes_override(env):
    sys_file = system(env, 1, TEMPLATE)
    assert state(env, which) is True
    assert set_enabled(False, env, which) is False
    assert user(env).read_text() == OVERRIDE and sys_file.read_text() == TEMPLATE
    assert set_enabled(True, env, which) is True and user(env).read_text() == TEMPLATE  # Benutzerdatei überschrieben


def test_on_with_active_system_entry_writes_nothing(env):
    system(env, 0, TEMPLATE)
    assert set_enabled(True, env, which) is True and not user(env).parent.exists()


def test_on_with_disabled_system_entry_writes_template(env):
    system(env, 0, OVERRIDE)
    assert set_enabled(True, env, which) is True and user(env).read_text() == TEMPLATE


@pytest.mark.parametrize("text,on", [
    (TEMPLATE, True),
    (OVERRIDE, False),
    (TEMPLATE.replace("X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-enabled=false"), False),
    ("[Desktop Entry]\nExec=orbitop\nHidden = true\n", False),  # Leerraum um = zählt nicht
    ("[Desktop Entry]\nExec=orbitop\nHidden=false\n", True),
    ("[Desktop Entry]\nExec=orbitop\n[Desktop Action a]\nHidden=true\nX-GNOME-Autostart-enabled=false\n", True),
    ("# Hidden=true\n[Desktop Entry]\nExec=orbitop\n", True),  # Kommentar
    ("", False),  # ohne Gruppe [Desktop Entry] kein gültiger Eintrag
    ("garbage\n", False),
    ("[Desktop Action a]\nExec=orbitop\n", False),
])
def test_hidden_and_gnome_disabled_count_as_off(env, text, on):
    put_user(env, text)
    assert state(env, which) is on


def test_user_file_and_first_system_dir_take_precedence(env):  # freedesktop: nur die Datei im wichtigsten Ordner
    system(env, 0, OVERRIDE)
    system(env, 1, TEMPLATE)
    assert state(env, which) is False
    put_user(env, TEMPLATE)
    assert state(env, which) is True


def test_relative_xdg_config_home_ignored(env, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rel = {"XDG_CONFIG_HOME": "rel", "XDG_CONFIG_DIRS": f"rel2:{tmp_path / 'xdg'}"}
    home = tmp_path / "home" / ".config" / "autostart" / FILE
    assert user_path(rel) == str(home) and user_path({}) == str(home)
    assert system_paths(rel) == [str(tmp_path / "xdg" / "autostart" / FILE)]
    assert system_paths({}) == system_paths({"XDG_CONFIG_DIRS": ""}) == ["/etc/xdg/autostart/" + FILE]
    assert set_enabled(True, rel, which) is True and home.read_text() == TEMPLATE
    assert not (tmp_path / "rel").exists() and not (tmp_path / "rel2").exists()


@pytest.mark.parametrize("home", ["rel", "~"])
@pytest.mark.parametrize("xdg", [{}, {"XDG_CONFIG_HOME": "cfg"}])
def test_relative_home_gives_none_and_writes_nothing(tmp_path, monkeypatch, home, xdg):  # Audit M1
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("HOME", home)
    rel = {**xdg, "XDG_CONFIG_DIRS": str(tmp_path / "xdg")}
    system(rel, 0, TEMPLATE)
    assert user_path(rel) is None and state(rel, which) is None
    assert set_enabled(True, rel, which) is None and set_enabled(False, rel, which) is None
    assert os.listdir(cwd) == []


def weird(p: Path, make: str, tmp_path: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if make == "fifo":
        os.mkfifo(p)
    elif make == "oversized":
        p.write_text(TEMPLATE + "#" * (autostart.MAX_BYTES - len(TEMPLATE.encode()) + 1))
    elif make == "symlink-to-dir":
        (tmp_path / "somedir").mkdir()
        p.symlink_to(tmp_path / "somedir")
    elif make == "unreadable":
        p.write_text(TEMPLATE)
        p.chmod(0)


def in_thread(fn):
    out = []
    t = threading.Thread(target=lambda: out.append(fn()), daemon=True)
    t.start()
    t.join(2)
    assert not t.is_alive(), "hängt"
    return out[0]


@pytest.mark.parametrize("make", ["fifo", "oversized", "symlink-to-dir", pytest.param("unreadable", marks=not_root)])
def test_fifo_and_oversized_and_symlink_to_dir_are_absent(env, tmp_path, make):  # Review Focus 2
    system(env, 1, OVERRIDE)
    weird(user(env), make, tmp_path)  # gälte die Benutzerdatei, wäre der Eintrag an (oder läse ewig)
    assert in_thread(lambda: state(env, which)) is False
    assert in_thread(lambda: set_enabled(True, env, which)) is True  # das Seltsame wird ersetzt, nicht gelesen
    assert user(env).is_file() and not user(env).is_symlink() and user(env).read_text() == TEMPLATE
    assert os.listdir(user(env).parent) == [FILE]
    if make == "symlink-to-dir":
        assert os.listdir(tmp_path / "somedir") == []


@pytest.mark.parametrize("make", ["fifo", "oversized", "symlink-to-dir", pytest.param("unreadable", marks=not_root)])
def test_strange_system_entry_is_absent(env, tmp_path, make):  # Review Focus 2: /etc/xdg/autostart
    weird(Path(env["XDG_CONFIG_DIRS"].split(":")[0]) / "autostart" / FILE, make, tmp_path)
    system(env, 1, TEMPLATE)
    assert in_thread(lambda: state(env, which)) is True  # der zweite Ordner gilt


def test_exactly_max_bytes_is_read(env):
    put_user(env, OVERRIDE + "#" * (autostart.MAX_BYTES - len(OVERRIDE)))
    assert user(env).stat().st_size == autostart.MAX_BYTES and state(env, which) is False


def test_write_replaces_symlink_not_target(env, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("x")
    user(env).parent.mkdir(parents=True)
    user(env).symlink_to(elsewhere)
    assert set_enabled(True, env, which) is True
    assert elsewhere.read_text() == "x" and user(env).is_file() and not user(env).is_symlink()
    os.unlink(user(env))
    user(env).symlink_to(elsewhere)
    assert set_enabled(False, env, which) is False  # ohne Systemeintrag: nur der Link verschwindet
    assert elsewhere.read_text() == "x" and not os.path.lexists(user(env))


@pytest.mark.parametrize("how", [pytest.param("readonly", marks=not_root), "replace-fails", "target-is-directory"])
def test_failed_write_keeps_state_and_leaves_no_tmp(env, monkeypatch, how):
    d = user(env).parent
    if how == "target-is-directory":
        user(env).mkdir(parents=True)
        assert set_enabled(True, env, which) is False and os.listdir(d) == [FILE] and user(env).is_dir()
        return
    set_enabled(True, env, which)
    system(env, 0, OVERRIDE)
    if how == "replace-fails":
        def boom(a, b):
            raise OSError("x")
        monkeypatch.setattr(userfile.os, "replace", boom)
        assert set_enabled(False, env, which) is True
    else:
        d.chmod(0o500)
        try:
            assert set_enabled(False, env, which) is True  # OVERRIDE schreiben scheitert
            os.unlink(Path(env["XDG_CONFIG_DIRS"].split(":")[0]) / "autostart" / FILE)
            assert set_enabled(False, env, which) is True  # Entfernen scheitert
        finally:
            d.chmod(0o700)
    assert os.listdir(d) == [FILE] and user(env).read_text() == TEMPLATE
