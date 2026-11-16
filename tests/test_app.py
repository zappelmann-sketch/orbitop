# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from orbitop import app
from orbitop.app import Worker, check_runtime, parse_message, snapshot_path, ui_file
from orbitop.i18n import load_texts

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "orbitop" / "ui"


# ---- parse_message ----
@pytest.mark.parametrize("raw,msg", [
    ('{"type":"ready"}', {"type": "ready"}),
    ('{"type":"quit"}', {"type": "quit"}),
    ('{"type":"view","tab":"overview","pid":null,"start":null}',
     {"type": "view", "tab": "overview", "pid": None, "start": None}),
    ('{"type":"view","tab":"procs","pid":42,"start":0}', {"type": "view", "tab": "procs", "pid": 42, "start": 0}),
    ('{"type":"terminate","pid":42,"start":123456,"force":false}',
     {"type": "terminate", "pid": 42, "start": 123456, "force": False}),
    ('{"type":"terminate","pid":1,"start":2,"force":true}', {"type": "terminate", "pid": 1, "start": 2, "force": True}),
    ('{"type":"ready","extra":[1,2],"pid":"x"}', {"type": "ready"}),  # Zusatzschlüssel werden ignoriert
    ('{"type":"terminate","pid":3,"start":4,"force":true,"sig":"HUP"}',
     {"type": "terminate", "pid": 3, "start": 4, "force": True}),
])
def test_parse_message_accepts_contract_shapes(raw, msg):
    assert parse_message(raw) == msg


@pytest.mark.parametrize("raw", [
    '{"type":"terminate","pid":true,"start":1,"force":false}',   # bool als pid
    '{"type":"terminate","pid":1,"start":false,"force":false}',
    '{"type":"view","tab":"procs","pid":true,"start":1}',
    '{"type":"terminate","pid":-1,"start":1,"force":false}',     # negativ
    '{"type":"view","tab":"procs","pid":1,"start":-5}',
    '{"type":"terminate","pid":"1","start":1,"force":false}',    # str
    '{"type":"terminate","pid":1.0,"start":1,"force":false}',    # float
    '{"type":"terminate","pid":1e400,"start":1,"force":false}',  # inf
    '{"type":"terminate","pid":NaN,"start":1,"force":false}',
    '{"type":"terminate","start":1,"force":false}',              # pid fehlt
    '{"type":"terminate","pid":1,"start":1}',                    # force fehlt
    '{"type":"terminate","pid":1,"start":1,"force":"yes"}',
    '{"type":"terminate","pid":1,"start":1,"force":1}',
    '{"type":"terminate","pid":1,"start":null,"force":true}',
    '{"type":"view","tab":"x","pid":null,"start":null}',
    '{"type":"view","tab":["procs"],"pid":null,"start":null}',
    '{"type":"view","pid":null,"start":null}',
    '{"type":"reload"}', '{"type":["ready"]}', '{"type":null}', '{}',
    '[{"type":"ready"}]', "null", "1", '"ready"', "", "{kaputt", '{"type":"ready"',
    '{"type":"ready","pad":"' + "x" * 4096 + '"}',               # zu lang
])
def test_parse_message_rejects(raw):
    assert parse_message(raw) is None


def test_parse_message_rejects_non_str_and_length_limit():
    assert parse_message(None) is None
    pad = '{"type":"ready","p":"%s"}'
    assert parse_message(pad % ("x" * (4096 - len(pad % "")))) == {"type": "ready"}  # genau 4096 Zeichen
    assert parse_message(pad % ("x" * (4097 - len(pad % "")))) is None


def test_parse_message_survives_deep_nesting(monkeypatch):
    deep = '{"type":"ready","x":' + "[" * 2030 + "]" * 2030 + "}"
    assert len(deep) <= 4096
    assert parse_message(deep) in (None, {"type": "ready"})  # je nach Python-Version geparst oder RecursionError

    def boom(_):
        raise RecursionError
    monkeypatch.setattr(app.json, "loads", boom)
    assert parse_message('{"type":"ready"}') is None


# ---- ui_file (orbitop://ui/…) ----
@pytest.fixture
def ui(tmp_path):
    """UI-Baum mit je einer Datei pro Typ, einer unbekannten Endung, Unterordner und Symlinks nach innen und außen."""
    d = tmp_path / "ui"
    (d / "fonts").mkdir(parents=True)
    for name in ("index.html", "app.js", "style.css", "fonts/a.ttf", "fonts/b.otf", "fonts/c.woff2", "fonts/e.woff",
                 "data.json", "i.svg", "p.png", "fonts/OFL.txt", "tool.py", "noext"):
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
    ("orbitop://ui/fonts/b.otf", "fonts/b.otf", "font/otf"),
    ("orbitop://ui/fonts/c.woff2", "fonts/c.woff2", "font/woff2"),
    ("orbitop://ui/fonts/e.woff", "fonts/e.woff", "font/woff"),
    ("orbitop://ui/data.json", "data.json", "application/json"),
    ("orbitop://ui/i.svg", "i.svg", "image/svg+xml"),
    ("orbitop://ui/p.png", "p.png", "image/png"),
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
    "orbitop://evil/index.html", "orbitop://ui:80/index.html", "orbitop://x@ui/index.html", "orbitop:///index.html",
    "orbitop:index.html", "orbitopx://ui/index.html",
    "file:///etc/passwd", "file://" + str(UI / "index.html"), "https://x", "about:blank",
    "data:text/html,hi", "javascript:alert(1)", "", None,
])
def test_ui_file_denies(ui, uri):
    assert ui_file(uri, str(ui)) is None


def test_ui_file_real_index():
    assert ui_file("orbitop://ui/index.html", str(UI)) == (str(UI / "index.html"), "text/html")


# ---- snapshot_path ----
def test_snapshot_path(tmp_path):
    good = str(tmp_path / "shot.png")
    assert snapshot_path(good) == good
    assert snapshot_path(None) is None and snapshot_path("") is None
    assert snapshot_path(str(tmp_path / "shot.jpg")) is None
    assert snapshot_path(str(tmp_path / "missing" / "shot.png")) is None
    assert snapshot_path(str(tmp_path)) is None


# ---- check_runtime / main / bin ----
def _clear_lang(monkeypatch, lang):
    for k in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LANG", lang)


@pytest.mark.parametrize("missing,package", [("WebKit", "gir1.2-webkit-6.0"), ("Gtk", "gir1.2-gtk-4.0")])
def test_check_runtime_reports_missing_package(monkeypatch, missing, package):  # Review Focus 5
    _clear_lang(monkeypatch, "en_US.UTF-8")
    calls = []

    def req(ns, v):
        calls.append((ns, v))
        if ns == missing:
            raise ValueError(f"Namespace {ns} not available")
    msg = check_runtime(req)
    assert package in msg
    assert msg == load_texts("en")["error.runtime_missing"].format(package=package)
    assert ("Gtk", "4.0") in calls


def test_check_runtime_speaks_german(monkeypatch):
    _clear_lang(monkeypatch, "de_DE.UTF-8")

    def req(ns, v):
        if ns == "WebKit":
            raise ValueError("Namespace WebKit not available")
    msg = check_runtime(req)
    assert msg == load_texts("de")["error.runtime_missing"].format(package="gir1.2-webkit-6.0")
    assert msg != load_texts("en")["error.runtime_missing"].format(package="gir1.2-webkit-6.0")


def test_check_runtime_ok():
    calls = []
    assert check_runtime(lambda ns, v: calls.append((ns, v))) is None
    assert calls == [("Gtk", "4.0"), ("WebKit", "6.0")]


def test_main_exit_2_without_webkit(monkeypatch, capsys):
    monkeypatch.setattr(app, "check_runtime", lambda *a: "Paket fehlt: x")
    assert app.main([]) == 2
    assert "Paket fehlt: x" in capsys.readouterr().err


def test_main_version_skips_runtime_check(monkeypatch, capsys):
    monkeypatch.setattr(app, "check_runtime", lambda *a: pytest.fail("kein Laufzeit-Check für --version"))
    assert app.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "orbitop 0.1.0"


def test_version_flag(tmp_path):
    r = subprocess.run([sys.executable, str(REPO / "bin" / "orbitop"), "--version"], capture_output=True, text=True,
                       cwd=tmp_path)
    assert r.stdout.strip() == "orbitop 0.1.0" and r.returncode == 0


def test_launcher_is_executable():
    assert os.access(REPO / "bin" / "orbitop", os.X_OK)


# ---- index.html / app.js ----
def test_index_has_csp_and_no_inline_script():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert ('http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\'; '
            "style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'none'") in html
    assert html.count("<script") == html.count('<script src="') >= 1
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "textContent" in js


# ---- Worker ----
class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class FakeSampler:
    def __init__(self, clock=None, cost=0.108, snap=None):
        self.clock, self.cost, self.snap = clock, cost, snap
        self.calls, self.views = [], []

    def _spend(self, cost):
        if self.clock:
            self.clock.t += cost

    def tick_system(self):
        self.calls.append(("sys", self.clock.t if self.clock else None))
        self._spend(self.cost(len(self.calls)) if callable(self.cost) else self.cost)

    def tick_procs(self):
        self.calls.append(("procs", self.clock.t if self.clock else None))
        self._spend(0.02)

    def snapshot(self, view):
        self.views.append(dict(view))
        return self.snap if self.snap is not None else {"type": "tick", "view": view}

    def sys_times(self):
        return [t for k, t in self.calls if k == "sys"]


def run_fake(sampler, clock, ticks, setup=lambda w: None, sleep=lambda timeout: timeout):
    """Lässt den Worker synchron laufen, bis `ticks` Systemtakte erfolgt sind; sleep: tatsächlich geschlafene Zeit."""
    posts = []

    def wait(timeout):
        assert timeout >= 0
        clock.t += sleep(timeout)
        if len(sampler.sys_times()) >= ticks:
            worker.stop()
        return False
    worker = Worker(sampler, posts.append, clock=clock, wait=wait)
    setup(worker)
    worker.run()
    return posts


def test_worker_ticks_on_drift_free_schedule():
    clock = Clock()
    s = FakeSampler(clock)
    posts = run_fake(s, clock, 6)
    assert s.sys_times() == pytest.approx([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    procs = [t for k, t in s.calls if k == "procs"]
    assert procs == pytest.approx([100.108, 102.108, 104.108])  # jeder zweite Takt, direkt nach tick_system
    assert posts == [] and s.views == []  # weder sichtbar noch ready: kein Schnappschuss


def test_worker_skips_missed_slots_instead_of_bursting():
    clock = Clock()
    s = FakeSampler(clock, cost=lambda n: 2.5 if n == 1 else 0.1)
    run_fake(s, clock, 3)
    assert s.sys_times() == pytest.approx([100.0, 103.0, 104.0])


@pytest.mark.parametrize("flags,expect", [
    ({}, False), ({"visible": True}, False), ({"ready": True}, False), ({"visible": True, "ready": True}, True),
])
def test_worker_snapshots_only_when_visible_and_ready(flags, expect):
    clock = Clock()
    s = FakeSampler(clock)
    view = {"type": "view", "tab": "procs", "pid": 5, "start": 7}

    def setup(w):
        assert w.update(**flags) is expect
        assert w.update(view=view) is expect
    posts = run_fake(s, clock, 3, setup)
    if expect:
        assert [json.loads(p) for p in posts] == [{"type": "tick", "view": view}] * 3
        assert s.views == [view] * 3
    else:
        assert posts == [] and s.views == []


def test_worker_stops_snapshots_when_hidden():
    clock = Clock()
    s = FakeSampler(clock)

    def setup(w):
        assert w.update(visible=True, ready=True)
        assert w.update(visible=False) is False
    assert run_fake(s, clock, 2, setup) == [] and s.views == []


def test_worker_publishes_once_per_tick_despite_early_wakeups():
    clock = Clock()
    s = FakeSampler(clock)
    posts = run_fake(s, clock, 3, lambda w: w.update(visible=True, ready=True),
                     sleep=lambda timeout: timeout / 2 if timeout > 0.01 else timeout)
    assert s.sys_times() == pytest.approx([100.0, 101.0, 102.0], abs=0.02)
    assert len(posts) == 3


def test_worker_serializes_ascii_and_drops_nan():
    clock = Clock()
    s = FakeSampler(clock, snap={"name": "Web Content ä"})
    posts = run_fake(s, clock, 2, lambda w: w.update(visible=True, ready=True))
    assert posts == ['{"name": "Web\\u2028Content \\u00e4"}'] * 2
    s = FakeSampler(clock, snap={"v": float("nan")})
    assert run_fake(s, clock, 3, lambda w: w.update(visible=True, ready=True)) == []
    assert len(s.sys_times()) == 3  # der Worker lebt weiter


class Flaky(FakeSampler):
    """Wirft beim ersten Aufruf von `fail` eine Ausnahme."""
    def __init__(self, clock, fail):
        super().__init__(clock)
        self.fail, self.failed = fail, False

    def _maybe(self):
        if not self.failed:
            self.failed = True
            raise RuntimeError("kaputt")

    def tick_system(self):
        super().tick_system()
        if self.fail == "tick_system":
            self._maybe()

    def tick_procs(self):
        super().tick_procs()
        if self.fail == "tick_procs":
            self._maybe()

    def snapshot(self, view):
        if self.fail == "snapshot":
            self._maybe()
        return super().snapshot(view)


@pytest.mark.parametrize("fail", ["tick_system", "tick_procs", "snapshot"])
def test_worker_survives_sampler_exception(fail, capsys):
    clock = Clock()
    s = Flaky(clock, fail)
    posts = run_fake(s, clock, 4, lambda w: w.update(visible=True, ready=True))
    assert s.failed and "RuntimeError: kaputt" in capsys.readouterr().err
    assert s.sys_times() == pytest.approx([100.0, 101.0, 102.0, 103.0])  # der Takt läuft weiter
    assert len(posts) == (3 if fail == "snapshot" else 4)
    assert len([k for k, _ in s.calls if k == "procs"]) == 2


def test_worker_prints_each_distinct_error_once(capsys):
    clock = Clock()

    class Broken(FakeSampler):
        def tick_system(self):
            super().tick_system()
            raise RuntimeError("anders" if len(self.sys_times()) == 4 else "kaputt")
    s = Broken(clock)
    run_fake(s, clock, 6)
    err = capsys.readouterr().err
    assert err.count("RuntimeError: kaputt") == 1 and err.count("RuntimeError: anders") == 1
    assert err.count("Traceback") == 2


def test_worker_thread_kicks_immediately_and_stops_fast():
    s = FakeSampler()
    got = threading.Event()
    posts = []
    w = Worker(s, lambda p: (posts.append(p), got.set()))
    w.start()
    deadline = time.monotonic() + 2
    while not s.calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert s.sys_times() == [None] and posts == []
    t0 = time.monotonic()
    assert w.update(visible=True, ready=True)
    assert got.wait(0.5)  # sofort, nicht erst beim nächsten Takt
    assert time.monotonic() - t0 < 0.5 and len(s.sys_times()) == 1
    t0 = time.monotonic()
    w.stop()
    assert time.monotonic() - t0 < 0.5
    assert not any(t.name == "orbitop-worker" for t in threading.enumerate())
    n = len(s.calls)
    time.sleep(1.2)
    assert len(s.calls) == n
