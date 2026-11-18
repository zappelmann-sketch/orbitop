# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""packaging/changelog.py: Debian- und RPM-Changelog aus der metainfo, Changelog von orbitop-apt-source."""
import pytest

from orbitop import __version__
from tests.packaging_common import METAINFO, NOREPLY, load_changelog

META = """<component><releases>
  <release version="0.2.0" date="2026-12-01"><description><p>Packages for Debian.</p>
    <p xml:lang="de">Pakete für Debian.</p></description></release>
  <release version="0.1.0" date="2026-11-18"/>
</releases></component>"""
TRAILER = f" -- zappelmann-sketch <{NOREPLY}>"


def release(description):
    return f'<component><releases><release version="0.2.0" date="2026-12-01"><description>{description}' \
           '</description></release></releases></component>'


def test_changelog_from_metainfo():
    changelog = load_changelog()
    assert changelog.debian(META, "0.2.0-1") == (
        "orbitop (0.2.0-1) stable; urgency=medium\n\n  * Packages for Debian.\n\n"
        f"{TRAILER}  Tue, 01 Dec 2026 00:00:00 +0000\n\n"
        "orbitop (0.1.0-1) stable; urgency=medium\n\n  * Release 0.1.0.\n\n"
        f"{TRAILER}  Wed, 18 Nov 2026 00:00:00 +0000\n")
    assert changelog.rpm(META, "0.2.0-1") == (
        f"* Tue Dec 01 2026 zappelmann-sketch <{NOREPLY}> - 0.2.0-1\n- Packages for Debian.\n\n"
        f"* Wed Nov 18 2026 zappelmann-sketch <{NOREPLY}> - 0.1.0-1\n- Release 0.1.0.\n")


def test_changelog_takes_lists_and_inline_markup():  # AppStream: <p>, <ul>/<ol> mit <li>, darin <code> und <em>
    meta = release("""<p>Uses <code>pkexec</code> and <em>polkit</em>.</p>
      <ul>
        <li>First</li>
        <li xml:lang="de">Erstens</li>
        <li>Second <code>x</code></li>
      </ul>
      <ol><li>Third</li></ol>
      <ul xml:lang="de"><li>Nur deutsch</li></ul>
      <p> </p>""")
    assert load_changelog().debian(meta, "0.2.0-1").split("\n\n")[1] == (
        "  * Uses pkexec and polkit.\n  * First\n  * Second x\n  * Third")


def test_rpm_escapes_percent():  # rpm expandiert Makros auch in %changelog
    meta = release("<p>CPU at 100% for %{name}</p>")
    assert "- CPU at 100%% for %%{name}\n" in load_changelog().rpm(meta, "0.2.0-1")
    assert "  * CPU at 100% for %{name}\n" in load_changelog().debian(meta, "0.2.0-1")


def test_changelog_top_entry_carries_build_version():  # K6: Prüfbau mit Suffix
    assert load_changelog().debian(META, "0.2.0-1+check1").startswith("orbitop (0.2.0-1+check1) stable;")
    rpm = load_changelog().rpm(META, "0.2.0-1.check1")
    assert rpm.startswith(f"* Tue Dec 01 2026 zappelmann-sketch <{NOREPLY}> - 0.2.0-1.check1\n")
    assert f"<{NOREPLY}> - 0.1.0-1\n" in rpm


def test_changelog_apt_source_only_from_keyring_version():  # nie aus der metainfo oder der orbitop-Version
    changelog = load_changelog()
    assert changelog.apt_source("2026.11.18") == (
        "orbitop-apt-source (2026.11.18) stable; urgency=medium\n\n"
        "  * Signing key and package source as of 2026-11-18.\n\n"
        f"{TRAILER}  Wed, 18 Nov 2026 00:00:00 +0000\n")
    for bad in ("2026.13.01", "2026-11-18", "2026.11.18-1"):
        with pytest.raises(ValueError):
            changelog.apt_source(bad)


def test_changelog_refuses_version_without_release():  # __version__ neuer als die metainfo: Bau bricht ab
    for make in (load_changelog().debian, load_changelog().rpm):
        with pytest.raises(ValueError):
            make(META, "0.3.0-1")


def test_changelog_rpm_release_only_from_keyring_version():  # wie orbitop-apt-source: gleiche Version, gleiche Bytes
    changelog = load_changelog()
    assert changelog.rpm_release("2026.11.18") == (
        f"* Wed Nov 18 2026 zappelmann-sketch <{NOREPLY}> - 2026.11.18-1\n"
        "- Signing key and package source as of 2026-11-18.\n")
    for bad in ("2026.13.01", "2026-11-18"):
        with pytest.raises(ValueError):
            changelog.rpm_release(bad)


def test_changelog_of_real_metainfo_matches_version():
    text = load_changelog().debian(METAINFO.read_text(encoding="utf-8"), f"{__version__}-1")
    assert text.startswith(f"orbitop ({__version__}-1) stable; urgency=medium\n")
