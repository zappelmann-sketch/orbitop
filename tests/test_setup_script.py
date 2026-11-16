# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TREES = ROOT / "tests" / "fixtures" / "roots"


RULE = ('ACTION=="add", SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", '
        'RUN+="/usr/bin/chmod 0444 /sys%p/energy_uj"')
SCRIPT = str(ROOT / "scripts" / "setup-privileges.sh")


def dry_run(tree, *args):
    env = {**os.environ, "ORBITOP_SYSROOT": str(TREES / tree)}
    r = subprocess.run(["bash", SCRIPT, "--dry-run", *args],
                       env=env, capture_output=True, text=True, check=True)
    return r.stdout


def test_intel_plans_webkit_igt_setcap_no_rapl():
    out = dry_run("intel-laptop")
    assert "WOULD: apt-get install -y gir1.2-webkit-6.0 intel-gpu-tools" in out
    assert "WOULD: setcap cap_perfmon=ep /usr/bin/intel_gpu_top" in out
    assert "rapl" not in out.lower().replace("--allow-rapl", "")


def test_amd_default_no_rapl_rule():
    out = dry_run("amd-desktop")
    assert "intel-gpu-tools" not in out and "70-orbitop-rapl.rules" not in out


def test_amd_allow_rapl_plans_udev_rule_with_warning():
    out = dry_run("amd-desktop", "--allow-rapl")
    assert "/etc/udev/rules.d/70-orbitop-rapl.rules" in out and "CVE-2020-8694" in out
    assert out.index("CVE-2020-8694") < out.index("70-orbitop-rapl.rules")
    assert RULE in out.splitlines()
    assert "WOULD: udevadm control --reload" in out
    assert "WOULD: udevadm trigger --subsystem-match=powercap --action=add" in out


def test_arm_plans_only_webkit():
    out = dry_run("arm-board")
    assert "gir1.2-webkit-6.0" in out and "setcap" not in out and "rapl" not in out.lower()


def test_vm_plans_only_webkit():
    out = dry_run("vm")
    assert "gir1.2-webkit-6.0" in out and "setcap" not in out and "rapl" not in out.lower()


def test_refuses_without_root_and_without_dry_run():
    if os.geteuid() == 0:
        pytest.skip("running as root")
    r = subprocess.run(["bash", SCRIPT], capture_output=True, text=True)
    assert r.returncode != 0 and "root" in r.stderr


@pytest.mark.parametrize("args", [["--bogus"], [""], ["--dry-run", ""], ["--dry-run", "extra"]])
def test_bad_arguments_exit_2_without_actions(args):
    r = subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True)
    assert r.returncode == 2 and "WOULD:" not in r.stdout


def test_shellcheck_clean():
    assert subprocess.run(["shellcheck", str(ROOT / "scripts/setup-privileges.sh"),
                           str(ROOT / "scripts/capture-fixture.sh")]).returncode == 0
