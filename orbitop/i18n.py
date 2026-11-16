# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Sprachwahl und Textdateien (locale/en.json, locale/de.json)."""
import json
import re
from collections.abc import Mapping
from pathlib import Path

LOCALE_DIR = Path(__file__).parent / "locale"


def detect_language(env: Mapping[str, str]) -> str:
    def get(key: str) -> str:
        return env.get(key, "").strip()

    locale = get("LC_ALL") or get("LC_MESSAGES") or get("LANG")
    if locale in ("", "C", "POSIX"):
        return "en"
    first = next((e.strip() for e in get("LANGUAGE").split(":") if e.strip()), "")
    return "de" if re.match(r"de([_.@-]|$)", first or locale) else "en"


def _read(lang: str) -> dict[str, str]:
    try:
        data = json.loads((LOCALE_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_texts(lang: str) -> dict[str, str]:
    texts = _read("en")
    if lang == "de":  # nur bekannte Sprachen, nie ein Dateiname aus fremder Eingabe
        texts.update(_read(lang))
    return texts
