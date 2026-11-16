# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Einstufung eines Prozesses anhand seines Zustands, seiner Dauerlast und seiner E/A."""
from dataclasses import dataclass

KERNEL_HANG_S = 10
BUSY_S = 120
BUSY_CPU = 90.0
VCTX_MAX = 1.0
WORKING_CPU = 1.0


def is_busy_sample(cpu: float, vctx_rate: float, io_delta: int | None) -> bool:
    return cpu >= BUSY_CPU and vctx_rate <= VCTX_MAX and (io_delta is None or io_delta == 0)


@dataclass
class ProcState:
    state: str
    d_since: float | None
    busy_since: float | None
    io_known: bool
    last_cpu: float
    last_io_delta: int | None


def classify(p: ProcState, now: float) -> tuple[str, int]:
    if p.state == "Z":
        return "zombie", 0
    if p.state in ("T", "t"):
        return "stopped", 0
    if p.state == "D" and p.d_since is not None and now - p.d_since > KERNEL_HANG_S:
        return "kernel_hang", int(now - p.d_since)
    if p.busy_since is not None and now - p.busy_since >= BUSY_S:
        return ("busy_noio" if p.io_known else "busy_iounknown"), int(now - p.busy_since)
    if p.last_cpu >= WORKING_CPU or (p.last_io_delta or 0) > 0 or p.state in ("R", "D"):
        return "working", 0
    return "waiting", 0
