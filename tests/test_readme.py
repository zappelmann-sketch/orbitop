# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""README.md und README.de.md: gegenseitig verlinkt, gleich aufgebaut, nur geprüfte Distributionen als unterstützt,
dieselben Befehle wie die Container-Matrix."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from orbitop import __version__, app, counterhelper, counters, packagekit
from tests.packaging_common import KEY_FILE
from tests.site_stub import kill_agent

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


# Paket mit /usr/bin/intel_gpu_top je Ziel (Container, 2026-11-20): Ubuntu 26.04 igt-gpu-tools (intel-gpu-tools ist
# dort nur ein Metapaket), Ubuntu 24.04, Debian 13, openSUSE und Arch intel-gpu-tools, Fedora igt-gpu-tools.
INTEL_TOOLS = [["Ubuntu 26.04", "`sudo apt install igt-gpu-tools`"],
               ["Ubuntu 24.04, Debian 13", "`sudo apt install intel-gpu-tools`"],
               ["Fedora", "`sudo dnf install igt-gpu-tools`"], ["openSUSE", "`sudo zypper install intel-gpu-tools`"],
               ["Arch Linux", "`sudo pacman -S intel-gpu-tools`"]]
INTEL_NAMES = {"Debian, Ubuntu": "`intel-gpu-tools`, Ubuntu 26.04: `igt-gpu-tools`", "Fedora": "`igt-gpu-tools`",
               "Arch Linux": "`intel-gpu-tools`", "openSUSE": "`intel-gpu-tools`"}


def test_readmes_name_the_package_of_intel_gpu_top():
    for text, names in ((EN, "### Package names\n"), (DE, "### Paketnamen\n")):
        assert table(text.split("### Intel\n", 1)[1].split("\n### ", 1)[0]) == INTEL_TOOLS
        assert {row[0]: row[-1] for row in table(text.split(names, 1)[1].split("\n## ", 1)[0])} == INTEL_NAMES


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
        links = {"hint.igt_noperm_readme": power, "hint.rapl_noperm_readme": power, "settings.counters_nohelper": power,
                 "settings.counters_manual_rule": power, "settings.lock_text_rule": power, "counters.unsafe": power,
                 "result.nohelper": "Installation"}
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


def key_records(tmp_path):
    """Die Felder je Zeile von gpg --with-colons --show-keys für KEY_FILE, gelesen in einem leeren Schlüsselbund."""
    if not shutil.which("gpg"):
        pytest.skip("gpg fehlt")
    (tmp_path / "gnupg").mkdir(mode=0o700)
    try:
        out = subprocess.run(["gpg", "--no-options", "--homedir", str(tmp_path / "gnupg"), "--batch", "--with-colons",
                              "--show-keys", str(KEY_FILE)], check=True, capture_output=True, text=True).stdout
    finally:
        kill_agent(tmp_path / "gnupg")
    return [ln.split(":") for ln in out.splitlines()]


# Plan 2026-11-18, Task 9: ohne Unterschlüssel, ohne Geheimes, User-ID ohne Mail
def test_key_file_holds_one_public_key(tmp_path):
    records = key_records(tmp_path)
    assert [r[0] for r in records if r[0] in ("pub", "sub", "sec", "ssb")] == ["pub"]
    assert [r[9] for r in records if r[0] == "uid"] == ["orbitop archive signing key"]
    assert b"PRIVATE KEY" not in KEY_FILE.read_bytes()


def test_readmes_name_the_fingerprint_of_the_key_file(tmp_path):
    fpr = next(r[9] for r in key_records(tmp_path) if r[0] == "fpr")
    for text in (EN, DE):
        assert "<FINGERPRINT>" not in text and fingerprint(text) == fpr
        # jeder Fingerabdruck, am Stück oder gruppiert wie gpg ihn zeigt (wie check_readme in scripts/release/checks.sh)
        assert fingerprints(text) == {fpr}


def fingerprints(text):
    return {m.replace(" ", "") for m in re.findall(r"\b[0-9A-F]{4}(?: {0,2}[0-9A-F]{4}){9}\b", text)}


ARCH_KEYS = (  # Fingerabdrücke der Hauptschlüssel mit genau dieser User-ID, geprüft, bevor pacman-key sie sieht;
    # pacman-key ruft gpg selbst mit --no-permission-warning auf, denn sein Ordner ist absichtlich 755
    "sudo gpg --homedir /etc/pacman.d/gnupg --no-options --no-permission-warning --batch --with-colons --list-keys "
    "'=orbitop archive signing key' | awk -F: '$1 == \"pub\" { p = 1; next } p && $1 == \"fpr\" { print $10 } "
    "{ p = 0 }' | grep -xE '[0-9A-F]{40}' | xargs -r -n1 sudo pacman-key --delete")
RPM_KEYS = ("rpmkeys --list | grep -F 'orbitop archive signing key' | sed 's/[: ].*//' | "
            "xargs -r -n1 sudo rpmkeys --delete")
ARCH_CHECK = "pacman-key --list-keys '=orbitop archive signing key'"


def test_uninstall_deletes_every_key_of_orbitop():  # Audit Task 7, F2: nach einer Erneuerung gibt es zwei
    joined = re.sub(r"\|\n\s*", "| ", re.sub(r"\s*\\\n\s*", " ", MATRIX))  # Folgezeilen der Skripte angehängt
    for text in (EN, DE):
        assert RPM_KEYS in text and ARCH_CHECK in text
        assert ARCH_KEYS in text  # nicht orbitop-trusted: nach einer Erneuerung fehlt dort der alte Schlüssel
        assert "orbitop-trusted" not in text
    for line in (RPM_KEYS, ARCH_KEYS, ARCH_CHECK):  # README = Matrix; die Matrix läuft als root, ohne sudo
        assert line.replace("sudo ", "") in joined, line


# 0.3.0 (Spec C6, Security-Dokument B2.8, B2.9, E1, E2, E3): dieselben Abschnitte in beiden Sprachen
COUNTERS = {"README.md": {"power": "## Graphics and power", "switch": "### Counter release",
                          "manual": "### Without the package", "move": "### Moving from 0.2.0",
                          "remove": "### The counter release on removal",
                          "fedora": "On Fedora the package manager installs for admins without a password prompt "
                                    "(rule of the distribution).", "downgrade": "before a downgrade to 0.2.0",
                          "xdg": "is set to an absolute path"},
            "README.de.md": {"power": "## Grafik und Leistung", "switch": "### Messzähler freigeben",
                             "manual": "### Ohne Paket", "move": "### Umstieg von 0.2.0",
                             "remove": "### Die Freigabe beim Entfernen",
                             "fedora": "Auf Fedora installiert die Paketverwaltung für Admins ohne Passwortabfrage "
                                       "(Regel der Distribution).", "downgrade": "Vor einem Downgrade auf 0.2.0",
                             "xdg": "auf einen absoluten Pfad gesetzt"}}
MIGRATION = "sudo rm -f /etc/udev/rules.d/70-orbitop-rapl.rules\nsudo setcap -r /usr/bin/intel_gpu_top\n"  # B2.9
REMOTE = "sudo /usr/lib/orbitop/counterhelper on\nsudo /usr/lib/orbitop/counterhelper off\n"  # E2


def section(text, heading):
    """Der Abschnitt ab heading bis zur nächsten Überschrift derselben oder einer höheren Ebene."""
    level = len(heading.split(" ")[0])
    start = text.index(f"\n{heading}\n") + 1
    ends = [text.find(f"\n{'#' * n} ", start + len(heading)) for n in range(2, level + 1)]
    return text[start:min([e for e in ends if e >= 0] or [len(text)])]


@pytest.mark.parametrize("name", COUNTERS)
def test_readmes_describe_the_counter_release(name):
    text, w = (EN if name == "README.md" else DE), COUNTERS[name]
    power = section(text, w["power"])
    for key in ("switch", "manual", "move"):
        assert f"\n{w[key]}\n" in power, (name, key)
    assert code_blocks(section(text, w["switch"])) == [REMOTE]
    assert counterhelper.MARKER in section(text, w["switch"]) and counters.MANUAL_RULE in section(text, w["manual"])
    assert code_blocks(section(text, w["move"])) == [MIGRATION]
    assert w["fedora"] in section(text, "### Intel")
    removal = section(text, w["remove"])
    assert code_blocks(removal) == ["sudo setcap -r /usr/bin/intel_gpu_top\n"], name  # R14
    assert w["downgrade"] in removal  # R7
    assert "counterhelper off" in removal and "Debian Policy 10.7.3" in removal  # B2.8, E1
    assert w["xdg"] in text


@pytest.mark.parametrize("name", COUNTERS)
def test_manual_release_only_for_starts_without_package(name):  # C6: die Befehle von Hand nur für Starts ohne Paket
    text = EN if name == "README.md" else DE
    manual = section(text, COUNTERS[name]["manual"])
    for command in ("setcap cap_perfmon=ep", "| sudo tee /etc/udev/rules.d/70-orbitop-rapl.rules"):
        assert text.count(command) == manual.count(command) == 1, command


def test_readmes_show_the_fallback_command_of_the_hint():  # der Befehl, den der Hinweis ohne PackageKit zeigt
    for manager in packagekit.NAMES:
        command = f"`{packagekit.command(manager)}`"
        assert command in section(EN, "### Intel") and command in section(DE, "### Intel"), manager


@pytest.mark.parametrize("name", COUNTERS)
def test_cleanup_and_setcap_notes(name):
    """Review Task 9: rm -rf nie unter einem relativen XDG_CONFIG_HOME, den orbitop ignoriert; setcap -r ohne Fähigkeit
    scheitert harmlos, und woher setcap auf einem minimalen System kommt."""
    text = EN if name == "README.md" else DE
    rm = [ln for block in code_blocks(text) for ln in block.splitlines() if ln.startswith("rm -rf")]
    assert rm == ['rm -rf -- "$config/orbitop"'] and "case ${XDG_CONFIG_HOME-} in /*) config=$XDG_CONFIG_HOME" in text
    # 0.4.0 D1 (#32): auch die Autostart-Befehle nehmen XDG_CONFIG_HOME nur absolut, wie die App (userfile.config_home)
    assert "${XDG_CONFIG_HOME:-" not in text and 'mkdir -p "$config/autostart"' in text
    unsafe = [p for p in section(text, COUNTERS[name]["switch"]).split("\n\n") if "energy_uj" in p and "0711" in p]
    assert len(unsafe) == 1 and "drwx--x--x" in unsafe[0]  # 0.4.0, Review T4 I-1: auch lesbar ist unsicher
    for part in (section(text, COUNTERS[name]["move"]), section(text, COUNTERS[name]["remove"])):
        assert "has no capability to remove" in part
    assert all(f"`{p}`" in section(text, COUNTERS[name]["remove"]) for p in ("libcap2-bin", "libcap-progs", "libcap"))


def test_status_names_the_version():  # 0.4.0, Schlussprüfung I-1: die Statuszeile zieht mit der Version mit
    assert f"**Status:** version {__version__}." in EN and f"**Stand:** Version {__version__}." in DE
