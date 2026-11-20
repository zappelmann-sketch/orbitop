# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsame Hilfen der Sensor-Tests: Dateien und hwmon-Chips in einem Testbaum anlegen."""
import os


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(str(text))


def hwmon(root, n, name, files):
    write(root, f"sys/class/hwmon/hwmon{n}/name", name)
    for k, v in files.items():
        write(root, f"sys/class/hwmon/hwmon{n}/{k}", v)
