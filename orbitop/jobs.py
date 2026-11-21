# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Aufträge der Seite in eigenen Threads, alle durch ein Tor (gate.Gate): einen Prozess beenden, die Zähler
freigeben oder sperren und intel_gpu_top über PackageKit installieren. pkexec blockiert bis zu 120 s, PackageKit länger;
danach wird nachgesehen bzw. der Zustand neu gelesen.

Ohne GTK: glib liefert idle_add und timeout_add_seconds (in der Hülle GLib), send erhält fertiges JSON aus encode()
und läuft nur im Hauptthread. Das Tor berührt nur der Hauptthread."""
import contextlib
import subprocess
import threading
from collections.abc import Callable

from orbitop import actions, counters, packagekit
from orbitop.gate import Gate
from orbitop.messages import encode

CHECK_DELAY_S = 5  # Nachsehen nach SIGTERM


def counters_payload(intel: bool) -> dict:
    """COUNTERS aus Klärung Q2: der Zustand ohne root und ob der Schalter nutzbar ist."""
    return {**counters.state(intel=intel), "usable": actions.counters_usable()}


def install_payload(intel: bool) -> dict:
    """Für init: ob der Knopf „Installieren“ gilt, und der Befehl für den Rückfall. Nur mit Intel-Grafik und mit dem
    Paket: ohne den Helfer aus dem Paket ist es ein Start aus dem Checkout, dann nur der Befehl (Review Focus 5)."""
    return {"usable": intel and actions.counters_usable() != "nohelper", "command": packagekit.command()}


def _install_outcome(result: str, job) -> str:
    """Für das Tor. Als Ablehnung zählt jeder letzte Schritt ohne Erfolg, denn er kann einen Dialog gezeigt haben (fail
    closed wie bei pkexec); Resolve und Simulation fragen nie. Nie ok: Eine Installation ohne Dialog (Fedora, I-2)
    setzte sonst die gemeinsame Sperre zurück, und counters bekäme fünf statt drei Dialoge (R9)."""
    if result == "installed":
        return "other"
    return "refused" if result == "denied" or job.interactive else "other"


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
        # Start und Eintrag des Kindes gegen stop(): sonst verpasste ein gleichzeitiges stop() ein pkexec, das gerade
        # startet; sein Dialog bliebe nach dem Ende von orbitop offen, und der Helfer handelte nach einer Bestätigung
        self._child_lock = threading.Lock()
        self._stopping = False  # nach stop() startet _run nichts mehr
        self._install: packagekit.Install | None = None  # laufende Installation, nur im Hauptthread gesetzt
        # Ein Lauf über PackageKit endete in installed, failed oder unavailable: in dieser Sitzung keiner mehr (B2.7),
        # wie der Knopf der Seite; sonst ließe eine Seite das root-packagekitd ohne Ende auflösen und simulieren
        self._closed = False

    def terminate(self, pid: int, start: int, force: bool) -> None:
        refused = self._start("terminate", self._terminate_thread, pid, start, force)
        if refused:  # busy oder locked als Ergebnis: sonst wartete die Seite nach einer Ablehnung ewig darauf
            self._send(encode({"type": "terminate_result", "pid": pid, "result": refused}))

    def counters(self, on: bool, tools) -> None:
        """tools (der Sampler): intel, ob es Intel-Grafik gibt, und recheck_tools() nach einer Freigabe (Q3)."""
        refused = self._start("counters", self._counters_thread, on, tools)
        if refused:
            self._send_counters(refused, tools)

    def install_tool(self, tools, refresh: Callable[[], None]) -> None:
        """tools (der Sampler): intel, igt_missing() und recheck_tools(); refresh schickt danach den frischen Stand."""
        if self._closed:  # ohne Thread und ohne Bus; eigenes Wort, denn locked heißt „zu oft abgelehnt“
            self._send(encode({"type": "install_state", "result": "closed"}))
            return
        job = packagekit.Install()  # hier im Hauptthread: stop() erreicht ihn auch, bevor der Thread läuft
        refused = self._start("install_tool", self._install_thread, tools, refresh, job)
        if refused:
            self._send(encode({"type": "install_state", "result": refused}))
        else:
            self._install = job

    def stop(self) -> None:
        """Beim Herunterfahren: kein neues pkexec mehr, ein offenes beenden, eine laufende Installation abbrechen."""
        with self._child_lock:
            self._stopping = True
            child = self._pkexec
            if child is not None:  # offenes pkexec: verwaist signalisierte es nach späterer Bestätigung ohne Rückmeldung
                with contextlib.suppress(PermissionError):  # schon der Helfer als root, er endet gleich von selbst
                    child.terminate()
        job = self._install
        if job is not None:  # sonst installierte PackageKit ohne orbitop weiter, auch nach einem späteren Dialog
            job.cancel()

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

    def _counted(self, codes: list[int | None]) -> Callable[[list[str], float], subprocess.CompletedProcess]:
        """_run, das je gestartetem pkexec den Exit-Code in codes einträgt, None ohne Ende (für das Tor)."""
        def run(argv: list[str], timeout: float) -> subprocess.CompletedProcess:
            codes.append(None)  # gestartet, auch wenn _run gleich scheitert
            r = self._run(argv, timeout)
            codes[-1] = r.returncode
            return r
        return run

    def _terminate_thread(self, pid: int, start: int, force: bool) -> None:  # pkexec blockiert bis zu 120 s
        codes: list[int | None] = []
        try:
            result = actions.terminate(pid, start, force, run=self._counted(codes))
        except Exception:  # sonst bliebe das Tor für immer zu
            result = "error"
        # nur nach pkexec: der eigene Prozess fragt nie, auch sein denied (PermissionError) zählt nicht; sent ist nie ok
        self._glib.idle_add(self._terminated, pid, start, force, result, _outcome(result, codes) if codes else "other")

    def _counters_thread(self, on: bool, tools) -> None:
        codes: list[int | None] = []
        try:
            result = actions.counters(on, run=self._counted(codes))
        except Exception:  # sonst bliebe das Tor für immer zu
            result = "error"
        # auch „schon so“ (die Merkdatei kann von außen gekommen sein: sudo counterhelper, sync) und nach den Exit-Codes
        # 1–4: der Helfer lief und kann einen Teil geändert haben
        if result == "ok" or any(c in (1, 2, 3, 4) for c in codes):
            # intel_gpu_top mit der neuen Fähigkeit ohne Neustart (Q3); kann Sekunden dauern, daher hier im Thread
            with contextlib.suppress(Exception):  # dann erkennt erst der Neustart neu; das Tor muss frei werden
                tools.recheck_tools()
        self._glib.idle_add(self._counters_done, result, _outcome(result, codes), tools)

    def _install_thread(self, tools, refresh, job) -> None:
        ran = False
        try:
            # harte Vorbedingung (B2.7): Intel-Grafik mit Paket und hint.igt_missing gilt; die Sitzung prüft
            # install_tool, das Tor lässt bis hier nur einen Auftrag zu
            if not tools.igt_missing() or not install_payload(tools.intel)["usable"]:
                result = "unavailable"
            else:
                ran = True
                result = job.run()
                # auch ohne installed: kam das Werkzeug von außen (apt, dnf), verschwindet so der veraltete Hinweis
                with contextlib.suppress(Exception):  # dann erkennt erst der Neustart neu; das Tor muss frei werden
                    tools.recheck_tools()  # nur bei Änderung, kann Sekunden dauern, daher hier im Thread (Q3)
        except Exception:  # sonst bliebe das Tor für immer zu
            result = "failed"
        self._glib.idle_add(self._install_done, result, _install_outcome(result, job), ran, refresh)

    def _run(self, argv: list[str], timeout: float) -> subprocess.CompletedProcess:
        """subprocess.run für pkexec, nur dass stop() das Kind erreicht und beenden kann: gestartet und eingetragen
        wird unter self._child_lock, und nach stop() gar nicht mehr (SubprocessError, für die Aufträge ein error)."""
        with self._child_lock:
            if self._stopping:
                raise subprocess.SubprocessError("orbitop is shutting down")
            p = self._pkexec = subprocess.Popen(argv)
        with p:
            try:
                return subprocess.CompletedProcess(argv, p.wait(timeout))
            except subprocess.TimeoutExpired:
                p.kill()
                raise
            finally:
                with self._child_lock:
                    self._pkexec = None

    def _terminated(self, pid: int, start: int, force: bool, result: str, outcome: str) -> None:
        self._gate.end("terminate", outcome)
        self._send(encode({"type": "terminate_result", "pid": pid, "result": result}))
        if result == "sent" and not force:
            self._glib.timeout_add_seconds(CHECK_DELAY_S, self._check, pid, start)

    def _counters_done(self, result: str, outcome: str, tools) -> None:
        self._gate.end("counters", outcome)
        self._send_counters(result, tools)

    def _install_done(self, result: str, outcome: str, ran: bool, refresh) -> None:
        self._install = None
        self._closed = self._closed or ran and result in ("installed", "failed", "unavailable")
        self._gate.end("install_tool", outcome)
        self._send(encode({"type": "install_state", "result": result}))
        if ran:
            refresh()  # Hinweise und Zeilen der Freigabe nach dem neuen Erkennen

    def _send_counters(self, result: str, tools) -> None:
        """Die Antwort mit einem frisch gelesenen Zustand (B2.1 „Ergebnis“) und dem festen Wort result."""
        self._send(encode({"type": "counters_state", "counters": counters_payload(tools.intel), "result": result}))

    def _check(self, pid: int, start: int) -> bool:
        def work():
            alive = actions.is_alive(pid, start)
            self._glib.idle_add(self._send, encode({"type": "terminate_check", "pid": pid, "alive": alive}))
        threading.Thread(target=work, daemon=True).start()
        return False  # einmalig
