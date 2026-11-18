# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from orbitop import actions

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "data" / "io.github.zappelmann_sketch.orbitop.policy"
LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def policy():
    return ET.parse(POLICY, ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))).getroot()


def text(lang):
    return json.loads((ROOT / "orbitop" / "locale" / f"{lang}.json").read_text(encoding="utf-8"))["polkit.terminate"]


def test_exactly_one_terminate_action():
    assert [a.get("id") for a in policy().findall("action")] == ["io.github.zappelmann_sketch.orbitop.terminate"]


def test_every_session_needs_admin_auth_each_time():
    defaults = policy().find("action/defaults")
    assert {e.tag: e.text for e in defaults} == dict.fromkeys(("allow_any", "allow_inactive", "allow_active"),
                                                              "auth_admin")


def test_only_annotation_is_exec_path_of_the_helper():  # kein allow_gui, kein argv1
    assert {a.get("key"): a.text for a in policy().iter("annotate")} == {
        "org.freedesktop.policykit.exec.path": actions._HELPER}


def test_texts_match_locale():
    action = policy().find("action")
    for tag in ("description", "message"):
        assert {e.get(LANG): e.text for e in action.findall(tag)} == {None: text("en"), "de": text("de")}, tag


def test_spdx_header_in_comment():
    comments = " ".join(c.text for c in policy().iter(ET.Comment))
    assert "SPDX-License-Identifier: GPL-3.0-or-later" in comments
    assert "Copyright © 2026 zappelmann-sketch" in comments
