# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import json
import re
from pathlib import Path

import pytest

from orbitop import i18n
from orbitop.i18n import detect_language, load_texts

LOCALE = Path(i18n.__file__).parent / "locale"
# Gesicherte Schlüssel, die spätere Tasks und bereits geschriebener Code verwenden.
REQUIRED = """
hint.igt_missing hint.igt_noperm hint.igt_failed hint.nvsmi_missing hint.rapl_noperm
missing.gpu missing.power missing.temp missing.fan missing.net missing.disk footer.missing
btn.terminate btn.kill btn.hint
confirm.title confirm.terminate_text confirm.kill_text confirm.yes confirm.cancel
about.title about.version about.license about.copyright about.fonts about.quit
procs.search filter.all filter.mine filter.flagged
col.process col.cpu col.last60 col.ram col.io col.state
detail.io_hidden detail.none_selected tab.overview tab.procs
""".split()
STATES = ["working", "waiting", "busy_noio", "busy_iounknown", "kernel_hang", "stopped", "zombie"]
RESULTS = ["sent", "gone", "mismatch", "zombie", "kernel", "denied", "nohelper", "error"]
# Typische Ersatzschreibweisen; "ue" allein wäre zu laut (Dauerlast, Queue).
UMLAUT_SUBSTITUTES = re.compile(
    r"\b(Ae|Oe|Ue)\w+|\w*(fuer|Groesse|groesse|Schluessel|Verfuegbar|verfuegbar|Waehle|waehle|Koennen|ueber|Ueber|koenn|moeg|wuerd|Laeuft|laeuft|Lueft|Prozess?e?n?\s+gehoer"
    r"|Datentraeger|Geraet|Gehaeuse|Zaehl|hoeher|waehl|aender|Aender|schliess|oeffn|Oeffn)\w*")


def json_of(lang):
    return json.loads((LOCALE / f"{lang}.json").read_text(encoding="utf-8"))


def placeholders(text):
    return set(re.findall(r"\{(\w+)\}", text))


@pytest.mark.parametrize("env,lang", [
    ({"LANG": "de_DE.UTF-8"}, "de"), ({"LANG": "de_AT.UTF-8@euro"}, "de"), ({"LANG": "fr_FR.UTF-8"}, "en"),
    ({"LANG": "C"}, "en"), ({}, "en"), ({"LANG": "en_US.UTF-8", "LC_ALL": "de_CH.UTF-8"}, "de"),
    ({"LANG": "de_DE.UTF-8", "LANGUAGE": "en:de"}, "en"), ({"LC_ALL": "C", "LANGUAGE": "de"}, "en"),
    ({"LANG": "en_US.UTF-8", "LC_MESSAGES": "de_DE.UTF-8"}, "de"),
    ({"LANG": "de_DE.UTF-8", "LC_ALL": ""}, "de"),
    ({"LANG": "POSIX"}, "en"), ({"LANG": "POSIX", "LANGUAGE": "de"}, "en"), ({"LANG": "", "LANGUAGE": "de"}, "en"),
    ({"LANG": "dex"}, "en"), ({"LANG": "dk_DK"}, "en"), ({"LANG": "deu"}, "en"), ({"LANG": "de"}, "de"),
    ({"LANG": "de.UTF-8"}, "de"), ({"LANG": "de_DE@euro"}, "de"),
    ({"LC_ALL": "de_DE", "LC_MESSAGES": "en_US"}, "de"), ({"LC_ALL": "en_US", "LC_MESSAGES": "de_DE"}, "en"),
    ({"LC_MESSAGES": "en_US", "LANG": "de_DE"}, "en"),
    ({"LANG": " de_DE "}, "de"), ({"LC_ALL": "  ", "LANG": "de_DE"}, "de"), ({"LANG": "en_US", "LANGUAGE": " de "}, "de"),
    ({"LANG": "en_US", "LANGUAGE": ":de"}, "de"), ({"LANG": "de_DE", "LANGUAGE": ":en"}, "en"), ({"LANG": "en_US.UTF-8", "LANGUAGE": "de:en"}, "de"),
])
def test_detect_language(env, lang):
    assert detect_language(env) == lang


def test_same_keys_in_both_languages():
    assert set(json_of("en")) == set(json_of("de"))


def test_placeholders_match():
    en, de = json_of("en"), json_of("de")
    for k in en:
        assert placeholders(en[k]) == placeholders(de[k]), k


def test_values_are_nonempty_strings_and_keys_sorted():
    for lang in ("en", "de"):
        data = json_of(lang)
        assert list(data) == sorted(data)
        assert all(isinstance(v, str) and v.strip() for v in data.values())


def test_brand_not_in_texts():
    assert not any("ORBITOP" in v for lang in ("en", "de") for v in json_of(lang).values())


def test_required_keys_exist():
    keys = set(json_of("en"))
    wanted = set(REQUIRED) | {f"{p}.{s}" for p in ("state", "legend", "verdict") for s in STATES}
    wanted |= {f"result.{r}" for r in RESULTS}
    assert wanted <= keys, sorted(wanted - keys)


def test_key_placeholders():
    en = json_of("en")
    assert placeholders(en["footer.missing"]) == {"list"}
    assert placeholders(en["cap.rate"]) == {"unit"}
    assert placeholders(en["about.version"]) == {"version"}
    assert placeholders(en["verdict.zombie"]) == {"parent"}
    assert {"name", "pid"} <= placeholders(en["confirm.terminate_text"]) & placeholders(en["confirm.kill_text"])
    for s in ("busy_noio", "busy_iounknown", "kernel_hang"):
        assert "since" in placeholders(en[f"verdict.{s}"])


def test_denied_does_not_blame_password():
    for lang in ("en", "de"):
        assert "password" not in json_of(lang)["result.denied"].lower()
        assert "passwort" not in json_of(lang)["result.denied"].lower()


def test_nohelper_points_to_the_readme():
    for lang in ("en", "de"):
        text = json_of(lang)["result.nohelper"]
        assert "README" in text and "setup-privileges" not in text


def test_rapl_hint_names_flag_and_risk():
    for lang in ("en", "de"):
        assert "--allow-rapl" in json_of(lang)["hint.rapl_noperm"]


def test_igt_noperm_hint_names_flag_and_risk():
    for lang in ("en", "de"):
        text = json_of(lang)["hint.igt_noperm"]
        assert "--allow-perfmon" in text and "CVE-2020-8694" in text


def test_igt_missing_hint_names_the_own_process_fallback():  # ohne intel_gpu_top zeigt die Kachel fdinfo eigener Prozesse
    assert "own processes" in json_of("en")["hint.igt_missing"]
    assert "eigene Prozesse" in json_of("de")["hint.igt_missing"]


def test_german_has_real_umlauts():
    de = json_of("de")
    assert de["tab.overview"] == "Übersicht"
    bad = {k: v for k, v in de.items() if UMLAUT_SUBSTITUTES.search(v)}
    assert not bad, bad


def test_umlaut_check_detects_substitutes():
    for word in ("Uebersicht", "fuer dich", "Groesse", "Schluessel", "Verfuegbar", "Waehle", "Koennen"):
        assert UMLAUT_SUBSTITUTES.search(word), word
    assert not UMLAUT_SUBSTITUTES.search("Dauerlast über Zeit")


def test_fallback_to_english():
    assert load_texts("de")["tab.overview"] == "Übersicht"
    assert load_texts("en")["tab.overview"] == "Overview"
    assert load_texts("xx") == load_texts("en")


def test_missing_german_key_falls_back_to_english(tmp_path, monkeypatch):
    (tmp_path / "en.json").write_text('{"a": "A", "b": "B"}', encoding="utf-8")
    (tmp_path / "de.json").write_text('{"a": "Ä"}', encoding="utf-8")
    monkeypatch.setattr(i18n, "LOCALE_DIR", tmp_path)
    assert load_texts("de") == {"a": "Ä", "b": "B"}


@pytest.mark.parametrize("de_content", [None, "{kaputt", "[1, 2]"])
def test_broken_or_missing_file_falls_back(tmp_path, monkeypatch, de_content):
    (tmp_path / "en.json").write_text('{"a": "A"}', encoding="utf-8")
    if de_content is not None:
        (tmp_path / "de.json").write_text(de_content, encoding="utf-8")
    monkeypatch.setattr(i18n, "LOCALE_DIR", tmp_path)
    assert load_texts("de") == {"a": "A"}


def test_broken_english_gives_empty_dict(tmp_path, monkeypatch):
    (tmp_path / "en.json").write_text("{kaputt", encoding="utf-8")
    monkeypatch.setattr(i18n, "LOCALE_DIR", tmp_path)
    assert load_texts("en") == {}
    assert load_texts("de") == {}


def test_works_from_other_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_texts("en")["tab.overview"] == "Overview"


def test_load_texts_ignores_unknown_language(tmp_path, monkeypatch):
    (tmp_path / "en.json").write_text('{"a": "A"}', encoding="utf-8")
    (tmp_path / "evil.json").write_text('{"a": "X"}', encoding="utf-8")
    (tmp_path.parent / "esc.json").write_text('{"a": "X"}', encoding="utf-8")
    monkeypatch.setattr(i18n, "LOCALE_DIR", tmp_path)
    assert load_texts("evil") == {"a": "A"}
    assert load_texts("../esc") == {"a": "A"}


def test_kill_dialog_has_own_labels():
    for lang in ("en", "de"):
        d = json_of(lang)
        assert d["confirm.title_kill"] != d["confirm.title"]
        assert d["confirm.yes_kill"] != d["confirm.yes"]


def test_every_tile_kind_has_missing_text():
    from orbitop.sampler import KINDS
    assert {f"missing.{k}" for k in KINDS} <= set(json_of("en"))
