# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""SECURITY.md: derselbe Schlüssel wie die READMEs, Verweise auf echte Abschnitte, der Fingerabdruck des
Tag-Schlüssels aus .github/allowed_signers."""
import base64
import hashlib
import re

from tests.release_stub import NOREPLY
from tests.test_readme import DE, EN, REPO, fingerprint, fingerprints, slug


def test_security_policy_names_the_key_and_links_existing_sections():
    security = (REPO / "SECURITY.md").read_text(encoding="utf-8")
    assert fingerprints(security) == {fingerprint(EN)}  # README: gegen die Schlüsseldatei geprüft
    assert "](SECURITY.md)" in EN and "](SECURITY.md)" in DE
    anchors = {name: {slug(h) for h in re.findall(r"^#+ (.+)$", text, re.M)}
               for name, text in (("README.md", EN), ("README.de.md", DE), ("", security))}
    links = re.findall(r"\]\(([^)#]*)#([^)]+)\)", security)
    assert links and all(anchor in anchors[page] for page, anchor in links)


def test_tag_key_is_the_one_signer_and_security_names_its_fingerprint():
    """docs/release.md, Tag key: eine Zeile, der Tagger (noreply) im Namespace git; SECURITY.md nennt in beiden
    Sprachen den Fingerabdruck, wie ssh-keygen -lf ihn zeigt (SHA256 über den Schlüssel, base64 ohne =)."""
    text = (REPO / ".github" / "allowed_signers").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert len(lines) == 1
    principal, options, kind, key, *_ = lines[0].split(" ")
    assert (principal, options, kind) == (NOREPLY, 'namespaces="git"', "ssh-ed25519")
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(base64.b64decode(key)).digest()).decode().rstrip("=")
    assert (REPO / "SECURITY.md").read_text(encoding="utf-8").count(f"`{fp}`") == 2
