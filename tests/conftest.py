# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import shutil
import subprocess
import warnings
from pathlib import Path
from urllib.parse import unquote

import pytest

from tests.roots import INTEL, VM

# PyGObject 3.56 warnt schon beim ersten Import von GLib über sein eigenes veraltetes unix_signal_add_full
# (gi/overrides/__init__.py, nicht orbitop). Einmal still vorladen, damit -W error::DeprecationWarning nur eigenen Code trifft.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", r"GLib\.unix_signal_add_full is deprecated", DeprecationWarning)
    try:
        from gi.repository import GLib  # noqa: F401
    except ImportError:
        pass


@pytest.fixture
def intel_copy(tmp_path):
    """Beschreibbare Kopie des intel-laptop-Baums."""
    dst = str(tmp_path / "root")
    shutil.copytree(INTEL, dst, symlinks=True)
    return dst


@pytest.fixture
def tree_copy(tmp_path):
    """Fabrik: beschreibbare Kopie eines beliebigen Baums."""
    def make(src):
        dst = str(tmp_path / "root")
        shutil.copytree(src, dst, symlinks=True)
        return dst
    return make


@pytest.fixture
def patched(monkeypatch):
    """Sampler, dessen Leser (read_sensors, read_battery, RaplReader.read) feste Werte liefern."""
    from orbitop import sampler as sampler_mod
    from orbitop.sampler import Sampler
    from tests.sampler_helpers import NoTools, fake_clock

    def make(root=VM, rapl=None, tools=None, ticks=4, **readers):
        for name, val in readers.items():
            monkeypatch.setattr(sampler_mod, name, lambda *a, val=val: val)
        s = Sampler(root, tools=tools or NoTools(), clock=fake_clock(), uid=1000)
        s._rapl.read = lambda now: rapl
        for _ in range(ticks):
            s.tick_system()
            s.tick_procs()
        return s
    return make


@pytest.fixture
def child():
    p = subprocess.Popen(["sleep", "1000"])
    yield p
    p.kill()
    p.wait()


@pytest.fixture
def foreign(tmp_path):
    """Lebender fremder Prozess 4242 mit Startzeit 77; der Testbaum als root."""
    from tests.actions_helpers import foreign_proc
    foreign_proc(tmp_path, 4242, 77, "S")
    return str(tmp_path)


@pytest.fixture
def threads(monkeypatch):
    """threading.Thread in orbitop.jobs ersetzt: start() zeichnet den Thread nur auf; die Liste der gestarteten.
    threading.Lock bleibt echt."""
    import threading
    from types import SimpleNamespace

    from orbitop import jobs
    started = []

    class Thread:
        def __init__(self, target, args=(), daemon=None):
            self.target, self.args, self.daemon = target, args, daemon

        def start(self):
            started.append(self)
    monkeypatch.setattr(jobs, "threading", SimpleNamespace(Thread=Thread, Lock=threading.Lock))
    return started


@pytest.fixture
def jobrig(threads):
    """Jobs mit einer GLib-Attrappe, deren idle_add und timeout_add_seconds nur aufzeichnen; sent: an die Seite."""
    from types import SimpleNamespace

    from orbitop import jobs
    sent, glib = [], SimpleNamespace(idle=[], timeouts=[])
    glib.idle_add = lambda fn, *args: glib.idle.append((fn, args))
    glib.timeout_add_seconds = lambda delay, fn, *args: glib.timeouts.append((delay, fn, args))
    return SimpleNamespace(j=jobs.Jobs(sent.append, glib), sent=sent, glib=glib, threads=threads)


@pytest.fixture
def rig(monkeypatch, tmp_path, threads):
    """Hülle ohne Fenster mit Attrappen für Worker, WebView, Thread und GLib; nur nach check_runtime() nutzbar."""
    from types import SimpleNamespace

    from orbitop import jobs, shell
    from orbitop.layout import LayoutFile
    from tests.shell_helpers import COUNTERS, INSTALL, FakeGLib, FakeView, FakeWorker
    log = []
    glib = FakeGLib()
    monkeypatch.setattr(shell, "GLib", glib)  # vor Shell(): die Hülle baut ihre Jobs selbst, mit dieser Attrappe
    monkeypatch.setattr(jobs.actions, "is_own", lambda pid: False)  # nie /proc des Rechners: jede PID fremd
    s = shell.Shell(False)
    s._worker, s._view = FakeWorker(log), FakeView()
    s._init_fields, s._layouts = {"type": "init"}, LayoutFile(str(tmp_path / "layout.json"))
    s._sampler = SimpleNamespace(close=lambda: log.append("close"), intel=False)
    s._app = SimpleNamespace(quit=lambda: log.append("quit"))
    # nie der echte Autostart-Ordner: set_enabled schriebe sonst nach ~/.config/autostart
    monkeypatch.setattr(shell.autostart, "state", lambda env: None)
    monkeypatch.setattr(shell.autostart, "set_enabled", lambda on, env: log.append(("autostart", on)))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))  # hints.json nie im echten Konfigurationsordner
    # fester Zustand der Freigabe statt des Rechners, auf dem die Tests laufen
    monkeypatch.setattr(jobs.counters, "state", lambda intel: {k: v for k, v in COUNTERS.items() if k != "usable"})
    monkeypatch.setattr(jobs.actions, "counters_usable", lambda: COUNTERS["usable"])
    monkeypatch.setattr(jobs.packagekit, "command", lambda: INSTALL["command"])  # nicht das os-release des Rechners
    return SimpleNamespace(s=s, log=log, glib=glib, threads=threads, js=s._view.js)


def gnupg_socket_dirs():
    """Die Socket-Ordner d.* unter dem socketdir von GnuPG (/run/user/<uid>/gnupg), einer je GNUPGHOME außer dem
    üblichen; leer ohne gpgconf oder wenn das socketdir der GnuPG-Ordner selbst ist (dann gibt es keine d.*)."""
    env = {k: v for k, v in os.environ.items() if k != "GNUPGHOME"}  # sonst legte gpgconf dessen d.* erst an
    try:
        out = subprocess.run(["gpgconf", "--list-dirs"], capture_output=True, text=True, env=env).stdout
    except FileNotFoundError:
        return set()
    dirs = dict(unquote(ln).split(":", 1) for ln in out.splitlines() if ":" in ln)
    base = dirs.get("socketdir")
    if not base or base == dirs.get("homedir") or not os.path.isdir(base):
        return set()
    return {n for n in os.listdir(base) if n.startswith("d.")}


def gpg_agents_below(path):
    """PID -> GNUPGHOME jedes laufenden gpg-agent, dessen --homedir unter PATH liegt."""
    found = {}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace").split("\0")
        except OSError:
            continue
        if os.path.basename(args[0]) == "gpg-agent" and "--homedir" in args[:-1]:
            home = args[args.index("--homedir") + 1]
            if home.startswith(f"{path}/"):
                found[pid] = home
    return found


@pytest.fixture(scope="session", autouse=True)
def gnupg_leaves_nothing(tmp_path_factory):
    """Jeder Test, der ein GNUPGHOME anlegt, stoppt am Ende dessen Agenten und entfernt den Socket-Ordner
    (site_stub.kill_agent); ein Testlauf lässt keinen neuen d.*-Ordner und keinen gpg-agent eines Test-GNUPGHOME
    zurück. shortcut: ein gleichzeitiger GnuPG-Lauf außerhalb dieser Tests zählt mit; schlägt der Wächter deshalb
    fehl, jeden d.* einem GNUPGHOME unter dem basetemp zuordnen (d.<zbase32 der ersten 15 Byte von SHA-1 des
    Pfads>, wie GnuPG ihn bildet)."""
    before = gnupg_socket_dirs()
    yield
    new = sorted(gnupg_socket_dirs() - before)
    agents = gpg_agents_below(tmp_path_factory.getbasetemp())
    assert not new and not agents, (f"GnuPG-Reste des Testlaufs (oder ein gleichzeitiger GnuPG-Lauf außerhalb dieser "
                                    f"Tests): Socket-Ordner {new}, gpg-agent {agents}")


@pytest.fixture(autouse=True)
def no_real_pkexec(monkeypatch):
    """Ein echter pkexec-Start (Passwortdialog!) lässt jeden Test laut scheitern, auch über den Default-Runner."""
    real = subprocess.Popen

    def guard(args, *a, **kw):
        assert "pkexec" not in str(args[0] if isinstance(args, (list, tuple)) else args), "echter pkexec-Aufruf"
        return real(args, *a, **kw)
    monkeypatch.setattr(subprocess, "Popen", guard)


@pytest.fixture(autouse=True)
def no_real_system_bus(monkeypatch):
    """Kein Test erreicht das PackageKit des Rechners (Installation, Dialog): der System-Bus nur als Fake-Bus."""
    try:
        from gi.repository import Gio
    except ImportError:
        return
    real = Gio.bus_get_sync

    def guard(bus_type, *a, **kw):
        assert bus_type != Gio.BusType.SYSTEM, "echter System-Bus"
        return real(bus_type, *a, **kw)
    monkeypatch.setattr(Gio, "bus_get_sync", guard)
