# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""SECURITY.md: derselbe Schlüssel wie die READMEs, Verweise auf echte Abschnitte."""
import re

from tests.test_readme import DE, EN, REPO, fingerprint, fingerprints, slug


def test_security_policy_names_the_key_and_links_existing_sections():
    security = (REPO / "SECURITY.md").read_text(encoding="utf-8")
    assert fingerprints(security) == {fingerprint(EN)}  # README: gegen die Schlüsseldatei geprüft
    assert "](SECURITY.md)" in EN and "](SECURITY.md)" in DE
    anchors = {name: {slug(h) for h in re.findall(r"^#+ (.+)$", text, re.M)}
               for name, text in (("README.md", EN), ("README.de.md", DE), ("", security))}
    links = re.findall(r"\]\(([^)#]*)#([^)]+)\)", security)
    assert links and all(anchor in anchors[page] for page, anchor in links)
