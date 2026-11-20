# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Aufträge der Seite in eigenen Threads, alle durch ein Tor (gate.Gate): einen Prozess beenden und die Zähler
freigeben oder sperren. pkexec blockiert bis zu 120 s; danach wird nachgesehen bzw. der Zustand neu gelesen.

Ohne GTK: glib liefert idle_add und timeout_add_seconds (in der Hülle GLib), send erhält fertiges JSON aus encode()
und läuft nur im Hauptthread. Das Tor berührt nur der Hauptthread."""
import contextlib
import subprocess
import threading
from collections.abc import Callable

from orbitop import actions, counters
from orbitop.gate import Gate
from orbitop.messages import encode

CHECK_DELAY_S = 5  # Nachsehen nach SIGTERM


def counters_payload(intel: bool) -> dict:
    """COUNTERS aus Klärung Q2: der Zustand ohne root und ob der Schalter nutzbar ist."""
    return {**counters.state(intel=intel), "usable": actions.counters_usable()}


def _outcome(result: str, codes: list[int | None]) -> str:
    """Für das Tor; codes: je gestartetem pkexec sein Exit-Code, None ohne Ende. Als Ablehnung zählt auch ein pkexec,
    das ein Signal beendete (fail closed: sonst gäbe jeder Weg, pkexec zu beenden, Dialoge ohne Zählung). Nur ein
    Erfolg nach einem pkexec setzt zurück: sonst öffnete eine Seite mit „schon so“ dazwischen alle 10 s einen Dialog."""
    if result in ("cancelled", "denied") or any(c is not None and c < 0 for c in codes):
        return "refused"
    return "ok" if result == "ok" and codes else "other"


class Jobs:
    def __init__(self, send: Callable[[str], None], glib):
        self._send, self._glib = send, glib
        self._gate = Gate()  # nie ein Stapel Passwortdialoge, und eine wachsende Sperre nach Ablehnungen (B2.7)
        self._pkexec: subprocess.Popen | None = None  # laufendes pkexec, gesetzt von _run im Auftrags-Thread

    def terminate(self, pid: int, start: int, force: bool) -> None:
        # busy: still verwerfen wie in 0.2.0, die Seite zeigt erst das Ergebnis des laufenden Auftrags
        self._start("terminate", self._terminate_thread, pid, start, force)

    def counters(self, on: bool, tools) -> None:
        """tools (der Sampler): intel, ob es Intel-Grafik gibt, und recheck_tools() nach einer Freigabe (Q3)."""
        refused = self._start("counters", self._counters_thread, on, tools)
        if refused:
            self._send_counters(refused, tools)

    def stop(self) -> None:
        """Beim Herunterfahren: ein offenes pkexec beenden."""
        child = self._pkexec
        if child is not None:  # offenes pkexec: verwaist signalisierte es nach späterer Bestätigung ohne Rückmeldung
            with contextlib.suppress(PermissionError):  # schon der Helfer als root, er endet gleich von selbst
                child.terminate()

    def _start(self, kind: str, target, *args) -> str | None:
        """target im Thread, wenn das Tor frei ist; sonst busy oder locked, ohne Thread."""
        refused = self._gate.begin(kind)
        if refused is None:
            try:
                threading.Thread(target=target, args=args, daemon=True).start()
            except BaseException:  # sonst bliebe das Tor für immer zu
                self._gate.end(kind, "other")
                raise
        return refused

    def _terminate_thread(self, pid: int, start: int, force: bool) -> None:  # pkexec blockiert bis zu 120 s
        try:
            result = actions.terminate(pid, start, force, run=self._run)
        except Exception:  # sonst bliebe das Tor für immer zu
            result = "error"
        self._glib.idle_add(self._terminated, pid, start, force, result)

    def _counters_thread(self, on: bool, tools) -> None:
        codes: list[int | None] = []

        def run(argv: list[str], timeout: float) -> subprocess.CompletedProcess:
            codes.append(None)  # gestartet, auch wenn _run gleich scheitert
            r = self._run(argv, timeout)
            codes[-1] = r.returncode
            return r
        try:
            result = actions.counters(on, run=run)
        except Exception:  # sonst bliebe das Tor für immer zu
            result = "error"
        if result == "ok":  # auch „schon so“: die Merkdatei kann von außen gekommen sein (sudo counterhelper, sync)
            # intel_gpu_top mit der neuen Fähigkeit ohne Neustart (Q3); kann Sekunden dauern, daher hier im Thread
            with contextlib.suppress(Exception):  # dann erkennt erst der Neustart neu; das Tor muss frei werden
                tools.recheck_tools()
        self._glib.idle_add(self._counters_done, result, _outcome(result, codes), tools)

    def _run(self, argv: list[str], timeout: float) -> subprocess.CompletedProcess:
        """subprocess.run für pkexec, nur dass stop() das Kind erreicht und beenden kann."""
        with subprocess.Popen(argv) as p:
            self._pkexec = p
            try:
                return subprocess.CompletedProcess(argv, p.wait(timeout))
            except subprocess.TimeoutExpired:
                p.kill()
                raise
            finally:
                self._pkexec = None

    def _terminated(self, pid: int, start: int, force: bool, result: str) -> None:
        self._gate.end("terminate", "other")
        self._send(encode({"type": "terminate_result", "pid": pid, "result": result}))
        if result == "sent" and not force:
            self._glib.timeout_add_seconds(CHECK_DELAY_S, self._check, pid, start)

    def _counters_done(self, result: str, outcome: str, tools) -> None:
        self._gate.end("counters", outcome)
        self._send_counters(result, tools)

    def _send_counters(self, result: str, tools) -> None:
        """Die Antwort mit einem frisch gelesenen Zustand (B2.1 „Ergebnis“) und dem festen Wort result."""
        self._send(encode({"type": "counters_state", "counters": counters_payload(tools.intel), "result": result}))

    def _check(self, pid: int, start: int) -> bool:
        def work():
            alive = actions.is_alive(pid, start)
            self._glib.idle_add(self._send, encode({"type": "terminate_check", "pid": pid, "alive": alive}))
        threading.Thread(target=work, daemon=True).start()
        return False  # einmalig
