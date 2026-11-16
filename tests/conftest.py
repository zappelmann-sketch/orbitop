# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import shutil
import subprocess
import warnings

import pytest

from tests.roots import INTEL

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


@pytest.fixture(autouse=True)
def no_real_pkexec(monkeypatch):
    """Ein echter pkexec-Start (Passwortdialog!) lässt jeden Test laut scheitern, auch über den Default-Runner."""
    real = subprocess.Popen

    def guard(args, *a, **kw):
        assert "pkexec" not in str(args[0] if isinstance(args, (list, tuple)) else args), "echter pkexec-Aufruf"
        return real(args, *a, **kw)
    monkeypatch.setattr(subprocess, "Popen", guard)
