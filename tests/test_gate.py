# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Tor und wachsende Sperre (Security-Dokument 0.3.0, B2.7, M-10), rein mit Uhr-Injektion.

Der Weg von pkexec 126 über Jobs bis ins Tor steht in test_jobs.py (test_gate_escalates) und
test_jobs_terminate.py."""
import pytest

from orbitop.gate import Gate


@pytest.fixture
def clock():
    now = [100.0]
    clock = lambda: now[0]  # noqa: E731
    clock.now = now
    return clock


def refuse(g, kind="counters"):
    assert g.begin(kind) is None
    g.end(kind, "refused")


def test_two_jobs_give_one_run_and_one_busy(clock):
    g = Gate(clock)
    assert g.begin("counters") is None
    assert [g.begin(k) for k in ("counters", "terminate", "install_tool")] == ["busy"] * 3
    g.end("counters", "ok")
    assert g.begin("terminate") is None and g.begin("counters") == "busy"
    g.end("terminate", "other")
    assert g.begin("install_tool") is None


def test_refusals_wait_10_then_60_then_lock_until_restart(clock):
    g = Gate(clock)
    refuse(g)
    assert g.begin("counters") == "busy"
    clock.now[0] = 109.9
    assert g.begin("counters") == "busy"
    clock.now[0] = 110.0
    refuse(g)
    clock.now[0] = 169.9
    assert g.begin("counters") == "busy"
    clock.now[0] = 170.0
    refuse(g)
    clock.now[0] = 1e9
    assert g.begin("counters") == "locked" and g.begin("install_tool") == "locked"


def test_success_resets_the_count(clock):
    g = Gate(clock)
    refuse(g)
    clock.now[0] = 110.0
    refuse(g)
    clock.now[0] = 170.0
    assert g.begin("counters") is None
    g.end("counters", "ok")
    refuse(g)  # sofort wieder frei, und die nächste Wartezeit ist wieder die erste
    clock.now[0] = 180.0
    refuse(g)
    clock.now[0] = 240.0
    refuse(g)
    assert g.begin("counters") == "locked"


def test_other_outcome_neither_resets_nor_counts(clock):
    g = Gate(clock)
    refuse(g)
    clock.now[0] = 110.0
    assert g.begin("counters") is None
    g.end("counters", "other")  # etwa error oder nohelper
    assert g.begin("counters") is None  # keine neue Wartezeit
    g.end("counters", "refused")  # die zweite Ablehnung: 60 s
    clock.now[0] = 169.9
    assert g.begin("counters") == "busy"


def test_counters_and_install_tool_share_one_count(clock):  # R9: höchstens drei Passwortdialoge bis zum Neustart
    g = Gate(clock)
    refuse(g, "counters")
    assert g.begin("install_tool") == "busy"
    clock.now[0] = 110.0
    refuse(g, "install_tool")
    clock.now[0] = 170.0
    refuse(g, "counters")
    assert g.begin("install_tool") == "locked"


def test_terminate_shares_the_count(clock):  # seit 0.3.0 (Schlussaudit): R9 gilt für alle drei Arten
    g = Gate(clock)
    refuse(g, "terminate")
    assert g.begin("terminate") == "busy" and g.begin("counters") == "busy"
    clock.now[0] = 110.0
    refuse(g, "counters")
    clock.now[0] = 170.0
    refuse(g, "terminate")
    clock.now[0] = 1e9
    assert [g.begin(k) for k in ("terminate", "counters", "install_tool")] == ["locked"] * 3

