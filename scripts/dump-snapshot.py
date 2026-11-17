#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gibt einen Schnappschuss (tick-Nachricht) als JSON aus; --js erzeugt die Demo-Datei der Oberfläche."""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from orbitop import __version__  # noqa: E402
from orbitop.gpu_tools import GpuTools  # noqa: E402
from orbitop.i18n import detect_language, load_texts  # noqa: E402
from orbitop.sampler import Sampler  # noqa: E402


def _interval(text: str) -> float:
    v = float(text)
    if not math.isfinite(v) or v <= 0:
        raise argparse.ArgumentTypeError("muss größer als 0 und endlich sein")
    return v


def anonymize(tick: dict) -> dict:
    """Ersetzt Prozessnamen, Argumente, Befehlszeilen, Benutzer und Elternnamen durch proc-N und user (Demodaten)."""
    names: dict[str, str] = {}

    def alias(name: str) -> str:
        return names.setdefault(name, f"proc-{len(names) + 1}")

    rows = [*(tick["top"]["cpu"] or []), tick["top"]["mem"], *(tick["procs"] or []), tick["detail"]]
    for r in filter(None, rows):
        r["name"] = alias(r["name"])
        if "args" in r:
            r["args"], r["user"] = "", "user"
        if "cmdline" in r:
            r["cmdline"], r["parent"] = r["name"], alias(r["parent"]) if r["parent"] else ""
    return tick


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default="/")
    ap.add_argument("--ticks", type=int, default=5)
    ap.add_argument("--interval", type=_interval, default=1.0, help="Sekunden zwischen den Takten")
    ap.add_argument("--view", choices=("overview", "procs"), default="overview",
                    help="procs füllt auch procs und detail (Prozess mit der höchsten CPU-Last)")
    ap.add_argument("--js", action="store_true", help="window.ORBITOP_DEMO = {init, tick};")
    ap.add_argument("--anonymize", action="store_true", help="Prozessnamen, Befehlszeilen und Benutzer ersetzen")
    a = ap.parse_args(argv)
    # Fixture-Bäume bekommen keine echten Werkzeuge, sonst mischten sich echte GPU-Werte in die Ausgabe
    sampler = Sampler(a.root, tools=GpuTools([]) if os.path.realpath(a.root) != "/" else None)
    try:
        for i in range(max(1, a.ticks)):
            if i:
                time.sleep(a.interval)
            sampler.tick_system()
            if i % 2 == 0:  # wie der Worker der App: Prozesse jeden zweiten Takt
                sampler.tick_procs(shr=a.view == "procs")
        tick = sampler.snapshot({"tab": a.view, "pid": None, "start": None})
        if a.view == "procs" and tick["procs"]:
            top = max(tick["procs"], key=lambda r: r["cpu"])
            tick = sampler.snapshot({"tab": "procs", "pid": top["pid"], "start": top["start"]})
    finally:
        sampler.close()
    if a.anonymize:
        tick = anonymize(tick)
    if a.js:
        lang = detect_language(os.environ)
        init = {"type": "init", "lang": lang, "texts": load_texts(lang), "version": __version__}
        print("window.ORBITOP_DEMO = " + json.dumps({"init": init, "tick": tick}, ensure_ascii=False) + ";")
    else:
        print(json.dumps(tick, ensure_ascii=False))


if __name__ == "__main__":
    main()
