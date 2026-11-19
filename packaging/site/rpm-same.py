# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Checks on the host that rpmsign changed nothing but the signature of an RPM (scripts/build-site.sh).

Usage: python3 -I rpm-same.py SIGNED UNSIGNED
Exit 0 if both files are RPMs and byte-identical from the main header onward: the 96-byte lead and the signature
header with its padding to 8 bytes are skipped (rpm's file format: lead, signature header, header, payload). Exit 1
with a message otherwise. rpm -K in the container checks the signature itself; this check makes sure that what a
client installs, the header and the payload, is the package from build-packages.sh.
"""
import sys

LEAD = 96
LEAD_MAGIC = b"\xed\xab\xee\xdb"
HEADER_MAGIC = b"\x8e\xad\xe8\x01"


def main_part(data):
    """The bytes from the main header onward; ValueError if DATA is no RPM of this layout."""
    if len(data) < LEAD + 16 or data[:4] != LEAD_MAGIC:
        raise ValueError("no RPM lead")
    sig = data[LEAD:]
    if sig[:4] != HEADER_MAGIC:
        raise ValueError("no signature header after the lead")
    count, size = int.from_bytes(sig[8:12], "big"), int.from_bytes(sig[12:16], "big")
    end = 16 + 16 * count + size
    end += -end % 8  # the signature header is padded to a multiple of 8 bytes
    main = sig[end:]
    if main[:4] != HEADER_MAGIC:
        raise ValueError("no main header after the signature header")
    return main


def main(argv):
    if len(argv) != 3:
        print(f"usage: {argv[0]} SIGNED UNSIGNED", file=sys.stderr)
        return 2
    try:
        parts = []
        for path in argv[1:]:
            with open(path, "rb") as f:
                parts.append(main_part(f.read()))
    except (OSError, ValueError) as e:
        print(f"{path}: {e}", file=sys.stderr)
        return 1
    if parts[0] != parts[1]:
        print(f"{argv[1]}: header or payload differ from {argv[2]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
