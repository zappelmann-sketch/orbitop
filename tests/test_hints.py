# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Ausgeblendete Hinweise (Klärung Q1, Q2): $XDG_CONFIG_HOME/orbitop/hints.json, nur bekannte Schlüssel der
Fußzeile, atomar über userfile geschrieben."""
import json
import os
from pathlib import Path

import pytest

from orbitop import hints, i18n


@pytest.fixture
def env(tmp_path):
    return {"XDG_CONFIG_HOME": str(tmp_path / "cfg"), "HOME": "/home/u"}


def path(env):
    return os.path.join(env["XDG_CONFIG_HOME"], "orbitop", "hints.json")


def put(env, data: bytes):
    os.makedirs(os.path.dirname(path(env)), exist_ok=True)
    with open(path(env), "wb") as f:
        f.write(data)


def test_keys_are_the_footer_hints():  # Q2: genau diese fünf, und jeder hat einen Text
    assert hints.KEYS == ("hint.igt_failed", "hint.igt_missing", "hint.igt_noperm", "hint.nvsmi_missing",
                          "hint.rapl_noperm")
    assert set(hints.KEYS) <= set(i18n.load_texts("en"))


def test_no_file_gives_empty(env):
    assert hints.load(env) == [] and not os.path.exists(path(env))


def test_hide_writes_and_load_reads_back(env):
    assert hints.hide("hint.rapl_noperm", env) == ["hint.rapl_noperm"]
    assert hints.hide("hint.igt_missing", env) == ["hint.igt_missing", "hint.rapl_noperm"]
    assert hints.hide("hint.igt_missing", env) == ["hint.igt_missing", "hint.rapl_noperm"]  # kein zweites Mal
    assert json.loads(Path(path(env)).read_text()) == ["hint.igt_missing", "hint.rapl_noperm"]
    assert hints.load(env) == ["hint.igt_missing", "hint.rapl_noperm"]


def test_hide_writes_atomically_through_userfile(env, monkeypatch):
    seen, real = [], hints.write_atomic
    monkeypatch.setattr(hints, "write_atomic", lambda p, data, name: seen.append((p, data, name)) or real(p, data, name))
    hints.hide("hint.igt_noperm", env)
    hints.show_all(env)
    assert seen == [(path(env), '["hint.igt_noperm"]', "hints"), (path(env), "[]", "hints")]


def test_symlink_at_the_file_is_replaced_not_followed(env, tmp_path):  # write_atomic: os.replace ersetzt den Link
    target = tmp_path / "elsewhere"
    target.write_text("keep")
    os.makedirs(os.path.dirname(path(env)))
    os.symlink(target, path(env))
    hints.hide("hint.igt_failed", env)
    assert target.read_text() == "keep" and not os.path.islink(path(env))


def test_unknown_key_writes_nothing(env):
    assert hints.hide("hint.evil", env) == [] and hints.hide("footer.missing", env) == []
    assert not os.path.exists(os.path.dirname(path(env)))


@pytest.mark.parametrize("data", [b"{kaputt", b'{"hint.igt_missing": 1}', b'"hint.igt_missing"', b"null", b"",
                                  b"[" * 4000, b'["hint.igt_missing"' + b" " * 4096 + b"]", b"\xff\xfe\x00"],
                         ids=["syntax", "object", "string", "null", "empty", "deep", "oversize", "not-utf8"])
def test_broken_file_gives_empty(env, data):
    put(env, data)
    assert hints.load(env) == []


def test_directory_at_the_path_gives_empty(env):
    os.makedirs(path(env))
    assert hints.load(env) == []


def test_only_known_keys_survive_load(env):
    put(env, b'["hint.rapl_noperm", "hint.evil", 3, ["hint.igt_missing"], {"k": 1}, "hint.rapl_noperm", null]')
    assert hints.load(env) == ["hint.rapl_noperm"]


def test_show_all_empties_the_list(env):
    hints.hide("hint.nvsmi_missing", env)
    assert hints.show_all(env) == [] and hints.load(env) == []
    assert json.loads(Path(path(env)).read_text()) == []


def test_write_error_returns_the_state_on_disk(env, monkeypatch):
    hints.hide("hint.igt_missing", env)
    monkeypatch.setattr(hints, "write_atomic", lambda *a: False)
    assert hints.hide("hint.rapl_noperm", env) == ["hint.igt_missing"]  # an die Seite nur der Stand danach
    assert hints.show_all(env) == ["hint.igt_missing"]


def test_without_config_home_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = {"HOME": "rel"}  # sonst landete die Datei unter dem Arbeitsverzeichnis
    assert hints.hide("hint.igt_missing", env) == [] and hints.show_all(env) == [] and hints.load(env) == []
    assert os.listdir(tmp_path) == []
