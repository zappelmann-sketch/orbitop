# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Hülle ohne Fenster: Nachrichten der Seite, darunter terminate bis in die Aufträge (jobs)."""
import json
import os
from types import SimpleNamespace

import pytest

from orbitop.app import check_runtime

if check_runtime():
    pytest.skip("GTK 4 oder WebKitGTK 6.0 fehlt", allow_module_level=True)

from orbitop import hints, jobs, shell  # noqa: E402
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


def test_init_carries_counters_and_hidden_hints(rig, monkeypatch):
    seen = []
    monkeypatch.setattr(jobs.counters, "state", lambda intel: seen.append(intel) or {"marker": "on"})
    rig.s._sampler.intel = True  # perfmon nur mit Intel-Grafik (Q2)
    hints.hide("hint.igt_missing", os.environ)
    rig.s._on_message(None, Value({"type": "ready"}))
    sent = json.loads(rig.js[-1].removeprefix("window.orbitop.receive(").removesuffix(")"))
    assert sent["counters"] == {"marker": "on", "usable": "nohelper"} and seen == [True]
    assert sent["hidden_hints"] == ["hint.igt_missing"]
    assert sent["install"] == {"usable": False, "command": "sudo apt install intel-gpu-tools"}  # ohne Paket kein Knopf


def test_counters_message_starts_the_job_with_the_sampler(rig):
    rig.s._on_message(None, Value({"type": "counters", "on": True, "x": 1}))
    assert [(t.target, t.args, t.daemon) for t in rig.threads] == [(rig.s._jobs._counters_thread,
                                                                     (True, rig.s._sampler), True)]


def test_hide_and_show_hints_reply_hints_state(rig, tmp_path):
    rig.s._on_message(None, Value({"type": "hide_hint", "key": "hint.rapl_noperm"}))
    assert json.loads((tmp_path / "cfg/orbitop/hints.json").read_text()) == ["hint.rapl_noperm"]
    rig.s._on_message(None, Value({"type": "show_hints"}))
    assert rig.js == [receive({"type": "hints_state", "hidden_hints": ["hint.rapl_noperm"]}),
                      receive({"type": "hints_state", "hidden_hints": []})]
    assert rig.log == []


def test_install_tool_starts_the_job_with_the_sampler_and_does_not_quit(rig):  # der Name kommt nie von der Seite
    rig.s._on_message(None, Value({"type": "install_tool", "package": "x"}))
    [t] = rig.threads
    assert (t.target, t.args[0], t.daemon) == (rig.s._jobs._install_thread, rig.s._sampler, True)
    assert rig.js == [] and rig.log == []
    t.args[1]()  # refresh nach dem Auftrag: init mit dem frischen Stand
    assert rig.js == [f"window.orbitop.receive({INIT})"]


@pytest.mark.parametrize("obj", [{"type": "terminate", "pid": True, "start": 1, "force": False}, {"type": "x"}, [1],
                                 {"type": "autostart", "on": 1}, {"type": "autostart"}, {"type": "counters", "on": 1},
                                 {"type": "hide_hint", "key": "hint.evil"}])
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
    rig.s._jobs._terminated(1, 0, False, "mismatch")
    assert rig.js == [receive({"type": "terminate_result", "pid": 1, "result": "mismatch"})]
    rig.s._on_message(None, terminate_msg(7, 8, True))  # nach dem Ergebnis ist wieder eines erlaubt
    assert len(rig.threads) == 2 and rig.threads[1].args == (7, 8, True)


def test_failed_thread_start_keeps_gate_open(rig, monkeypatch):
    class NoThread:
        def __init__(self, **kw):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")
    monkeypatch.setattr(jobs, "threading", SimpleNamespace(Thread=NoThread))
    with pytest.raises(RuntimeError):
        rig.s._on_message(None, terminate_msg(1, 2))
    monkeypatch.setattr(jobs, "threading", SimpleNamespace(Thread=lambda **kw: SimpleNamespace(
        start=lambda: rig.threads.append(kw))))
    rig.s._on_message(None, terminate_msg(3, 4))  # das Tor ist noch offen
    assert rig.threads == [{"target": rig.s._jobs._terminate_thread, "args": (3, 4, False), "daemon": True}]


@pytest.mark.parametrize("outcome,result", [("sent", "sent"), (RuntimeError("x"), "error")])
def test_terminate_thread_posts_result(rig, monkeypatch, outcome, result):
    def fake_terminate(pid, start, force, run):
        assert (pid, start, force, run) == (5, 6, False, rig.s._jobs._run)  # über _run erreicht _shutdown das pkexec
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr(jobs.actions, "terminate", fake_terminate)
    rig.s._on_message(None, terminate_msg(5, 6))
    t = rig.threads[0]
    t.target(*t.args)
    assert rig.glib.idle == [(rig.s._jobs._terminated, (5, 6, False, result))]
