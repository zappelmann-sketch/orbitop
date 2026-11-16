# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""GTK-4-Fenster mit WebView: Einzelinstanz, Hintergrundbetrieb und Brücke zur Seite.

Erst nach app.check_runtime() importieren, sonst endet ein fehlendes WebKit in einem Traceback."""
import os
import signal
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit  # noqa: E402

from orbitop import APP_ID, __version__, actions  # noqa: E402
from orbitop.app import Worker, allowed_uri, encode, parse_message, snapshot_path  # noqa: E402
from orbitop.i18n import detect_language, load_texts  # noqa: E402
from orbitop.sampler import Sampler  # noqa: E402

UI_DIR = str(Path(__file__).resolve().parent / "ui")
CHECK_DELAY_S = 5  # Nachsehen nach SIGTERM
SNAPSHOT_DELAY_S = 5


def _settings() -> WebKit.Settings:
    return WebKit.Settings(
        enable_javascript=True,
        enable_developer_extras=os.environ.get("ORBITOP_DEVTOOLS") == "1",
        # Nicht gebraucht, also aus: weniger Angriffsfläche
        enable_webgl=False, enable_webaudio=False, enable_webrtc=False, enable_media=False,
        enable_media_stream=False, enable_mediasource=False, enable_media_capabilities=False,
        enable_encrypted_media=False, media_playback_requires_user_gesture=True,
        enable_html5_local_storage=False, enable_html5_database=False, enable_fullscreen=False,
        javascript_can_open_windows_automatically=False, javascript_can_access_clipboard=False,
        allow_file_access_from_file_urls=False, allow_universal_access_from_file_urls=False,
        allow_top_navigation_to_data_urls=False, disable_web_security=False,
    )


class Shell:
    def __init__(self, hidden: bool):
        self._hidden = hidden
        self._pending: set[tuple[int, int]] = set()  # laufende terminate je (pid, start); nur Hauptthread
        self._app = Gtk.Application(application_id=APP_ID)
        self._app.connect("startup", self._startup)
        self._app.connect("activate", self._activate)
        self._app.connect("shutdown", self._shutdown)

    def run(self) -> int:
        return self._app.run(["orbitop"])

    # ---- Lebenszyklus (nur in der ersten Instanz) ----
    def _startup(self, app) -> None:
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        quit_action = Gio.SimpleAction(name="quit")
        quit_action.connect("activate", lambda *_: app.quit())
        app.add_action(quit_action)
        app.set_accels_for_action("app.quit", ["<Control>q"])
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, app.quit)  # sauber beenden, auch per timeout/kill
        app.hold()  # weiterlaufen, auch ohne sichtbares Fenster
        lang = detect_language(os.environ)
        self._init = encode({"type": "init", "lang": lang, "texts": load_texts(lang), "version": __version__})
        env = os.environ.get("ORBITOP_SNAPSHOT")
        self._snapshot = snapshot_path(env)
        if env and not self._snapshot:
            print("orbitop: ORBITOP_SNAPSHOT must be a .png path in an existing directory", file=sys.stderr)
        self._sampler = Sampler()
        self._worker = Worker(self._sampler, lambda text: GLib.idle_add(self._send, text))
        self._worker.start()
        self._build_window(app)

    def _build_window(self, app) -> None:
        ucm = WebKit.UserContentManager()
        ucm.register_script_message_handler("orbitop", None)
        ucm.connect("script-message-received::orbitop", self._on_message)
        self._view = WebKit.WebView(user_content_manager=ucm, settings=_settings(),
                                    network_session=WebKit.NetworkSession.new_ephemeral())  # nichts auf der Platte
        bg = Gdk.RGBA()
        bg.parse("#0c1115")
        self._view.set_background_color(bg)  # kein weißes Aufblitzen vor dem ersten Zeichnen
        self._view.connect("decide-policy", self._decide_policy)
        self._win = Gtk.ApplicationWindow(application=app, title="orbitop", default_width=1600, default_height=1000,
                                          child=self._view)
        self._win.connect("close-request", self._on_close)
        self._win.connect("notify::visible", self._on_visible)
        self._view.load_uri(Path(UI_DIR, "index.html").as_uri())

    def _activate(self, _app) -> None:
        if self._hidden:
            self._hidden = False  # nur der erste Start bleibt verborgen, jeder weitere zeigt das Fenster
        else:
            self._win.present()

    def _shutdown(self, _app) -> None:
        self._worker.stop()
        self._sampler.close()  # beendet intel_gpu_top

    def _on_close(self, win) -> bool:
        win.set_visible(False)
        return True  # nur ausblenden, nicht zerstören

    def _on_visible(self, win, _pspec) -> None:
        visible = win.get_visible()
        if self._worker.update(visible=visible):
            self._send(self._init)  # der Worker schickt gleich danach einen tick
        if visible and self._snapshot:
            GLib.timeout_add_seconds(SNAPSHOT_DELAY_S, self._save_snapshot, self._snapshot)
            self._snapshot = None

    # ---- Brücke ----
    def _send(self, text: str) -> None:
        """text stammt aus encode(), ist also ein sicheres JS-Literal."""
        self._view.evaluate_javascript(f"window.orbitop.receive({text})", -1, None, None, None, None, None)

    def _on_message(self, _ucm, value) -> None:
        msg = parse_message(value.to_json(0))
        if msg is None:
            return
        kind = msg["type"]
        if kind == "ready":
            if self._worker.update(ready=True):
                self._send(self._init)
        elif kind == "view":
            self._worker.update(view=msg)
        elif kind == "terminate":
            self._terminate(msg["pid"], msg["start"], msg["force"])
        else:
            self._app.quit()

    def _decide_policy(self, _view, decision, kind) -> bool:
        if kind == WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            ok = allowed_uri(decision.get_navigation_action().get_request().get_uri(), UI_DIR)
        elif kind == WebKit.PolicyDecisionType.RESPONSE:  # nicht darstellbar hieße Download
            ok = decision.is_mime_type_supported() and allowed_uri(decision.get_request().get_uri(), UI_DIR)
        else:  # neue Fenster
            ok = False
        if ok:
            decision.use()
        else:
            decision.ignore()
        return True

    # ---- Beenden von Prozessen ----
    def _terminate(self, pid: int, start: int, force: bool) -> None:
        if (pid, start) in self._pending:
            return
        self._pending.add((pid, start))
        threading.Thread(target=self._terminate_thread, args=(pid, start, force), daemon=True).start()

    def _terminate_thread(self, pid: int, start: int, force: bool) -> None:  # pkexec blockiert bis zu 120 s
        try:
            result = actions.terminate(pid, start, force)
        except Exception:  # sonst bliebe (pid, start) für immer gesperrt
            result = "error"
        GLib.idle_add(self._terminated, pid, start, force, result)

    def _terminated(self, pid: int, start: int, force: bool, result: str) -> None:
        self._pending.discard((pid, start))
        self._send(encode({"type": "terminate_result", "pid": pid, "result": result}))
        if result == "sent" and not force:
            GLib.timeout_add_seconds(CHECK_DELAY_S, self._check, pid, start)

    def _check(self, pid: int, start: int) -> bool:
        def work():
            alive = actions.is_alive(pid, start)
            GLib.idle_add(self._send, encode({"type": "terminate_check", "pid": pid, "alive": alive}))
        threading.Thread(target=work, daemon=True).start()
        return False  # einmalig

    # ---- Sichtprüfung ----
    def _save_snapshot(self, path: str) -> bool:
        self._view.get_snapshot(WebKit.SnapshotRegion.VISIBLE, WebKit.SnapshotOptions.NONE, None,
                                self._snapshot_done, path)
        return False

    def _snapshot_done(self, view, result, path: str) -> None:
        try:
            ok = view.get_snapshot_finish(result).save_to_png(path)
        except GLib.Error:
            ok = False
        print(f"orbitop: snapshot {'saved to' if ok else 'failed:'} {path}", file=sys.stderr)
