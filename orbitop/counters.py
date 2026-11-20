# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Zustand der Zählerfreigabe ohne root (Security-Dokument 0.3.0, B2.5, B2.2 „Lesen in der App“, B2.9).

Liest nur: lstat, security.capability und die Lesebits von energy_uj; öffnet keine Datei. Der Zustand dient nur der
Anzeige und den Vorbedingungen; was gilt, entscheidet der Helfer als root (R5.2)."""
import os
import stat
import struct

from orbitop import sysfs
from orbitop.counterhelper import MARKER, RAPL, TOOL

MANUAL_RULE = "/etc/udev/rules.d/70-orbitop-rapl.rules"  # die Handregel der README 0.2.0 (B2.9)
CAP_PERFMON, CAP_SYS_ADMIN = 38, 21
_REVISION, _EFFECTIVE = 0xFF000000, 0x000001
_V2, _V3 = 0x02000000, 0x03000000

# Messung je Teil -> Anzeige je Merkdatei (Tabelle B2.5). Messung: "missing" (Werkzeug oder Zonen fehlen), "works"
# (genau die Wirkung des Helfers), "other" (eine Wirkung, die der Helfer nie setzt: cap_sys_admin, ein Teil der
# Zonen), "none". Bei "unclear" (aus, Zustand unklar) zeigt der Teil ehrlich, was wirkt; "broken" setzt eine
# gültige Merkdatei voraus und "missing" eine Freigabe, die es nicht gibt.
_SHOW = {"on": {"missing": "missing", "works": "works", "other": "broken", "none": "broken"},
         "off": {"missing": "none", "works": "manual", "other": "manual", "none": "none"},
         "unclear": {"missing": "none", "works": "works", "other": "manual", "none": "none"}}


def _permitted(path: str, getxattr) -> int:
    """Das 64-Bit-Permitted-Set einer wirksamen Datei-Fähigkeit, sonst 0: v2 mit 20 Bytes oder v3 mit 24 Bytes und
    rootid 0 (eine andere rootid wirkt im Init-Namespace nicht), jeweils mit Effective-Bit (capabilities(7))."""
    try:  # ENODATA: keine Fähigkeit; ENOTSUP: Dateisystem ohne xattr; ELOOP, ENOENT, EACCES ebenso nichts
        data = getxattr(path, "security.capability", follow_symlinks=False)
    except OSError:
        return 0
    if len(data) == 20:
        magic, lo, _, hi, _ = struct.unpack("<5I", data)
        valid = magic & _REVISION == _V2
    elif len(data) == 24:
        magic, lo, _, hi, _, rootid = struct.unpack("<6I", data)
        valid = magic & _REVISION == _V3 and rootid == 0
    else:
        return 0
    return lo | hi << 32 if valid and magic & _EFFECTIVE else 0


def perfmon_cap(path: str, getxattr=os.getxattr) -> bool:
    """True nur für cap_perfmon, wirksam und erlaubt (B2.5); eine andere Fähigkeit ergibt False (R5.1)."""
    return bool(_permitted(path, getxattr) >> CAP_PERFMON & 1)


def _marker(root: str, lstat) -> str:
    """on nur für eine reguläre Datei von root in einem Verzeichnis von root, das Gruppe und andere weder schreiben
    noch lesen dürfen (dieselbe Regel wie der Helfer, B2.2). Ohne /etc/orbitop (Start ohne Paket) ist es off."""
    try:
        st = lstat(sysfs.path(root, os.path.dirname(MARKER)))
    except FileNotFoundError:
        return "off"
    except OSError:
        return "unclear"
    if not (stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not stat.S_IMODE(st.st_mode) & 0o066):
        return "unclear"
    try:
        st = lstat(sysfs.path(root, MARKER))
    except FileNotFoundError:
        return "off"
    except OSError:
        return "unclear"
    return "on" if stat.S_ISREG(st.st_mode) and st.st_uid == 0 else "unclear"


def _perfmon(root: str, getxattr, lstat) -> str:
    """Messung am festen Pfad des Helfers. Ein Symlink zählt nie (im Helfer ELOOP), auch nicht für „von Hand“."""
    path = sysfs.path(root, TOOL)
    try:
        if not stat.S_ISREG(lstat(path).st_mode):
            return "none"
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "none"
    caps = _permitted(path, getxattr)
    if caps >> CAP_PERFMON & 1:
        return "works"
    return "other" if caps >> CAP_SYS_ADMIN & 1 else "none"  # für „von Hand“ zählt zusätzlich Bit 21 (B2.5)


def _other_readable(path: str, lstat) -> bool:
    try:
        st = lstat(path)  # ein Symlink als energy_uj zählt nicht: der Helfer öffnet mit O_NOFOLLOW
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and bool(st.st_mode & stat.S_IROTH)


def _rapl(root: str, lstat) -> str:
    """Messung über genau die Zonen des Helfers und von sensors.RaplReader: works heißt alle energy_uj o+r."""
    zones = sysfs.glob(root, RAPL)
    if not zones:
        return "missing"
    readable = sum(_other_readable(p, lstat) for p in zones)
    return "works" if readable == len(zones) else "other" if readable else "none"


def state(root: str = "/", intel: bool = False, getxattr=os.getxattr, lstat=os.lstat) -> dict:
    """COUNTERS aus Klärung Q2 ohne usable (das ergänzt die App): perfmon nur mit Intel-Grafik, rapl immer."""
    marker = _marker(root, lstat)
    parts = [("perfmon", _perfmon(root, getxattr, lstat))] if intel else []
    parts.append(("rapl", _rapl(root, lstat)))
    return {"marker": marker, "manual_rule": os.path.lexists(sysfs.path(root, MANUAL_RULE)),
            "parts": [{"part": p, "state": _SHOW[marker][m]} for p, m in parts]}
