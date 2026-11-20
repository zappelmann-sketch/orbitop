# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Ein Tor für die Aufträge der Seite mit Passwortdialog (Security-Dokument 0.3.0, B2.7, M-10).

Höchstens ein Auftrag zugleich. Für das Freigeben und das Installieren zusätzlich eine wachsende Sperre nach jeder
Ablehnung. Rein, mit Uhr-Injektion, ohne Threads: nur der Hauptthread ruft begin und end."""
import time

WAITS = (10.0, 60.0)  # nach der ersten und der zweiten Ablehnung; nach der dritten gesperrt bis zum Neustart
ESCALATING = ("counters", "install_tool")  # terminate bleibt wie in 0.2.0: nur einer zugleich, keine Sperre


class Gate:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._running: str | None = None
        # Ablehnungen seit dem letzten Erfolg, gemeinsam für beide Arten: höchstens drei Dialoge bis zum Neustart (R9)
        self._refusals = 0
        self._until = 0.0

    def begin(self, kind: str) -> str | None:
        """None: frei, der Auftrag kind läuft jetzt. Sonst busy (ein Auftrag läuft oder die Wartezeit nach einer
        Ablehnung) oder locked (zu oft abgelehnt)."""
        escalating = kind in ESCALATING
        if escalating and self._refusals > len(WAITS):
            return "locked"
        if self._running is not None or escalating and self._clock() < self._until:
            return "busy"
        self._running = kind
        return None

    def end(self, kind: str, outcome: str) -> None:
        """outcome: ok (Erfolg, setzt die Sperre zurück), refused (abgebrochen oder abgelehnt) oder other."""
        self._running = None
        if kind not in ESCALATING or outcome == "other":
            return
        if outcome == "ok":
            self._refusals = 0
            return
        self._refusals += 1
        if self._refusals <= len(WAITS):
            self._until = self._clock() + WAITS[self._refusals - 1]
