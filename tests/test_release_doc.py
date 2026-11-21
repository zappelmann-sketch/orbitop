# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""docs/release.md, „Test version“: Die nummerierte Prüfliste für die Testversion enthält jede Hardware-Pflicht-Prüfung
des Security-Dokuments 0.3.0 mit ihrem Befehl (Schlussprüfung I-1). Sonst prüfte RAPL und die udev-Regel beim Start
nichts (R20), denn die Container-Matrix sieht keine Zonen."""
import re

import pytest

from tests.packaging_common import ROOT

RAPL = "stat -c '%a %n' /sys/class/powercap/intel-rapl:*/energy_uj"


def checklist() -> list[str]:
    """Die Punkte der nummerierten Liste im Abschnitt „Test version“, je Punkt mit seinen eingerückten Zeilen."""
    text = (ROOT / "docs" / "release.md").read_text(encoding="utf-8")
    start = text.index("\n## Test version\n")
    section = text[start:text.index("\n## ", start + 1)]
    return re.findall(r"^\d+\. .*(?:\n(?:   .*|))*", section, re.M)


def step(*needles: str) -> str:
    """Ein Punkt, der alle needles enthält: Befehl und erwartetes Ergebnis stehen zusammen."""
    found = [s for s in checklist() if all(n in s for n in needles)]
    assert found, needles
    return found[0]


def test_steps_are_numbered_in_order():
    numbers = [int(s.split(".", 1)[0]) for s in checklist()]
    assert numbers == list(range(1, len(numbers) + 1)) and len(numbers) >= 10


@pytest.mark.parametrize("needles", [
    ("sudo apt install ./orbitop_0.3.0~rc1-1_all.deb",),
    ("pkaction --action-id io.github.zappelmann-sketch.orbitop.counters-release --verbose",
     "pkaction --action-id io.github.zappelmann-sketch.orbitop.counters-lock --verbose", "auth_admin"),
    (RAPL, "444", "getcap /usr/bin/intel_gpu_top", "cap_perfmon=ep", "stat -c '%U %a %F' /etc/orbitop/counters-released"),
    ("journalctl -b -t pkexec", "counterhelper"),
    ("Cancel", "nothing changes"),
    ("sudo apt install --reinstall igt-gpu-tools", "cap_perfmon=ep"),
    ("sudo modprobe -r intel_rapl_msr", "only if", "444"),
    ("sudo setcap cap_perfmon=ep /usr/bin/intel_gpu_top", "released by hand", "B2.9"),
    ("sudo apt remove igt-gpu-tools intel-gpu-tools", "Quit", "start orbitop again", "Install"),
    ("10 s", "60 s", "refused too often – restart orbitop", "process of another user"),
    ("rc1", "rc2", "0.3.0", "without a dialog"),
    ("R22", "only if"),
], ids=["install", "pkaction", "on", "journal", "cancel", "reinstall", "modprobe", "manual", "button", "lockout",
        "upgrade", "r22"])
def test_checklist_has_the_hardware_item(needles):
    step(*needles)


def test_both_reboots_check_the_udev_rule():  # B2.3 (Pflicht), B2.2: nur der Neustart prüft die Regel beim Start
    reboots = [s for s in checklist() if "Reboot" in s]
    assert len(reboots) == 2
    on, off = reboots
    assert "444" in on and "cap_perfmon=ep" in on and "400" in off and "no output" in off
    assert all(RAPL in s and "getcap /usr/bin/intel_gpu_top" in s for s in reboots)
