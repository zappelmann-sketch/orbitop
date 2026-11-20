# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Attrappen der Hüllen-Tests: Worker, WebView, GLib-Zeitgeber, Nachrichtenwert.

Nur importieren, nachdem check_runtime() GTK 4 und WebKitGTK 6.0 gefunden hat.
"""
import json
from pathlib import Path

from gi.repository import GLib

from orbitop import shell
from orbitop.layout import COLUMNS, DEFAULT_HIDDEN


UI = Path(shell.UI_DIR)
COUNTERS = {"marker": "off", "manual_rule": False, "parts": [{"part": "rapl", "state": "none"}], "usable": "nohelper"}
INIT = json.dumps({"type": "init", "layout": None, "autostart": None, "counters": COUNTERS, "hidden_hints": []})
L = {"order": list(COLUMNS), "hidden": list(DEFAULT_HIDDEN), "widths": {"cpu": 90}, "split": 0.6}


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


def receive(obj):
    return f"window.orbitop.receive({json.dumps(obj)})"
