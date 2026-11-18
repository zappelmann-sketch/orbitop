# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Dateihelfer für layout.py und autostart.py: XDG-Basis, sicheres Lesen, atomares Schreiben."""
import os
import threading

import pytest

from orbitop import userfile
from orbitop.userfile import config_home, read_regular, write_atomic


@pytest.mark.parametrize("home,env,want", [
    ("/home/u", {"XDG_CONFIG_HOME": "/x/cfg"}, "/x/cfg"),
    ("/home/u", {"XDG_CONFIG_HOME": "cfg"}, "/home/u/.config"),  # XDG: relative Werte ignorieren
    ("/home/u", {}, "/home/u/.config"),
    ("rel", {}, None),  # sonst landete alles unter dem Arbeitsverzeichnis
    ("~", {"XDG_CONFIG_HOME": "cfg"}, None),
    ("rel", {"XDG_CONFIG_HOME": "/x/cfg"}, "/x/cfg"),
])
def test_config_home(monkeypatch, home, env, want):
    monkeypatch.setenv("HOME", home)
    assert config_home(env) == want


def test_read_regular_limit_and_symlink(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"x" * 8)
    assert read_regular(str(p), 8) == b"x" * 8 and read_regular(str(p), 7) is None
    (tmp_path / "link").symlink_to(p)  # ein Symlink auf eine reguläre Datei ist erlaubt
    assert read_regular(str(tmp_path / "link"), 8) == b"x" * 8


@pytest.mark.parametrize("make", ["fifo", "directory", "missing"])
def test_read_regular_rejects_non_regular_without_hanging(tmp_path, make):
    p = tmp_path / "f"
    if make == "fifo":
        os.mkfifo(p)
    elif make == "directory":
        p.mkdir()
    out = []
    t = threading.Thread(target=lambda: out.append(read_regular(str(p), 100)), daemon=True)
    t.start()
    t.join(2)
    assert not t.is_alive() and out == [None]


def test_write_atomic_creates_private_dir_and_replaces_symlink_itself(tmp_path):
    target = tmp_path / "elsewhere"
    target.write_text("x")
    p = tmp_path / "a" / "b" / "f"
    assert write_atomic(str(p), "eins") and p.read_text() == "eins"
    assert (tmp_path / "a" / "b").stat().st_mode & 0o777 == 0o700  # makedirs: mode gilt für den letzten Ordner
    os.unlink(p)
    p.symlink_to(target)
    assert write_atomic(str(p), "zwei") and p.read_text() == "zwei" and not p.is_symlink()
    assert target.read_text() == "x" and os.listdir(p.parent) == ["f"]


@pytest.mark.parametrize("how", ["replace-fails", "target-is-directory",
                                 pytest.param("readonly", marks=pytest.mark.skipif(
                                     os.geteuid() == 0, reason="root ignores directory permissions"))])
def test_write_atomic_failure_returns_false_and_leaves_no_tmp(tmp_path, monkeypatch, how):
    d = tmp_path / "d"
    d.mkdir()
    p = d / "f"
    if how == "replace-fails":
        def boom(a, b):
            raise OSError("x")
        monkeypatch.setattr(userfile.os, "replace", boom)
    elif how == "target-is-directory":
        p.mkdir()
    else:
        d.chmod(0o500)
    try:
        assert write_atomic(str(p), "x") is False
    finally:
        d.chmod(0o700)
    assert os.listdir(d) == (["f"] if how == "target-is-directory" else [])
