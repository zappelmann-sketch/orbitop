# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Dateien in data/, die die Pakete installieren: Starter, Autostart-Vorlage, AppStream, Symbol."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = "io.github.zappelmann_sketch.orbitop"
METAINFO = ROOT / "data" / f"{APP}.metainfo.xml"
SVG = ROOT / "data" / "icons" / f"{APP}.svg"


def test_desktop_files_validate():
    for f in (ROOT / "data" / f"{APP}.desktop", ROOT / "data" / "autostart.desktop"):
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


def test_svg_is_clean():
    s = SVG.read_text().lower()
    assert "<script" not in s and "href=" not in s and "#4fd8ff" in s
