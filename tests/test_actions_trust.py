# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Vertrauensprüfung des Root-Helfers (F-1) und von pkexec (I-3): nur eine root-eigene, nicht beschreibbare Kette und
nur das setuid-ELF von polkit starten pkexec."""
import errno
import os
import signal
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from orbitop import actions
from orbitop.actions import terminate
from tests.actions_helpers import ELF, ELF_HEAD, HELPER, INSTALLED, PKEXEC, TRUSTED, chain_lstat, fake, opener, start_of


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
    assert terminate(4242, 77, True, root=foreign, run=fake(calls, 0), lstat=lstat, opener=ELF) == "sent"
    assert seen == [INSTALLED, "/usr/lib/orbitop", "/usr/lib", "/usr", "/", PKEXEC, "/usr/bin", "/usr", "/", PKEXEC]
    assert [c[0] for c in calls] == [["/usr/bin/pkexec", INSTALLED, "4242", "77", "KILL"]]


def test_trust_check_accepts_a_real_root_chain():
    assert actions.trusted(os.path.realpath("/usr/bin/python3"))


def test_own_process_needs_no_helper(child):
    def no_lstat(path):
        pytest.fail("eigene Prozesse brauchen keinen Helfer")
    assert terminate(child.pid, start_of(child.pid), False, lstat=no_lstat) == "sent"
    assert child.wait(5) == -signal.SIGTERM


# ---- Nur das pkexec von polkit (I-3): run0-wrappers auf openSUSE legt ein bash-Skript als /usr/bin/pkexec ab ----
@pytest.mark.parametrize("over,data,want", [
    ({}, ELF_HEAD, "sent"),                                                  # echtes ELF mit setuid
    ({}, b"#!/bin/bash\nexec run0 ", "nohelper"),                            # Shell-Skript mit setuid
    ({PKEXEC: (0, stat.S_IFREG | 0o755)}, ELF_HEAD, "nohelper"),             # ELF ohne setuid
    ({PKEXEC: (0, stat.S_IFLNK | stat.S_ISUID | 0o777)}, ELF_HEAD, "nohelper"),  # Symlink
    ({PKEXEC: (1000, stat.S_IFREG | stat.S_ISUID | 0o755)}, ELF_HEAD, "nohelper"),  # nicht root-eigen
    ({PKEXEC: (0, stat.S_IFREG | stat.S_ISUID | 0o757)}, ELF_HEAD, "nohelper"),  # für andere beschreibbar
    ({"/usr/bin": (1000, stat.S_IFDIR | 0o755)}, ELF_HEAD, "nohelper"),     # Ordner gehört dem User
    ({}, b"\x7fEL", "nohelper"),                                              # zu kurz
    ({}, b"", "nohelper"),
], ids=["elf-setuid", "script-setuid", "elf-no-setuid", "symlink", "not-root", "other-writable", "dir-not-root",
        "short", "empty"])
def test_only_polkits_pkexec_is_started(foreign, over, data, want):
    calls = []
    assert terminate(4242, 77, False, root=foreign, run=fake(calls, 0), lstat=chain_lstat(**over),
                     opener=opener(data)) == want
    assert len(calls) == (want == "sent")


def test_pkexec_is_read_without_following_links_and_closed():
    seen = []
    assert actions.real_pkexec(TRUSTED, opener(seen=seen))
    [(path, flags, fd)] = seen
    assert path == PKEXEC and flags & os.O_NOFOLLOW and flags & os.O_CLOEXEC and flags & os.O_ACCMODE == os.O_RDONLY
    with pytest.raises(OSError):
        os.fstat(fd)  # schon geschlossen


@pytest.mark.parametrize("err", [errno.ELOOP, errno.EACCES, errno.ENOENT], ids=errno.errorcode.get)
def test_pkexec_open_error_is_nohelper(foreign, err):
    def fail(path, flags):
        raise OSError(err, "x")
    calls = []
    assert terminate(4242, 77, False, root=foreign, run=fake(calls, 0), lstat=TRUSTED, opener=fail) == "nohelper"
    assert calls == []


def test_real_open_refuses_a_link_that_lstat_hid(monkeypatch, tmp_path):
    """Echtes os.open: O_NOFOLLOW lässt einen Symlink scheitern, auch wenn der Tausch nach lstat käme."""
    elf, link = tmp_path / "elf", tmp_path / "link"
    elf.write_bytes(ELF_HEAD)
    link.symlink_to(elf)
    for path, want in ((elf, True), (link, False)):
        monkeypatch.setattr(actions, "PKEXEC", str(path))

        def lstat(p):
            mode = stat.S_IFREG | stat.S_ISUID | 0o755 if p == str(path) else stat.S_IFDIR | 0o755
            return SimpleNamespace(st_uid=0, st_mode=mode)
        assert actions.real_pkexec(lstat) is want
