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


def slug(heading):
    """Anker, den GitHub für eine Überschrift vergibt."""
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def test_hints_link_a_section_of_the_readme():  # das Paket liefert keine README mit: die Texte nennen ihre Adresse
    texts = {lang: json.loads((REPO / "orbitop" / "locale" / f"{lang}.json").read_text(encoding="utf-8"))
             for lang in ("en", "de")}
    for lang, name, text, power in (("en", "README.md", EN, "Graphics and power"),
                                    ("de", "README.de.md", DE, "Grafik und Leistung")):
        links = {"hint.igt_noperm": power, "hint.rapl_noperm": power, "result.nohelper": "Installation"}
        for key, section in links.items():
            assert f"\n## {section}\n" in text, (lang, section)
            url = f"https://github.com/zappelmann-sketch/orbitop/blob/main/{name}#{slug(section)}"
            assert url in texts[lang][key], (lang, key)


def fingerprint(text):
    """Der Fingerabdruck aus dem ersten Codeblock unter dem Abschnitt zum Signierschlüssel."""
    section = re.search(r"^### (Signing key|Signierschlüssel)\n(.*?)^### ", text, re.M | re.S)[2]
    return code_blocks(section)[0].strip()


def test_key_check_needs_exactly_one_key_and_its_fingerprint():  # Audit Task 7, F1: ein zweiter Schlüssel in der Datei
    for text, rule in ((EN, "exactly one key"), (DE, "genau einen Schlüssel")):
        assert rule in text
        assert f"using EDDSA key {fingerprint(text)}" in text  # gpgv nimmt jeden Schlüssel der Datei an
        first_curl = next(block for block in code_blocks(text) if "curl " in block)
        assert first_curl.startswith('cd "$(mktemp -d)"\n')  # F3: eigener Ordner für die Downloads


ARCH_KEYS = (  # Fingerabdrücke der Hauptschlüssel mit genau dieser User-ID, geprüft, bevor pacman-key sie sieht
    "sudo gpg --homedir /etc/pacman.d/gnupg --no-options --batch --with-colons --list-keys "
    "'=orbitop archive signing key' | awk -F: '$1 == \"pub\" { p = 1; next } p && $1 == \"fpr\" { print $10 } "
    "{ p = 0 }' | grep -xE '[0-9A-F]{40}' | xargs -r -n1 sudo pacman-key --delete")


def test_uninstall_deletes_every_key_of_orbitop():  # Audit Task 7, F2: nach einer Erneuerung gibt es zwei
    for text in (EN, DE):
        assert "rpmkeys --list | grep -F 'orbitop archive signing key' | " in text
        assert ARCH_KEYS in text  # nicht orbitop-trusted: nach einer Erneuerung fehlt dort der alte Schlüssel
        assert "orbitop-trusted" not in text
