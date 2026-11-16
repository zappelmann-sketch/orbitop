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
from orbitop.app import Worker, allowed_uri, check_runtime, parse_message, snapshot_path
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


# ---- allowed_uri ----
@pytest.mark.parametrize("uri,ok", [
    ((UI / "index.html").as_uri(), True),
    ((UI / "index.html").as_uri() + "#tab", True),
    ((UI / "fonts" / "Orbitron.ttf").as_uri(), True),
    (UI.as_uri() + "/../sysfs.py", False),
    (UI.as_uri() + "/%2e%2e/sysfs.py", False),
    (UI.as_uri() + "/", False),             # Verzeichnis selbst (Auflistung)
    (UI.as_uri(), False),
    (UI.as_uri() + "x/index.html", False),  # Nachbarverzeichnis mit gleichem Präfix
    (UI.as_uri() + "/a%00b.html", False),
    ("file://host" + str(UI / "index.html"), False),
    ("https://x", False), ("http://localhost/", False), ("file:///etc/passwd", False),
    ("about:blank", False), ("data:text/html,hi", False), ("javascript:alert(1)", False), ("", False),
])
def test_allowed_uri(uri, ok):
    assert allowed_uri(uri, str(UI)) is ok


def test_allowed_uri_resolves_symlinks(tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    (tmp_path / "secret.txt").write_text("x")
    (ui / "link.txt").symlink_to(tmp_path / "secret.txt")
    (ui / "page.html").write_text("x")
    assert allowed_uri((ui / "page.html").as_uri(), str(ui))
    assert not allowed_uri((ui / "link.txt").as_uri(), str(ui))


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
