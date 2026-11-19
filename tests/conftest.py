# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import shutil
import subprocess
import warnings

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


@pytest.fixture(autouse=True)
def no_real_pkexec(monkeypatch):
    """Ein echter pkexec-Start (Passwortdialog!) lässt jeden Test laut scheitern, auch über den Default-Runner."""
    real = subprocess.Popen

    def guard(args, *a, **kw):
        assert "pkexec" not in str(args[0] if isinstance(args, (list, tuple)) else args), "echter pkexec-Aufruf"
        return real(args, *a, **kw)
    monkeypatch.setattr(subprocess, "Popen", guard)
