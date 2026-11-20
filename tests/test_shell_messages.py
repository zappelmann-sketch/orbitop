# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Hülle ohne Fenster: Nachrichten der Seite und das Beenden eines Prozesses."""
import json
import os
from types import SimpleNamespace

import pytest

from orbitop.app import check_runtime

if check_runtime():
    pytest.skip("GTK 4 oder WebKitGTK 6.0 fehlt", allow_module_level=True)

from orbitop import shell  # noqa: E402
from tests.shell_helpers import INIT, L, Value, receive  # noqa: E402


# ---- Nachrichten ----
def test_layout_message_saved_once_to_fixed_path(rig, tmp_path):
    rig.s._on_message(None, Value({"type": "layout", **L, "path": str(tmp_path / "evil")}))
    rig.s._on_message(None, Value({"type": "layout", **L}))
    assert json.loads((tmp_path / "layout.json").read_text()) == L and sorted(os.listdir(tmp_path)) == ["layout.json"]
    assert rig.js == [] and rig.log == []


def test_invalid_layout_message_not_saved(rig, tmp_path):
    rig.s._on_message(None, Value({"type": "layout", **L, "hidden": ["process"]}))
    assert os.listdir(tmp_path) == [] and rig.js == [] and rig.log == []


def test_init_after_layout_carries_current_layout(rig):  # Review Focus 2
    rig.s._on_message(None, Value({"type": "layout", **L}))
    rig.s._on_message(None, Value({"type": "ready"}))
    sent = rig.js[-1].removeprefix("window.orbitop.receive(").removesuffix(")")
    assert json.loads(sent)["layout"] == L


def test_ready_sends_init_when_live(rig):
    rig.s._on_message(None, Value({"type": "ready"}))
    assert rig.log == [("update", {"ready": True})]
    assert rig.js == [f"window.orbitop.receive({INIT})"]


def test_ready_while_hidden_sends_nothing(rig):
    rig.s._worker.live = False
    rig.s._on_message(None, Value({"type": "ready"}))
    assert rig.js == []


def test_init_carries_autostart_state(rig, monkeypatch):
    seen = iter([False, True])
    monkeypatch.setattr(shell.autostart, "state", lambda env: next(seen) if env is os.environ else pytest.fail())
    rig.s._on_message(None, Value({"type": "ready"}))
    rig.s._on_message(None, Value({"type": "ready"}))  # bei jedem Senden neu ermittelt
    sent = [json.loads(j.removeprefix("window.orbitop.receive(").removesuffix(")")) for j in rig.js]
    assert [m["autostart"] for m in sent] == [False, True]


@pytest.mark.parametrize("on,after", [(True, True), (False, False), (True, None), (False, True)])
def test_autostart_message_sets_and_replies(rig, monkeypatch, on, after):
    calls = []
    monkeypatch.setattr(shell.autostart, "set_enabled",
                        lambda value, env: calls.append((value, env is os.environ)) or after)
    rig.s._on_message(None, Value({"type": "autostart", "on": on, "path": "/tmp/x"}))
    assert calls == [(on, True)] and rig.log == []
    assert rig.js == [receive({"type": "autostart_state", "on": after})]


def test_view_goes_to_worker(rig):
    rig.s._on_message(None, Value({"type": "view", "tab": "procs", "pid": 3, "start": 4, "x": 1}))
    assert rig.log == [("update", {"view": {"type": "view", "tab": "procs", "pid": 3, "start": 4}})]


def test_quit_message_quits(rig):
    rig.s._on_message(None, Value({"type": "quit"}))
    assert rig.log == ["quit"]


@pytest.mark.parametrize("obj", [{"type": "terminate", "pid": True, "start": 1, "force": False}, {"type": "x"}, [1],
                                 {"type": "autostart", "on": 1}, {"type": "autostart"}])
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
    def fake_terminate(pid, start, force, run):
        assert (pid, start, force, run) == (5, 6, False, rig.s._run)  # über _run erreicht _shutdown das pkexec
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
