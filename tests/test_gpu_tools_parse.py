# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Ausgabe der Werkzeuge zerlegen: JSON-Strom von intel_gpu_top, CSV-Zeilen von nvidia-smi."""
import json
from pathlib import Path

import pytest

from orbitop import gpu_tools
from orbitop.gpu_tools import parse_intel, parse_nvidia_line, split_json_stream, split_lines

FIX = Path(__file__).parent / "fixtures" / "tools"


def test_split_and_parse_recorded_intel():
    with open(FIX / "intel_gpu_top.json") as f:
        objs = list(split_json_stream(f))
    assert len(objs) >= 2
    s = parse_intel(objs[-1])
    assert 0 <= s["busy"] <= 100 and s["freq_mhz"] >= 0


def test_parse_intel_old_engine_names():
    assert parse_intel({"engines": {"Render/3D/0": {"busy": 12.5}}})["busy"] == 12.5


def test_parse_intel_missing_fields():
    assert parse_intel({}) == {"busy": None, "freq_mhz": None, "gpu_w": None, "pkg_w": None}


def test_split_clients_block_with_hostile_names():
    with open(FIX / "intel_gpu_top_clients.json") as f:
        objs = list(split_json_stream(f))
    assert [parse_intel(o)["busy"] for o in objs] == [0.0, 1.004995, 2.733251]
    assert [parse_intel(o)["freq_mhz"] for o in objs] == [0.0, 7.848317, 4.919986]
    assert [parse_intel(o)["pkg_w"] for o in objs] == [21.701609, 10.824967, 12.486207]
    assert all("clients" not in o for o in objs)


def test_split_clients_not_last_member():
    lines = ['{\n', '\t"clients": {\n', '\t\t"1": {"name": "a"b"},\n', '\t},\n', '\t"x": 1\n', '}\n']
    assert list(split_json_stream(lines)) == [{"x": 1}]


def test_split_newline_in_name_does_not_freeze():
    bad = ['{\n', '\t"engines": {"R": {"busy": 1}},\n', '\t"clients": {\n', '\t\t"1": {\n',
           '\t\t\t"name": "x\n', '}\n', '{\n', '",\n', '\t\t}\n', '\t}\n', '}\n']
    good = ['{\n', '\t"engines": {"R": {"busy": 9}}\n', '}\n']
    assert list(split_json_stream(bad + good))[-1] == {"engines": {"R": {"busy": 9}}}


def test_split_skips_malformed():
    assert list(split_json_stream(['{\n', '"a": }\n', '},\n', '{\n', '"b": 1\n', '}\n'])) == [{"b": 1}]


def test_split_drops_oversized_object_and_resyncs():
    big = ['{\n'] + ['\t"x": "' + "a" * 65000 + '",\n'] * 20 + ['}\n', '{\n', '"ok": 1\n', '}\n']
    assert list(split_json_stream(big)) == [{"ok": 1}]


def test_split_deep_nesting_does_not_raise():
    deep = ['{\n', '"a": ' + "[" * 300000 + "]" * 300000 + '\n', '}\n', '{\n', '"ok": 1\n', '}\n']
    assert list(split_json_stream(deep)) == [{"ok": 1}]


def test_parse_non_finite_is_none():
    d = parse_intel(json.loads('{"engines": {"R": {"busy": NaN}}, "power": {"GPU": Infinity}}'))
    assert d["busy"] is None and d["gpu_w"] is None
    n = parse_nvidia_line("00000000:01:00.0, X, nan, inf, -inf, 1, 2, 3, 4")
    assert n["busy"] is None and n["vram_used"] is None and n["vram_total"] is None and n["temp_c"] == 1.0


def test_parse_intel_max_over_engines():
    assert parse_intel({"engines": {"A": {"busy": 1}, "B": {"busy": 50}}})["busy"] == 50


def test_parse_nvidia_pci_normalized():
    assert parse_nvidia_line("00000000:0A:00.0, X, 1, 1, 1, 1, 1, 1, 1")["pci"] == "0000:0a:00.0"


def test_parse_nvidia_na():
    d = parse_nvidia_line("00000000:01:00.0, NVIDIA GeForce GTX 1080, 18, 3379, 8192, 54, [N/A], 607, 1911")
    assert d["pci"] == "0000:01:00.0" and d["power_w"] is None and d["busy"] == 18.0
    assert d["name"] == "NVIDIA GeForce GTX 1080" and d["vram_total"] == 8192.0 and d["freq_max_mhz"] == 1911.0
    assert set(d) == {"pci", "name", "busy", "vram_used", "vram_total", "temp_c", "power_w", "freq_mhz", "freq_max_mhz"}


def test_nvidia_query_matches_parser():
    query = gpu_tools._nvidia_cmd("/usr/bin/nvidia-smi")[1].removeprefix("--query-gpu=").split(",")
    assert len(query) == 9 and "fan.speed" not in query  # nur abgefragt, was eine Kachel zeigt
    assert parse_nvidia_line(", ".join(["00000000:01:00.0", "X"] + ["1"] * 7))["busy"] == 1.0


def test_parse_nvidia_fixture_not_supported():
    with open(FIX / "nvidia-smi.csv") as f:
        lines = list(split_lines(f))
    assert parse_nvidia_line(lines[1])["freq_max_mhz"] is None
    with pytest.raises(ValueError):
        parse_nvidia_line("kaputt")


def test_brace_prefixed_line_in_name_keeps_object():
    lines = ['{\n', '\t"engines": {"R": {"busy": 3}},\n', '\t"clients": {\n', '\t\t"1": {\n',
             '\t\t\t"name": "x\n', '{y",\n', '\t\t\t"n2": "p\n', '\t{\n', 'q",\n', '\t\t}\n', '\t}\n', '}\n']
    assert list(split_json_stream(lines)) == [{"engines": {"R": {"busy": 3}}}]
