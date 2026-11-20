# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Nachrichten mit der Seite: encode für alles an sie, parse_message als Schleuse für alles von ihr."""
import json

from orbitop.layout import validate

MAX_MESSAGE = 4096


def encode(msg: dict) -> str:
    """JSON nur mit ASCII (auch U+2028/2029 maskiert) und ohne NaN: als JS-Literal sicher."""
    return json.dumps(msg, ensure_ascii=True, allow_nan=False)


PID_MAX, START_MAX = 4194304, 2**63 - 1  # PID_MAX_LIMIT des Kernels; start ist ein u64-Zähler in Ticks


def _uint(v, top: int) -> bool:
    return type(v) is int and 0 <= v <= top  # bool ist kein int im Sinne des Vertrags


def parse_message(raw) -> dict | None:
    """Schleuse für Nachrichten der Seite: nur die Formen des Vertrags, sonst None (still verworfen)."""
    if not isinstance(raw, str) or len(raw) > MAX_MESSAGE:
        return None
    try:
        m = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(m, dict):
        return None
    kind = m.get("type")
    if kind in ("ready", "quit"):
        return {"type": kind}
    if kind == "view":
        tab, pid, start = m.get("tab"), m.get("pid"), m.get("start")
        if tab in ("overview", "procs") and (pid is None or _uint(pid, PID_MAX)) and (
                start is None or _uint(start, START_MAX)):
            return {"type": "view", "tab": tab, "pid": pid, "start": start}
    if kind == "layout":
        layout = validate(m)
        return {"type": "layout", **layout} if layout else None
    if kind == "terminate":
        pid, start, force = m.get("pid"), m.get("start"), m.get("force")
        if _uint(pid, PID_MAX) and _uint(start, START_MAX) and type(force) is bool:
            return {"type": "terminate", "pid": pid, "start": start, "force": force}
    if kind == "autostart" and type(m.get("on")) is bool:
        return {"type": "autostart", "on": m["on"]}
    return None
