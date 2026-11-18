# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Debian- und RPM-Changelog aus den <release>-Einträgen der metainfo, der einzigen Quelle.

Aufruf beim Bauen: python3 -I changelog.py debian|rpm METAINFO [DEBIAN-VERSION]"""
import email.utils
import sys
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

MAINTAINER = "zappelmann-sketch <235797375+zappelmann-sketch@users.noreply.github.com>"
LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def _releases(metainfo: str) -> list[tuple[str, str, list[str]]]:
    """(Version, RFC-2822-Datum, Änderungen) je <release>, in der Reihenfolge der metainfo (neueste zuerst)."""
    out = []
    for rel in ET.fromstring(metainfo).iterfind("releases/release"):
        version = rel.get("version")
        date = email.utils.format_datetime(datetime.fromisoformat(rel.get("date")).replace(tzinfo=timezone.utc))
        items = [" ".join(e.text.split()) for e in rel.iterfind("description/*") if not e.get(LANG) and e.text]
        out.append((version, date, items or [f"Release {version}."]))
    return out


def debian(metainfo: str, version: str) -> str:
    """deb-changelog(5); der oberste Eintrag trägt die gebaute Debian-Version (etwa 0.2.0-1+check1, K6)."""
    releases = _releases(metainfo)
    if not releases or version.rsplit("-", 1)[0] != releases[0][0]:
        raise ValueError(f"{version}: kein passender oberster <release> in der metainfo")
    entries = []
    for i, (v, date, items) in enumerate(releases):
        body = "\n".join(textwrap.fill(t, 79, initial_indent="  * ", subsequent_indent="    ") for t in items)
        entries.append(f"orbitop ({version if i == 0 else v + '-1'}) stable; urgency=medium\n\n{body}\n\n"
                       f" -- {MAINTAINER}  {date}\n")
    return "\n".join(entries)


def rpm(metainfo: str) -> str:
    """%changelog: "* Wed Nov 18 2026 Name <Mail> - 0.1.0-1" und je Änderung eine Zeile "- …"."""
    entries = []
    for v, date, items in _releases(metainfo):
        day, num, month, year = date.replace(",", "").split()[:4]
        body = "\n".join(textwrap.fill(t, 79, initial_indent="- ", subsequent_indent="  ") for t in items)
        entries.append(f"* {day} {month} {num} {year} {MAINTAINER} - {v}-1\n{body}\n")
    return "\n".join(entries)


if __name__ == "__main__":
    kind, path, *version = sys.argv[1:]
    with open(path, encoding="utf-8") as f:
        sys.stdout.write({"debian": debian, "rpm": rpm}[kind](f.read(), *version))
