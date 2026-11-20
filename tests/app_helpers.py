# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Hilfen der Worker-Tests: feste Uhr, Ersatz-Sampler, synchrone Läufe beider Takte."""
from orbitop.app import Worker, encode


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class FakeSampler:
    def __init__(self, clock=None, cost=0.108, snap=None):
        self.clock, self.cost, self.snap = clock, cost, snap
        self.calls, self.views, self.shr, self.resends = [], [], [], []

    def _spend(self, cost):
        if self.clock:
            self.clock.t += cost

    def tick_system(self):
        self.calls.append(("sys", self.clock.t if self.clock else None))
        self._spend(self.cost(len(self.calls)) if callable(self.cost) else self.cost)

    def tick_procs(self, shr=False):
        self.shr.append(shr)
        self.calls.append(("procs", self.clock.t if self.clock else None))
        self._spend(0.02)

    def snapshot(self, view):
        self.views.append(dict(view))
        return self.snap if self.snap is not None else {"type": "tick", "view": view}

    def snapshot_json(self, view, resend=True):
        self.resends.append(resend)
        return encode(self.snapshot(view))

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


def run_procs_fake(sampler, clock, n, sleep=lambda timeout: timeout):
    """Lässt den Prozess-Takt bei sichtbarem Fenster synchron laufen, bis n Prozess-Takte erfolgt sind."""
    def wait(timeout):
        assert timeout >= 0
        clock.t += sleep(timeout)
        if sum(k == "procs" for k, _ in sampler.calls) >= n:
            worker.stop()
        return False
    worker = Worker(sampler, [].append, clock=clock)
    worker.update(visible=True)  # sichtbar: Takt PROCS_PERIOD_S
    worker.run_procs(wait)
