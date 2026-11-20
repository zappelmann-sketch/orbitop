# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Prüfseite tests/ui/check.html im kopflosen Chrome: Zahlenformat, sichere Texte, Nachrichten an Python.
Dazu der Aufbau der Module unter orbitop/ui/js: zyklenfrei, klein, genau eine Stelle für terminate.
Und die Stylesheets unter orbitop/ui/css: in Regelreihenfolge eingebunden, als text/css ausgeliefert."""
import contextlib
import functools
import http.server
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from orbitop.app import ui_file

CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
REPO = Path(__file__).resolve().parent.parent
UI = REPO / "orbitop" / "ui"
JS_DIR = UI / "js"
CHECK_DIR = REPO / "tests" / "ui"
IMPORT = re.compile(r'^(?:import|export)\s+(?:[^;"]*?\s+from\s+)?"(\.\.?/[^"]+)";', re.M)
CSS = ["base.css", "header.css", "tiles.css", "procs.css", "dialogs.css"]  # Reihenfolge der Regeln im früheren style.css
LINK = re.compile(r'<link rel="stylesheet" href="([^"]+)">')


def relative_imports(src):
    """Relative Module, die src importiert oder re-exportiert, auch ohne from und über mehrere Zeilen."""
    return IMPORT.findall(src)


@contextlib.contextmanager
def serve(root):
    """Basis-URL eines HTTP-Servers nur auf 127.0.0.1 mit freiem Port und der Wurzel root."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def ui_server(tmp_path_factory):
    """Basis-URL eines HTTP-Servers nur auf 127.0.0.1: Chrome lädt Module nicht über file://.
    Die Wurzel enthält nur orbitop/ui und tests/ui."""
    root = tmp_path_factory.mktemp("www")
    for part in ("orbitop/ui", "tests/ui"):
        (root / part).parent.mkdir(parents=True, exist_ok=True)
        (root / part).symlink_to(REPO / part)
    with serve(root) as base:
        yield base


def dump(tmp_path, base, size, fragment=""):
    return subprocess.run([CHROME, "--headless=new", f"--user-data-dir={tmp_path}", f"--window-size={size}",
                           "--dump-dom", base + "tests/ui/check.html" + fragment],
                          capture_output=True, text=True, timeout=60).stdout


def check_page(tmp_path, base, size, fragment=""):
    out = dump(tmp_path, base, size, fragment)
    assert "<title>PASS</title>" in out, out[out.find("<title>"):out.find("</title>")]


@pytest.mark.skipif(not CHROME, reason="kein Chrome oder Chromium installiert")
def test_ui_check_page(tmp_path, ui_server):
    check_page(tmp_path, ui_server, "1600,1000")


@pytest.mark.skipif(not CHROME, reason="kein Chrome oder Chromium installiert")
def test_ui_check_page_narrow(tmp_path, ui_server):
    """Unter 1100 px: Liste über dem Detail, kein Trenner, die Seite rollt nicht waagerecht."""
    check_page(tmp_path, ui_server, "1000,800", "#narrow")


@pytest.mark.skipif(not CHROME, reason="kein Chrome oder Chromium installiert")
def test_ui_check_page_reports_module_error(tmp_path):
    """Wirft ein Modul der App schon beim Auswerten, steht FAIL im Titel statt RUNNING: Die Stubs der Prüfseite
    (onerror, gefälschte Brücke, Zeitgeber) laden vor jedem Modul der App."""
    root = tmp_path / "www"
    shutil.copytree(REPO / "orbitop" / "ui", root / "orbitop" / "ui")
    chart = root / "orbitop" / "ui" / "js" / "chart.js"
    chart.write_text(chart.read_text(encoding="utf-8") + '\nthrow new Error("probe");\n', encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "ui").symlink_to(REPO / "tests" / "ui")
    with serve(root) as base:
        out = dump(tmp_path / "chrome", base, "1600,1000")
    title = out[out.find("<title>"):out.find("</title>")]
    assert title.startswith("<title>FAIL Ausnahme: ") and "probe" in title, title


@pytest.mark.parametrize("src, want", [
    ('import { a } from "./a.js";', ["./a.js"]),
    ('import "./b.js";', ["./b.js"]),
    ('import {\n  a,\n  b,\n} from "../c.js";', ["../c.js"]),
    ('export { a } from "./d.js";', ["./d.js"]),
    ('export * from "./e.js";', ["./e.js"]),
    ('export function f() {}\nconst g = "./g.js";', []),
    ('import { h } from "https://example.com/h.js";', []),
])
def test_relative_imports(src, want):
    assert relative_imports(src) == want


def test_ui_modules_have_no_import_cycle():
    """Ein Zyklus ließe einen importierten Namen beim Auswerten undefined. Dazu: Jedes importierte Modul gibt es,
    jede Datei der Seite und der Prüfseite hat höchstens 300 Zeilen, und die Seite nutzt den Reiter „Prozesse“
    außerhalb von procs/ nur über dessen Fassade procs/view.js."""
    files = [*JS_DIR.rglob("*.js"), CHECK_DIR / "check.js", *(CHECK_DIR / "check").rglob("*.js")]
    procs = JS_DIR / "procs"
    graph = {}
    for p in sorted(files):
        src = p.read_text(encoding="utf-8")
        deps = [(p.parent / m).resolve() for m in relative_imports(src)]
        assert all(d.is_file() for d in deps), (p.name, [str(d) for d in deps if not d.is_file()])
        graph[p.resolve()] = deps
        assert len(src.splitlines()) <= 300, p.relative_to(REPO).as_posix()
        if p.parent == JS_DIR:
            assert {d.name for d in deps if d.parent == procs} <= {"view.js"}, p.name
    assert graph[(JS_DIR / "main.js").resolve()], "keine Importe in main.js erkannt"
    done = set()

    def visit(node, path):
        assert node not in path, "Zyklus: " + " -> ".join(n.name for n in [*path, node])
        if node not in done:
            for dep in graph.get(node, []):
                visit(dep, [*path, node])
            done.add(node)

    for node in graph:
        visit(node, [])


def test_terminate_is_posted_only_by_the_confirm_button():
    """Kein Beenden ohne Rückfrage: genau eine Stelle sendet terminate (confirmed in dialogs.js), nur der
    Bestätigungsknopf ruft sie auf, und kein anderes Modul fasst den Knopf an."""
    sources = {p.relative_to(JS_DIR).as_posix(): p.read_text(encoding="utf-8") for p in sorted(JS_DIR.rglob("*.js"))}
    terminate = re.compile(r"""["'`]terminate["'`]""")  # gleich in welchen Anführungszeichen
    assert {name: len(terminate.findall(s)) for name, s in sources.items() if terminate.search(s)} == {"dialogs.js": 1}
    js = sources["dialogs.js"]
    body = js[js.index("function confirmed() {"):]
    assert body.index('post({ type: "terminate"') < body.index("\n}\n")
    code = [line for s in sources.values() for line in s.splitlines()
            if "confirmed" in line and not line.lstrip().startswith("//")]
    assert code == ['  ui.cYes = button("btn term", cb, confirmed);', "function confirmed() {"]
    assert [name for name, s in sources.items() if "cYes" in s] == ["dialogs.js"]
    assert not re.search(r"cYes\s*\.\s*(click|dispatchEvent)\b", js)


@pytest.mark.parametrize("kind, module", [("counters", "settings.js"), ("show_hints", "settings.js"),
                                          ("hide_hint", "footer.js")])
def test_new_messages_are_posted_by_one_module(kind, module):  # Q2: je Nachricht genau eine Stelle der Seite
    word = re.compile(rf"""["'`]{kind}["'`]""")
    sources = {p.relative_to(JS_DIR).as_posix(): p.read_text(encoding="utf-8") for p in sorted(JS_DIR.rglob("*.js"))}
    assert {name: len(word.findall(s)) for name, s in sources.items() if word.search(s)} == {module: 1}


def test_counters_is_posted_only_by_the_step():
    """Erklärung vor polkit (C1, E6: Bedienung, kein Schutz): counters sendet nur stepConfirmed, und nur der Knopf
    „Freigeben“/„Sperren“ im Schritt ruft es auf, nie das Laden der Seite oder der Schalter selbst."""
    js = (JS_DIR / "settings.js").read_text(encoding="utf-8")
    body = js[js.index("function stepConfirmed() {"):]
    assert body.index('post({ type: "counters"') < body.index("\n}\n")
    code = [line.strip() for line in js.splitlines() if "stepConfirmed" in line and not line.lstrip().startswith("//")]
    assert code == ['ui.cntGo = button("btn term", btns, stepConfirmed);', "function stepConfirmed() {"]


TEXT_KEY = re.compile(r"""["'`]((?:settings|counters|hint)\.[a-z0-9_]+)["'`]""")


def test_ui_texts_in_both_languages():
    """C7: Jeder Schlüssel der Einstellungen, der Ergebnisse und der Hinweise, den ein Modul der Seite nennt, steht in
    beiden Sprachen. Die Wörter für counters.<Ergebnis> prüft test_i18n.test_counters_results_have_texts."""
    used = {k for p in JS_DIR.rglob("*.js") for k in TEXT_KEY.findall(p.read_text(encoding="utf-8"))}
    assert {"settings.counters", "settings.release_text", "settings.lock_text", "settings.state_missing_rapl",
            "hint.hide", "hint.igt_noperm_readme", "settings.show_hints"} <= used
    for lang in ("en", "de"):
        texts = json.loads((REPO / "orbitop" / "locale" / f"{lang}.json").read_text(encoding="utf-8"))
        assert used <= set(texts), (lang, sorted(used - set(texts)))


def test_stylesheets_linked_in_order():
    """Die Kaskade hängt an der Reihenfolge: Seite, Prüfseite und Demo binden genau die fünf Stylesheets so ein."""
    for page in (UI / "index.html", CHECK_DIR / "check.html", CHECK_DIR / "demo.html"):
        hrefs = LINK.findall(page.read_text(encoding="utf-8"))
        assert [(page.parent / h).resolve() for h in hrefs] == [UI / "css" / n for n in CSS], page.name


def test_css_files_are_served():  # im Standardmodus nimmt die Engine ein Stylesheet nur mit text/css an
    assert sorted(p.relative_to(UI).as_posix() for p in UI.rglob("*.css")) == sorted("css/" + n for n in CSS)
    for name in CSS:
        assert ui_file("orbitop://ui/css/" + name, str(UI)) == (str(UI / "css" / name), "text/css")
