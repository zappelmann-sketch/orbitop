# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Prüfseite tests/ui/check.html im kopflosen Chrome: Zahlenformat, sichere Texte, Nachrichten an Python."""
import functools
import http.server
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
REPO = Path(__file__).resolve().parent.parent
APP_JS = REPO / "orbitop" / "ui" / "js" / "app.js"


@pytest.fixture
def ui_server(tmp_path_factory):
    """Basis-URL eines HTTP-Servers nur auf 127.0.0.1: Chrome lädt Module nicht über file://.
    Die Wurzel enthält nur orbitop/ui und tests/ui."""
    root = tmp_path_factory.mktemp("www")
    for part in ("orbitop/ui", "tests/ui"):
        (root / part).parent.mkdir(parents=True, exist_ok=True)
        (root / part).symlink_to(REPO / part)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()
    server.server_close()
    thread.join()


def check_page(tmp_path, base, size, fragment=""):
    out = subprocess.run([CHROME, "--headless=new", f"--user-data-dir={tmp_path}", f"--window-size={size}",
                          "--dump-dom", base + "tests/ui/check.html" + fragment],
                         capture_output=True, text=True, timeout=60).stdout
    assert "<title>PASS</title>" in out, out[out.find("<title>"):out.find("</title>")]


@pytest.mark.skipif(not CHROME, reason="kein Chrome oder Chromium installiert")
def test_ui_check_page(tmp_path, ui_server):
    check_page(tmp_path, ui_server, "1600,1000")


@pytest.mark.skipif(not CHROME, reason="kein Chrome oder Chromium installiert")
def test_ui_check_page_narrow(tmp_path, ui_server):
    """Unter 1100 px: Liste über dem Detail, kein Trenner, die Seite rollt nicht waagerecht."""
    check_page(tmp_path, ui_server, "1000,800", "#narrow")


def test_terminate_is_posted_only_by_the_confirm_button():
    """Kein Beenden ohne Rückfrage: genau eine Stelle sendet terminate, und nur der Bestätigungsknopf ruft sie auf."""
    js = APP_JS.read_text(encoding="utf-8")
    assert js.count('"terminate"') == 1
    body = js[js.index("function confirmed() {"):]
    assert body.index('post({ type: "terminate"') < body.index("\n}\n")
    code = [line for line in js.splitlines() if "confirmed" in line and not line.lstrip().startswith("//")]
    assert code == ['  ui.cYes = button("btn term", cb, confirmed);', "function confirmed() {"]
