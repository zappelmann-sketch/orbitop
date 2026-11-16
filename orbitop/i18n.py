# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Sprachwahl und Textdateien (locale/en.json, locale/de.json)."""
import json
from collections.abc import Mapping
from pathlib import Path

LOCALE_DIR = Path(__file__).parent / "locale"


def detect_language(env: Mapping[str, str]) -> str:
    locale = env.get("LC_ALL") or env.get("LC_MESSAGES") or env.get("LANG") or ""
    if locale in ("", "C", "POSIX"):
        return "en"
    first = (env.get("LANGUAGE") or "").split(":")[0]
    return "de" if (first or locale).startswith("de") else "en"


def _read(lang: str) -> dict[str, str]:
    try:
        data = json.loads((LOCALE_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_texts(lang: str) -> dict[str, str]:
    texts = _read("en")
    if lang != "en":
        texts.update(_read(lang))
    return texts
