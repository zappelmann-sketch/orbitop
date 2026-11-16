# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Lesehelfer für /sys und /proc. Alle Pfade lassen sich auf ein Testverzeichnis umbiegen."""
import glob as _glob
import os
import re


def path(root: str, *parts: str) -> str:
    return root.rstrip("/") + "".join(parts)


def read_str(p: str) -> str | None:
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return None


def read_int(p: str) -> int | None:
    try:
        return int(read_str(p))
    except (TypeError, ValueError):
        return None


def read_float(p: str) -> float | None:
    try:
        return float(read_str(p))
    except (TypeError, ValueError):
        return None


def _natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def glob(root: str, pattern: str) -> list[str]:
    return sorted(_glob.glob(path(root, pattern)), key=_natural)


def link_name(p: str) -> str | None:
    """Basename des Linkziels, ohne dem Link zu folgen."""
    try:
        return os.path.basename(os.readlink(p))
    except OSError:
        return None
