# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from orbitop import actions

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "data" / "io.github.zappelmann-sketch.orbitop.policy"  # polkit(8): ohne "_", anders als die App-ID
LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def policy():
    return ET.parse(POLICY, ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))).getroot()


def text(lang, key="polkit.terminate"):
    return json.loads((ROOT / "orbitop" / "locale" / f"{lang}.json").read_text(encoding="utf-8"))[key]


def test_exactly_one_terminate_action():
    assert [a.get("id") for a in policy().findall("action")] == ["io.github.zappelmann-sketch.orbitop.terminate"]


def test_names_follow_polkit8():  # nur [A-Za-z0-9.-], Datei heißt nach dem Namensraum der Action
    action_id = policy().find("action").get("id")
    assert re.fullmatch(r"[A-Za-z0-9.-]+", action_id)
    assert POLICY.name == action_id.rsplit(".", 1)[0] + ".policy"


def test_every_session_needs_admin_auth_each_time():
    defaults = policy().find("action/defaults")
    assert sorted((e.tag, e.text) for e in defaults) == [(k, "auth_admin") for k in
                                                         ("allow_active", "allow_any", "allow_inactive")]


def test_only_annotation_is_exec_path_of_the_helper():  # kein allow_gui, kein argv1
    assert [(a.get("key"), a.text) for a in policy().iter("annotate")] == [
        ("org.freedesktop.policykit.exec.path", actions._HELPER)]


def test_texts_match_locale():  # K7: je Sprache genau ein Element
    action = policy().find("action")
    for tag, key in (("description", "polkit.terminate_description"), ("message", "polkit.terminate")):
        assert sorted((e.get(LANG, ""), e.text) for e in action.findall(tag)) == [("", text("en", key)),
                                                                                  ("de", text("de", key))], tag


def test_dialog_shows_the_command_line():  # sonst sähe der Admin nicht, welche PID der Helfer beenden soll
    assert all(text(lang).endswith(": $(command_line)") for lang in ("en", "de"))
    assert not [e.text for e in policy().iter("description") if "$(" in e.text]  # polkit ersetzt nur in <message>


def test_ui_never_uses_polkit_texts():  # polkit.* ist nur für die .policy; die Seite setzt $(…) nicht ein
    assert not [p for p in (ROOT / "orbitop" / "ui").rglob("*") if p.is_file() and b"polkit" in p.read_bytes()]


def test_spdx_header_in_comment():
    comments = " ".join(c.text for c in policy().iter(ET.Comment))
    assert "SPDX-License-Identifier: GPL-3.0-or-later" in comments
    assert "Copyright © 2026 zappelmann-sketch" in comments
