# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import shutil

import pytest

ROOTS = os.path.join(os.path.dirname(__file__), "fixtures", "roots")
INTEL, AMD, ARM, VM = (os.path.join(ROOTS, n) for n in ("intel-laptop", "amd-desktop", "arm-board", "vm"))


@pytest.fixture
def intel_copy(tmp_path):
    """Beschreibbare Kopie des intel-laptop-Baums."""
    dst = str(tmp_path / "root")
    shutil.copytree(INTEL, dst, symlinks=True)
    return dst
