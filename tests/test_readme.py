# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""README.md und README.de.md: gegenseitig verlinkt, gleich aufgebaut, nur geprüfte Distributionen als unterstützt."""
import re
from pathlib import Path

from orbitop import app

REPO = Path(__file__).resolve().parent.parent
EN = (REPO / "README.md").read_text(encoding="utf-8")
DE = (REPO / "README.de.md").read_text(encoding="utf-8")
CHECK = (REPO / "docs" / "distro-check.md").read_text(encoding="utf-8")
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```$", re.M | re.S)


def head(text, n):
    return "\n".join(text.splitlines()[:n])


def headings(text, prefix):
    return [ln for ln in FENCE.sub("", text).splitlines() if ln.startswith(prefix)]


def code_blocks(text):
    return FENCE.findall(text)


def table(text):
    """Zeilen der Markdown-Tabellen ohne Kopf: nur die Zeilen nach der Trennzeile |---|."""
    rows, body = [], False
    for ln in text.splitlines():
        if not ln.startswith("|"):
            body = False
        elif set(ln) <= set("|-: "):
            body = True
        elif body:
            rows.append([cell.strip() for cell in ln.strip().strip("|").split("|")])
    return rows


def between(text, start, end):
    return text[text.index(start) + len(start):text.index(end)]


def first_column(text):
    return [row[0] for row in table(text)]


def test_readmes_link_each_other():
    assert "[Deutsch](README.de.md)" in head(EN, 5) and "[English](README.md)" in head(DE, 5)


def test_readmes_mirror_each_other():
    assert len(headings(EN, "## ")) == len(headings(DE, "## ")) == 10
    assert len(headings(EN, "### ")) == len(headings(DE, "### "))
    assert code_blocks(EN) == code_blocks(DE)  # gleiche Befehle in beiden Sprachen


def test_supported_distros_were_checked():
    """Anti-Ziel: nichts Ungeprüftes als unterstützt."""
    passed = {row[0] for row in table(CHECK) if row[-1] == "pass"}
    assert passed
    for text in (EN, DE):
        listed = first_column(between(text, "<!-- supported:start -->", "<!-- supported:end -->"))
        assert listed and set(listed) <= passed


def test_readmes_name_the_package_names():
    for names in app.PACKAGES.values():
        assert all(n in EN and n in DE for n in names)


def test_images_are_the_same_and_exist():
    images = [re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text) for text in (EN, DE)]
    assert images[0] and images[0] == images[1]
    assert all((REPO / f).is_file() and (REPO / f).stat().st_size > 0 for f in images[0]), images[0]
