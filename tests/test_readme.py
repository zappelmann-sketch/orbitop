# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""README.md und README.de.md: gegenseitig verlinkt, gleich aufgebaut, nur geprüfte Distributionen als unterstützt,
dieselben Befehle wie die Container-Matrix."""
import json
import re
from pathlib import Path

from orbitop import app

REPO = Path(__file__).resolve().parent.parent
EN = (REPO / "README.md").read_text(encoding="utf-8")
DE = (REPO / "README.de.md").read_text(encoding="utf-8")
CHECK = (REPO / "docs" / "distro-check.md").read_text(encoding="utf-8")
MATRIX = "\n".join(f.read_text(encoding="utf-8") for f in
                   [REPO / "scripts" / "check-distros.sh", *sorted((REPO / "scripts" / "matrix").glob("*.sh"))])
MATRIX = MATRIX.replace('"${ZYPPER[@]}"', "zypper")  # zypper.sh: ZYPPER=(zypper --non-interactive)
PAGES = re.search(r"^PAGES=(\S+)", MATRIX, re.M)[1]
# Befehlsköpfe der README, die die Matrix genau so ausführt: erste Installation, Update, Entfernen, voller Abbau
STEPS = [
    "apt install ./orbitop-apt-source.deb", "apt update", "apt install orbitop", "apt upgrade", "apt remove orbitop",
    "apt purge orbitop orbitop-apt-source",
    "rpm --import", "rpm -K", "rpmkeys --list", "rpmkeys --delete",
    "dnf install ./orbitop-release-fedora.rpm", "dnf install orbitop", "dnf upgrade", "dnf remove orbitop",
    "dnf remove orbitop-release", "rm -rf /var/cache/libdnf5/orbitop-*",
    "zypper install ./orbitop-release-opensuse.rpm", "zypper install orbitop", "zypper dup", "zypper remove orbitop",
    "zypper remove orbitop-release",
    "pacman-key --init", "pacman-key --populate archlinux", "pacman-key --add", "pacman-key --lsign-key",
    "SigLevel = Required DatabaseRequired", "pacman -Syu orbitop", "pacman -Syu",
    "pacman -R orbitop", "pacman-key --delete", "pacman -Sc",
]
MOVE = {"README.md": "## Moving from 0.1.0", "README.de.md": "## Umstieg von 0.1.0"}
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
    assert len(headings(EN, "## ")) == len(headings(DE, "## ")) == 13
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


def test_commands_are_the_steps_of_the_matrix():  # Task 7: eine Abweichung ist ein Fehler
    for step in STEPS:
        assert step in MATRIX, step
        assert step in EN and step in DE, step
    assert 'Server = ${PAGES}arch/\\$arch' in MATRIX  # pacman.sh hängt den Abschnitt [orbitop] so an
    assert f"Server = {PAGES}arch/$arch" in EN and f"Server = {PAGES}arch/$arch" in DE


def without_section(text, heading):
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[:start] + (text[end:] if end >= 0 else "")


def test_stage_1_scripts_are_gone():  # Spec 7: nur der Umstieg nennt noch den alten Helfer
    for name, text in (("README.md", EN), ("README.de.md", DE)):
        assert "setup-privileges" not in text and "install-user" not in text, name
        assert "/usr/local/libexec" in text, name
        assert "/usr/local/libexec" not in without_section(text, MOVE[name]), name


def test_hints_name_a_section_of_the_readme():  # hint.igt_noperm und hint.rapl_noperm verweisen auf die README
    texts = {lang: json.loads((REPO / "orbitop" / "locale" / f"{lang}.json").read_text(encoding="utf-8"))
             for lang in ("en", "de")}
    for lang, text, section in (("en", EN, "Graphics and power"), ("de", DE, "Grafik und Leistung")):
        assert f"\n## {section}\n" in text
        for key in ("hint.igt_noperm", "hint.rapl_noperm"):
            assert "README" in texts[lang][key] and section in texts[lang][key], (lang, key)
