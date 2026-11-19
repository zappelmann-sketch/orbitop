# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/dump-snapshot.py: Demo-Daten, Ansicht procs, Anonymisieren, Startoptionen."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.roots import INTEL
from tests.test_procs import make_proc


# dump-snapshot
SCRIPT = str(Path(__file__).parent.parent / "scripts" / "dump-snapshot.py")


def dump(*args, check=True):
    return subprocess.run([sys.executable, SCRIPT, "--root", INTEL, "--ticks", "2", "--interval", "0.05", *args],
                          capture_output=True, text=True, check=check)


def load_dump():
    import importlib.util
    spec = importlib.util.spec_from_file_location("dump_snapshot", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dump_snapshot_js(tmp_path):
    out = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "scripts" / "dump-snapshot.py"),
         "--root", INTEL, "--ticks", "2", "--interval", "0.05", "--js"],
        capture_output=True, text=True, check=True, env={"LANG": "de_DE.UTF-8", "PATH": "/usr/bin:/bin"}).stdout
    assert out.startswith("window.ORBITOP_DEMO = ") and out.rstrip().endswith("};")
    demo = json.loads(out[len("window.ORBITOP_DEMO = "):].rstrip().removesuffix(";"))
    assert demo["init"]["lang"] == "de" and demo["init"]["version"] and demo["init"]["texts"]["tab.procs"]
    assert demo["init"]["layout"] is None
    assert demo["tick"]["type"] == "tick" and len(demo["tick"]["tiles"]) == 8


def test_dump_view_procs_fills_detail(intel_copy):
    make_proc(Path(intel_copy), 7)
    out = subprocess.run([sys.executable, SCRIPT, "--root", intel_copy, "--ticks", "2", "--interval", "0.05",
                          "--view", "procs"], capture_output=True, text=True, check=True).stdout
    tick = json.loads(out)
    assert tick["procs"] and tick["detail"]["pid"] == max(tick["procs"], key=lambda r: r["cpu"])["pid"]
    assert json.loads(dump().stdout)["procs"] is None


# R30: Demodaten ohne echte Prozessnamen, Befehlszeilen und Benutzer
def test_dump_anonymize_removes_names_cmdlines_users(intel_copy):
    # gegenseitige Eltern: detail (erste Zeile, Reihenfolge je Dateisystem) hat immer einen geheimen Elternnamen
    make_proc(Path(intel_copy), 7, comm="geheim-kind", ppid=8, cmdline=b"/opt/geheim\0--token=xyz\0")
    make_proc(Path(intel_copy), 8, comm="geheim-eltern", ppid=7, cmdline=b"/opt/geheim-eltern\0--pass\0")
    out = subprocess.run([sys.executable, SCRIPT, "--root", intel_copy, "--ticks", "2", "--interval", "0.05",
                          "--view", "procs", "--anonymize"], capture_output=True, text=True, check=True).stdout
    tick = json.loads(out)
    assert "geheim" not in out and "token" not in out and "--pass" not in out
    rows = tick["procs"] + [tick["detail"], tick["top"]["mem"]] + tick["top"]["cpu"]
    assert {r["name"] for r in rows} <= {f"proc-{i}" for i in range(1, len(rows) + 1)}
    assert {r["user"] for r in tick["procs"]} == {"user"} and {r["args"] for r in tick["procs"]} == {""}
    d = tick["detail"]
    assert d["cmdline"] == d["name"] and d["parent"] in {r["name"] for r in tick["procs"]} - {d["name"]}


@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf", "x"])
def test_dump_rejects_bad_interval(bad):
    r = dump("--interval", bad, check=False)
    assert r.returncode == 2 and "interval" in r.stderr


def test_dump_fixture_root_starts_no_tools():
    # Mit Fixture-Baum liefert keine Werkzeug-Quelle Werte: kein pkg_w, also bleibt der RAPL-Hinweis stehen
    tick = json.loads(dump("--ticks", "5").stdout)
    assert tick["hints"] == ["hint.rapl_noperm"]


# N7: Fixture-Baum startet keine echten Werkzeuge (hostunabhängig)
def test_dump_fixture_root_spawns_no_tool(monkeypatch):
    import importlib.util
    from orbitop import gpu_tools
    spec = importlib.util.spec_from_file_location("dump_snapshot", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    started = []
    monkeypatch.setattr(gpu_tools.ToolReader, "start", lambda self: started.append(self._cmd))
    monkeypatch.setattr(gpu_tools.shutil, "which", lambda name, path=None: "/usr/bin/" + name)
    monkeypatch.setattr(gpu_tools, "_has_capability", lambda p: True)
    mod.main(["--root", INTEL, "--ticks", "1"])
    assert started == []


def test_anonymize_replaces_every_name_field():
    secret = "geheimname"
    brief = {"pid": 5, "start": 9, "name": secret, "cpu": 1.0, "rss": 1}
    row = {**brief, "args": secret + " --flag", "user": secret}
    tick = {"top": {"cpu": [dict(brief)], "mem": dict(brief)}, "procs": [dict(row)],
            "detail": {**row, "cmdline": secret + " --flag", "parent": secret}}
    out = load_dump().anonymize(tick)
    assert secret not in json.dumps(out)
    assert out["top"]["cpu"][0]["name"] == out["detail"]["parent"] == "proc-1"
    assert out["detail"]["user"] == "user" and out["procs"][0]["args"] == ""
