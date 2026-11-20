# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Aufträge der Seite in eigenen Threads: einen Prozess beenden (pkexec blockiert bis zu 120 s), danach nachsehen.

Ohne GTK: glib liefert idle_add und timeout_add_seconds (in der Hülle GLib), send erhält fertiges JSON aus encode()
und läuft nur im Hauptthread."""
import contextlib
import subprocess
import threading
from collections.abc import Callable

from orbitop import actions
from orbitop.messages import encode

CHECK_DELAY_S = 5  # Nachsehen nach SIGTERM


class Jobs:
    def __init__(self, send: Callable[[str], None], glib):
        self._send, self._glib = send, glib
        self._terminating = False  # höchstens ein terminate zugleich, nie ein Stapel Passwortdialoge; nur Hauptthread
        self._pkexec: subprocess.Popen | None = None  # laufendes pkexec, gesetzt von _run im terminate-Thread

    def terminate(self, pid: int, start: int, force: bool) -> None:
        if self._terminating:
            return  # still verwerfen: die Seite zeigt erst das Ergebnis des laufenden Auftrags
        threading.Thread(target=self._terminate_thread, args=(pid, start, force), daemon=True).start()
        self._terminating = True  # erst nach erfolgreichem start(), sonst bliebe das Tor für immer zu

    def stop(self) -> None:
        """Beim Herunterfahren: ein offenes pkexec beenden."""
        child = self._pkexec
        if child is not None:  # offenes pkexec: verwaist signalisierte es nach späterer Bestätigung ohne Rückmeldung
            with contextlib.suppress(PermissionError):  # schon der Helfer als root, er endet gleich von selbst
                child.terminate()

    def _terminate_thread(self, pid: int, start: int, force: bool) -> None:  # pkexec blockiert bis zu 120 s
        try:
            result = actions.terminate(pid, start, force, run=self._run)
        except Exception:  # sonst bliebe das Beenden für immer gesperrt
            result = "error"
        self._glib.idle_add(self._terminated, pid, start, force, result)

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
        self._terminating = False
        self._send(encode({"type": "terminate_result", "pid": pid, "result": result}))
        if result == "sent" and not force:
            self._glib.timeout_add_seconds(CHECK_DELAY_S, self._check, pid, start)

    def _check(self, pid: int, start: int) -> bool:
        def work():
            alive = actions.is_alive(pid, start)
            self._glib.idle_add(self._send, encode({"type": "terminate_check", "pid": pid, "alive": alive}))
        threading.Thread(target=work, daemon=True).start()
        return False  # einmalig
