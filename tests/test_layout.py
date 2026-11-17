# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import json
import os
import threading
from pathlib import Path

import pytest

from orbitop import layout
from orbitop.layout import COLUMNS, DEFAULT_HIDDEN, LayoutFile, config_path, repair, validate

L = {"order": list(COLUMNS), "hidden": list(DEFAULT_HIDDEN), "widths": {"cpu": 90}, "split": 0.6}


def test_validate_accepts_contract_and_bounds():
    assert validate(L) == L and validate({**L, "path": "/etc/x"}) == L
    assert validate({**L, "widths": {"cpu": 40, "process": 1200}, "split": 0.2}) is not None
    assert validate({**L, "split": 0.8}) is not None


@pytest.mark.parametrize("bad", [
    {"order": [c for c in COLUMNS if c != "time"]}, {"order": [*COLUMNS[:-1], "pid"]},
    {"order": [*COLUMNS, "gpu"]}, {"order": "pid"}, {"hidden": ["process"]}, {"hidden": ["gpu"]},
    {"hidden": ["pri", "pri"]}, {"hidden": [1]}, {"widths": {"cpu": 39}}, {"widths": {"cpu": 1201}},
    {"widths": {"cpu": 90.0}}, {"widths": {"cpu": True}}, {"widths": {"cpu": "90"}}, {"widths": {"gpu": 90}},
    {"widths": [90]}, {"split": 0.19}, {"split": 0.81}, {"split": True}, {"split": "0.5"},
    {"split": float("nan")}, {"split": 10**400}, {"split": float("inf")}, {"split": None}])
def test_validate_rejects(bad):
    assert validate({**L, **bad}) is None


def test_validate_needs_all_keys():
    assert validate({k: v for k, v in L.items() if k != "split"}) is None and validate([L]) is None


def test_repair_drops_unknown_and_adds_missing_at_default_place():
    old = {"order": [c for c in COLUMNS if c != "time"] + ["gpu"], "hidden": ["pri", "gpu"],
           "widths": {"gpu": 50, "cpu": 70}, "split": 0.5}
    r = repair(old)
    assert r["order"] == list(COLUMNS) and "time" in r["hidden"] and "gpu" not in r["hidden"]
    assert r["widths"] == {"cpu": 70}


def test_repair_keeps_users_order_and_strict_after():
    r = repair({**L, "order": ["process", *[c for c in COLUMNS if c not in ("process", "mem")]]})
    assert r["order"][0] == "process" and r["order"].index("mem") == r["order"].index("s") + 1
    assert r["hidden"].count("mem") == 1 and repair({**L, "hidden": ["process"]}) is None


def test_config_path(monkeypatch):
    assert config_path({"XDG_CONFIG_HOME": "/x/cfg"}) == "/x/cfg/orbitop/layout.json"
    monkeypatch.setenv("HOME", "/home/u")
    assert config_path({}) == config_path({"XDG_CONFIG_HOME": "cfg"}) == "/home/u/.config/orbitop/layout.json"


@pytest.mark.parametrize("make", ["missing", "truncated", "oversize", "directory", "fifo", "link-to-fifo",
                                  "not-a-dict", "huge-split", "deep"])
def test_load_bad_file_is_none_without_hanging(tmp_path, make):  # Review Focus 1
    p = tmp_path / "layout.json"
    if make == "truncated":
        p.write_text(json.dumps(L)[:30])
    elif make == "oversize":
        p.write_text(json.dumps({**L, "pad": "x" * 5000}))
    elif make == "directory":
        p.mkdir()
    elif make == "fifo":
        os.mkfifo(p)
    elif make == "link-to-fifo":
        os.mkfifo(tmp_path / "f")
        p.symlink_to(tmp_path / "f")
    elif make == "huge-split":
        p.write_text(json.dumps({**L, "split": 10**400}))
    elif make == "deep":
        p.write_text("[" * 4000)
    elif make == "not-a-dict":
        p.write_text("[1, 2]")
    f = LayoutFile(str(p))
    f.current = L
    result = []
    t = threading.Thread(target=lambda: result.append(f.load()), daemon=True)
    t.start()
    t.join(2)
    assert not t.is_alive() and result == [None] and f.current is None


def test_load_valid_and_repaired(tmp_path):
    p = tmp_path / "layout.json"
    p.write_text(json.dumps(L))
    assert LayoutFile(str(p)).load() == L
    old = {**L, "order": [c for c in COLUMNS if c != "time"], "hidden": []}
    p.write_text(json.dumps(old))
    r = LayoutFile(str(p)).load()
    assert r["order"] == list(COLUMNS) and r["hidden"] == ["time"]


def test_load_symlink_to_regular_file_is_allowed(tmp_path):
    (tmp_path / "real.json").write_text(json.dumps(L))
    (tmp_path / "layout.json").symlink_to(tmp_path / "real.json")
    assert LayoutFile(str(tmp_path / "layout.json")).load() == L


def test_save_atomic_only_when_changed(tmp_path, monkeypatch):
    calls = []
    real = layout.os.replace
    monkeypatch.setattr(layout.os, "replace", lambda a, b: calls.append(b) or real(a, b))
    f = LayoutFile(str(tmp_path / "cfg" / "orbitop" / "layout.json"))
    assert f.save(L) and not f.save(dict(L)) and len(calls) == 1
    assert json.loads(Path(f.path).read_text()) == L and os.listdir(Path(f.path).parent) == ["layout.json"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_save_failure_is_silent(tmp_path):  # Review Focus 1
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    try:
        f = LayoutFile(str(d / "orbitop" / "layout.json"))
        assert f.save(L) is False and f.current == L
    finally:
        d.chmod(0o700)


def test_repair_missing_visible_stays_visible_and_first_goes_to_front():
    r = repair({**L, "order": [c for c in COLUMNS if c not in ("cpu", "pid")]})
    assert r["order"] == list(COLUMNS) and "cpu" not in r["hidden"] and "pid" not in r["hidden"]


def test_save_failure_leaves_no_temp_file(tmp_path, monkeypatch):
    def boom(a, b):
        raise OSError("x")
    monkeypatch.setattr(layout.os, "replace", boom)
    f = LayoutFile(str(tmp_path / "orbitop" / "layout.json"))
    assert f.save(L) is False and os.listdir(tmp_path / "orbitop") == []
