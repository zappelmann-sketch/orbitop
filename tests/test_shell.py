# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Hülle ohne Fenster: Handler mit Attrappen für Worker, WebView, Entscheidungen, Thread und GLib-Zeitgeber."""
import json
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from orbitop.app import check_runtime

if check_runtime():
    pytest.skip("GTK 4 oder WebKitGTK 6.0 fehlt", allow_module_level=True)

import gi  # noqa: E402
from gi.repository import GLib, WebKit  # noqa: E402

from orbitop import shell  # noqa: E402

UI = Path(shell.UI_DIR)
INIT = '{"type": "init"}'


class FakeWorker:
    def __init__(self, log, live=True):
        self.log, self.live = log, live

    def update(self, **kw):
        self.log.append(("update", kw))
        return self.live

    def stop(self):
        self.log.append("stop")


class FakeView:
    def __init__(self):
        self.js, self.loads = [], []

    def evaluate_javascript(self, script, *_):
        self.js.append(script)

    def load_uri(self, uri):
        self.loads.append(uri)


class FakeGLib:
    """Zeichnet Zeitgeber und idle-Aufrufe auf; alles andere kommt aus dem echten GLib."""

    def __init__(self):
        self.idle, self.timeouts = [], []

    def idle_add(self, fn, *args):
        self.idle.append((fn, args))

    def timeout_add_seconds(self, delay, fn, *args):
        self.timeouts.append((delay, fn, args))

    def __getattr__(self, name):
        return getattr(GLib, name)


class Value:
    def __init__(self, obj):
        self.text = json.dumps(obj)

    def to_json(self, _indent):
        return self.text


@pytest.fixture
def rig(monkeypatch):
    log, threads = [], []

    class Thread:
        def __init__(self, target, args=(), daemon=None):
            self.target, self.args, self.daemon = target, args, daemon

        def start(self):
            threads.append(self)

    s = shell.Shell(False)
    s._worker, s._view, s._init = FakeWorker(log), FakeView(), INIT
    s._sampler = SimpleNamespace(close=lambda: log.append("close"))
    s._app = SimpleNamespace(quit=lambda: log.append("quit"))
    glib = FakeGLib()
    monkeypatch.setattr(shell, "GLib", glib)
    monkeypatch.setattr(shell, "threading", SimpleNamespace(Thread=Thread))
    return SimpleNamespace(s=s, log=log, glib=glib, threads=threads, js=s._view.js)


def receive(obj):
    return f"window.orbitop.receive({json.dumps(obj)})"


# ---- Nachrichten ----
def test_ready_sends_init_when_live(rig):
    rig.s._on_message(None, Value({"type": "ready"}))
    assert rig.log == [("update", {"ready": True})]
    assert rig.js == [f"window.orbitop.receive({INIT})"]


def test_ready_while_hidden_sends_nothing(rig):
    rig.s._worker.live = False
    rig.s._on_message(None, Value({"type": "ready"}))
    assert rig.js == []


def test_view_goes_to_worker(rig):
    rig.s._on_message(None, Value({"type": "view", "tab": "procs", "pid": 3, "start": 4, "x": 1}))
    assert rig.log == [("update", {"view": {"type": "view", "tab": "procs", "pid": 3, "start": 4}})]


def test_quit_message_quits(rig):
    rig.s._on_message(None, Value({"type": "quit"}))
    assert rig.log == ["quit"]


@pytest.mark.parametrize("obj", [{"type": "terminate", "pid": True, "start": 1, "force": False}, {"type": "x"}, [1]])
def test_invalid_message_is_ignored(rig, obj):
    rig.s._on_message(None, Value(obj))
    assert rig.log == [] and rig.js == [] and rig.threads == []


# ---- Beenden ----
def terminate_msg(pid, start, force=False):
    return Value({"type": "terminate", "pid": pid, "start": start, "force": force})


def test_terminate_flood_starts_one_thread(rig):
    for start in range(20):
        rig.s._on_message(None, terminate_msg(1, start))
    assert len(rig.threads) == 1
    assert rig.threads[0].args == (1, 0, False) and rig.threads[0].daemon
    rig.s._terminated(1, 0, False, "mismatch")
    assert rig.js == [receive({"type": "terminate_result", "pid": 1, "result": "mismatch"})]
    rig.s._on_message(None, terminate_msg(7, 8, True))  # nach dem Ergebnis ist wieder eines erlaubt
    assert len(rig.threads) == 2 and rig.threads[1].args == (7, 8, True)


def test_failed_thread_start_keeps_gate_open(rig, monkeypatch):
    class NoThread:
        def __init__(self, **kw):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")
    monkeypatch.setattr(shell, "threading", SimpleNamespace(Thread=NoThread))
    with pytest.raises(RuntimeError):
        rig.s._on_message(None, terminate_msg(1, 2))
    monkeypatch.setattr(shell, "threading", SimpleNamespace(Thread=lambda **kw: SimpleNamespace(
        start=lambda: rig.threads.append(kw))))
    rig.s._on_message(None, terminate_msg(3, 4))  # das Tor ist noch offen
    assert rig.threads == [{"target": rig.s._terminate_thread, "args": (3, 4, False), "daemon": True}]


@pytest.mark.parametrize("outcome,result", [("sent", "sent"), (RuntimeError("x"), "error")])
def test_terminate_thread_posts_result(rig, monkeypatch, outcome, result):
    def fake_terminate(pid, start, force):
        assert (pid, start, force) == (5, 6, False)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr(shell.actions, "terminate", fake_terminate)
    rig.s._on_message(None, terminate_msg(5, 6))
    t = rig.threads[0]
    t.target(*t.args)
    assert rig.glib.idle == [(rig.s._terminated, (5, 6, False, result))]


@pytest.mark.parametrize("force,result,check", [(False, "sent", True), (True, "sent", False),
                                                (False, "denied", False), (False, "gone", False)])
def test_check_only_after_plain_sent(rig, force, result, check):
    rig.s._terminated(5, 6, force, result)
    assert rig.glib.timeouts == ([(5, rig.s._check, (5, 6))] if check else [])


def test_check_reports_alive_from_thread(rig, monkeypatch):
    monkeypatch.setattr(shell.actions, "is_alive", lambda pid, start: (pid, start) == (5, 6))
    assert rig.s._check(5, 6) is False  # einmalig
    t = rig.threads[0]
    t.target(*t.args)
    fn, args = rig.glib.idle[0]
    fn(*args)
    assert rig.js == [receive({"type": "terminate_check", "pid": 5, "alive": True})]


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
    (NAV, "orbitop://ui/app.js", True, "ignore"),  # oben nur Seiten, nie Skripte
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


@pytest.mark.parametrize("value,on", [("1", True), ("yes", False), ("0", False), ("", False)])
def test_devtools_only_with_env_1(monkeypatch, value, on):
    monkeypatch.setenv("ORBITOP_DEVTOOLS", value)
    assert shell._settings().get_enable_developer_extras() is on


# ---- Signale ----
def test_unix_signal_add_prefers_glibunix():
    gi.require_version("GLibUnix", "2.0")
    from gi.repository import GLibUnix
    with warnings.catch_warnings():  # GLib.unix_signal_add wäre hier derselbe Aufruf, aber mit Veraltet-Warnung
        warnings.simplefilter("error", DeprecationWarning)
        assert shell._unix_signal_add() == GLibUnix.signal_add


@pytest.mark.parametrize("block", ["require", "import"])
def test_unix_signal_add_falls_back_without_glibunix(monkeypatch, block):  # z. B. Ubuntu 24.04, PyGObject 3.48
    if block == "require":
        real = gi.require_version

        def require(namespace, version):
            if namespace == "GLibUnix":
                raise ValueError("Namespace GLibUnix not available")
            return real(namespace, version)
        monkeypatch.setattr(gi, "require_version", require)
    else:
        monkeypatch.setitem(sys.modules, "gi.repository.GLibUnix", None)
        monkeypatch.delattr(sys.modules["gi.repository"], "GLibUnix", raising=False)
    with warnings.catch_warnings():  # die Ausweichfunktion ist im neuen PyGObject veraltet
        warnings.simplefilter("ignore", DeprecationWarning)
        assert shell._unix_signal_add() == GLib.unix_signal_add


# ---- Lebenszyklus ----
def test_shutdown_stops_worker_then_closes_sampler(rig):
    rig.s._shutdown(None)
    assert rig.log == ["stop", "close"]


class Win:
    def __init__(self, visible=True, suspended=False):
        self.visible, self.suspended, self.presented = visible, suspended, 0

    def get_visible(self):
        return self.visible

    def is_suspended(self):
        return self.suspended

    def present(self):
        self.presented += 1


@pytest.mark.parametrize("visible,suspended,shown", [(True, False, True), (True, True, False), (False, False, False)])
def test_minimized_or_hidden_counts_as_invisible(rig, visible, suspended, shown):
    rig.s._worker.live = shown
    rig.s._snapshot = None
    rig.s._on_visible(Win(visible, suspended), None)
    assert rig.log == [("update", {"visible": shown})]
    assert rig.js == ([f"window.orbitop.receive({INIT})"] if shown else [])


def test_snapshot_scheduled_once_on_first_show(rig):
    rig.s._snapshot = "/tmp/x.png"
    rig.s._on_visible(Win(), None)
    rig.s._on_visible(Win(), None)
    assert rig.glib.timeouts == [(5, rig.s._save_snapshot, ("/tmp/x.png",))]


@pytest.mark.parametrize("args,shown", [(["orbitop"], True), (["orbitop", "--hidden"], False)])
def test_command_line_presents_unless_hidden(args, shown):  # erste wie weitere Starts
    s = shell.Shell(False)
    s._win = Win()
    assert s._command_line(None, SimpleNamespace(get_arguments=lambda: args)) == 0
    assert s._win.presented == int(shown)


def test_activate_presents_window():  # gapplication launch / D-Bus Activate
    s = shell.Shell(False)
    s._win = Win()
    s._app.emit("activate")
    assert s._win.presented == 1


@pytest.mark.parametrize("hidden,argv", [(True, ["orbitop", "--hidden"]), (False, ["orbitop"])])
def test_run_forwards_hidden_flag(hidden, argv):
    s = shell.Shell(hidden)
    s._app = SimpleNamespace(run=lambda a: 0 if a == argv else pytest.fail(str(a)))
    assert s.run() == 0


def test_web_process_crash_reloads_at_most_every_10_s(rig, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(shell, "time", SimpleNamespace(monotonic=lambda: now[0]))
    view = rig.s._view

    def crash_and_fire():
        rig.s._on_web_crash(view, None)
        delay, fn, args = rig.glib.timeouts[-1]
        assert fn(*args) is False
        return delay
    assert crash_and_fire() == 0
    assert rig.log == [("update", {"ready": False})] and view.loads == [shell.INDEX_URI]
    now[0] = 103.0
    assert crash_and_fire() == 7  # Absturzschleife: frühestens 10 s nach dem letzten Neuladen
    now[0] = 200.0
    assert crash_and_fire() == 0
    assert len(view.loads) == 3
