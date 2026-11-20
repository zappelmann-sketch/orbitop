# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from orbitop import actions

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "data" / "io.github.zappelmann-sketch.orbitop.policy"  # polkit(8): ohne "_", anders als die App-ID
LANG = "{http://www.w3.org/XML/1998/namespace}lang"
NS = "io.github.zappelmann-sketch.orbitop."
COUNTERHELPER = "/usr/lib/orbitop/counterhelper"  # B2.1, installiert von packaging/install-tree.sh
EXEC = "org.freedesktop.policykit.exec."
# Action -> (Vorgaben any, inactive, active; Annotationen; Schlüssel der Texte in locale/*.json)
ACTIONS = {
    "terminate": (("auth_admin",) * 3, [(EXEC + "path", actions._HELPER)], "polkit.terminate"),
    # E2 = A: nur lokale, aktive Sitzungen; argv1 wählt die Action nach dem ersten Wort des Helfers
    "counters-release": (("no", "no", "auth_admin"), [(EXEC + "path", COUNTERHELPER), (EXEC + "argv1", "on")],
                         "polkit.counters_release"),
    "counters-lock": (("no", "no", "auth_admin"), [(EXEC + "path", COUNTERHELPER), (EXEC + "argv1", "off")],
                      "polkit.counters_lock"),
}


def policy():
    return ET.parse(POLICY, ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))).getroot()


def action(name):
    return policy().find(f"action[@id='{NS}{name}']")


def text(lang, key="polkit.terminate"):
    return json.loads((ROOT / "orbitop" / "locale" / f"{lang}.json").read_text(encoding="utf-8"))[key]


def test_exactly_the_three_actions():
    assert [a.get("id") for a in policy().findall("action")] == [NS + name for name in ACTIONS]


def test_names_follow_polkit8():  # nur [A-Za-z0-9.-], Datei heißt nach dem Namensraum der Actions
    for a in policy().findall("action"):
        assert re.fullmatch(r"[A-Za-z0-9.-]+", a.get("id"))
        assert POLICY.name == a.get("id").rsplit(".", 1)[0] + ".policy"


@pytest.mark.parametrize("name", ACTIONS)
def test_defaults(name):  # jedes Mal das Admin-Passwort; die Zähler nur in lokalen, aktiven Sitzungen
    defaults = action(name).find("defaults")
    assert [(e.tag, e.text) for e in defaults] == list(zip(("allow_any", "allow_inactive", "allow_active"),
                                                           ACTIONS[name][0]))


@pytest.mark.parametrize("name", ACTIONS)
def test_annotations_only_exec_path_and_argv1(name):  # kein allow_gui (M-8)
    assert [(a.get("key"), a.text) for a in action(name).iter("annotate")] == ACTIONS[name][1]


def test_never_kept_or_granted_and_no_gui_annotation():  # B2.1: nie auth_admin_keep, nie yes, nie exec.allow_gui
    assert not {e.text for d in policy().iter("defaults") for e in d} & {"auth_admin_keep", "yes", "auth_self",
                                                                          "auth_self_keep"}
    assert "allow_gui" not in POLICY.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ACTIONS)
def test_texts_match_locale(name):  # K7: je Sprache genau ein Element
    key = ACTIONS[name][2]
    for tag, k in (("description", key + "_description"), ("message", key)):
        assert sorted((e.get(LANG, ""), e.text) for e in action(name).findall(tag)) == [("", text("en", k)),
                                                                                       ("de", text("de", k))], tag


def test_release_texts_name_the_risk():  # B2.1: der Dialog nennt, wer liest und welches Risiko
    assert text("en", "polkit.counters_release") == (
        "Every account on this computer will be able to read the GPU and energy counters. "
        "Risk: power side channels (Platypus, CVE-2020-8694).")
    assert text("de", "polkit.counters_release") == (
        "Jedes Konto auf diesem Rechner kann dann die Grafik- und Energiezähler lesen. "
        "Risiko: Seitenkanal über den Stromverbrauch (Platypus, CVE-2020-8694).")
    assert text("de", "polkit.counters_release_description") == "Grafik- und Energiezähler für alle Konten freigeben"
    assert text("de", "polkit.counters_lock_description") == "Grafik- und Energiezähler wieder sperren"


def test_dialog_shows_the_command_line():  # sonst sähe der Admin nicht, welche PID der Helfer beenden soll
    assert all(text(lang).endswith(": $(command_line)") for lang in ("en", "de"))
    assert not [e.text for e in policy().iter("description") if "$(" in e.text]  # polkit ersetzt nur in <message>


def test_ui_never_uses_polkit_texts():  # polkit.* ist nur für die .policy; die Seite setzt $(…) nicht ein
    assert not [p for p in (ROOT / "orbitop" / "ui").rglob("*") if p.is_file() and b"polkit" in p.read_bytes()]


def test_spdx_header_in_comment():
    comments = " ".join(c.text for c in policy().iter(ET.Comment))
    assert "SPDX-License-Identifier: GPL-3.0-or-later" in comments
    assert "Copyright © 2026 zappelmann-sketch" in comments
