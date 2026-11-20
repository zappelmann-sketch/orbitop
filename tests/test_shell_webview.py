# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Hülle ohne Fenster: Navigation, Auslieferung über orbitop://ui/ und Einstellungen der WebView."""
from types import SimpleNamespace

import pytest

from orbitop.app import check_runtime

if check_runtime():
    pytest.skip("GTK 4 oder WebKitGTK 6.0 fehlt", allow_module_level=True)

from gi.repository import WebKit  # noqa: E402

from orbitop import shell  # noqa: E402
from tests.shell_helpers import UI  # noqa: E402


# ---- Navigation ----
class Decision:
    def __init__(self, uri, supported=True):
        self.uri, self.supported, self.verdict = uri, supported, None
        request = SimpleNamespace(get_uri=lambda: self.uri)
        self.get_request = lambda: request
        self.get_navigation_action = lambda: SimpleNamespace(get_request=lambda: request)

    def is_mime_type_supported(self):
        return self.supported

    def use(self):
        self.verdict = "use"

    def ignore(self):
        self.verdict = "ignore"


NAV, NEW, RESP = (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION,
                  WebKit.PolicyDecisionType.RESPONSE)


@pytest.mark.parametrize("kind,uri,supported,verdict", [
    (NAV, shell.INDEX_URI, True, "use"),
    (NAV, shell.INDEX_URI + "#procs", True, "use"),
    (NAV, "orbitop://ui/js/main.js", True, "ignore"),  # oben nur Seiten, nie Skripte
    (NAV, (UI / "index.html").as_uri(), True, "ignore"),
    (NAV, "file:///etc/passwd", True, "ignore"),
    (NAV, "orbitop://ui/../app.py", True, "ignore"),
    (NAV, "https://example.com/", True, "ignore"),
    (NAV, "about:blank", True, "ignore"),
    (NEW, shell.INDEX_URI, True, "ignore"),
    (NEW, "https://example.com/", True, "ignore"),
    (RESP, shell.INDEX_URI, True, "use"),
    (RESP, shell.INDEX_URI, False, "ignore"),  # nicht darstellbar hieße Download
    (RESP, "file:///etc/passwd", True, "ignore"),
])
def test_decide_policy(rig, kind, uri, supported, verdict):
    d = Decision(uri, supported)
    assert rig.s._decide_policy(None, d, kind) is True
    assert d.verdict == verdict


@pytest.mark.parametrize("name,verdict", [("page.html", "use"), ("a.js", "ignore"), ("OFL.txt", "ignore"),
                                          ("f.ttf", "ignore"), ("s.css", "ignore")])
def test_top_level_navigation_only_to_html(rig, monkeypatch, tmp_path, name, verdict):
    (tmp_path / name).write_text("x")
    monkeypatch.setattr(shell, "UI_DIR", str(tmp_path))
    d = Decision("orbitop://ui/" + name)
    rig.s._decide_policy(None, d, NAV)
    assert d.verdict == verdict


# ---- orbitop://ui/ ----
class Request:
    def __init__(self, uri):
        self.uri, self.done = uri, None

    def get_uri(self):
        return self.uri

    def finish(self, stream, length, mime):
        self.done = ("ok", stream.read_bytes(length + 1, None).get_data(), length, mime)

    def finish_error(self, err):
        self.done = ("error", err.message)


def test_serve_index():
    r = Request("orbitop://ui/index.html")
    shell.Shell(False)._serve(r)
    data = (UI / "index.html").read_bytes()
    assert r.done == ("ok", data, len(data), "text/html")


@pytest.mark.parametrize("name,mime", [("a.js", "text/javascript"), ("f.ttf", "font/ttf"), ("s.css", "text/css"),
                                       ("OFL.txt", "text/plain")])
def test_serve_content_types(monkeypatch, tmp_path, name, mime):
    (tmp_path / name).write_bytes(b"\x00\x01data")
    monkeypatch.setattr(shell, "UI_DIR", str(tmp_path))
    r = Request("orbitop://ui/" + name)
    shell.Shell(False)._serve(r)
    assert r.done == ("ok", b"\x00\x01data", 6, mime)


def test_serve_unreadable_file_is_error(monkeypatch, tmp_path):
    f = tmp_path / "a.js"
    f.write_text("x")
    f.chmod(0)
    monkeypatch.setattr(shell, "UI_DIR", str(tmp_path))
    r = Request("orbitop://ui/a.js")
    try:
        shell.Shell(False)._serve(r)
    finally:
        f.chmod(0o644)
    assert r.done[0] == "error"


@pytest.mark.parametrize("uri", ["orbitop://ui/missing.html", "orbitop://ui/../app.py", "orbitop://ui/%2e%2e/app.py",
                                 "orbitop://ui/", "orbitop://evil/index.html"])
def test_serve_denies(uri):
    r = Request(uri)
    shell.Shell(False)._serve(r)
    assert r.done[0] == "error"


# ---- Einstellungen ----
# WebKit.Settings stürzt ohne Anzeige ab (Segfault statt Ausnahme), etwa im Container oder über SSH
needs_display = pytest.mark.skipif(shell.Gdk.Display.get_default() is None, reason="keine Anzeige")


@needs_display
def test_settings_hardened(monkeypatch):
    monkeypatch.delenv("ORBITOP_DEVTOOLS", raising=False)
    st = shell._settings()
    assert st.get_enable_javascript() and not st.get_enable_developer_extras()
    assert not st.get_allow_file_access_from_file_urls() and not st.get_allow_universal_access_from_file_urls()
    assert not st.get_allow_top_navigation_to_data_urls() and not st.get_disable_web_security()
    assert not st.get_javascript_can_open_windows_automatically() and not st.get_javascript_can_access_clipboard()
    assert not (st.get_enable_webgl() or st.get_enable_webaudio() or st.get_enable_webrtc() or st.get_enable_media())
    assert not (st.get_enable_html5_local_storage() or st.get_enable_html5_database() or st.get_enable_fullscreen())
    assert st.get_media_playback_requires_user_gesture()


@needs_display
@pytest.mark.parametrize("value,on", [("1", True), ("yes", False), ("0", False), ("", False)])
def test_devtools_only_with_env_1(monkeypatch, value, on):
    monkeypatch.setenv("ORBITOP_DEVTOOLS", value)
    assert shell._settings().get_enable_developer_extras() is on
