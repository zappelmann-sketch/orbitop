# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""counterhelper ohne Ausführen: Shebang, Importe, Konstanten, OS-Schicht und die udev-Regel (B2.1, B2.3)."""
import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

from orbitop import counterhelper
from tests.counterhelper_helpers import TreeOS

ROOT = Path(__file__).resolve().parent.parent
HELPER = Path(counterhelper.__file__)
RULE = ROOT / "data" / "70-orbitop-counters.rules"
ALLOWED = {"errno", "fcntl", "glob", "os", "stat", "struct", "sys", "time"}  # B2.1: nur diese Standardmodule


def tree():
    return ast.parse(HELPER.read_text(encoding="utf-8"))


def test_shebang():  # B2.1: unter -S lädt Python keine .pth-Datei aus site-packages, auch nicht als root
    assert HELPER.read_bytes().split(b"\n", 1)[0] == b"#!/usr/bin/python3 -IS"


def test_only_listed_standard_modules():
    imported = set()
    for node in ast.walk(tree()):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add("." * node.level + (node.module or ""))
    assert imported == ALLOWED
    assert imported <= sys.stdlib_module_names


@pytest.mark.parametrize("name", ["subprocess", "system", "environ", "environb", "getenv", "putenv", "popen",
                                  "execv", "execve", "spawnv", "fork", "posix_spawn", "eval", "exec", "__import__"])
def test_never_starts_programs_or_reads_the_environment(name):
    used = {n.id for n in ast.walk(tree()) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(tree()) if isinstance(n, ast.Attribute)}
    assert name not in used


def test_main_only_when_started():  # Task 5/6 importieren MARKER: der Import selbst tut nichts
    body = tree().body
    calls = [n for n in body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
    assert not calls
    assert isinstance(body[-1], ast.If) and ast.unparse(body[-1].test) == "__name__ == '__main__'"


def test_helper_is_executable_in_git():  # der Checkout-Modus hängt von der umask ab, das Repository gibt 100755
    assert os.access(HELPER, os.X_OK)
    try:
        out = subprocess.run(["git", "ls-files", "-s", "--", str(HELPER)], cwd=ROOT, capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("git nicht verfügbar")
    if out.returncode != 0 or not out.stdout:
        pytest.skip("kein Git-Checkout")
    assert out.stdout.startswith("100755 ")


def test_constants():
    assert counterhelper.CAP.hex() == "0100000200000000000000004000000000000000"  # = setcap cap_perfmon=ep (P1)
    assert counterhelper.MARKER == "/etc/orbitop/counters-released"
    assert counterhelper.TOOL == "/usr/bin/intel_gpu_top"
    assert counterhelper.RAPL == "/sys/class/powercap/intel-rapl:*/energy_uj"  # wie sensors.RaplReader, ohne MMIO
    assert counterhelper.WORDS == ("on", "off", "sync")
    codes = (counterhelper.OK, counterhelper.FAILED, counterhelper.INVALID, counterhelper.UNSAFE,
             counterhelper.PARTIAL)
    assert codes == (0, 1, 2, 3, 4)  # 126 und 127 meldet pkexec für Abbruch und Ablehnung


def test_tree_os_has_every_call_of_the_real_one():  # sonst liefe in einem Test still ein echter Systemaufruf
    real = {n for n in vars(counterhelper.RealOS) if not n.startswith("_")}
    fake = {n for n, _ in inspect.getmembers(TreeOS, inspect.isfunction) if not n.startswith("_")}
    assert real <= fake
    assert {"open", "fstat", "lstat", "setxattr", "removexattr", "fchmod", "flock", "glob", "uid_map"} <= real


def rules():
    return [ln for ln in RULE.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def test_udev_rule_is_the_one_line_of_b23():
    assert rules() == ['ACTION=="add", SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", '
                       f'TEST=="{counterhelper.MARKER}", RUN+="/usr/bin/chmod go+r /sys%p/energy_uj"']


def test_udev_rule_has_its_own_name():  # R3.1: die Handregel aus der README 0.2.0 verdeckte sonst die Paketregel
    assert RULE.name != "70-orbitop-rapl.rules"
    assert RULE.name.endswith(".rules")


def test_udev_rule_header():
    head = RULE.read_text(encoding="utf-8").splitlines()[:2]
    assert head == ["# SPDX-License-Identifier: GPL-3.0-or-later", "# Copyright © 2026 zappelmann-sketch"]
