# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Prüfseite tests/ui/check.html im kopflosen Chrome: Zahlenformat, sichere Texte, Nachrichten an Python."""
import shutil
import subprocess
from pathlib import Path

import pytest

CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
PAGE = Path(__file__).parent / "ui" / "check.html"
APP_JS = Path(__file__).parent.parent / "orbitop" / "ui" / "app.js"


@pytest.mark.skipif(not CHROME, reason="kein Chrome oder Chromium installiert")
def test_ui_check_page(tmp_path):
    out = subprocess.run([CHROME, "--headless=new", f"--user-data-dir={tmp_path}", "--dump-dom", PAGE.as_uri()],
                         capture_output=True, text=True, timeout=60).stdout
    assert "<title>PASS</title>" in out, out[out.find("<title>"):out.find("</title>")]


def test_terminate_is_posted_only_by_the_confirm_button():
    """Kein Beenden ohne Rückfrage: genau eine Stelle sendet terminate, und nur der Bestätigungsknopf ruft sie auf."""
    js = APP_JS.read_text(encoding="utf-8")
    assert js.count('"terminate"') == 1
    body = js[js.index("function confirmed() {"):]
    assert body.index('post({ type: "terminate"') < body.index("\n}\n")
    code = [line for line in js.splitlines() if "confirmed" in line and not line.lstrip().startswith("//")]
    assert code == ['  ui.cYes = button("btn term", cb, confirmed);', "function confirmed() {"]
