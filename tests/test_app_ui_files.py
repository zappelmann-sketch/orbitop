# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""ui_file (orbitop://ui/…) und die Seite selbst: was ausgeliefert wird, CSP und Moduleinstieg."""
import os
from pathlib import Path

import pytest

from orbitop import app
from orbitop.app import ui_file

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "orbitop" / "ui"


# ---- ui_file (orbitop://ui/…) ----
@pytest.fixture
def ui(tmp_path):
    """UI-Baum mit je einer Datei pro Typ, einer unbekannten Endung, Unterordner und Symlinks nach innen und außen."""
    d = tmp_path / "ui"
    (d / "fonts").mkdir(parents=True)
    for name in ("index.html", "app.js", "style.css", "fonts/a.ttf", "fonts/b.otf", "fonts/c.woff2", "data.json",
                 "i.svg", "fonts/OFL.txt", "tool.py", "noext"):
        (d / name).write_text("x")
    (d / "d.js").mkdir()  # Verzeichnis mit bekannter Endung
    (tmp_path / "uix").mkdir()  # Nachbar mit gleichem Präfix
    (tmp_path / "uix" / "index.html").write_text("x")
    (tmp_path / "secret.js").write_text("x")
    (d / "out.js").symlink_to(tmp_path / "secret.js")
    (d / "in.js").symlink_to(d / "app.js")
    return d


@pytest.mark.parametrize("uri,name,mime", [
    ("orbitop://ui/index.html", "index.html", "text/html"),
    ("orbitop://ui/index.html#tab", "index.html", "text/html"),
    ("orbitop://ui/index.html?x=1", "index.html", "text/html"),
    ("orbitop://ui/app.js", "app.js", "text/javascript"),
    ("orbitop://ui/style.css", "style.css", "text/css"),
    ("orbitop://ui/fonts/a.ttf", "fonts/a.ttf", "font/ttf"),
    ("orbitop://ui/fonts/OFL.txt", "fonts/OFL.txt", "text/plain"),
    ("orbitop://ui/%61pp.js", "app.js", "text/javascript"),
    ("orbitop://ui/fonts/../app.js", "app.js", "text/javascript"),
    ("orbitop://ui/in.js", "app.js", "text/javascript"),       # Symlink innerhalb bleibt erlaubt
])
def test_ui_file_serves_known_types(ui, uri, name, mime):
    assert ui_file(uri, str(ui)) == (os.path.realpath(ui / name), mime)


@pytest.mark.parametrize("uri", [
    "orbitop://ui/../secret.js", "orbitop://ui/%2e%2e/secret.js", "orbitop://ui/fonts/%2E%2E/%2E%2E/secret.js",
    "orbitop://ui/%2Fetc%2Fpasswd", "orbitop://ui//etc/passwd", "orbitop://ui/out.js",   # Symlink nach außen
    "orbitop://ui/", "orbitop://ui", "orbitop://ui/fonts", "orbitop://ui/missing.html",
    "orbitop://ui/../uix/index.html", "orbitop://ui/%2e%2e/uix/index.html", "orbitop://ui/d.js",
    "orbitop://ui/tool.py", "orbitop://ui/noext", "orbitop://ui/a%00b.html",
    "orbitop://ui/fonts/b.otf", "orbitop://ui/fonts/c.woff2", "orbitop://ui/data.json", "orbitop://ui/i.svg",  # nicht ausgeliefert
    "orbitop://evil/index.html", "orbitop://ui:80/index.html", "orbitop://x@ui/index.html", "orbitop:///index.html",
    "orbitop:index.html", "orbitopx://ui/index.html",
    "file:///etc/passwd", "file://" + str(UI / "index.html"), "https://x", "about:blank",
    "data:text/html,hi", "javascript:alert(1)", "", None,
])
def test_ui_file_denies(ui, uri):
    assert ui_file(uri, str(ui)) is None


def test_mime_list_has_only_shipped_types():  # Freigabeliste: jeder Eintrag erweitert, was ausgeliefert werden kann
    assert set(app.MIME) == {p.suffix for p in UI.rglob("*") if p.is_file()}


def test_ui_file_real_index():
    assert ui_file("orbitop://ui/index.html", str(UI)) == (str(UI / "index.html"), "text/html")


def test_module_files_are_served():  # WebKit führt ein Modul nur mit JavaScript-Inhaltstyp aus
    files = sorted((UI / "js").rglob("*.js"))
    assert UI / "js" / "main.js" in files
    for p in files:
        assert ui_file("orbitop://ui/" + p.relative_to(UI).as_posix(), str(UI)) == (str(p), "text/javascript")


# ---- index.html / Module ----
def test_index_has_csp_and_no_inline_script():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert ('http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\'; '
            "style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'none'") in html
    assert html.count("<script") == html.count('<script type="module" src="') >= 1
    js = "".join(p.read_text(encoding="utf-8") for p in sorted((UI / "js").rglob("*.js")))
    assert "innerHTML" not in js and "textContent" in js


def test_index_loads_only_the_module_entry():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert html.count("<script") == 1 and '<script type="module" src="js/main.js"></script>' in html
