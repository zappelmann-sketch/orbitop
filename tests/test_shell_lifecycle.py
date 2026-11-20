# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Hülle ohne Fenster: Unix-Signale, Herunterfahren, Sichtbarkeit, Start und Absturz der Seite."""
import json
import signal
import sys
import threading
import time
import warnings
from types import SimpleNamespace

import pytest

from orbitop.app import check_runtime

if check_runtime():
    pytest.skip("GTK 4 oder WebKitGTK 6.0 fehlt", allow_module_level=True)

import gi  # noqa: E402
from gi.repository import GLib  # noqa: E402

from orbitop import shell  # noqa: E402
from tests.shell_helpers import INIT, L  # noqa: E402


# ---- Signale ----
def test_unix_signal_add_prefers_glibunix():
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        preferred = GLibUnix.signal_add
    except (ImportError, ValueError, AttributeError):
        pytest.skip("GLibUnix.signal_add fehlt (ältere GLib)")
    with warnings.catch_warnings():  # GLib.unix_signal_add wäre hier derselbe Aufruf, aber mit Veraltet-Warnung
        warnings.simplefilter("error", DeprecationWarning)
        assert shell._unix_signal_add() == preferred


# require/import: ältere GLib ohne GLibUnix; attr: GLib 2.80 (Ubuntu 24.04) hat dort nur signal_add_full
@pytest.mark.parametrize("block", ["require", "import", "attr"])
def test_unix_signal_add_falls_back_without_glibunix(monkeypatch, block):
    if block == "attr":
        fake = SimpleNamespace()  # Modul ohne signal_add
        monkeypatch.setitem(sys.modules, "gi.repository.GLibUnix", fake)
        monkeypatch.setattr(sys.modules["gi.repository"], "GLibUnix", fake, raising=False)
    elif block == "require":
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


def test_unix_signal_add_really_adds_a_signal_source():  # Triage 12: der Rückfall lief auf Ubuntu 24.04 nie echt
    with warnings.catch_warnings():  # GLib.unix_signal_add ist im neuen PyGObject veraltet
        warnings.simplefilter("ignore", DeprecationWarning)
        ids = [add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, lambda *a: True)
               for add in (shell._unix_signal_add(), GLib.unix_signal_add)]
    names = [GLib.MainContext.default().find_source_by_id(i).get_name() for i in ids]
    assert [GLib.source_remove(i) for i in ids] == [True, True]
    assert all(n.startswith("GUnixSignalSource") for n in names), names


# ---- Lebenszyklus ----
def test_shutdown_stops_worker_then_closes_sampler(rig):
    rig.s._shutdown(None)
    assert rig.log == ["stop", "close"]


@pytest.mark.parametrize("exc", [None, PermissionError])  # PermissionError: pkexec läuft schon als root-Helfer
def test_shutdown_terminates_open_pkexec(rig, exc):
    def terminate():
        rig.log.append("pkexec")
        if exc:
            raise exc
    rig.s._jobs._pkexec = SimpleNamespace(terminate=terminate)
    rig.s._shutdown(None)
    assert rig.log == ["pkexec", "stop", "close"]


def test_run_child_ends_with_shutdown(rig):
    """_run wie subprocess.run, aber das Kind bleibt für _shutdown erreichbar; hier ein eigenes sleep statt pkexec."""
    out = []
    t = threading.Thread(target=lambda: out.append(rig.s._jobs._run(["sleep", "30"], timeout=120)))
    t.start()
    deadline = time.monotonic() + 5
    while rig.s._jobs._pkexec is None and time.monotonic() < deadline:
        time.sleep(0.01)
    rig.s._shutdown(None)
    t.join(5)
    assert out[0].returncode == -signal.SIGTERM and rig.s._jobs._pkexec is None


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


def test_startup_wires_layout_from_config_dir(monkeypatch, tmp_path):
    (tmp_path / "orbitop").mkdir()
    (tmp_path / "orbitop" / "layout.json").write_text(json.dumps(L))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("ORBITOP_SNAPSHOT", raising=False)
    s = shell.Shell(False)
    settings = SimpleNamespace(set_property=lambda *a: None)
    monkeypatch.setattr(shell, "Gtk", SimpleNamespace(Settings=SimpleNamespace(get_default=lambda: settings)))
    monkeypatch.setattr(shell, "_unix_signal_add", lambda: lambda *a: None)
    monkeypatch.setattr(shell, "Sampler", lambda: SimpleNamespace())
    monkeypatch.setattr(shell, "Worker", lambda *a: SimpleNamespace(start=lambda: None))
    monkeypatch.setattr(s, "_build_window", lambda app: None)
    app = SimpleNamespace(add_action=lambda a: None, set_accels_for_action=lambda *a: None, hold=lambda: None, quit=lambda: None)
    s._startup(app)
    assert s._layouts.path == str(tmp_path / "orbitop" / "layout.json")
    assert json.loads(s._init_message())["layout"] == L
