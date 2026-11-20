# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Parser für security.capability (Security-Dokument 0.3.0, B2.5): nur cap_perfmon, wirksam (Effective) und im
Permitted-Set, aus v2 oder v3 mit rootid 0, ergibt True; alles andere False."""
import errno
import os
import struct

import pytest

from orbitop import counterhelper
from orbitop.counters import perfmon_cap

PERFMON, NET_RAW, SYS_ADMIN = 38, 13, 21
V2, V3, EFFECTIVE = 0x02000000, 0x03000000, 0x1


def v2(*caps, magic=V2 | EFFECTIVE):
    permitted = sum(1 << c for c in caps)
    return struct.pack("<5I", magic, permitted & 0xFFFFFFFF, 0, permitted >> 32, 0)


def v3(*caps, rootid=0, magic=V3 | EFFECTIVE):
    return v2(*caps, magic=magic) + struct.pack("<I", rootid)


def returning(data):
    seen = []

    def getxattr(path, name, *, follow_symlinks=True):
        seen.append((path, name, follow_symlinks))
        if isinstance(data, int):
            raise OSError(data, os.strerror(data), path)
        return data
    getxattr.seen = seen
    return getxattr


@pytest.mark.parametrize("data,want", [
    (v2(PERFMON), True),                                   # v2 perfmon
    (bytes.fromhex("0100000200000000000000004000000000000000"), True),  # was setcap cap_perfmon=ep schreibt (P1)
    (counterhelper.CAP, True),                             # die Bytes des Helfers
    (v2(PERFMON, NET_RAW), True),                          # perfmon unter anderen
    (v2(NET_RAW), False),                                  # v2 cap_net_raw
    (v2(SYS_ADMIN), False),                                # cap_sys_admin zählt nur für „von Hand“
    (v2(PERFMON, magic=V2), False),                        # v2 ohne Effective-Bit
    (v3(PERFMON, rootid=1000), False),                     # v3 mit rootid 1000 wirkt im Init-Namespace nicht
    (v3(PERFMON, rootid=0), True),                         # v3 mit rootid 0
    (v3(NET_RAW, rootid=0), False),
    (v3(PERFMON, magic=V3), False),                        # v3 ohne Effective-Bit
    (v2(PERFMON, magic=V3 | EFFECTIVE), False),            # 20 Bytes, aber Revision 3
    (v3(PERFMON, magic=V2 | EFFECTIVE), False),            # 24 Bytes, aber Revision 2
    (struct.pack("<3I", 0x01000001, 1 << 6, 0), False),    # v1 (12 Bytes, 32 Bit) gibt es für Bit 38 nicht
    (struct.pack("<5I", V2 | EFFECTIVE, 0, 0, 0, 1 << 6), False),  # Bit 38 nur im Inheritable-Set
    (struct.pack("<5I", V2 | EFFECTIVE, 1 << 6, 0, 0, 0), False),  # Bit 6 im unteren Wort ist nicht Bit 38
])
def test_parser_fixtures(data, want):
    assert perfmon_cap("/usr/bin/intel_gpu_top", returning(data)) is want


@pytest.mark.parametrize("data", [b"", v2(PERFMON)[:19], v2(PERFMON) + b"\0", v3(PERFMON)[:23], v3(PERFMON) + b"\0",
                                  v3(PERFMON) + b"\0" * 4, v2(PERFMON) * 2])
def test_truncated_or_overlong_bytes_are_false(data):
    assert perfmon_cap("/x", returning(data)) is False


@pytest.mark.parametrize("err", [errno.ENODATA, errno.ENOTSUP, errno.ENOENT, errno.EACCES, errno.ELOOP])
def test_read_errors_are_false(err):
    assert perfmon_cap("/x", returning(err)) is False


def test_reads_security_capability_without_following_symlinks():
    get = returning(v2(PERFMON))
    perfmon_cap("/usr/bin/intel_gpu_top", get)
    assert get.seen == [("/usr/bin/intel_gpu_top", "security.capability", False)]


def test_real_file_without_capability_is_false(tmp_path):
    f = tmp_path / "tool"
    f.write_bytes(b"\x7fELF")
    (tmp_path / "link").symlink_to(f)
    assert perfmon_cap(str(f)) is False and perfmon_cap(str(tmp_path / "link")) is False
    assert perfmon_cap(str(tmp_path / "missing")) is False

