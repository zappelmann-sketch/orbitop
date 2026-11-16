# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREES = ROOT / "tests" / "fixtures" / "roots"


def dry_run(tree):
    env = {**os.environ, "ORBITOP_SYSROOT": str(TREES / tree)}
    r = subprocess.run(
        ["bash", str(ROOT / "scripts" / "setup-privileges.sh"), "--dry-run"],
        env=env, capture_output=True, text=True, check=True,
    )
    return r.stdout


def test_intel_plans_webkit_igt_setcap_rapl():
    out = dry_run("intel-laptop")
    assert "WOULD: apt-get install -y gir1.2-webkit-6.0 intel-gpu-tools" in out
    assert "setcap cap_perfmon=ep" in out and "/etc/tmpfiles.d/orbitop-rapl.conf" in out


def test_amd_plans_rapl_but_no_igt():
    out = dry_run("amd-desktop")
    assert "intel-gpu-tools" not in out and "orbitop-rapl.conf" in out


def test_arm_plans_only_webkit():
    out = dry_run("arm-board")
    assert "gir1.2-webkit-6.0" in out and "setcap" not in out and "rapl" not in out.lower()


def test_vm_plans_only_webkit():
    out = dry_run("vm")
    assert "gir1.2-webkit-6.0" in out and "setcap" not in out and "rapl" not in out.lower()


def test_refuses_without_root_and_without_dry_run():
    if os.geteuid() == 0:
        return
    r = subprocess.run(["bash", str(ROOT / "scripts" / "setup-privileges.sh")],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "root" in r.stderr


def test_shellcheck_clean():
    assert subprocess.run(["shellcheck", str(ROOT / "scripts/setup-privileges.sh"),
                           str(ROOT / "scripts/capture-fixture.sh")]).returncode == 0
