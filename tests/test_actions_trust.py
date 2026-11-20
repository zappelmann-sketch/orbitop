# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Vertrauensprüfung des Root-Helfers (F-1): nur eine root-eigene, nicht beschreibbare Kette startet pkexec."""
import os
import signal
import stat
from pathlib import Path

import pytest

from orbitop import actions
from orbitop.actions import terminate
from tests.actions_helpers import HELPER, INSTALLED, TRUSTED, chain_lstat, fake, start_of


# ---- Vertrauensprüfung des Root-Helfers (F-1) ----
@pytest.mark.parametrize("make", ["user_file", "missing", "symlink"])
def test_helper_in_user_tree_is_nohelper(monkeypatch, foreign, tmp_path, make):
    """Echtes lstat: ein Helfer, den User-Code austauschen könnte, startet nie pkexec."""
    f = tmp_path / "libexec" / "killhelper.py"
    f.parent.mkdir()
    if make == "user_file":
        f.write_bytes(Path(HELPER).read_bytes())
        f.chmod(0o755)
    elif make == "symlink":
        f.symlink_to(os.path.realpath("/usr/bin/python3"))  # Ziel root-eigen, der Link selbst zählt
    monkeypatch.setattr(actions, "_HELPER", str(f))
    calls = []
    assert terminate(4242, 77, False, root=foreign, run=fake(calls, 0)) == "nohelper"
    assert calls == []


@pytest.mark.parametrize("over", [
    {INSTALLED: (1000, stat.S_IFREG | 0o755)},                   # Datei gehört dem User
    {INSTALLED: (0, stat.S_IFREG | 0o775)},                      # Datei für die Gruppe beschreibbar
    {INSTALLED: (0, stat.S_IFLNK | 0o777)},                      # Symlink
    {INSTALLED: (0, stat.S_IFDIR | 0o755)},                      # keine reguläre Datei
    {INSTALLED: (0, stat.S_IFREG | 0o644)},                      # nicht ausführbar: pkexec scheiterte nach dem Passwort
    {"/usr/lib/orbitop": (0, stat.S_IFDIR | 0o775)},             # Elternverzeichnis für die Gruppe beschreibbar
    {"/usr": (0, stat.S_IFDIR | 0o757)},                         # weiter oben für andere beschreibbar
    {"/usr/lib": (1000, stat.S_IFDIR | 0o755)},                  # Verzeichnis gehört dem User
    {"/": (0, stat.S_IFDIR | 0o777)},
])
def test_untrusted_chain_is_nohelper(foreign, over):
    calls = []
    assert terminate(4242, 77, False, root=foreign, run=fake(calls, 0), lstat=chain_lstat(**over)) == "nohelper"
    assert calls == []


def test_trusted_chain_reaches_runner_with_exact_argv(foreign):
    seen, calls = [], []

    def lstat(path):
        seen.append(path)
        return TRUSTED(path)
    assert terminate(4242, 77, True, root=foreign, run=fake(calls, 0), lstat=lstat) == "sent"
    assert seen == [INSTALLED, "/usr/lib/orbitop", "/usr/lib", "/usr", "/"]
    assert [c[0] for c in calls] == [["/usr/bin/pkexec", INSTALLED, "4242", "77", "KILL"]]


def test_trust_check_accepts_a_real_root_chain():
    assert actions._trusted(os.path.realpath("/usr/bin/python3"))


def test_own_process_needs_no_helper(child):
    def no_lstat(path):
        pytest.fail("eigene Prozesse brauchen keinen Helfer")
    assert terminate(child.pid, start_of(child.pid), False, lstat=no_lstat) == "sent"
    assert child.wait(5) == -signal.SIGTERM
