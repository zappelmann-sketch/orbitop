# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import shutil

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
