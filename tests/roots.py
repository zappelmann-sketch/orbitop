# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os

ROOTS = os.path.join(os.path.dirname(__file__), "fixtures", "roots")
INTEL, AMD, ARM, VM = (os.path.join(ROOTS, n) for n in ("intel-laptop", "amd-desktop", "arm-board", "vm"))
