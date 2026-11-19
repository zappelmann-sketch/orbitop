# orbitop: Umbau vor 0.3.0 (Plan 1) – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der Code von orbitop ist modular (Dateien höchstens etwa 300 Zeilen), ohne dass sich Aussehen oder Verhalten ändern, und die geparkten Punkte aus 0.2.0 sind behoben.

**Architecture:**
- Die Oberfläche lädt als ES-Module ohne Build-Schritt: `index.html` → `main.js`, das die übrigen Module importiert. Die Brücke setzt `window.orbitop` ausdrücklich, denn Python ruft `window.orbitop.receive(...)`.
- Der Kachelbau zieht aus `sampler.py` nach `tiles.py`, das CSS wird nach Bereichen getrennt, große Testdateien nach Themen.
- Die geparkten Punkte betreffen Matrix, Release-Skript, Paketierung und zwei App-Module.

**Tech Stack:** Python ≥ 3.12 (Standardbibliothek plus PyGObject), GTK 4, WebKitGTK 6.0, Vanilla-JS (ES-Module), pytest, kopfloser Chrome, Bash, shellcheck, Docker.

**Spec:** `docs/superpowers/specs/2026-11-19-orbitop-umbau-und-0.3.0-design.md`, Teil A. Sie baut auf der Stufe-2-Spec auf; deren Regeln gelten weiter. Teil B (Security-Runde) führt der Controller parallel zu diesem Plan aus; er berührt keine Datei dieses Plans.

## Global Constraints

### Übernommen (gelten wörtlich weiter)

- Repository `zappelmann-sketch/orbitop`, öffentlich. Python-Paket `orbitop/`, App-ID `io.github.zappelmann_sketch.orbitop`, Lizenz GPL-3.0-or-later.
- Kopf jeder Quelldatei: `SPDX-License-Identifier: GPL-3.0-or-later` und `Copyright © 2026 zappelmann-sketch`, als Kommentar im Stil der Datei. Das gilt auch für jede neue JS-, CSS- und Testdatei.
- **Git:**
  - Identität `zappelmann-sketch` / `235797375+zappelmann-sketch@users.noreply.github.com`.
  - Commit-Nachrichten auf Deutsch (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`), am Ende `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Nie `git add -A`, immer die Dateien der Task nennen.
  - `CLAUDE.md`, `.claude/`, `.mcp.json` und `.superpowers/` werden nie committet.
- **Keine persönlichen Daten** in Code, Tests, Bildern oder Commits. Nur Platzhalter wie `alice`, `/home/u`, `<repo>`, `example.com`. Screenshots nur aus den anonymisierten Demo-Daten (`tests/ui/demo.html`).
- Python ≥ 3.12, nur Standardbibliothek und PyGObject, kein psutil, keine neue Abhängigkeit. Kein npm, kein Bundler, kein Build-Schritt für die Oberfläche.
- Sichtbare Texte nur über `orbitop/locale/{en,de}.json`. Systemdaten nur per `textContent`, nie als HTML. Keine Inline-Stile (die CSP verbietet sie), Farben nur über CSSOM.
- Die CSP der Seite bleibt `default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'none'; base-uri 'none'; form-action 'none'`.
- Seite → Python nur über `parse_message`. Die Seite schickt nie einen Pfad. Die Auslieferung unter `orbitop://ui/` bleibt auf reguläre Dateien bekannten Typs unter `orbitop/ui/` beschränkt (`ui_file` in `orbitop/app.py`).
- `terminate` sendet genau eine Stelle der Seite, und nur der Bestätigungsknopf ruft sie auf (heute `confirmed()` in `app.js`).
- **Eigenlast:** sichtbar ≤ 9 % eines Kerns, ausgeblendet ≤ 3 %, PSS < 275 MB. Die Ausnahme für „alle Spalten“ (Dauermessung bis etwa 9,4 %) bleibt. Das Messverfahren steht im Plan vom 2026-11-17, Abschnitt „Messverfahren“, mit `scripts/measure-load.py`; gestörte Läufe werden verworfen (siehe `CLAUDE.md`).
- `$SCRATCH` = das Scratchpad der Sitzung, je Task `$SCRATCH/task<N>/`. Proben, Live-Läufe, Screenshots und Messungen laufen dort, nie im Repository.
- **Sicherheitsregeln:**
  - Nie einen echten Prozess beenden; die laufende orbitop-Instanz des Users (`/usr/bin/orbitop`) wird nie beendet.
  - Tests und Live-Läufe erreichen nie `/usr/bin/pkexec`; der Wächter in `tests/conftest.py` bleibt.
  - Live-Läufe nur mit `XDG_CONFIG_HOME=$SCRATCH/task<N>/cfg dbus-run-session -- <worktree>/bin/orbitop …`.
  - Auf dem Rechner kein `sudo`, keine Installation von Paketen.
  - Container nur `docker run --rm`, ohne `--privileged`, `--cap-add`, `--network=host`, Eingaben schreibgeschützt.
  - `~/.gnupg` und `~/.local/share/orbitop-release` werden nie angefasst.
- Am Ende jeder Task laufen `pytest -q` und `pytest -q -W error::ResourceWarning -W error::DeprecationWarning`, beide grün, und `shellcheck -x` für jedes geänderte Shell-Skript.
- Gearbeitet wird auf dem Zweig `umbau-0.3.0` im Worktree `.worktrees/umbau-0.3.0`. Kein Push, kein Release in diesem Plan.

### Neu für den Umbau

- **Gleiches Verhalten** (Spec A6, Anti-Ziel „Umbau ändert Aussehen oder Verhalten“):
  - Kein Test wird gelöscht oder abgeschwächt. Beim Aufteilen von Testdateien bleibt die Menge der Test-IDs gleich, bis auf den Pfad der Datei. Belegt wird das mit `pytest --collect-only -q` vorher und nachher, die Namen werden verglichen.
  - Die Chrome-Prüfseite (`tests/test_ui.py`) bleibt grün, ihre Prüfungen bleiben inhaltlich gleich.
  - Screenshots der Demo-Seite (Übersicht, Prozesse, schmal) vor und nach jeder UI-Task sind pixelgleich (`cmp` der PNG-Dateien oder Pixelvergleich). Abweichungen werden erklärt und dem Controller gemeldet.
  - Der Schnappschuss-Vertrag (`tick`-JSON) bleibt Byte für Byte gleich.
- **Module:**
  - Jede neue Datei hat eine Aufgabe und höchstens etwa 300 Zeilen.
  - Abhängigkeiten laufen in eine Richtung, ohne Zyklen. Zustand liegt in einem eigenen Modul (`state.js`), nicht in globalen Variablen.
  - Einziger globaler Name ist `window.orbitop`, gesetzt von der Brücke.
  - JS-Module liegen unter `orbitop/ui/js/`. Einstieg ist `orbitop/ui/js/main.js`, eingebunden mit `<script type="module" src="js/main.js">`.

### Review-Pflicht (Vorgabe des Users, jede Task)

- Code-Review durch einen eigenen Agenten (Opus).
- Security-Audit des Task-Diffs mit den Pflicht-Skills `security-audit` (guidance mode), `cybersecurity-katalog` (passende Einträge) und `ponytail:ponytail-review`.
- Toter Code wird entfernt; der Hauptagent prüft jeden Befund am Code gegen.
- Jedes Review prüft Dateigröße, Aufgabenteilung und Schnittstellen (globale Regel „Modularer, kleiner Code“).

## Review Focus

1. **Ein Modul lädt in WebKitGTK nicht** (CORS oder MIME beim Schema `orbitop://`). Dann bleibt das Fenster leer, während die Chrome-Tests grün sind. Erwartet: Die App zeigt die Übersicht wie vorher. Test: Live-Lauf mit Screenshot in Task 1. Dazu ein pytest-Test: Jede Datei, die `main.js` direkt oder indirekt importiert, liefert `ui_file` mit `text/javascript` aus (Task 1, erweitert in Task 2 und 3).
2. **Python ruft `receive` vor der Auswertung der Module.** Module laufen verzögert, und die erste Nachricht `init` ginge verloren. Erwartet: Die erste Nachricht kommt an. Test in Task 1: `window.orbitop.receive` ist vor `DOMContentLoaded` definiert, eine Nachricht davor wird verarbeitet oder gepuffert. Dazu prüft der Live-Lauf das erste Bild.
3. **Zyklische Importe**, durch die ein Name bei der Auswertung noch `undefined` ist. Erwartet: Es gibt keinen Zyklus. Test `test_ui_modules_have_no_import_cycle` (Task 2): Er liest die `import … from "./…"`-Zeilen aller Module und prüft, dass der Graph zyklenfrei ist und jede Datei ≤ 300 Zeilen hat.
4. **Netzaussetzer und echter Fehler in der Matrix sehen gleich aus.** Erwartet: Ein Aussetzer wird wiederholt, ein Fehler des Pakets bleibt `fail`. Test in Task 8 mit beiden Fällen.
5. **`tiles.py` ändert den Schnappschuss** auf einem anderen Testbaum als dem geprüften. Erwartet: gleiche Bytes. Test in Task 5 über alle vier Testbäume (`intel-laptop`, `amd-desktop`, `arm-board`, `vm`).

## Klärungen gegenüber der Spec (Wahl des Planers)

- **P1 – Ort der Module:** `orbitop/ui/js/`. `chart.js` zieht als Modul dorthin. `ui_file` erlaubt Unterordner schon heute, die Pakete übernehmen `orbitop/ui/` als ganzen Baum. Task 1 prüft das in `packaging/install-tree.sh`.
- **P2 – Chrome-Tests:** `tests/test_ui.py` startet einen HTTP-Server aus der Standardbibliothek (`http.server`), nur auf `127.0.0.1` mit freiem Port, für die Dauer des Tests. Seine Wurzel ist ein temporäres Verzeichnis, das nur `orbitop/ui` und `tests/ui` enthält (Kopie oder Symlink). Aufgerufen wird `http://127.0.0.1:<port>/tests/ui/check.html`. Startoptionen, die Sicherheitsprüfungen von Chrome abschalten, gibt es nicht.
- **P3 – WebKitGTK:** Lädt ein Modul unter `orbitop://` nicht, registriert `shell.py` das Schema über den `WebKitSecurityManager` als CORS-fähig (`register_uri_scheme_as_cors_enabled`) und, falls nötig, als sicher. Mehr nicht. Scheitert auch das, meldet die Task BLOCKED, und der User entscheidet über den Rückfall (Spec A1).
- **P4 – Prüfseite:** `tests/ui/check.js` wird ein Modul, das die App-Module importiert und ihre Exporte prüft. Es wird entlang derselben Module aufgeteilt (`tests/ui/check/*.js`, Einstieg `check.js`).
- **P5 – Testdateien über 400 Zeilen** werden in Task 6 aufgeteilt. Dateien zwischen 300 und 400 Zeilen teilt Plan 2 auf, sobald er ihnen etwas hinzufügt (Spec A5).

---

### Task 1: Die Seite lädt als ES-Module

**Files:**
- Create: `orbitop/ui/js/main.js`, `orbitop/ui/js/chart.js` (aus `orbitop/ui/chart.js`), `orbitop/ui/js/app.js` (aus `orbitop/ui/app.js`, vorerst ungeteilt)
- Modify: `orbitop/ui/index.html`, `tests/ui/check.html`, `tests/ui/demo.html`, `tests/ui/check.js`, `tests/ui/demo.js`, `tests/test_ui.py`, `orbitop/shell.py` (nur wenn P3 nötig), `packaging/install-tree.sh` (nur wenn der Baum `orbitop/ui/js/` sonst fehlt)
- Test: `tests/test_ui.py`, `tests/test_shell.py` oder `tests/test_app.py` (Auslieferung der Module)

**Interfaces:**
- Produces: `orbitop/ui/js/main.js` als einziger Einstieg; `window.orbitop = { receive }` wird dort gesetzt (bis Task 2 aus `app.js` re-exportiert). `chart.js` exportiert seine bisherigen globalen Funktionen als benannte Exporte. `tests/test_ui.py` hat eine Fixture `ui_server` → Basis-URL `http://127.0.0.1:<port>/`.

- [ ] **Step 1: Screenshots vorher.** Demo-Seite in Chrome: Übersicht (`1600,1000`), Prozesse (`#procs`, `1600,1000`), schmal (`1000,800`). Ablage `$SCRATCH/task1/before-*.png`. Der Befehl wie in `CLAUDE.md`, nur über den Server aus P2.
- [ ] **Step 2: Failing Tests.**
  - `test_ui_check_page` und `test_ui_check_page_narrow` laufen über die Fixture `ui_server`, wie in P2.
  - Neu ist `test_module_files_are_served`: Für jede `.js`-Datei unter `orbitop/ui/js/` liefert `ui_file("orbitop://ui/js/<name>", UI_DIR)` den Typ `text/javascript`.
  - Neu ist `test_index_loads_only_the_module_entry`: `index.html` enthält genau ein `<script`, nämlich `type="module" src="js/main.js"`.
  - In der Prüfseite prüft `check.js`, dass `typeof window.orbitop.receive === "function"` vor `DOMContentLoaded` gilt.
- [ ] **Step 3: Tests laufen rot.** `pytest tests/test_ui.py -v`, erwartet FAIL (Datei `js/main.js` fehlt).
- [ ] **Step 4: Umstellen.**
  - `chart.js` und `app.js` ziehen nach `orbitop/ui/js/`, als Module mit `import`/`export`. `main.js` importiert sie und setzt `window.orbitop`.
  - `index.html`, `check.html` und `demo.html` laden nur noch das jeweilige Modul.
  - Der Test `test_terminate_is_posted_only_by_the_confirm_button` liest künftig `orbitop/ui/js/app.js`.
- [ ] **Step 5: Tests grün.** `pytest tests/test_ui.py tests/test_app.py -v`, erwartet PASS.
- [ ] **Step 6: Live-Lauf in WebKitGTK.**
  - Befehl: `cd $SCRATCH/task1 && XDG_CONFIG_HOME=$SCRATCH/task1/cfg ORBITOP_SNAPSHOT=$SCRATCH/task1/live.png dbus-run-session -- timeout 12 <worktree>/bin/orbitop`, dasselbe mit `ORBITOP_TAB=procs`.
  - Erwartet: zwei Bilder mit gefüllter Übersicht bzw. Prozessliste, keine Fehlermeldung im Protokoll.
  - Bleibt die Seite leer, folgt P3, danach der Live-Lauf erneut. Scheitert er wieder, wird BLOCKED gemeldet.
- [ ] **Step 7: Screenshots nachher** wie in Step 1, `cmp` gegen vorher. Erwartet: gleich.
- [ ] **Step 8: Volle Tests und Commit.** Beide pytest-Läufe. Dann `git add` mit den geänderten Dateien und `git rm` der alten Pfade; Nachricht `refactor: Oberfläche lädt als ES-Module`.

### Task 2: `app.js` in Module – Grundlagen, Kacheln, Dialoge

**Files:**
- Create in `orbitop/ui/js/`: `state.js` (bisher `state`, `ui`, `tiles`, `procRows`, `formats`), `format.js` (Texte und Zahlen: `text`, `fill`, `number`, `fmt`, `show`, `shortName`, `byteStep`, `BYTES`, `DIGITS`), `dom.js` (`el`, `label`, `setText`, `pairs`, `button`, `svg`, `pathEl`, `fillInto`), `bridge.js` (`post`, `receive`, Verteilung der Nachrichten), `page.js` (`build`, `hdrInfo`, `showTab`, `select`, `renderOverview`), `strip.js`, `tiles.js` (Kacheln samt `AREA`, `SECOND`, `GPU_SHADES`, `EXTRA`, `CAPS`, `POINTS`), `footer.js`, `dialogs.js`
- Modify: `orbitop/ui/js/app.js` (verliert diese Teile; der Rest sind die Prozesse für Task 3), `orbitop/ui/js/main.js`, `tests/ui/check.js` → `tests/ui/check/*.js`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: Task 1 (`main.js`, Fixture `ui_server`).
- Produces: die genannten Module mit benannten Exporten. `bridge.js` exportiert `post(message)` und `receive(message)` und setzt `window.orbitop`. `dialogs.js` enthält die einzige `terminate`-Stelle (`confirmed`). Die Namen der Funktionen bleiben, wie sie sind.

- [ ] **Step 1: Screenshots vorher** wie in Task 1 Step 1, Ablage `$SCRATCH/task2/`.
- [ ] **Step 2: Failing Test** `test_ui_modules_have_no_import_cycle` in `tests/test_ui.py`. Er liest alle `orbitop/ui/js/*.js` (später auch Unterordner). Pro Datei sammelt er die relativen Importe `import … from "./…"`. Er prüft dreierlei:
  - Der Graph ist zyklenfrei.
  - Jede importierte Datei existiert.
  - Jede Datei hat ≤ 300 Zeilen. Ausnahme ist bis Task 3 nur `app.js`, mit Kommentar im Test, den Task 3 entfernt.

  `test_terminate_is_posted_only_by_the_confirm_button` liest `dialogs.js`.
- [ ] **Step 3: Rot.** `pytest tests/test_ui.py -v`, erwartet FAIL.
- [ ] **Step 4: Aufteilen.**
  - Code wird verschoben, nicht umgeschrieben. Geteilter Zustand kommt nur aus `state.js`.
  - `check.js` wird entlang derselben Module aufgeteilt, die Prüfungen bleiben gleich.
- [ ] **Step 5: Grün,** beide pytest-Läufe.
- [ ] **Step 6: Live-Lauf und Screenshots nachher** wie in Task 1 Step 6 und 7. Erwartet: pixelgleich.
- [ ] **Step 7: Commit** `refactor: Grundlagen, Kacheln und Dialoge als eigene Module`.

### Task 3: `app.js` in Module – Prozess-Reiter

**Files:**
- Create in `orbitop/ui/js/procs/`:
  - `columns.js`: Spalten und Formate, also `COLS`, `KIND`, `ICONS`, `SEVERITY`, `MIN_W`, `FILTERS`, `RESULTS`, `withUnit`, `memShare`, `cpuTime`, `duration`, `clock`, `makeBadge`, `setBadge`.
  - `table.js`: `buildProcs`, `pressFilters`, `sortBy`, `sortHeads`.
  - `layout.js`: Abschnitt „Spalten: Layout …“.
  - `drag.js`: Abschnitt „Ziehen“.
  - `menu.js`: Abschnitt „Spaltenmenü“ bis `menuKey`.
  - `rows.js`: `pickRow` bis `makePad`.
  - `detail.js`: `ioText`, `renderDetail`, `renderButtons`.
- Delete: `orbitop/ui/js/app.js`.
- Modify: `main.js`, `bridge.js` (Verteilung an die Prozess-Module), `tests/ui/check/*.js`.
- Test: `tests/test_ui.py`. Die Ausnahme für `app.js` im Größentest entfällt, der Test prüft auch `js/procs/`.

**Interfaces:**
- Consumes: Task 2 (`state.js`, `format.js`, `dom.js`, `bridge.js`, `dialogs.js`).
- Produces: `procs/table.js` exportiert `buildProcs`, `procs/rows.js` exportiert `renderProcs`. Die Brücke ruft genau diese beiden.

- [ ] **Step 1: Screenshots vorher** (Prozesse, Prozesse schmal, dazu ein Bild mit offenem Spaltenmenü über `check.html#…`, falls die Prüfseite das schon zeigt), Ablage `$SCRATCH/task3/`.
- [ ] **Step 2: Rot.** Größentest ohne Ausnahme für `app.js`, erwartet FAIL.
- [ ] **Step 3: Aufteilen** wie Task 2 Step 4. Es gibt keine Datei über 300 Zeilen. Ist `buildProcs` allein zu groß, wird es in benannte Teilfunktionen in derselben Datei zerlegt, ohne Verhalten zu ändern.
- [ ] **Step 4: Grün,** beide pytest-Läufe.
- [ ] **Step 5: Live-Lauf mit `ORBITOP_TAB=procs` und Screenshots nachher.** Erwartet: pixelgleich.
- [ ] **Step 6: Commit** `refactor: Prozess-Reiter als eigene Module`.

### Task 4: `style.css` nach Bereichen

**Files:**
- Create in `orbitop/ui/css/`, nach den bestehenden Abschnitten:
  - `base.css`: Kopf bis vor „Kopfzeile“, also Farben, Schriften, Grundregeln.
  - `header.css`: Kopfzeile, Info-Knopf, Lastzeile.
  - `tiles.css`: Kacheln, Diagramme, Threads, Geräte, Fußzeile.
  - `procs.css`: Prozesse bis Spaltenmenü.
  - `dialogs.css`: Dialoge und Schalter.
- Delete: `orbitop/ui/style.css`.
- Modify: `orbitop/ui/index.html`, `tests/ui/check.html`, `tests/ui/demo.html` (fünf `<link>` in dieser Reihenfolge).
- Test: `tests/test_ui.py`.

**Interfaces:**
- Produces: `orbitop/ui/css/*.css`. Die Reihenfolge der `<link>` ist gleich der Reihenfolge der Regeln im alten `style.css`.

- [ ] **Step 1: Screenshots vorher** (Übersicht, Prozesse, schmal), Ablage `$SCRATCH/task4/`.
- [ ] **Step 2: Failing Tests:**
  - `test_stylesheets_linked_in_order`: `index.html`, `check.html` und `demo.html` binden genau `css/base.css`, `css/header.css`, `css/tiles.css`, `css/procs.css` und `css/dialogs.css` in dieser Reihenfolge ein.
  - `test_css_files_are_served`: `text/css` über `ui_file`.
- [ ] **Step 3: Rot, dann Aufteilen, dann Grün.** Prüfschritt vor dem Commit: Die fünf Dateien in Link-Reihenfolge, ohne ihre Kopfkommentare, ergeben Zeile für Zeile den Inhalt des alten `style.css` nach dessen Kopf (`git show HEAD:orbitop/ui/style.css`, `diff`). Erwartet: keine Abweichung außer Leerzeilen an den Schnittstellen.
- [ ] **Step 4: Live-Lauf und Screenshots nachher.** Erwartet: pixelgleich.
- [ ] **Step 5: Commit** `refactor: Stylesheet nach Bereichen aufgeteilt`.

### Task 5: Kachelbau in `tiles.py`

**Files:**
- Create: `orbitop/tiles.py`.
- Modify: `orbitop/sampler.py` (nur noch Lesen, Raten, Verläufe, Schnappschuss), `tests/test_sampler.py` → zusätzlich `tests/test_tiles.py`.
- Test: `tests/test_tiles.py`, `tests/test_sampler.py`, neu `tests/test_snapshot_bytes.py`.

**Interfaces:**
- Produces: In `orbitop/tiles.py` stehen die Formathilfen (`num`, `opt`, `kv`, `kl`, `tk`, `tl`, `pct`, `nice`, `seg`, `unique`, `clean`) als modulweite Funktionen ohne Unterstrich. Dazu `tile(kind, id, name, main, aside, seg, series, kv, warn, devices=None, threads=None) -> dict` und je Kachel eine Funktion `cpu_tile(...)`, `gpu_tile(...)`, `mem_tile`, `power_tile`, `temp_tile`, `fan_tile`, `net_tile`, `disk_tile`. Sie bekommen Werte und Verläufe als Argumente und lesen nie das Dateisystem. `Sampler._tiles()` ruft sie auf.

- [ ] **Step 1: Bytes festhalten.** Ein Hilfsskript in `$SCRATCH/task5/` schreibt für jeden der vier Testbäume nach einer festen Tick-Folge den Schnappschuss. Grundlage ist der Stand vor der Task, mit `clock`, `statvfs` und `tools` wie in den bestehenden Sampler-Tests. Die Ausgabe ist `snapshot_json` als Datei unter `tests/fixtures/snapshots/<baum>.json`.
- [ ] **Step 2: Test** `test_snapshot_bytes_unchanged[<baum>]` in `tests/test_snapshot_bytes.py`. Er erzeugt dieselbe Folge und vergleicht die Bytes mit der Datei. Läuft vor dem Umbau grün; der Wächter für den Umbau.
- [ ] **Step 3: Umbau,** die Test-IDs von `test_sampler.py` vorher sichern (`pytest --collect-only -q`).
- [ ] **Step 4: Tests aufteilen.** Tests, die nur den Kachelbau betreffen, ziehen nach `test_tiles.py`. Keine Datei bleibt über 400 Zeilen, möglichst unter 300. Die Test-IDs vergleichen, wie unter „Neu für den Umbau“ beschrieben.
- [ ] **Step 5: Grün,** beide pytest-Läufe. `sampler.py` ≤ 300 Zeilen, `tiles.py` ≤ 300 Zeilen.
- [ ] **Step 6: Commit** `refactor: Kachelbau in tiles.py`.

### Task 6: Große Testdateien nach Themen

**Files:**
- Modify/Create: `tests/test_app.py` (613 Zeilen), `tests/test_shell.py` (539), `tests/test_procs.py` (480), `tests/test_sensors.py` (431), `tests/test_actions.py` (405). Jede wird nach den Themen ihrer Tests geteilt (Dateinamen `tests/test_<modul>_<thema>.py`). Gemeinsame Hilfen kommen in ein Hilfsmodul `tests/<modul>_helpers.py` oder nach `conftest.py`, wenn mehrere Dateien sie brauchen.
- Test: alle betroffenen.

**Interfaces:**
- Produces: nur Testdateien; keine Änderung am Produktcode.

- [ ] **Step 1:** `pytest --collect-only -q > $SCRATCH/task6/before.txt`.
- [ ] **Step 2: Aufteilen.** Jede neue Datei hat ≤ 300 Zeilen, keine über 400.
- [ ] **Step 3:** `pytest --collect-only -q > $SCRATCH/task6/after.txt`. Der Vergleich ohne Dateipfad (`::`-Teil) ergibt dieselbe Menge. Beide pytest-Läufe grün.
- [ ] **Step 4: Commit** `test: große Testdateien nach Themen aufgeteilt`.

### Task 7: Eigenlast nach dem Umbau und ausgeblendet

**Files:**
- Modify: `docs/superpowers/specs/2026-11-19-orbitop-umbau-und-0.3.0-design.md` (neuer Abschnitt „Messung Eigenlast (Umbau)“). Code nur, wenn die Ursache in orbitop liegt.
- Test: wie die Änderung es verlangt.

**Interfaces:**
- Consumes: Tasks 1–6.

- [ ] **Step 1: Messen.**
  - Vier Lagen: ausgeblendet, Übersicht, Prozesse Standard, Prozesse alle Spalten.
  - Je Lage zwei Läufe, im Wechsel zwischen diesem Zweig und `main` (Stand 0.2.0; Checkout `main` als zweiter Worktree nur lesend, oder `git worktree add` unter `$SCRATCH`).
  - Verfahren wie unter „Global Constraints“.
  - Erwartet: Der Zweig liegt im Rahmen der Streuung gleich auf mit `main`.
- [ ] **Step 2: Ausgeblendet untersuchen** (Spec A7.1). Am 2026-11-19 lag `main` bei 3,08 %; orbitop ≈ 1,9 %, `intel_gpu_top` ≈ 1,2 %. Am 2026-11-17 waren es 1,78 % und 1,03 %. Zu klären:
  - Aufteilung je Thread im orbitop-Prozess (`orbitop-worker`, `orbitop-procs`, GTK-Hauptthread) aus `/proc/<pid>/task/*/stat`;
  - Version von `intel_gpu_top` und Kernel gegenüber 2026-11-17 (`/var/log/apt/history.log` lesen ist erlaubt);
  - ein Lauf ohne `intel_gpu_top`, mit `XDG_CONFIG_HOME` wie immer und einem `PATH` ohne das Werkzeug, falls `gpu_tools.py` den `PATH` nutzt; sonst über die vorhandene Test-Naht.
- [ ] **Step 3: Ergebnis.**
  - Liegt die Ursache in orbitop, folgt eine Änderung mit Test und neuer Messung.
  - Liegt sie in `intel_gpu_top` selbst oder im System, ändert die Task nichts am Code und meldet DONE_WITH_CONCERNS mit der Messtabelle und den Möglichkeiten. Der Controller legt die Tabelle dem User vor (Spec A7.1).
- [ ] **Step 4: Dokumentieren** im Aufbau der Tabelle „Messung Eigenlast (2026-11-17)“ der Spec vom 2026-11-17 (CPU % eines Kerns, PSS in Klammern). Commit `docs: Messung Eigenlast nach dem Umbau`.

### Task 8: Matrix wiederholt Netzaussetzer der Spiegel

**Files:**
- Modify: `scripts/matrix/lib.sh` (Einstufung), `scripts/matrix/inside.sh`, je nach Bauweise `scripts/matrix/{apt,dnf,zypper,pacman}.sh`.
- Test: `tests/test_matrix_lib.py`.

**Interfaces:**
- Produces:
  - Eine Funktion in `lib.sh`, die einen Schritt des Paketmanagers bei einem Netzaussetzer bis zu dreimal wiederholt. Netzaussetzer sind Meldungen, die auf `Curl error (6|7|28|35|52|56)`, `Connection reset by peer`, `Could not resolve host`, `Temporary failure in name resolution` oder `Operation timed out` passen, mit Pause.
  - Erst wenn der letzte Versuch scheitert, gilt der Schritt als `fail`.
  - Alle anderen `NOISE`-Treffer bleiben sofort `fail`.

- [ ] **Step 1: Failing Tests** in `tests/test_matrix_lib.py`, mit einem Ersatz-Paketmanager (Shell-Funktion), der seine Ausgabe aus einer Datei nimmt:
  - `test_network_hiccup_is_retried_then_passes`: erster Lauf mit `Curl error (56): … Connection reset by peer`, zweiter sauber; erwartet `pass` und zwei Aufrufe.
  - `test_network_hiccup_three_times_fails`: erwartet `fail`.
  - `test_package_error_is_never_retried`: zum Beispiel `Error: GPG check FAILED`; erwartet sofort `fail` und ein Aufruf.
  - `test_tampered_index_still_fails`: Der Manipulationstest der Matrix bleibt `fail`-gewertet, er wird nie wiederholt.
- [ ] **Step 2: Rot, Umsetzung, Grün.** `shellcheck -x` für alle geänderten Skripte.
- [ ] **Step 3: Eine echte Matrix** über die Images aus `scripts/container-common.sh`. Die Seite stammt aus einem Wegwerfbau wie im Probelauf von 0.2.0 (Wegwerfschlüssel in `$SCRATCH/task8/gnupg`, `build-packages.sh` und `build-site.sh` in `$SCRATCH/task8/`). Erwartet: alle `pass` bzw. `pass install`. Ergebnis in den Bericht, nicht in `docs/distro-check.md`.
- [ ] **Step 4: Commit** `fix: Matrix wiederholt Netzaussetzer der Spiegel`.

### Task 9: Release-Skript: Fetch-Adresse, fester Commit, Stubs

**Files:**
- Modify: `scripts/release/checks.sh` (`check_origin`), `scripts/container-common.sh` (`tracked_files`), `scripts/release.sh`, `scripts/release/build.sh` (Übergabe des festen Commits), `tests/release_stub.py`, `tests/test_release_checks.py`, `tests/test_release_script.py`, `docs/release.md`.

**Interfaces:**
- Produces:
  - `check_origin` prüft mit derselben Regel sowohl `git remote get-url --all --push origin` als auch `git remote get-url --all origin`.
  - `tracked_files` nimmt den Commit aus `ORBITOP_REV` und fällt sonst auf `HEAD` zurück. `release.sh` setzt `ORBITOP_REV=$pinned` für Bau, Seite und Matrix.

- [ ] **Step 1: Failing Tests.**
  - `test_check_origin` bekommt Fälle: Fetch-Adresse ein Spiegel, Push-Adresse GitHub → Abbruch beim echten Lauf, Warnung beim Trockenlauf. Der bisherige Fall „pushurl GitHub, url Spiegel erlaubt“ entfällt.
  - `test_builds_use_the_pinned_commit`: HEAD wandert während des Laufs (Stub-Commit nach Schritt 1). Die Bauten bekommen trotzdem den Baum von `$pinned`.
  - Im gh-Stub: `--notes-from-tag` zusammen mit `--repo` oder `-R` wird in jeder Reihenfolge und auch als `--notes-from-tag=true` abgelehnt; Test mit allen drei Formen.
  - `test_dry_run_checks_the_pages_identity`: Der Trockenlauf prüft die Identität im gh-pages-Worktree wie der echte Lauf.
  - `release_stub.run()` setzt `GIT_AUTHOR_*`/`GIT_COMMITTER_*` aus der Shell nicht durch. Test: Mit gesetzten Fremdwerten ist die Identität weiter die noreply-Adresse.
- [ ] **Step 2: Rot, Umsetzung, Grün,** `shellcheck -x`.
- [ ] **Step 3: Externe Aufrufe gefahrlos prüfen** (Spec A7.4).
  - Für jeden Aufruf von `gh`, `curl`, `git` und `docker` in `scripts/release*` und `scripts/matrix` wird geprüft:
    - **lesende Befehle:** echt ausführen, ohne dass etwas verändert wird;
    - **`gh release create`:** wie am 2026-11-19 mit einem nicht vorhandenen Tag und `--verify-tag`; erwartet ist der Abbruch an der Tag-Prüfung;
    - **sonst:** `--help` lesen und darin die verwendeten Optionen finden.
  - Ergebnis in `docs/release.md` als „Probe on <Datum>“, mit Version der Werkzeuge. Nie ein Aufruf, der bei GitHub etwas anlegt, ändert oder löscht.
- [ ] **Step 4: Commit** `fix: Release prüft Fetch-Adresse und baut den festen Commit`.

### Task 10: Kleinigkeiten in der Paketierung

**Files:**
- Modify: `packaging/container-prologue.sh`, `tests/test_rpm_same.py`, `tests/test_packaging_arch.py`, `tests/test_packaging_debian.py` (K3-Wächter), `tests/test_packaging_rpm.py` (K3-Wächter), `packaging/site/apt-inside.sh` und `packaging/site/check-apt-index.py` (nur wenn Step 4 es erlaubt), `docs/release.md`.

- [ ] **Step 1: Prolog.** `container-prologue.sh` prüft zuerst, ob es als root in einem Wegwerf-Container läuft, und liest erst dann den Schlüssel von stdin in eine temporäre Datei. Außerhalb eines Containers bleibt keine Datei zurück. Test: Aufruf außerhalb eines Containers (als normaler Benutzer) → Abbruch, kein neues `tmp.*` in `$TMPDIR`. Der Kopfkommentar beschreibt die Reihenfolge richtig.
- [ ] **Step 2: Tests schärfen.**
  - Der Arch-Test der vertrauenswürdigen Datei prüft das gebaute Artefakt (`orbitop-trusted` im Paket aus einem Testbau oder aus dem Ergebnis von `build-inside.sh` mit Docker-Ersatz) statt des Skripttexts.
  - Die K3-Wächter erkennen auch Alternativen (`foo | orbitop-apt-source`, `orbitop-release or …`) und Versionsangaben. Die Fälle werden als Parameter getestet.
  - Der Kommentar in `tests/test_rpm_same.py:45` beschreibt den Fall richtig (gleiche unsignierte Bytes).
- [ ] **Step 3: Rot, Umsetzung, Grün.**
- [ ] **Step 4: apt-`Release` nur mit SHA256 und SHA512.**
  - Mit `APT::FTPArchive::MD5 "false"` und `APT::FTPArchive::SHA1 "false"` (apt-ftparchive(1)) prüfen, ob apt in allen apt-Images der Matrix die Quelle annimmt.
  - Erst wenn das so ist: umstellen und `check-apt-index.py` auf die beiden Hashes beschränken. Danach Matrix wie in Task 8 Step 3.
  - Sonst bleibt es, wie es ist, mit einer Zeile Begründung in `docs/release.md`.
- [ ] **Step 5: Commit** `fix: Kleinigkeiten in Paketierung und Tests`.

### Task 11: Kleinigkeiten in der App

**Files:**
- Modify: `orbitop/userfile.py`, `orbitop/autostart.py`, `orbitop/layout.py`.
- Test: `tests/test_userfile.py`, `tests/test_autostart.py`, `tests/test_layout.py`.

**Interfaces:**
- Produces:
  - `userfile.config_home(env) -> str | None` hat eine klare Regel: `XDG_CONFIG_HOME`, falls absolut und nicht leer; sonst `$HOME/.config`, falls `HOME` absolut und nicht leer; sonst `None`. Beide Werte kommen aus `env`, nie gemischt mit `os.environ`.
  - `write_atomic` legt fehlende Verzeichnisebenen alle mit 0700 an.
  - Schreibfehler melden `autostart` und `layout` je Art einmal je Programmlauf auf stderr, mit Fehlerart, aber ohne Pfad unter dem Home und ohne Benutzernamen. Das Ergebnis an die Seite bleibt wie heute.

- [ ] **Step 1: Failing Tests:**
  - `test_config_home_empty_home_is_none`;
  - `test_config_home_never_reads_os_environ` (Monkeypatch von `os.environ` mit anderem `HOME`);
  - `test_write_atomic_creates_all_levels_0700`;
  - `test_autostart_write_error_is_reported_once` (capsys, zwei Fehlschläge → eine Zeile);
  - `test_layout_write_error_is_reported_once`.
- [ ] **Step 2: Rot, Umsetzung, Grün.**
- [ ] **Step 3: Commit** `fix: klare Regeln für Konfigordner und gemeldete Schreibfehler`.

---

## Nach dem letzten Task

- Schlussprüfung dieses Plans durch ein Review auf Opus über den ganzen Bereich ab `9485b82`, eine Fix-Welle bei Bedarf, dann die Nachprüfung.
- Plan 2 (Teil C) entsteht erst danach, aus dem Dokument der Security-Runde und den Entscheidungen des Users dazu. Er setzt auf demselben Zweig fort.
