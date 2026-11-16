# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = "io.github.zappelmann_sketch.orbitop"
METAINFO = ROOT / "data" / f"{APP}.metainfo.xml"
SVG = ROOT / "data" / "icons" / f"{APP}.svg"
SCRIPT = ROOT / "scripts" / "install-user.sh"


def run_install(home, *args, script=SCRIPT, env=None):
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True,
                          env={**os.environ, "HOME": str(home), **(env or {})})


def expected(home):
    return [home / ".local/share/applications" / f"{APP}.desktop",
            home / ".local/share/icons/hicolor/scalable/apps" / f"{APP}.svg",
            home / ".config/autostart" / f"{APP}.desktop"]


def exec_line(path):
    return next(ln for ln in path.read_text().splitlines() if ln.startswith("Exec="))[5:]


def unescape_exec(value):
    """Desktop Entry Spec: string-value unescape (\\\\ -> \\), then quoted-argument parsing."""
    out, i = "", 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value) and value[i + 1] == "\\":
            out += "\\"
            i += 2
        else:
            out += value[i]
            i += 1
    args, cur, inq, i, started = [], "", False, 0, False
    while i < len(out):
        c = out[i]
        if inq and c == "\\" and i + 1 < len(out):
            cur += out[i + 1]
            i += 2
            continue
        if c == '"':
            inq, started = not inq, True
        elif c == " " and not inq:
            if started or cur:
                args.append(cur)
            cur, started = "", False
        else:
            cur += c
        i += 1
    if started or cur:
        args.append(cur)
    return [a.replace("%%", "%") for a in args]


def test_install_creates_three_files(tmp_path):
    r = run_install(tmp_path)
    assert r.returncode == 0, r.stderr
    assert all(f.exists() for f in expected(tmp_path))


def test_autostart_is_hidden(tmp_path):
    run_install(tmp_path)
    auto = expected(tmp_path)[2].read_text()
    assert exec_line(expected(tmp_path)[2]).endswith(" --hidden")
    assert "X-GNOME-Autostart-enabled=true" in auto and "NoDisplay=true" in auto
    assert "--hidden" not in exec_line(expected(tmp_path)[0])


def test_exec_is_absolute_repo_path(tmp_path):
    run_install(tmp_path)
    assert unescape_exec(exec_line(expected(tmp_path)[0])) == [str(ROOT / "bin" / "orbitop")]


def repo_copy(tmp_path, name, with_bin=True):
    repo = tmp_path / name
    (repo / "scripts").mkdir(parents=True)
    (repo / "bin").mkdir()
    (repo / "data/icons").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts")
    shutil.copy(ROOT / "data" / f"{APP}.desktop", repo / "data")
    shutil.copy(SVG, repo / "data/icons")
    if with_bin:
        shutil.copy(ROOT / "bin/orbitop", repo / "bin")
    home = tmp_path / "home"
    home.mkdir()
    return repo, home


def test_exec_quoting_with_special_path(tmp_path):
    repo, home = repo_copy(tmp_path, 'my repo "q" $x `b` \\s %f')
    r = run_install(home, script=repo / "scripts/install-user.sh")
    assert r.returncode == 0, r.stderr
    d, _, a = expected(home)
    assert unescape_exec(exec_line(d)) == [str(repo / "bin/orbitop")]
    assert unescape_exec(exec_line(a)) == [str(repo / "bin/orbitop"), "--hidden"]
    assert "%%f" in exec_line(d)
    assert subprocess.run(["desktop-file-validate", str(d), str(a)]).returncode == 0


def test_refuses_newline_in_repo_path(tmp_path):
    repo, home = repo_copy(tmp_path, "evil\nNoDisplay=true")
    r = run_install(home, script=repo / "scripts/install-user.sh")
    assert r.returncode != 0
    assert not any(f.exists() for f in expected(home))


def test_refuses_missing_launcher(tmp_path):
    repo, home = repo_copy(tmp_path, "norepo", with_bin=False)
    r = run_install(home, script=repo / "scripts/install-user.sh")
    assert r.returncode != 0
    assert not any(f.exists() for f in expected(home))


def test_refuses_relative_home(tmp_path):
    r = run_install("relhome")
    assert r.returncode != 0


def test_rejects_extra_arguments(tmp_path):
    for args in (["--bogus"], ["--uninstall", "x"], ["x", "y"]):
        assert run_install(tmp_path, *args).returncode != 0
    assert not any(f.exists() for f in expected(tmp_path))


def test_installed_modes(tmp_path):
    run_install(tmp_path)
    assert [f.stat().st_mode & 0o777 for f in expected(tmp_path)] == [0o644] * 3


def test_script_is_executable():
    assert os.access(SCRIPT, os.X_OK)


def test_refuses_root(tmp_path):
    fake = tmp_path / "fakebin"
    fake.mkdir()
    (fake / "id").write_text("#!/bin/sh\necho 0\n")
    (fake / "id").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    r = run_install(home, env={"PATH": f"{fake}:{os.environ['PATH']}"})
    assert r.returncode != 0
    assert not any(f.exists() for f in expected(home))


def test_refuses_without_home():
    env = {k: v for k, v in os.environ.items() if k != "HOME"}
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)
    assert r.returncode != 0


def test_idempotent(tmp_path):
    run_install(tmp_path)
    first = [f.read_text() for f in expected(tmp_path)]
    assert run_install(tmp_path).returncode == 0
    assert [f.read_text() for f in expected(tmp_path)] == first


def test_uninstall_removes_only_ours(tmp_path):
    other = tmp_path / ".config/autostart/other.desktop"
    other.parent.mkdir(parents=True)
    other.write_text("x")
    run_install(tmp_path)
    assert run_install(tmp_path, "--uninstall").returncode == 0
    assert not any(f.exists() for f in expected(tmp_path))
    assert other.read_text() == "x"
    assert run_install(tmp_path, "--uninstall").returncode == 0


def test_desktop_files_validate(tmp_path):
    run_install(tmp_path)
    for f in (expected(tmp_path)[0], expected(tmp_path)[2], ROOT / "data" / f"{APP}.desktop"):
        r = subprocess.run(["desktop-file-validate", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


def test_template_fields():
    t = (ROOT / "data" / f"{APP}.desktop").read_text()
    for s in ["Name=orbitop", "Exec=orbitop", f"Icon={APP}", f"StartupWMClass={APP}",
              "Categories=System;Monitor;", "StartupNotify=true", "Terminal=false",
              "Comment[de]=", "Keywords[de]="]:
        assert s in t


def test_metainfo_validates():
    r = subprocess.run(["appstreamcli", "validate", "--no-net", str(METAINFO)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_install_script_shellcheck():
    assert subprocess.run(["shellcheck", str(SCRIPT)]).returncode == 0


def test_svg_is_clean():
    s = SVG.read_text().lower()
    assert "<script" not in s and "href=" not in s and "#4fd8ff" in s
