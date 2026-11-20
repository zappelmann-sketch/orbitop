# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Dateihelfer für layout.py und autostart.py: XDG-Basis, sicheres Lesen, atomares Schreiben."""
import errno
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
def test_config_home(home, env, want):
    assert config_home({**env, "HOME": home}) == want


def test_config_home_empty_home_is_none():
    assert config_home({"HOME": ""}) is None and config_home({"HOME": "", "XDG_CONFIG_HOME": ""}) is None


def test_config_home_never_reads_os_environ(monkeypatch):
    monkeypatch.setenv("HOME", "/home/other")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/other/cfg")
    assert config_home({"HOME": "/home/u"}) == "/home/u/.config" and config_home({}) is None


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
    assert write_atomic(str(p), "eins", "layout") and p.read_text() == "eins"
    assert (tmp_path / "a" / "b").stat().st_mode & 0o777 == 0o700
    os.unlink(p)
    p.symlink_to(target)
    assert write_atomic(str(p), "zwei", "layout") and p.read_text() == "zwei" and not p.is_symlink()
    assert target.read_text() == "x" and os.listdir(p.parent) == ["f"]


def test_write_atomic_creates_all_levels_0700(tmp_path):
    p = tmp_path / "a" / "b" / "c" / "f"
    old = os.umask(0o002)  # durchlässige umask wie unter Ubuntu: os.makedirs gäbe den oberen Ebenen dann 0775
    try:
        assert write_atomic(str(p), "x", "layout")
    finally:
        os.umask(old)
    assert [(tmp_path / d).stat().st_mode & 0o777 for d in ("a", "a/b", "a/b/c")] == [0o700] * 3


class BrokenStream:
    def __init__(self, exc):
        self.exc = exc

    def write(self, _text):
        raise self.exc


@pytest.mark.parametrize("exc", [BrokenPipeError(errno.EPIPE, "x"), OSError(errno.ENOSPC, "x"),
                                 ValueError("I/O operation on closed file.")], ids=["EPIPE", "ENOSPC", "closed"])
def test_write_error_report_survives_a_broken_stderr(tmp_path, monkeypatch, exc):
    """Sonst würfe LayoutFile.save, und der Autostart-Schalter bekäme nie seinen autostart_state."""
    monkeypatch.setattr(userfile, "_reported", set())
    monkeypatch.setattr(userfile.sys, "stderr", BrokenStream(exc))
    (tmp_path / "f").mkdir()  # os.replace auf einen Ordner scheitert
    assert write_atomic(str(tmp_path / "f"), "x", "layout") is False
    assert userfile.report_write_error("autostart", OSError(errno.EPERM, "x")) is None  # Weg von os.unlink


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
        assert write_atomic(str(p), "x", "layout") is False
    finally:
        d.chmod(0o700)
    assert os.listdir(d) == (["f"] if how == "target-is-directory" else [])
