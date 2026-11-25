# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""GTK-4-Fenster mit WebView: Einzelinstanz, Hintergrundbetrieb und Brücke zur Seite.

Erst nach app.check_runtime() importieren, sonst endet ein fehlendes WebKit in einem Traceback."""
import math
import os
import signal
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit  # noqa: E402

from orbitop import APP_ID, __version__, autostart, hints  # noqa: E402
from orbitop.app import SCHEME, UI_HOST, Worker, snapshot_path, ui_file  # noqa: E402
from orbitop.i18n import detect_language, load_texts  # noqa: E402
from orbitop.jobs import Jobs, counters_payload, install_payload  # noqa: E402
from orbitop.layout import KEYS, LayoutFile, config_path  # noqa: E402
from orbitop.messages import encode, parse_message  # noqa: E402
from orbitop.sampler import Sampler  # noqa: E402

UI_DIR = str(Path(__file__).resolve().parent / "ui")
INDEX_URI = f"{SCHEME}://{UI_HOST}/index.html"
SNAPSHOT_DELAY_S = 5
RELOAD_GAP_S = 10  # nach Abstürzen des Web-Prozesses höchstens einmal je 10 s neu laden


def _unix_signal_add():
    """GLibUnix.signal_add (neue GLib), sonst GLib.unix_signal_add (GLib 2.80 in Ubuntu 24.04: nur signal_add_full)."""
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        return GLibUnix.signal_add
    except (ImportError, ValueError, AttributeError):
        return GLib.unix_signal_add


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
        self._argv = ["orbitop", "--hidden"] if hidden else ["orbitop"]
        self._jobs = Jobs(self._send, GLib)  # Aufträge der Seite in eigenen Threads
        self._reloaded = -math.inf
        # Jeder Start reicht seine Argumente an die erste Instanz weiter (Einzelinstanz über D-Bus)
        self._app = Gtk.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self._app.connect("startup", self._startup)
        self._app.connect("command-line", self._command_line)
        self._app.connect("activate", lambda _app: self._win.present())  # gapplication launch, D-Bus Activate
        self._app.connect("shutdown", self._shutdown)

    def run(self) -> int:
        return self._app.run(self._argv)

    # ---- Lebenszyklus (nur in der ersten Instanz) ----
    def _startup(self, app) -> None:
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        quit_action = Gio.SimpleAction(name="quit")
        quit_action.connect("activate", lambda *_: app.quit())
        app.add_action(quit_action)
        app.set_accels_for_action("app.quit", ["<Control>q"])
        _unix_signal_add()(GLib.PRIORITY_DEFAULT, signal.SIGTERM, app.quit)  # sauber beenden, auch per timeout/kill
        app.hold()  # weiterlaufen, auch ohne sichtbares Fenster
        lang = detect_language(os.environ)
        self._init_fields = {"type": "init", "lang": lang, "texts": load_texts(lang), "version": __version__}
        self._layouts = LayoutFile(config_path(os.environ))
        self._layouts.load()
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
        # eigenes Schema statt file://: so deckt 'self' in der CSP nur orbitop/ui/ ab, keine beliebige lokale Datei
        self._view.get_context().register_uri_scheme(SCHEME, self._serve)
        # Eine Seite ohne Navigation: kleinste Caches (Eigenlast, Speicher); muss vor dem Laden gesetzt sein
        self._view.get_context().set_cache_model(WebKit.CacheModel.DOCUMENT_VIEWER)
        self._view.connect("decide-policy", self._decide_policy)
        self._view.connect("web-process-terminated", self._on_web_crash)
        self._win = Gtk.ApplicationWindow(application=app, title="orbitop", default_width=1600, default_height=1000,
                                          child=self._view)
        self._win.connect("close-request", self._on_close)
        self._win.connect("notify::visible", self._on_visible)
        self._win.connect("notify::suspended", self._on_visible)
        # Nur zur Sichtprüfung: zusammen mit ORBITOP_SNAPSHOT öffnet ORBITOP_TAB=procs den Reiter „Prozesse“
        procs_tab = self._snapshot and os.environ.get("ORBITOP_TAB") == "procs"
        self._view.load_uri(INDEX_URI + ("#procs" if procs_tab else ""))

    def _command_line(self, _app, cmdline) -> int:
        if "--hidden" not in cmdline.get_arguments():  # verborgene Starts (Autostart) zeigen nie das Fenster
            self._win.present()
        return 0

    def _shutdown(self, _app) -> None:
        self._jobs.stop()
        self._worker.stop()
        self._sampler.close()  # beendet intel_gpu_top

    def _on_close(self, win) -> bool:
        win.set_visible(False)
        return True  # nur ausblenden, nicht zerstören

    def _on_visible(self, win, _pspec) -> None:
        visible = win.get_visible() and not win.is_suspended()  # minimiert zählt als ausgeblendet
        if self._worker.update(visible=visible):
            self._send(self._init_message())  # der Worker schickt gleich danach einen tick
        if visible and self._snapshot:
            GLib.timeout_add_seconds(SNAPSHOT_DELAY_S, self._save_snapshot, self._snapshot)
            self._snapshot = None

    # ---- Brücke ----
    def _init_message(self) -> str:
        # bei jedem Senden das aktuelle Layout und die Stände von jetzt: Autostart, Freigabe, ausgeblendete Hinweise
        intel = self._sampler.intel
        return encode({**self._init_fields, "layout": self._layouts.current, "autostart": autostart.state(os.environ),
                       "counters": counters_payload(intel), "hidden_hints": hints.load(os.environ),
                       "install": {**install_payload(intel), "closed": self._jobs.closed}})

    def _send(self, text: str) -> None:
        """text stammt aus encode(), ist also ein sicheres JS-Literal."""
        self._view.evaluate_javascript(f"window.orbitop.receive({text})", -1, None, None, None, None, None)

    def _on_web_crash(self, _view, _reason) -> None:
        self._worker.update(ready=False)
        delay = math.ceil(max(0.0, self._reloaded + RELOAD_GAP_S - time.monotonic()))
        GLib.timeout_add_seconds(delay, self._reload)

    def _reload(self) -> bool:
        self._reloaded = time.monotonic()
        self._view.load_uri(INDEX_URI)  # die neue Seite meldet ready, dann folgen init und tick
        return False

    def _serve(self, request) -> None:
        """Antwort für orbitop://ui/…: nur reguläre Dateien bekannten Typs unter orbitop/ui/."""
        found = ui_file(request.get_uri(), UI_DIR)
        try:
            data = GLib.Bytes.new(Path(found[0]).read_bytes()) if found else None
        except OSError:
            data = None
        if data is None:
            request.finish_error(GLib.Error.new_literal(Gio.io_error_quark(), "not found", Gio.IOErrorEnum.NOT_FOUND))
            return
        request.finish(Gio.MemoryInputStream.new_from_bytes(data), data.get_size(), found[1])

    def _on_message(self, _ucm, value) -> None:
        msg = parse_message(value.to_json(0))
        if msg is None:
            return
        kind = msg["type"]
        if kind == "ready":
            if self._worker.update(ready=True):
                self._send(self._init_message())
        elif kind == "view":
            self._worker.update(view=msg)
        elif kind == "layout":
            self._layouts.save({k: msg[k] for k in KEYS})
        elif kind == "terminate":
            self._jobs.terminate(msg["pid"], msg["start"], msg["force"])
        elif kind == "autostart":
            self._send(encode({"type": "autostart_state", "on": autostart.set_enabled(msg["on"], os.environ)}))
        elif kind == "counters":
            self._jobs.counters(msg["on"], self._sampler)
        elif kind == "install_tool":
            self._jobs.install_tool(self._sampler, lambda: self._send(self._init_message()))
        elif kind in ("hide_hint", "show_hints"):
            hidden = hints.hide(msg["key"], os.environ) if kind == "hide_hint" else hints.show_all(os.environ)
            self._send(encode({"type": "hints_state", "hidden_hints": hidden}))
        else:
            self._app.quit()

    def _decide_policy(self, _view, decision, kind) -> bool:
        if kind == WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            found = ui_file(decision.get_navigation_action().get_request().get_uri(), UI_DIR)
            ok = found is not None and found[1] == "text/html"  # navigiert wird nur zu Seiten
        elif kind == WebKit.PolicyDecisionType.RESPONSE:  # nicht darstellbar hieße Download
            ok = decision.is_mime_type_supported() and ui_file(decision.get_request().get_uri(), UI_DIR) is not None
        else:  # neue Fenster
            ok = False
        if ok:
            decision.use()
        else:
            decision.ignore()
        return True

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
