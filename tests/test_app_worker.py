# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Worker synchron mit Attrappen: Takte, Schnappschüsse, erneutes Senden und Fehler des Samplers."""
import json

import pytest

from orbitop.app import Worker
from tests.app_helpers import Clock, FakeSampler, run_fake, run_procs_fake


def test_worker_ticks_on_drift_free_schedule():
    clock = Clock()
    s = FakeSampler(clock)
    posts = run_fake(s, clock, 6)
    assert s.sys_times() == pytest.approx([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    assert not any(k == "procs" for k, _ in s.calls)  # Prozesse laufen im eigenen Thread (run_procs)
    assert posts == [] and s.views == []  # weder sichtbar noch ready: kein Schnappschuss


@pytest.mark.parametrize("visible,ready,tab,shr", [
    (True, True, "procs", True), (False, True, "procs", False),
    (True, False, "procs", False), (True, True, "overview", False)])
def test_procs_tick_reads_shr_only_when_procs_tab_visible(visible, ready, tab, shr):
    clock = Clock()
    s = FakeSampler(clock)

    def wait(timeout):
        worker.stop()
        return False
    worker = Worker(s, [].append, clock=clock)
    worker.update(visible=visible, ready=ready, view={"tab": tab, "pid": None, "start": None})
    worker.run_procs(wait)
    assert s.shr == [shr]


def test_procs_tick_every_2_s_drift_free_and_skips_missed():
    clock = Clock()
    s = FakeSampler(clock)
    run_procs_fake(s, clock, 4)
    assert [t for _, t in s.calls] == pytest.approx([100.0, 102.0, 104.0, 106.0])
    clock = Clock()
    s = FakeSampler(clock)
    run_procs_fake(s, clock, 3, sleep=lambda timeout: timeout + 3.0)  # ein hängender Takt holt nichts nach
    assert [t for _, t in s.calls] == pytest.approx([100.0, 105.0, 109.0])


def test_procs_tick_every_4_s_when_hidden_and_at_once_when_shown():
    """Ausgeblendet halbe Eigenlast des Prozess-Takts; beim Einblenden sofort frische Prozesse, dann wieder 2 s."""
    clock = Clock()
    s = FakeSampler(clock)
    times = lambda: [t for k, t in s.calls if k == "procs"]  # noqa: E731

    def wait(timeout):
        assert timeout >= 0
        n = len(times())
        if n == 2:
            worker.update(visible=False)
        if n == 4:
            clock.t = 109.0  # mitten in der 4-s-Pause eingeblendet
            worker.update(visible=True)
            return True
        if n >= 6:
            worker.stop()
        clock.t += timeout
        return False
    worker = Worker(s, [].append, clock=clock)
    worker.update(visible=True)
    worker.run_procs(wait)
    assert times() == pytest.approx([100.0, 102.0, 104.0, 108.0, 109.0, 111.0])


def test_hidden_procs_period_keeps_rates_valid():
    from orbitop import app, system
    assert app.PROCS_PERIOD_S < app.PROCS_PERIOD_HIDDEN_S < system.MAX_DT  # sonst gälten ausgeblendet alle Raten als ungültig


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


def test_worker_resends_procs_after_ready_and_view():
    """Volle Prozessliste nach jedem ready und view und nach einem nicht gesendeten Tick, sonst darf sie fehlen."""
    s, posts = FakeSampler(), []
    w = Worker(s, posts.append)
    w.update(visible=True, ready=True)
    w._publish()
    w._publish()
    w.update(view={"tab": "procs", "pid": None, "start": None})
    w._publish()
    w._publish()
    w.update(visible=False)
    w.update(visible=True)  # nur sichtbar: die Seite hat ihre Liste noch
    w._publish()
    w.update(ready=False)
    w.update(ready=True)
    w._publish()
    assert s.resends == [True, False, True, False, False, True]
    s.snap = {"v": float("nan")}  # encode wirft ValueError: nichts gesendet
    w._publish()
    s.snap = None
    w._publish()
    assert s.resends[6:] == [False, True] and len(posts) == 7


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

    def snapshot(self, view):
        if self.fail == "snapshot":
            self._maybe()
        return super().snapshot(view)


@pytest.mark.parametrize("fail", ["tick_system", "snapshot"])
def test_worker_survives_sampler_exception(fail, capsys):
    clock = Clock()
    s = Flaky(clock, fail)
    posts = run_fake(s, clock, 4, lambda w: w.update(visible=True, ready=True))
    assert s.failed and "RuntimeError: kaputt" in capsys.readouterr().err
    assert s.sys_times() == pytest.approx([100.0, 101.0, 102.0, 103.0])  # der Takt läuft weiter
    assert len(posts) == (3 if fail == "snapshot" else 4)


def test_procs_tick_survives_exception_and_reports_it_once(capsys):
    clock = Clock()

    class Broken(FakeSampler):
        def tick_procs(self, shr=False):
            super().tick_procs(shr)
            raise RuntimeError("proc kaputt")
    s = Broken(clock)
    run_procs_fake(s, clock, 3)
    err = capsys.readouterr().err
    assert err.count("RuntimeError: proc kaputt") == 1 and sum(k == "procs" for k, _ in s.calls) == 3


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
