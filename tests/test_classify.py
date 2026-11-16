# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import pytest

from orbitop.classify import ProcState, classify, is_busy_sample


def PS(state, d_since=None, busy_since=None, io_known=True, last_cpu=0.0, last_io_delta=None):
    return ProcState(state, d_since, busy_since, io_known, last_cpu, last_io_delta)


@pytest.mark.parametrize("p,now,expected", [
    (PS("Z"), 0, ("zombie", 0)),
    (PS("t"), 0, ("stopped", 0)),
    (PS("D", d_since=0), 10.0, ("working", 0)),
    (PS("D", d_since=0), 10.5, ("kernel_hang", 10)),
    (PS("R", busy_since=0, io_known=True, last_cpu=99), 119, ("working", 0)),
    (PS("R", busy_since=0, io_known=True, last_cpu=99), 120, ("busy_noio", 120)),
    (PS("R", busy_since=0, io_known=False, last_cpu=99), 300, ("busy_iounknown", 300)),
    (PS("S", last_cpu=0.2, last_io_delta=0), 5, ("waiting", 0)),
    (PS("S", last_cpu=0.0, last_io_delta=512), 5, ("working", 0)),
    (PS("S", last_cpu=1.0, last_io_delta=0), 5, ("working", 0)),
    (PS("S", last_cpu=0.99), 5, ("waiting", 0)),
    (PS("R"), 5, ("working", 0)),
    (PS("R", busy_since=0, io_known=True, last_cpu=99), 130.9, ("busy_noio", 130)),
    (PS("D", d_since=0), 20.9, ("kernel_hang", 20)),
])
def test_classify(p, now, expected):
    assert classify(p, now) == expected


def test_busy_sample_rejects_io():
    assert not is_busy_sample(99, 0.0, 4096) and is_busy_sample(99, 0.5, None)


@pytest.mark.parametrize("cpu,vctx,io,expected", [
    (90.0, 1.0, 0, True),
    (89.9, 0.0, 0, False),
    (99.0, 1.1, 0, False),
])
def test_busy_sample_boundaries(cpu, vctx, io, expected):
    assert is_busy_sample(cpu, vctx, io) is expected
