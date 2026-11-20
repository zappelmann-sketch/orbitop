# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""packaging/container-prologue.sh, der gemeinsame Anfang der Skripte in den Wegwerf-Containern: Außerhalb eines
Containers bricht er ab, bevor er den Schlüssel von stdin liest, und hinterlässt keine Datei. Im Container läuft er
im Arch-Testbau mit (tests/test_packaging_arch.py)."""
import os
import subprocess

import pytest

from tests.packaging_common import PKG


@pytest.mark.skipif(os.path.exists("/.dockerenv") and os.geteuid() == 0, reason="root im Container: läuft weiter")
def test_outside_a_container_it_stops_before_reading_the_key(tmp_path):
    r = subprocess.run(["bash", "-c", '. "$1"; echo after', "prologue", str(PKG / "container-prologue.sh")],
                       input=b"key", capture_output=True, env={**os.environ, "TMPDIR": str(tmp_path), "OWNER": "0:0"})
    assert r.returncode == 1 and b"only as root inside a disposable container" in r.stderr, r.stderr
    assert b"after" not in r.stdout
    assert list(tmp_path.iterdir()) == []  # mktemp legt tmp.* in TMPDIR an
