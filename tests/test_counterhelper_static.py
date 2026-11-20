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


# Jedes Attribut, das der Helfer an einem Modul benutzt, dazu os.O_*: Systemaufrufe aus Python, kein exec, keine
# Umgebung (B2.1). Eine Positivliste: was hier fehlt, fällt auf, auch execlp, getenvb oder posix_spawnp.
USES = {
    "os": {"close", "fchmod", "fstat", "fsync", "geteuid", "lstat", "open", "path", "removexattr", "setxattr", "stat",
           "umask", "unlink"},
    "os.path": {"dirname", "split"},
    "errno": {"ENODATA"}, "fcntl": {"LOCK_EX", "LOCK_NB", "flock"}, "glob": {"glob"},
    "stat": {"S_IMODE", "S_ISDIR", "S_ISREG"}, "struct": {"pack"}, "sys": {"argv", "exit", "stderr"},
    "time": {"monotonic", "sleep"},
}
BANNED = {"getattr", "setattr", "delattr", "__import__", "importlib", "__builtins__", "eval", "exec", "compile",
          "globals", "locals", "vars", "breakpoint"}


def problems(source):
    """Was gegen die Regeln des Helfers verstößt: ein Import außer `import x` aus ALLOWED (kein from, kein as), ein
    Modul anders als in `modul.attr`, ein Attribut außerhalb von USES, ein Name aus BANNED."""
    nodes = list(ast.walk(ast.parse(source)))
    found, prefixes = [], set()
    for n in nodes:
        if isinstance(n, ast.ImportFrom):
            found.append(f"from {n.module} import")
        elif isinstance(n, ast.Import):
            found += [f"import {a.name} as {a.asname}" for a in n.names if a.name not in ALLOWED or a.asname]
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in ALLOWED:
            prefixes.add(id(n.value))
            if n.attr not in USES[n.value.id] and not (n.value.id == "os" and n.attr.startswith("O_")):
                found.append(f"{n.value.id}.{n.attr}")
        elif isinstance(n, ast.Attribute) and ast.unparse(n.value) == "os.path" and n.attr not in USES["os.path"]:
            found.append(f"os.path.{n.attr}")
    for n in nodes:
        if isinstance(n, ast.Name) and n.id in BANNED:
            found.append(n.id)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in ALLOWED and id(n) not in prefixes:
            found.append(f"{n.id} as a value")
    return found


def test_only_listed_standard_modules():
    imported = {a.name for n in ast.walk(tree()) if isinstance(n, ast.Import) for a in n.names}
    assert imported == ALLOWED and imported <= sys.stdlib_module_names


def test_only_listed_calls_no_programs_no_environment():
    assert problems(HELPER.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("snippet", [
    "from os import system as s", "from os import environ", "import os as z", "import subprocess", "import importlib",
    "os.execlp('x', 'x')", "os.execv('x', [])", "os.system('x')", "os.environ['A']", "os.getenvb(b'A')",
    "os.posix_spawnp('x', [], {})", "os.fork()", "os.path.expanduser('~')", "sys.modules", "time.time()",
    "getattr(os, 'system')", "__import__('os')", "eval('1')", "x = os", "f(os)"])
def test_the_check_finds_forbidden_forms(snippet):  # Gegenprobe: die Positivliste lässt keine dieser Formen durch
    assert problems(snippet)


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
