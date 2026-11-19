# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Debian- und RPM-Changelog aus den <release>-Einträgen der metainfo, der einzigen Quelle.

Aufruf beim Bauen: python3 -I changelog.py debian|rpm METAINFO VERSION-REVISION
               oder python3 -I changelog.py apt-source|rpm-release KEYRING-VERSION
beim Release:      python3 -I changelog.py notes METAINFO VERSION"""
import email.utils
import re
import sys
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

MAINTAINER = "zappelmann-sketch <235797375+zappelmann-sketch@users.noreply.github.com>"
LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def _rfc2822(day: datetime) -> str:
    return email.utils.format_datetime(day.replace(tzinfo=timezone.utc))


def _items(description) -> list[str]:
    """Absätze und Listenpunkte (<p>, <ul>/<ol> mit <li>) ohne Übersetzungen, Text samt <code>/<em>."""
    elements = []
    for child in description if description is not None else ():
        if child.get(LANG):
            continue
        if child.tag == "p":
            elements.append(child)
        elif child.tag in ("ul", "ol"):
            elements += [li for li in child.iterfind("li") if not li.get(LANG)]
    return [t for t in (" ".join("".join(e.itertext()).split()) for e in elements) if t]


def _releases(metainfo: str) -> list[tuple[str, str, list[str]]]:
    """(Version, RFC-2822-Datum, Änderungen) je <release>, in der Reihenfolge der metainfo (neueste zuerst)."""
    out = []
    for rel in ET.fromstring(metainfo).iterfind("releases/release"):
        version = rel.get("version")
        date = _rfc2822(datetime.fromisoformat(rel.get("date")))
        items = _items(rel.find("description"))
        out.append((version, date, items or [f"Release {version}."]))
    return out


def _built(metainfo: str, version: str) -> list[tuple[str, str, list[str]]]:
    """Die Releases der metainfo; der oberste muss zur gebauten Version VERSION-REVISION passen."""
    releases = _releases(metainfo)
    if not releases or version.rsplit("-", 1)[0] != releases[0][0]:
        raise ValueError(f"{version}: kein passender oberster <release> in der metainfo")
    return releases


def _keyring_day(version: str) -> datetime:
    """Datum aus packaging/keyring.version (JJJJ.MM.TT, Datum des Schlüssels)."""
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", version):
        raise ValueError(f"{version}: Version des Schlüssels ist JJJJ.MM.TT")
    return datetime.strptime(version, "%Y.%m.%d")  # ValueError bei einem ungültigen Datum


def _rpm_heading(date: str, version: str) -> str:
    """"* Wed Nov 18 2026 Name <Mail> - VERSION" aus einem RFC-2822-Datum, unabhängig von der Locale."""
    day, num, month, year = date.replace(",", "").split()[:4]
    return f"* {day} {month} {num} {year} {MAINTAINER} - {version}"


def debian(metainfo: str, version: str) -> str:
    """deb-changelog(5); der oberste Eintrag trägt die gebaute Debian-Version (etwa 0.2.0-1+check1, K6)."""
    releases = _built(metainfo, version)
    entries = []
    for i, (v, date, items) in enumerate(releases):
        body = "\n".join(textwrap.fill(t, 79, initial_indent="  * ", subsequent_indent="    ") for t in items)
        entries.append(f"orbitop ({version if i == 0 else v + '-1'}) stable; urgency=medium\n\n{body}\n\n"
                       f" -- {MAINTAINER}  {date}\n")
    return "\n".join(entries)


def apt_source(version: str) -> str:
    """deb-changelog(5) von orbitop-apt-source, nur aus packaging/keyring.version (JJJJ.MM.TT, Datum des Schlüssels):
    Gleiche Version ergibt dieselben Bytes, egal mit welchem orbitop das Paket gebaut wird."""
    day = _keyring_day(version)
    return (f"orbitop-apt-source ({version}) stable; urgency=medium\n\n"
            f"  * Signing key and package source as of {day.date().isoformat()}.\n\n"
            f" -- {MAINTAINER}  {_rfc2822(day)}\n")


def rpm(metainfo: str, version: str) -> str:
    """%changelog: "* Wed Nov 18 2026 Name <Mail> - 0.1.0-1" und je Änderung eine Zeile "- …"; der oberste Eintrag
    trägt die gebaute Version (etwa 0.2.0-1.check1, K6). "%" wird zu "%%", weil rpm auch im %changelog
    Makros expandiert."""
    entries = []
    for i, (v, date, items) in enumerate(_built(metainfo, version)):
        body = "\n".join(textwrap.fill(t.replace("%", "%%"), 79, initial_indent="- ", subsequent_indent="  ")
                         for t in items)
        entries.append(f"{_rpm_heading(date, version if i == 0 else v + '-1')}\n{body}\n")
    return "\n".join(entries)


def rpm_release(version: str) -> str:
    """%changelog von orbitop-release, nur aus packaging/keyring.version, wie apt_source."""
    day = _keyring_day(version)
    return (f"{_rpm_heading(_rfc2822(day), version + '-1')}\n"
            f"- Signing key and package source as of {day.date().isoformat()}.\n")


def notes(metainfo: str, version: str) -> str:
    """Release-Notizen für Tag und GitHub-Release (scripts/release.sh): die Änderungen von VERSION als Liste."""
    for v, _, items in _releases(metainfo):
        if v == version:
            return "".join(f"- {t}\n" for t in items)
    raise ValueError(f"{version}: kein <release> in der metainfo")


if __name__ == "__main__":
    kind, arg, *version = sys.argv[1:]
    if kind in ("apt-source", "rpm-release"):
        sys.stdout.write({"apt-source": apt_source, "rpm-release": rpm_release}[kind](arg))
    else:
        with open(arg, encoding="utf-8") as f:
            sys.stdout.write({"debian": debian, "rpm": rpm, "notes": notes}[kind](f.read(), *version))
