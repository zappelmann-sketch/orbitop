#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gibt einen Schnappschuss (tick-Nachricht) als JSON aus; --js erzeugt die Demo-Datei der Oberfläche."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from orbitop import __version__  # noqa: E402
from orbitop.i18n import detect_language, load_texts  # noqa: E402
from orbitop.sampler import Sampler  # noqa: E402


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default="/")
    ap.add_argument("--ticks", type=int, default=5)
    ap.add_argument("--interval", type=float, default=1.0, help="Sekunden zwischen den Takten")
    ap.add_argument("--js", action="store_true", help="window.ORBITOP_DEMO = {init, tick};")
    a = ap.parse_args(argv)
    sampler = Sampler(a.root)
    try:
        for i in range(max(1, a.ticks)):
            if i:
                time.sleep(a.interval)
            sampler.tick_system()
            sampler.tick_procs()
        tick = sampler.snapshot({"tab": "overview", "pid": None, "start": None})
    finally:
        sampler.close()
    if a.js:
        lang = detect_language(os.environ)
        init = {"type": "init", "lang": lang, "texts": load_texts(lang), "version": __version__}
        print("window.ORBITOP_DEMO = " + json.dumps({"init": init, "tick": tick}, ensure_ascii=False) + ";")
    else:
        print(json.dumps(tick, ensure_ascii=False))


if __name__ == "__main__":
    main()
