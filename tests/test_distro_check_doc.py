# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/release/distro-check.py: das Ergebnis der Container-Matrix in docs/distro-check.md, nur mit Werten aus
einem kleinen Zeichenvorrat (die Container schreiben die Protokolle), und dasselbe über scripts/release.sh."""
import subprocess

import pytest

from tests.packaging_common import ROOT
from tests.release_stub import VERSION, make_repo, matrix_output, run
from tests.site_stub import kill_agent, make_keys, needs_git

SCRIPT = ROOT / "scripts" / "release" / "distro-check.py"
FPR = "A" * 40
START = "<!-- matrix:start: scripts/release.sh writes this part from the output of scripts/check-distros.sh -->"
END = "<!-- matrix:end -->"


def write(tmp_path, output, *args):
    doc = tmp_path / "doc.md"
    doc.write_text(f"# Head\n\n{START}\nold\n{END}\n\n## Notes\n")
    r = subprocess.run(["python3", "-I", str(SCRIPT), str(doc), VERSION, "2026.11.18", *args], input=output,
                       capture_output=True, text=True)
    return r, doc.read_text()


def test_writes_only_between_the_markers(tmp_path):
    r, doc = write(tmp_path, matrix_output(FPR), "--dry-run")
    assert r.returncode == 0, r.stderr
    assert doc.startswith(f"# Head\n\n{START}\n- Run: `scripts/release.sh {VERSION} --dry-run` on ")
    assert doc.endswith(f"{END}\n\n## Notes\n") and "old" not in doc
    assert "| Debian 13 | `debian:trixie` |" in doc and "| Debian 12 | `debian:bookworm` |" in doc


def test_takes_the_summary_of_a_test_run_over_a_minute(tmp_path):  # pytest hängt dann "(0:01:05)" an
    r, doc = write(tmp_path, matrix_output(FPR).replace("in 30.25s", "in 65.12s (0:01:05)"))
    assert r.returncode == 0, r.stderr
    assert "| 1000 passed, 50 skipped | pass |" in doc


@pytest.mark.parametrize("change", [
    ("VERSIONS python 3.13.5 pygobject", "VERSIONS python 3.13.5|evil pygobject"),
    ("VERSION_ID=\"13\"", "VERSION_ID=\"13 | <b>\""),
    ("offered", "offered `x`"),
    ("1000 passed, 50 skipped in 30.25s", "1000 passed, <img src=x> in 30.25s"),
    ("but 3.11.2-1+b1 is", "but 3.11 | x is"),
    ("IMAGE debian:bookworm", "IMAGE debian:trixie"),  # ein Image zweimal
    ("IMAGE debian:bookworm", "IMAGE Debian Bookworm"),
    ("pass install", "fail install"),
    (f"KEY {FPR}\nRESULT", f"KEY {'B' * 40}\nRESULT"),  # zwei Schlüssel
    ("RESULT debian:trixie debian@sha256:", "RESULT debian:trixie debian@sha256:x"),
], ids=["versions", "version-id", "update", "tests", "refusal", "duplicate-image", "image", "fail", "two-keys",
        "digest"])
def test_refuses_anything_outside_the_patterns(tmp_path, change):
    output = matrix_output(FPR)
    assert change[0] in output
    r, doc = write(tmp_path, output.replace(change[0], change[1], 1))
    assert r.returncode != 0 and "distro-check.py:" in r.stderr, r.stderr
    assert "\nold\n" in doc  # nichts geschrieben


@needs_git
def test_release_writes_the_results(tmp_path):
    keys = make_keys(tmp_path / "gnupg")
    try:
        repo = make_repo(tmp_path, keys["fpr"], readme=keys["fpr"])
        r, _ = run(tmp_path, repo, keys, VERSION, "--dry-run")
    finally:
        kill_agent(keys["home"])
    assert r.returncode == 0, r.stderr
    doc = (repo["repo"] / "docs" / "distro-check.md").read_text()
    block = doc[doc.index("<!-- matrix:start"):doc.index(END)]
    assert f"`scripts/release.sh {VERSION} --dry-run`" in block and f"`KEY {keys['fpr']}`" in block
    assert "throwaway key" in block
    assert (f"| Debian 13 | `debian:trixie` | `debian@sha256:{'1' * 64}` | `orbitop {VERSION}-1` → "
            f"`{VERSION}-1+check1`: Python 3.13.5, PyGObject 3.50.0, GTK 4.18.6, WebKitGTK 2.54.0 | "
            "1000 passed, 50 skipped | pass |") in block
    assert (f"| Debian 12 | `debian:bookworm` | `debian@sha256:{'2' * 64}` | `orbitop {VERSION}-1` refused | – | "
            'pass (expected refusal): step `install`, "orbitop : Depends: python3 (>= 3.12) but 3.11.2-1+b1 is to '
            'be installed" |') in block
    assert "| Distribution |" not in doc.replace(block, "")  # nur die Tabelle im geschriebenen Teil
