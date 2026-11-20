# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""counterhelper: Aufruf, root, User-Namespace, Lock und Exit-Codes (B2.1), über TreeOS unter einem Testbaum."""
import errno
import fcntl
import os
import subprocess
import sys

import pytest

from orbitop import counterhelper
from orbitop.counterhelper import main
from tests.counterhelper_helpers import make_tree, marker


@pytest.fixture
def osl(tmp_path):
    return make_tree(tmp_path)


@pytest.mark.parametrize("argv", [[], ["on", "x"], ["ON"], ["on\n"], ["оn"], ["--on"], ["on "], ["of"],
                                  ["sync", "on"], [""], ["off\x00"]])
def test_invalid_call_gives_2_and_touches_nothing(osl, argv):  # "оn": mit kyrillischem о
    assert main(argv, osl) == counterhelper.INVALID
    assert (osl.log, osl.opens, osl.mask) == ([], [], None)


@pytest.mark.parametrize("word", counterhelper.WORDS)
def test_not_root_gives_2_and_touches_nothing(tmp_path, word):
    osl = make_tree(tmp_path)
    osl.euid = 1000
    marker(tmp_path).touch()
    assert main([word], osl) == counterhelper.INVALID
    assert (osl.log, osl.opens, osl.mask) == ([], [], None)
    assert marker(tmp_path).exists()


def test_umask_is_set_before_anything_is_opened(osl):
    seen = []
    real_open = osl.open
    osl.open = lambda *a, **k: seen.append(osl.mask) or real_open(*a, **k)
    assert main(["on"], osl) == counterhelper.OK
    assert seen and set(seen) == {0o022}


@pytest.mark.parametrize("uid_map", ["0 1000 1\n", "         0       1000      65536\n", "0 0 4294967294\n",
                                     "0 0 4294967295\n1 1 1\n", ""])
def test_user_namespace_refuses_on_and_skips_sync(tmp_path, uid_map):  # R1.9: v3-Fähigkeit wirkte nicht auf dem Host
    osl = make_tree(tmp_path)
    osl.map = uid_map
    assert main(["on"], osl) == counterhelper.UNSAFE
    assert osl.writes() == [] and not marker(tmp_path).exists()
    marker(tmp_path).touch()
    assert main(["sync"], osl) == counterhelper.OK
    assert osl.writes() == []


def test_unreadable_uid_map_counts_as_user_namespace(tmp_path):
    osl = make_tree(tmp_path)
    osl.fail["uid_map"] = errno.ENOENT
    assert main(["on"], osl) == counterhelper.UNSAFE
    marker(tmp_path).touch()
    assert main(["sync"], osl) == counterhelper.OK
    assert osl.writes() == []


def test_off_works_in_a_user_namespace(tmp_path):  # zurücknehmen schadet nie
    osl = make_tree(tmp_path)
    osl.map = "0 1000 1\n"
    marker(tmp_path).touch()
    assert main(["off"], osl) == counterhelper.OK
    assert not marker(tmp_path).exists()


def test_kernel_format_of_the_init_namespace_counts(tmp_path, osl):  # zusammengefasst: "0 0 4294967295"
    assert osl.map != "0 0 4294967295\n"
    assert main(["on"], osl) == counterhelper.OK
    assert marker(tmp_path).exists()


@pytest.fixture
def held(osl):
    """Ein anderer Prozess hält das Lock auf /etc/orbitop (eigene offene Datei, flock wie der Helfer)."""
    fd = os.open(osl.root + "/etc/orbitop", os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    yield fd
    os.close(fd)


@pytest.mark.parametrize("word", counterhelper.WORDS)
def test_held_lock_gives_1_after_10_s(tmp_path, osl, held, word):  # R1.8: nie endlos warten, Uhr injiziert
    marker(tmp_path).touch()
    assert main([word], osl) == counterhelper.FAILED
    assert 10.0 <= osl.now < 10.0 + 2 * counterhelper.LOCK_STEP
    assert set(osl.sleeps) == {counterhelper.LOCK_STEP} and len(osl.sleeps) >= 50
    assert osl.writes() == [] and marker(tmp_path).exists()


def test_lock_is_taken_once_it_is_free(tmp_path, osl, held):
    sleep = osl.sleep

    def release_after_one_second(s):
        sleep(s)
        if osl.now >= 1.0:
            fcntl.flock(held, fcntl.LOCK_UN)
    osl.sleep = release_after_one_second
    assert main(["on"], osl) == counterhelper.OK
    assert 1.0 <= osl.now < 1.5 and marker(tmp_path).exists()


CALLS = ["uid_map", "open", "close", "fstat", "lstat", "stat", "fsync", "unlink", "setxattr", "removexattr", "fchmod",
         "flock", "glob"]


@pytest.mark.parametrize("call", CALLS)
@pytest.mark.parametrize("err", [errno.EIO, errno.EROFS, errno.ELOOP, errno.ENOENT, errno.EACCES, errno.EPERM])
def test_exit_codes_never_126_or_127(tmp_path, call, err):  # R1.6: die App läse sie als Abbruch oder Ablehnung
    for word in counterhelper.WORDS:
        osl = make_tree(tmp_path / word)
        marker(tmp_path / word).touch()
        osl.fail[call] = err
        assert main([word], osl) in range(5), (word, call, err)


@pytest.mark.skipif(os.geteuid() == 0, reason="der Helfer läuft hier nie als root")
@pytest.mark.parametrize("argv, code", [(["ON"], 2), (["sync"], 2), ([], 2)])
def test_started_as_script_prints_one_line(argv, code):  # wie pkexec ihn startet: python3 -IS, Exit-Code von main
    r = subprocess.run([sys.executable, "-IS", counterhelper.__file__, *argv], capture_output=True, text=True,
                       timeout=30)
    assert (r.returncode, r.stdout, r.stderr.count("\n")) == (code, "", 1)
    assert r.stderr.startswith("counterhelper: ")
