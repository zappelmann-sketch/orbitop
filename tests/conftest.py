# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import shutil
import subprocess

import pytest

from tests.roots import INTEL


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
