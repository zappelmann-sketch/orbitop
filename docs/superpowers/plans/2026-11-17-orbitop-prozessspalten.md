# orbitop Prozess-Spalten, README und Release v0.1.0 – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der Prozess-Reiter zeigt die `top`-Spalten, lässt sich per Maus und Tastatur einrichten (Spalten ein- und ausblenden, verbreitern, umordnen, Trenner zur Detailansicht), behält das Layout über einen Neustart, und orbitop bekommt ein für mehrere Distributionen geprüftes Setup, zweisprachige README und das Release v0.1.0.

**Architecture:** Die neuen Felder kommen aus der schon gelesenen `stat`-Zeile, nur SHR liest `statm`, und das nur bei sichtbarem Prozess-Reiter. Ein neues Modul `orbitop/layout.py` besitzt die Spalten-ids, prüft die Layout-Nachricht der Seite und die Datei `layout.json` und schreibt sie atomar; die Hülle reicht das Layout in `init` an die Seite. Die Seite führt eine Reihenfolge aller Spalten, die Menge der ausgeblendeten und die Breiten, zeichnet daraus Kopf, `colgroup` und Zellen und meldet Änderungen gedrosselt über die Schleuse.

**Tech Stack:** Python ≥ 3.12 (Standardbibliothek plus PyGObject), GTK 4, WebKitGTK 6.0, Vanilla-JS unter `orbitop://ui/`, pytest, kopfloser Chrome (`tests/ui/check.html`), Bash, shellcheck, Docker (nur Task 7), `gh`.

**Spec:** `docs/superpowers/specs/2026-11-17-orbitop-prozessspalten-readme-release-design.md` (maßgeblich). Sie baut auf `docs/superpowers/specs/2026-11-16-orbitop-design.md` auf; deren Regeln gelten weiter.

## Global Constraints

### Aus Stufe 1 übernommen (gelten wörtlich weiter)

- Projektordner `<repo>` = Repository `zappelmann-sketch/orbitop` (privat). Python-Paket `orbitop/`, Anwendungs-ID `io.github.zappelmann_sketch.orbitop`.
- Lizenz GPL-3.0-or-later. Kopf jeder Quelldatei: `# SPDX-License-Identifier: GPL-3.0-or-later` und `# Copyright © 2026 zappelmann-sketch` (in JS und CSS als Kommentar).
- Git-Identität nur im Repository setzen: `user.name zappelmann-sketch`, `user.email 235797375+zappelmann-sketch@users.noreply.github.com`. **Nie** eine private Mail-Adresse. Jede Commit-Nachricht endet mit `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Code muss unter Python 3.12 laufen, also keine Sprachmittel ab 3.13. **Kein psutil**, keine Pakete außer `python3-gi`, `gir1.2-gtk-4.0` und `gir1.2-webkit-6.0`. Optional sind `intel-gpu-tools` und `nvidia-smi`.
- KI-Anweisungen und -Einstellungen (`CLAUDE.md`, `CLAUDE.local.md`, `.claude/`, `.mcp.json`) stehen in `.gitignore` und werden nie committet (Vorgabe des Users).
- Kein Netzwerkzugriff, kein Port, die WebView lädt nur Dateien unter `orbitop/ui/`.
- Alle sichtbaren Texte stammen aus `orbitop/locale/{en,de}.json`. Ausnahme ist der Markenname `ORBITOP`. Die deutschen Texte werden wörtlich aus den Entwürfen übernommen.
- Taktung: System-Kacheln alle 1 s mit 300 Punkten (5 min). Prozesse alle 2 s, 150 Punkte Verlauf, 30 Punkte Mini-Verlauf. Prozesse werden auch bei ausgeblendetem Fenster erhoben.
- Einstufung: `kernel_hang` ab Zustand D > 10 s. Dauerlast ab ≥ 90 % eines Kerns über ≥ 120 s bei ≤ 1 freiwilligen Kontextwechsel pro Sekunde, und, wenn die E/A lesbar ist, ohne E/A-Bytes.
- Beenden: Vorher Rückfrage. PID und Startzeit werden unmittelbar vor dem Signal geprüft. 5 s nach SIGTERM wird nachgesehen, ob der Prozess noch lebt. Fremde Prozesse nur über `pkexec`.
- Eigenlast insgesamt (Programm, alle WebKit-Kindprozesse und Hilfsprogramme): höchstens 9 % eines Kerns bei sichtbarem Fenster, höchstens 3 % ausgeblendet, PSS unter 275 MB (vom User am 2026-11-17 angehoben; ursprünglich 5 %, 1,5 %, 250 MB).
- Farben, Schriften (Orbitron, Oxanium) und Stilregeln exakt laut Spec-Abschnitt „Aussehen“. Immer dunkel.
- Screenshots und Wegwerfdateien gehören ins Scratchpad `$SCRATCH`. Jeden aussagekräftigen Screenshot dem User mit `code -r <pfad>` öffnen (globale Regel des Users).
- Rate = Zählerdifferenz geteilt durch tatsächliches dt. Bei dt ≤ 0, dt > 5 s oder einem kleiner gewordenen Zähler ist der Punkt `None`, also eine Lücke im Diagramm.

### Ergänzt für diese Runde

- `$SCRATCH` = das Scratchpad der Sitzung, je Task `$SCRATCH/task<N>/`. Probe-Skripte, Live-Läufe und Messungen laufen mit diesem Verzeichnis als cwd, nie im Repository.
- Paketnamen: Die Liste oben nennt die Debian-Namen. Die Entsprechungen je Distribution stehen ab Task 6 in `orbitop/app.py` `PACKAGES`. Ein Test hält sie gleich mit `setup-privileges.sh`.
- Neue sichtbare Texte immer in beiden Locale-Dateien. Deutsche Texte aus der Spec übernehmen, wo sie einen nennt. Systemdaten (Prozessnamen, Argumente, Benutzer) nie als HTML einsetzen, nur über `textContent`.
- **Sicherheitsregeln (jede Task):**
  - Nie einen echten Prozess beenden. Ausnahme ist nur die selbst gestartete Mess- oder Probe-Instanz, und die über ihre eigene PID.
  - Tests und Live-Läufe erreichen nie `/usr/bin/pkexec`. Der Autouse-Wächter in `tests/conftest.py` bleibt.
  - `setup-privileges.sh` läuft auf dem Rechner nur mit `--dry-run`, nie mit `sudo` oder als root.
  - Live-Läufe der App starten mit `XDG_CONFIG_HOME=$SCRATCH/task<N>/cfg…` in eigener D-Bus-Sitzung, nie gegen die echte `~/.config/orbitop/layout.json`: `dbus-run-session -- [timeout 12] <repo>/bin/orbitop`. Grund: Die orbitop-Instanz des Users läuft (Autostart). Ein Start in derselben Sitzung reicht nur an sie weiter.
  - Die laufende Instanz des Users wird nie beendet.
- **Container-Ausnahme (Spec, vom User am 2026-11-17 erlaubt):** `setup-privileges.sh` darf echt als root laufen, aber **nur** in wegwerfbaren Containern:
  - `docker run --rm`
  - ohne `--allow-*`-Optionen
  - ohne Zugriff auf den Rechner außer einer schreibgeschützten Kopie des Repositorys (`-v <repo>:/src:ro`), ohne `--privileged`, ohne weitere Mounts
  - Auf dem echten Rechner gilt weiter: nur `--dry-run`.
- Das Repository bleibt privat. Nie `gh repo edit --visibility` oder Ähnliches. Die README ist trotzdem für die öffentliche Nutzung geschrieben.
- Das Release (Task 9) entsteht erst nach der Schlussprüfung des Controllers: Review des ganzen Zweigs, Security-Audit mit Fix-Welle, Lastmessung und Merge in `main`.
- **Budget gilt für beide Fälle** (Spec „Eigenlast“): für die Standardauswahl der Spalten und für alle eingeblendeten Spalten.
- **Messverfahren** (Task 3, 4 kurz, Task 5 vollständig):
  1. Instanz starten wie unter „Sicherheitsregeln“, für den Prozess-Reiter zusätzlich `ORBITOP_SNAPSHOT=$S/<lage>.png ORBITOP_TAB=procs`.
  2. Mess-PID holen: `pgrep -P <pid von dbus-run-session> -f bin/orbitop`.
  3. Einmal `python3 <repo>/scripts/measure-load.py --pid <pid> --seconds 60 >/dev/null` zum Aufwärmen, dann dieselbe Messung zählen.
  4. Danach `kill -TERM <pid>`.
  5. Grenzen: ausgeblendet `cpu_pct_of_one_core ≤ 3.0`, sichtbar `≤ 9.0`, `pss_mb < 275`.
  6. „Alle Spalten“ heißt: `$S/cfg-all/orbitop/layout.json` mit `{"order": COLUMNS, "hidden": [], "widths": {}, "split": 0.6078}`, geschrieben über `orbitop.layout`.
- Am Ende jeder Task: `pytest -q` und `pytest -q -W error::ResourceWarning -W error::DeprecationWarning`, beide grün.
- Commit-Nachrichten auf Deutsch (`feat:`, `fix:`, `test:`, `docs:`, `perf:`, `chore:`), Abschluss `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`. Nie `git add -A` (CLAUDE.md liegt lokal), immer die Dateien der Task nennen.

### Review-Pflicht (Vorgabe des Users, gilt für jede Task)

Jede Task gilt erst als fertig, wenn alle vier Punkte erledigt sind:

1. **Code-Review** durch einen eigenen Agenten: Erfüllt die Task die Spec, ist der Code korrekt, sauber und nachvollziehbar?
2. **Security-Audit** des Task-Diffs mit diesen Schwerpunkten:
   - Rechtegrenzen: pkexec, killhelper, setcap, tmpfiles, sudo-Skripte
   - Eingaben aus der WebView: Jede Nachricht wird auf Typ und Wertebereich geprüft
   - Navigation und Dateizugriffe der WebView
   - Symlinks und Pfade aus `/proc` und `/sys`, Shell-Quoting
   - Aufrufe externer Programme, nur mit Argumentlisten und nie mit `shell=True`
   - Daten aus dem System, die in HTML landen: Prozessnamen und Befehlszeilen immer als Text einsetzen, nie als HTML
3. **Toter Code:** Ungenutzte Funktionen, Parameter, Importe, Dateien, Schlüssel und auskommentierter Code werden entfernt.
4. **Gegenprüfung durch den Hauptagenten:** Jeder Befund wird am Code verifiziert, bevor er umgesetzt oder begründet abgelehnt wird. Gefundene Schwachstellen werden sofort behoben, nicht später.

**Pflicht-Skills in jedem Task-Review (Vorgabe des Users):** Der Prüfer lädt sie über das Skill-Werkzeug und nennt sie im Bericht.
- `security-audit` im Modus für gezielte Prüfungen (guidance mode), auf den Task-Diff
- `cybersecurity-katalog` mit den 1–3 passenden Katalogeinträgen, sobald ein Spezialthema berührt ist (Root-Skripte, Capabilities, pkexec/polkit, WebView, Subprozesse)
- `ponytail:ponytail-review` für toten und überflüssigen Code

Für die Schlussprüfung: `security-audit` im vollen Modus über den ganzen Zweig, mit Berichtsordner außerhalb des Repositorys.

Diese Prüfungen veranlasst der Controller mit eigenen Prüfern, nicht der Implementer. Vor Task 9 folgen ein **Security-Audit des gesamten Zweigs** (Skill `security-audit`) und ein abschließendes Code-Review.

### Schnappschuss-Vertrag (Python ↔ Oberfläche)

Stand Stufe 1, wörtlich:

Python → Seite: `window.orbitop.receive(msg)`.

```text
init  {"type":"init","lang":"de|en","texts":{key:str},"version":"0.1.0"}
tick  {"type":"tick","tiles":[Tile],"missing":[kind],"hints":[textkey],
       "top":{"cpu":[ProcBrief],"mem":ProcBrief|null},
       "procs":[ProcRow]|null, "detail":ProcDetail|null}
terminate_result {"type":"terminate_result","pid":int,"result":Result}
terminate_check  {"type":"terminate_check","pid":int,"alive":bool}

Tile      {"id":"cpu|gpu0|gpu1…|mem|power|temp|fan|net|disk","kind":"cpu|gpu|mem|power|temp|fan|net|disk",
           "name":str,"main":Num,"aside":Num|Txt|null,"seg":0..100,
           "series":[Series],"threads":[[float|null]]|null,"kv":[KV],"devices":Devices|null,
           "warn":bool}   (warn: Bernstein ab 80 % nur bei absoluter Obergrenze)
Num       {"v":float|null,"u":"%|GHz|MHz|W|°C|rpm|B/s|B|"}  optional: "of":float|null (Anzeige „v / of u“),
          "p":"↓"|"↑" (Präfix vor dem Wert)
Series    {"key":textkey | "label":str,"fill":bool,"max":float,"u":unit,"values":[float|null]}   (≤300)
KV        {"k":textkey | "l":str,"v":Num|Txt|[Num|Txt]}   (Liste wird mit „ · “ verbunden)
Txt       {"k":textkey} | {"l":str}   ("k" übersetzen, "l" = rohe Beschriftung/Name, nie übersetzen; kein nacktes str als Wert)
Devices   {"cols":[textkey],"rows":[{"name":str,"values":[Num|null]}]}   (kleine Tabelle mit Spaltenköpfen; null → „–“)
ProcBrief {"pid":int,"start":int,"name":str,"cpu":float,"rss":int}
ProcRow   {"pid","start","name","args","user","own":bool,"cpu":float,"spark":[float],"rss":int,
           "io":float|null,"state":State,"since":int}
ProcDetail ProcRow + {"cmdline":str,"ppid":int,"parent":str,"threads":int,"vctx":float,"nvctx":float,"kernel":bool,
           "started":int,"history":[float]}   (history ≤150; kernel = PID 1 oder Kernel-Thread → nicht beendbar, Regel nur in Python)
State     working|waiting|busy_noio|busy_iounknown|kernel_hang|stopped|zombie
Result    sent|gone|mismatch|zombie|kernel|denied|nohelper|error   (nohelper: root-eigener Helfer fehlt oder ist nicht vertrauenswürdig → kein pkexec; Hinweis auf setup-privileges.sh)
```

Seite → Python über `window.webkit.messageHandlers.orbitop.postMessage(obj)`:
`{"type":"ready"}`, `{"type":"view","tab":"overview|procs","pid":int|null,"start":int|null}`, `{"type":"terminate","pid":int,"start":int,"force":bool}`, `{"type":"quit"}`.

`procs` und `detail` werden nur gefüllt, wenn der zuletzt gemeldete `view.tab` gleich `procs` ist. Das Formatieren der Einheiten übernimmt die Seite (`Intl.NumberFormat(lang)`), Python schickt Basiseinheiten.

**Erweiterung dieser Runde:**

```text
init      + "layout": Layout|null          (null: die Seite nimmt den Standard; immer das aktuelle Layout, auch beim erneuten Anzeigen)
ProcRow   + "pri":int (PR, stat 18), "nice":int (NI, stat 19), "virt":int (Bytes, stat 23),
            "shr":int|null (Bytes, statm Feld 3 × Seitengröße; null, solange der Prozess-Reiter nicht sichtbar ist),
            "s":str (Zustandsbuchstabe des Kernels, stat 3), "time":float (CPU-Sekunden, (utime+stime)/CLK_TCK)
Layout    {"order":[ColId],          Permutation aller 15 ids
           "hidden":[ColId],         ohne Doppelte, nie "process"
           "widths":{ColId:int},     nur vom User gesetzte Breiten, ganzzahlig 40..1200
           "split":float}            Anteil der Liste an der Breite, 0.2..0.8, endlich
ColId     pid|process|user|cpu|last60|ram|io|state|pri|nice|virt|shr|s|mem|time   (Grundreihenfolge; Standard
          ausgeblendet: pri nice virt shr s mem time; orbitop/layout.py COLUMNS = COLS in app.js, Test)
```

Seite → Python: `{"type":"layout","order":[…],"hidden":[…],"widths":{…},"split":float}`. `parse_message` prüft streng, Zusatzschlüssel fallen weg wie bei den anderen Nachrichten. Die Seite meldet erst am Ende eines Ziehens und höchstens einmal je 500 ms.

Layout-Datei:
- Pfad `$XDG_CONFIG_HOME/orbitop/layout.json`, wenn `XDG_CONFIG_HOME` absolut ist, sonst `~/.config/orbitop/layout.json`. Kein Pfad kommt von der Seite.
- Gelesen wird nur eine reguläre Datei, höchstens 4096 Bytes, ohne Blockieren.
- Erst nachsichtig: unbekannte ids entfallen, fehlende kommen an ihren Standardplatz mit Standard-Sichtbarkeit. Danach streng mit derselben Prüfung. Kaputt heißt `null`.
- Geschrieben wird atomar (temporäre Datei im selben Verzeichnis, dann `os.replace`) und nur bei Änderung.

## Review Focus

1. **Kaputte oder feindliche `layout.json`:** abgeschnittenes JSON, über 4096 Bytes, ein Verzeichnis oder eine FIFO an ihrer Stelle, nicht beschreibbares Konfigurationsverzeichnis. Erwartet: Standardlayout, kein Hängen beim Start, Speichern scheitert still ohne Absturz. Tests in Task 2.
2. **Fenster erneut anzeigen oder Web-Prozess neu geladen:** `init` geht erneut an die Seite. Erwartet: das zuletzt gemeldete Layout, nicht das vom Start. Test in Task 2.
3. **Die Sortierspalte wird ausgeblendet, auch CPU selbst:** Erwartet: Sortierung fällt auf CPU absteigend zurück, Auswahl bleibt, keine Ausnahme. Test in Task 3.
4. **Fenster schmaler, als die gespeicherte Trennerposition erlaubt:** Erwartet: Liste ≥ 360 px und Detail ≥ 300 px beim Anzeigen. Der gespeicherte Wert bleibt, bis der User den Trenner bewegt. Test in Task 4.
5. **Python 3.11 (Debian 12) oder fehlende bzw. unbekannte `/etc/os-release`:** Erwartet: eine klare Meldung mit Exit-Code 2 statt eines Tracebacks, bei unbekannter Distribution die Debian-Namen. Tests in Task 6.

## Abweichungen vom vorgeschlagenen Zuschnitt und Klärungen

- **SHR-Schalter über den Worker:** Die Spec sagt „Der Sampler kennt den sichtbaren Reiter schon aus der view-Nachricht“. Im Code kennt nur `app.Worker` Sichtbarkeit, `ready` und `view`. Der Sampler sieht die Ansicht nur in `snapshot()`, und der Prozess-Takt läuft in einem eigenen Thread. Deshalb übergibt `Worker.run_procs` das Flag an `Sampler.tick_procs(shr=…)` (Task 1).
- **`error.runtime_missing` nennt heute fest `sudo apt install`.** Der Text bekommt den Platzhalter `{command}`, damit `check_runtime` den Befehl der laufenden Distribution nennt (Task 6).
- **Tooltips „wie heute“:** Die Spec nennt für `cpu`, `last60`, `io` und `state` als Tooltip „wie heute“. Heute haben die Köpfe aber keine Tooltips. Der Plan legt die Texte in Task 3 fest.
- **Test „JS-ids = Python-ids“ in Task 3 statt Task 2:** Die ids entstehen in `app.js` erst in Task 3.
- **Gedrosseltes Senden in Task 3:** `saveLayout()` entsteht schon in Task 3, weil die Menüpunkte das Layout ändern. Task 4 ruft es nur am Ende eines Ziehens auf.
- **Prüfseite mit 1600×1000:** Mit PID und Benutzer ist die Standardtabelle breiter als das heutige 800-px-Fenster des kopflosen Chrome. Die Prüfung „400 Zeichen ohne waagerechtes Scrollen“ hängt deshalb an der breiten Ansicht (Task 3). Die schmale Ansicht prüft ein zweiter Lauf (Task 4).
- **Prozess-Spalte füllt den Rest:** Die Tabelle ist so breit wie die Summe der Spaltenbreiten. Bleibt Platz übrig, nimmt ihn die Prozess-Spalte, wie heute: angezeigte Breite = max(gespeicherte Breite, Bereich − übrige Spalten). Die gespeicherte Breite wirkt also als Untergrenze.
- **„Standard wiederherstellen“ setzt das ganze Layout zurück**, auch den Trenner. So ist auch der Trenner per Tastatur zurückzusetzen (Anti-Ziel „nur mit der Maus“).
- **Messung in vier Lagen statt drei:** ausgeblendet, Übersicht, Prozess-Reiter mit Standardauswahl und mit allen Spalten, weil das Budget für beide Spaltenfälle gilt (Task 5).
- **Python-Versionsprüfung:** `check_runtime` meldet Python < 3.12 klar (Review Focus 5). Unter 3.11 lassen sich alle Module heute importieren (geprüft); ohne die Prüfung liefe orbitop dort halb.

---

### Task 1: Neue Prozessfelder (PR, NI, VIRT, SHR, S, TIME+)

**Files:**
- Modify: `orbitop/procs.py` (`parse_stat`, `RawProc`, `scan`, `ProcTable._row`)
- Modify: `orbitop/sampler.py` (`tick_procs`)
- Modify: `orbitop/app.py` (`Worker.run_procs`)
- Modify: `scripts/dump-snapshot.py`
- Test: `tests/test_procs.py`, `tests/test_sampler.py`, `tests/test_app.py`

**Interfaces:**
- Produces:
  - `parse_stat(text) -> dict` mit zusätzlich `"pri": int(f[15])`, `"nice": int(f[16])`, `"virt": int(f[20])` (Feld 18, 19, 23 nach proc(5); `f[0]` ist Feld 3).
  - `RawProc` bekommt am Ende `pri: int = 0`, `nice: int = 0`, `virt: int = 0`, `shr: int | None = None`. Die Defaults halten die positionalen Aufrufe der Tests gültig.
  - `scan(root, cmdlines=None, page_size=…, want_status=None, want_shr: bool = False)`: nur mit `want_shr` wird `/proc/<pid>/statm` gelesen (über `_read`), `shr = int(feld3) * page_size`. Fehlt die Datei oder ist sie kaputt, ist `shr = None`, der Prozess bleibt in der Liste.
  - ProcRow (`ProcTable._row`) zusätzlich: `"pri"`, `"nice"`, `"virt"`, `"shr"`, `"s": raw.state`, `"time": raw.ticks / self.clk_tck`.
  - `Sampler.tick_procs(shr: bool = False)` reicht `want_shr=shr` an `scan`.
  - `Worker.run_procs` ruft `tick_procs(shr=…)` mit `True` genau dann, wenn (unter `self._lock`) `_visible and _ready and _view.get("tab") == "procs"`.
  - `dump-snapshot.py` ruft `tick_procs(shr=a.view == "procs")`.

- [ ] **Step 1: Failing tests**

`stat_line` bekommt die Parameter `pri=20, nice=0, virt=0` an den Stellen der Felder 18, 19 und 23. `make_proc` bekommt `statm: str | None = None` (schreibt die Datei nur, wenn gesetzt). `raw()` bekommt `pri=20, nice=0, virt=0, shr=None`.

```python
# tests/test_procs.py
def test_parse_stat_priority_nice_vsize():
    d = parse_stat(stat_line(7, pri=39, nice=19, virt=123_456_789))
    assert (d["pri"], d["nice"], d["virt"]) == (39, 19, 123_456_789)
    assert parse_stat(stat_line(8, pri=0, nice=-20))["nice"] == -20

def test_scan_reads_statm_only_when_wanted(tmp_path, monkeypatch):
    make_proc(tmp_path, 100, statm="1000 321 77 10 0 200 0\n")
    seen, real = [], procs._read
    monkeypatch.setattr(procs, "_read", lambda p: seen.append(p) or real(p))
    assert scan(str(tmp_path), page_size=4096)[(100, 98765)].shr is None
    assert not any(p.endswith("/statm") for p in seen)
    assert scan(str(tmp_path), page_size=4096, want_shr=True)[(100, 98765)].shr == 77 * 4096

def test_scan_statm_missing_or_broken_keeps_process(tmp_path):  # verschwindet zwischen stat und statm
    make_proc(tmp_path, 100)
    make_proc(tmp_path, 101, statm="kaputt")
    got = scan(str(tmp_path), want_shr=True)
    assert sorted(k[0] for k in got) == [100, 101] and {r.shr for r in got.values()} == {None}

def test_row_has_top_fields():
    t = ProcTable(clk_tck=CLK, uid=1000)
    t.update({(10, 1): raw(ticks=12345, state="R", pri=20, nice=-5, virt=8192, shr=4096)}, 0.0)
    r = t.rows(0.0)[0]
    assert (r["pri"], r["nice"], r["virt"], r["shr"], r["s"], r["time"]) == (20, -5, 8192, 4096, "R", 123.45)
```

```python
# tests/test_sampler.py: with_procs schreibt je Prozess statm="1000 321 77 10 0 200 0\n"
def test_shr_only_after_procs_tick_with_shr(with_procs):
    s = run(with_procs)
    assert {r["shr"] for r in s.snapshot(PROCS)["procs"]} == {None}
    s.tick_procs(shr=True)
    assert all(type(r["shr"]) is int and r["shr"] > 0 for r in s.snapshot(PROCS)["procs"])
# validate_tick: für jede Zeile in snap["procs"] (falls Liste)
#   type(pri) is int, type(nice) is int, type(virt) is int, shr None oder int,
#   s str der Länge 1, type(time) is float
```

`PROCS = {"tab": "procs", "pid": None, "start": None}` als Konstante neben `OVERVIEW`, falls sie fehlt.

```python
# tests/test_app.py: FakeSampler.tick_procs(self, shr=False) hängt shr an self.shr an
@pytest.mark.parametrize("visible,ready,tab,shr", [
    (True, True, "procs", True), (False, True, "procs", False),
    (True, False, "procs", False), (True, True, "overview", False)])
def test_procs_tick_reads_shr_only_when_procs_tab_visible(visible, ready, tab, shr):
    ...  # Worker.update(visible=…, ready=…, view={"tab": tab, "pid": None, "start": None}), ein Prozess-Takt über run_procs
    assert s.shr == [shr]
```

- [ ] **Step 2:** `pytest tests/test_procs.py tests/test_sampler.py tests/test_app.py -q` → FAIL (KeyError `pri`, unerwartetes Argument `want_shr`/`shr`)
- [ ] **Step 3:** umsetzen laut Interfaces.
- [ ] **Step 4:** `pytest tests/test_procs.py tests/test_sampler.py tests/test_app.py -q` → PASS
- [ ] **Step 5:** `pytest -q` und streng → grün
- [ ] **Step 6: Commit**

```bash
git add orbitop/procs.py orbitop/sampler.py orbitop/app.py scripts/dump-snapshot.py tests/test_procs.py tests/test_sampler.py tests/test_app.py
git commit -m "feat: Prozessfelder PR, NI, VIRT, SHR, S und TIME+ (SHR nur bei sichtbarem Prozess-Reiter)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Layout prüfen, speichern und in `init` mitgeben

**Files:**
- Create: `orbitop/layout.py`, `tests/test_layout.py`
- Modify: `orbitop/app.py` (`parse_message`), `orbitop/shell.py` (Start, `_on_message`, `init`), `scripts/dump-snapshot.py` (`init.layout = None`)
- Test: `tests/test_app.py`, `tests/test_shell.py`, `tests/test_sampler.py` (`test_dump_snapshot_js`)

**Interfaces:**
- Produces (`orbitop/layout.py`, ohne GTK):
  - `COLUMNS: tuple[str, ...] = ("pid", "process", "user", "cpu", "last60", "ram", "io", "state", "pri", "nice", "virt", "shr", "s", "mem", "time")`
  - `DEFAULT_HIDDEN: tuple[str, ...] = ("pri", "nice", "virt", "shr", "s", "mem", "time")`
  - `WIDTH_MIN, WIDTH_MAX = 40, 1200`; `SPLIT_MIN, SPLIT_MAX = 0.2, 0.8`; `MAX_BYTES = 4096`
  - `validate(obj) -> dict | None`: streng laut Vertrag „Layout“. Alle vier Schlüssel nötig, andere Schlüssel fallen weg. Breite: `type(v) is int`. Split: int oder float, kein bool, `math.isfinite`. Gibt eine neue Kopie `{"order": list, "hidden": list, "widths": dict, "split": float}` zurück.
  - `repair(obj) -> dict | None`: für die Datei. Unbekannte ids fallen aus `order`, `hidden` und `widths`. Eine fehlende id kommt in `order` direkt hinter ihren nächsten Vorgänger aus `COLUMNS`, der vorhanden ist (sonst an den Anfang). Steht sie in `DEFAULT_HIDDEN` und fehlt in `hidden`, kommt sie dazu. Danach `validate`.
  - `config_path(env: Mapping[str, str]) -> str`: laut Vertrag. Ein relativer `XDG_CONFIG_HOME` wird ignoriert (XDG-Spezifikation). Das Home-Verzeichnis kommt aus `os.path.expanduser("~")`.
  - `class LayoutFile(path: str)` mit:
    - `path: str` und `current: dict | None`
    - `load() -> dict | None`: `os.open(…, O_RDONLY | O_NONBLOCK)`, `fstat` muss eine reguläre Datei zeigen, höchstens `MAX_BYTES + 1` lesen (mehr heißt kaputt), JSON, dann `repair`. Setzt `current`, jeder Fehler ergibt `None`. Ein Symlink auf eine reguläre Datei bleibt erlaubt (Dotfile-Verwaltung). Eine FIFO oder ein Gerät dahinter fängt `fstat` ab.
    - `save(layout: dict) -> bool`: Gleich `current` heißt `False` ohne Schreiben. Sonst wird `current` gesetzt, dann Verzeichnis anlegen (`0o700`), `tempfile.mkstemp(dir=…)`, schreiben, `os.replace`. `True` bei Erfolg; bei `OSError` die temporäre Datei entfernen und `False`.
- Produces (`app.parse_message`): `{"type":"layout"}` → `{"type": "layout", **validate(m)}` oder `None`.
- Produces (`shell.Shell`):
  - In `_startup`: `self._layouts = LayoutFile(config_path(os.environ))`, danach `self._layouts.load()`. `self._init_fields = {"type": "init", "lang": …, "texts": …, "version": …}`.
  - `_init_message() -> str` = `encode({**self._init_fields, "layout": self._layouts.current})`, gebaut bei jedem Senden. Es ersetzt `self._init`.
  - `_on_message` „layout“ ruft `self._layouts.save({k: msg[k] for k in ("order", "hidden", "widths", "split")})` und antwortet nicht.

- [ ] **Step 1: Failing tests** in `tests/test_layout.py`

```python
L = {"order": list(COLUMNS), "hidden": list(DEFAULT_HIDDEN), "widths": {"cpu": 90}, "split": 0.6}
def test_validate_accepts_contract_and_bounds():
    assert validate(L) == L and validate({**L, "path": "/etc/x"}) == L
    assert validate({**L, "widths": {"cpu": 40, "process": 1200}, "split": 0.2}) is not None
    assert validate({**L, "split": 0.8}) is not None
@pytest.mark.parametrize("bad", [
    {"order": [c for c in COLUMNS if c != "time"]}, {"order": [*COLUMNS[:-1], "pid"]},
    {"order": [*COLUMNS, "gpu"]}, {"order": "pid"}, {"hidden": ["process"]}, {"hidden": ["gpu"]},
    {"hidden": ["pri", "pri"]}, {"hidden": [1]}, {"widths": {"cpu": 39}}, {"widths": {"cpu": 1201}},
    {"widths": {"cpu": 90.0}}, {"widths": {"cpu": True}}, {"widths": {"cpu": "90"}}, {"widths": {"gpu": 90}},
    {"widths": [90]}, {"split": 0.19}, {"split": 0.81}, {"split": True}, {"split": "0.5"},
    {"split": float("nan")}, {"split": float("inf")}, {"split": None}])
def test_validate_rejects(bad): assert validate({**L, **bad}) is None
def test_validate_needs_all_keys(): assert validate({k: v for k, v in L.items() if k != "split"}) is None and validate([L]) is None
def test_repair_drops_unknown_and_adds_missing_at_default_place():
    old = {"order": [c for c in COLUMNS if c != "time"] + ["gpu"], "hidden": ["pri", "gpu"], "widths": {"gpu": 50, "cpu": 70}, "split": 0.5}
    r = repair(old)
    assert r["order"] == list(COLUMNS) and "time" in r["hidden"] and "gpu" not in r["hidden"] and r["widths"] == {"cpu": 70}
def test_repair_keeps_users_order_and_strict_after():
    r = repair({**L, "order": ["process", *[c for c in COLUMNS if c not in ("process", "mem")]]})
    assert r["order"][0] == "process" and r["order"].index("mem") == r["order"].index("s") + 1
    assert r["hidden"].count("mem") == 1 and repair({**L, "hidden": ["process"]}) is None
def test_config_path(monkeypatch):
    assert config_path({"XDG_CONFIG_HOME": "/x/cfg"}) == "/x/cfg/orbitop/layout.json"
    monkeypatch.setenv("HOME", "/home/u")
    assert config_path({}) == config_path({"XDG_CONFIG_HOME": "cfg"}) == "/home/u/.config/orbitop/layout.json"
@pytest.mark.parametrize("make", ["missing", "truncated", "oversize", "directory", "fifo", "link-to-fifo", "not-a-dict"])
def test_load_bad_file_is_none_without_hanging(tmp_path, make):     # Review Focus 1
    ...  # Datei laut make anlegen; load() in einem Thread, join(2)
    assert done and result is None and f.current is None
def test_load_valid_and_repaired(tmp_path): ...  # gültige Datei → current == Inhalt; alte Datei ohne "time" → ergänzt
def test_save_atomic_only_when_changed(tmp_path, monkeypatch):
    calls = []; real = layout.os.replace; monkeypatch.setattr(layout.os, "replace", lambda a, b: calls.append(b) or real(a, b))
    f = LayoutFile(str(tmp_path / "cfg" / "orbitop" / "layout.json"))
    assert f.save(L) and not f.save(dict(L)) and len(calls) == 1
    assert json.loads(Path(f.path).read_text()) == L and os.listdir(Path(f.path).parent) == ["layout.json"]
def test_save_failure_is_silent(tmp_path):                           # Review Focus 1; skip als root
    d = tmp_path / "ro"; d.mkdir(); d.chmod(0o500)
    f = LayoutFile(str(d / "orbitop" / "layout.json")); assert f.save(L) is False and f.current == L
```

```python
# tests/test_app.py
# test_parse_message_accepts_contract_shapes um diesen Fall ergänzen:
#   json.dumps({"type": "layout", **L, "path": "/etc/passwd"})  →  {"type": "layout", **L}
def test_parse_message_layout_rejects_bad_and_oversize():
    assert parse_message(json.dumps({"type": "layout", **L, "hidden": ["process"]})) is None
    assert parse_message(json.dumps({"type": "layout", **L, "pad": "x" * 4096})) is None
    assert parse_message('{"type":"layout","order":[],"hidden":[],"widths":{},"split":NaN}') is None
```

```python
# tests/test_shell.py: rig bekommt tmp_path, setzt s._init_fields = {"type": "init"} und
# s._layouts = LayoutFile(str(tmp_path / "layout.json")); INIT = encode({"type": "init", "layout": None})
def test_layout_message_saved_once_to_fixed_path(rig, tmp_path):
    rig.s._on_message(None, Value({"type": "layout", **L, "path": str(tmp_path / "evil")}))
    rig.s._on_message(None, Value({"type": "layout", **L}))
    assert json.loads((tmp_path / "layout.json").read_text()) == L and sorted(os.listdir(tmp_path)) == ["layout.json"]
    assert rig.js == [] and rig.log == []
def test_invalid_layout_message_not_saved(rig, tmp_path): ...  # hidden ["process"] → keine Datei
def test_init_after_layout_carries_current_layout(rig):          # Review Focus 2
    rig.s._on_message(None, Value({"type": "layout", **L}))
    rig.s._on_message(None, Value({"type": "ready"}))
    assert json.loads(rig.js[-1].removeprefix("window.orbitop.receive(").removesuffix(")"))["layout"] == L
```

`test_dump_snapshot_js` prüft zusätzlich `demo["init"]["layout"] is None`.

- [ ] **Step 2:** `pytest tests/test_layout.py tests/test_app.py tests/test_shell.py tests/test_sampler.py -q` → FAIL (ModuleNotFoundError `orbitop.layout`)
- [ ] **Step 3:** `orbitop/layout.py` mit SPDX-Kopf, dann `parse_message`, `Shell` und `dump-snapshot.py` umsetzen laut Interfaces.
- [ ] **Step 4:** → PASS
- [ ] **Step 5:** `pytest -q` und streng → grün
- [ ] **Step 6: Commit**

```bash
git add orbitop/layout.py orbitop/app.py orbitop/shell.py scripts/dump-snapshot.py tests/test_layout.py tests/test_app.py tests/test_shell.py tests/test_sampler.py
git commit -m "feat: Layout der Prozessspalten geprüft speichern und in init mitgeben" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Oberfläche A – Spaltenmodell, neue Spalten, Sortieren, Tooltips, Spaltenmenü

**Files:**
- Modify: `orbitop/ui/app.js`, `orbitop/ui/style.css`, `orbitop/locale/en.json`, `orbitop/locale/de.json`
- Modify: `tests/ui/check.js`, `tests/test_ui.py` (Fenstergröße), `tests/test_layout.py` (Gleichheit der ids), `tests/ui/demo-data.js` (neu erzeugt)

**Interfaces:**
- Consumes: `init.layout`, die ProcRow-Felder aus Task 1, die `layout`-Nachricht aus Task 2, `layout.COLUMNS` und `layout.DEFAULT_HIDDEN`.
- Produces (globale Funktionen und Konstanten in `app.js`, für Task 4 und `check.js`):
  - `COLS`: je Spalte **eine Zeile** `{ id, key: "col.<id>", tip: "coltip.<id>", w, …, get }`. Dazu `off: true` für standardmäßig ausgeblendete Spalten, `asc: true` für aufsteigende Erstsortierung (pid, process, user, s) und `cls: "r"` für rechtsbündige Zahlen. Reihenfolge = `COLUMNS`.
  - Standardbreiten in px: pid 64, process 240, user 96, cpu 52, last60 104, ram 74, io 80, state 200, pri 44, nice 44, virt 80, shr 80, s 40, mem 64, time 84.
  - `MIN_W = 40`, `MIN_PROCESS_W = 120`, `MAX_W = 1200`, `DEFAULT_SPLIT = 1.55 / 2.55`, `LAYOUT_GAP_MS = 500`.
  - `state.layout = { order: string[], hidden: Set<string>, widths: {id: px}, split: number }`.
  - `defaultLayout()`.
  - `applyLayout(l)`: aus `init` oder einer Änderung; aus `init` sendet es nie selbst. Ändern sich Reihenfolge oder Sichtbarkeit, wird der Kopf neu gebaut und `procRows` geleert. Beim Neuaufbau kommen die Texte direkt aus `state.texts`, nicht über `label()`, sonst wüchse `ui.labels` mit jedem Umbau. Breiten über `<colgroup>` und CSSOM.
  - `layoutMessage()` → Vertrag „Layout“ (`hidden` als Array). `saveLayout()` postet höchstens einmal je `LAYOUT_GAP_MS`. Zu frühe Änderungen sammelt ein einziger `setTimeout` mit der Restzeit, der dann den neuesten Stand sendet.
  - `visibleCols()`, `toggleColumn(id)`, `moveColumn(id, dir)` (dir −1/+1, zum nächsten **sichtbaren** Nachbarn), `restoreLayout()` (ganzes Layout samt Split), `setWidth(id, px)` (begrenzt auf `MIN_W` bzw. `MIN_PROCESS_W` bis `MAX_W`; für Task 4).
  - `cpuTime(sec) -> "m:ss.hh"`: über ganze Hundertstel gerundet, Minuten ohne Obergrenze, immer `.` wie in `top`.
  - `openColumnMenu(th, x, y)` und `closeColumnMenu()`.
  - Kopfzelle `th[data-col=<id>]` mit `button` (Sortieren, `title` = Tooltip).
- Formate: pid, pri und nice als `String(v)`; user und s als Text; virt und shr mit `fmt(…, "B")` (null → „–“); TIME+ über `cpuTime`. %MEM = `rss / of × 100` mit `of` aus `aside.of` der Kachel `mem` im selben tick, eine Nachkommastelle, Prozentzeichen wie `fmt` („25,0 %“ de, „25.0%“ en); ohne Kachel „–“. Sortierschlüssel: mem nach `rss`, shr null als −1.
- Die Prozess-Spalte füllt den Rest: angezeigte Breite = max(gespeicherte oder Standardbreite, `ui.scroll.clientWidth` − übrige Spalten). Die Tabellenbreite ist die Summe. `clientWidth` misst der vorhandene ResizeObserver mit.
- Sortierung: Wird die Sortierspalte ausgeblendet, gilt `{ col: "cpu", desc: true }`.
- Spaltenmenü:
  - `role="menu"` mit `aria-label` (`menu.columns`). Je Spalte ein `menuitemcheckbox` mit `aria-checked`; Prozess fest an mit `aria-disabled="true"`.
  - Dann `role="separator"`, dann „Nach links“ und „Nach rechts“ (`menuitem`) für die angeklickte Spalte, am Rand `aria-disabled`, zuletzt „Standard wiederherstellen“.
  - Öffnen: `contextmenu` auf einem Kopf (`preventDefault`), Taste `ContextMenu` oder Umschalt+F10 auf dem fokussierten Kopfknopf. Öffnen ist idempotent, denn WebKit kann zur Taste zusätzlich ein `contextmenu` schicken.
  - Fokus auf dem ersten Eintrag, Roving Tabindex. ↑ und ↓ laufen im Kreis, Pos1 und Ende springen. Eingabe oder Leertaste löst aus.
  - Häkchen und Verschieben lassen das Menü offen, „Standard wiederherstellen“ schließt es.
  - Escape schließt und gibt den Fokus an den Kopfknopf zurück. `pointerdown` außerhalb oder Tab schließt. Das Menü bleibt im Fenster.
- Locale (beide Dateien, „de“ / „en“):

  | Schlüssel | de | en |
  |---|---|---|
  | `col.pid`, `col.user` | PID, Benutzer | PID, User |
  | `col.pri`, `col.nice`, `col.virt`, `col.shr`, `col.s`, `col.mem`, `col.time` | PR, NI, VIRT, SHR, S, %MEM, TIME+ | wie de |
  | `coltip.pid` | Prozessnummer | Process ID |
  | `coltip.process` | Name und Argumente (COMMAND) | Name and arguments (COMMAND) |
  | `coltip.user` | Eigentümer | Owner |
  | `coltip.cpu` | CPU-Last in Prozent eines Kerns | CPU load in percent of one core |
  | `coltip.last60` | CPU-Verlauf der letzten 60 s | CPU history of the last 60 s |
  | `coltip.ram` | belegter Arbeitsspeicher (RES) | Resident memory (RES) |
  | `coltip.io` | Lesen und Schreiben je Sekunde | Read and write per second |
  | `coltip.state` | orbitop-Einstufung | orbitop classification |
  | `coltip.pri`, `coltip.nice`, `coltip.virt`, `coltip.shr` | Priorität, Nice-Wert, virtueller Speicher, gemeinsam genutzter Speicher | Priority, Nice value, Virtual memory, Shared memory |
  | `coltip.s` | Kernel-Zustand (R, S, D, Z, T, I …) | Kernel state (R, S, D, Z, T, I …) |
  | `coltip.mem`, `coltip.time` | Anteil am Arbeitsspeicher, verbrauchte CPU-Zeit | Share of memory, CPU time used |
  | `menu.columns` | Spalten | Columns |
  | `menu.move_left`, `menu.move_right` | Nach links, Nach rechts | Move left, Move right |
  | `menu.restore` | Standard wiederherstellen | Restore defaults |

  Bestehende Texte bleiben. Die festen `.ptable th:nth-child(n)`-Breiten in `style.css` entfallen. Das Menü übernimmt den Stil der bestehenden Rahmen und Knöpfe, ohne neue Farben.

- [ ] **Step 1: Failing tests**

```python
# tests/test_layout.py
def test_js_columns_match_python():
    js = (REPO / "orbitop" / "ui" / "app.js").read_text(encoding="utf-8")
    block = js[js.index("const COLS = ["):]
    lines = [ln for ln in block[:block.index("\n];")].splitlines() if 'id: "' in ln]
    assert [re.search(r'id: "(\w+)"', ln)[1] for ln in lines] == list(COLUMNS)
    assert [re.search(r'id: "(\w+)"', ln)[1] for ln in lines if "off: true" in ln] == list(DEFAULT_HIDDEN)
```

`tests/test_ui.py`: Der Chrome-Aufruf bekommt `--window-size=1600,1000`.

Der Kopf von `tests/ui/check.js` ersetzt vor `app.js` die Funktion `window.setTimeout` durch eine Aufzeichnung `timers.push({ fn, ms })` und bietet `flush()` an. `app.js` nutzt sonst keine Zeitgeber. In den init-Texten der Prüfung stehen zusätzlich `"coltip.pid": "Prozessnummer"` und `"menu.restore": "Standard"`.

Hilfen in `check.js`:
- `th(id)` liefert den Kopf `.ptable th[data-col=id]`.
- `cell(tr, id)` liefert die Zelle an der Indexstelle dieses Kopfes.
- `ids()` ergibt die `data-col` der Köpfe, mit Komma verbunden.
- `items()` sind die `menuitemcheckbox` des Menüs, `item(id)` ist das Häkchen der Spalte `id`.
- `menuOpen()` meldet, ob das Menü sichtbar ist.
- `layouts()` sind die geposteten `layout`-Nachrichten.
- `sortedBy(c)`: `aria-sort` sitzt auf `th(c.id)`, und die Zeilen sind nach `c.get` in dieser Richtung monoton.
- Die bisherigen Zugriffe `heads[1]` usw. und `children[4]` laufen künftig über `th("cpu")` bzw. `cell(…, "io")`.

Neue Prüfungen (`eq(got, want, name)`):

```js
eq(ids(), "pid,process,user,cpu,last60,ram,io,state", "Standardspalten in Grundreihenfolge");
eq(th("pid").querySelector("button").title, "Prozessnummer", "Tooltip aus coltip.pid");
eq([cpuTime(0), cpuTime(3.5), cpuTime(59.999), cpuTime(7530.5)].join("|"), "0:00.00|0:03.50|1:00.00|125:30.50", "TIME+ als m:ss.hh");
// alle Spalten sichtbar (applyLayout), Zeile pid 4242, user "<b>u</b>", pri 20, nice -5, virt 3 GiB, shr null,
// s "S", time 7530.5, rss 1 GiB; tick mit mem-Kachel aside {v:…, u:"B", of: 4 GiB}
eq(["pid", "nice", "virt", "shr", "s", "mem", "time"].map((c) => plain(cell(r, c).textContent)).join("|"),
   "4242|-5|3 GB|–|S|25,0 %|125:30.50", "Formate der neuen Spalten");
eq(cell(r, "user").textContent + "/" + cell(r, "user").querySelectorAll("b").length, "<b>u</b>/0", "Benutzer als Text");
// ohne mem-Kachel: %MEM „–“
for (const c of COLS) { /* Kopf c klicken */ eq(sortedBy(c), true, `sortiert nach ${c.id}`); }  // aria-sort gesetzt, Zeilen monoton nach c.get
// Menü
th("cpu").dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 300, clientY: 80 }));
eq(menuOpen() && document.activeElement === items()[0], true, "Rechtsklick öffnet das Menü, Fokus auf dem ersten Eintrag");
eq(items().length + "/" + item("process").getAttribute("aria-disabled"), "15/true", "15 Häkchen, Prozess fest");
// ↓ fokussiert den zweiten Eintrag, ↑ auf dem ersten den letzten
// Enter auf „pri“: ids() endet auf ",pri", aria-checked true, Menü offen
// Escape: zu, Fokus auf th("cpu") button
// keydown Shift+F10 und keydown "ContextMenu" auf dem Kopfknopf öffnen (zweimal → ein Menü)
// pointerdown auf document.body: zu
// „Nach links“ auf cpu: ids "pid,process,cpu,user,…"; auf pid: „Nach links“ aria-disabled
// Enter auf dem Prozess-Häkchen: process bleibt sichtbar
// „Standard wiederherstellen“: ids wie Standard, layoutMessage().widths leer, Menü zu
// Layout-Meldung
eq(layouts().length, 1, "Häkchen sendet sofort ein layout");   // order mit allen 15 ids, hidden ohne "pri"
// sofort zweites Häkchen: kein neues layout, genau ein Timer mit 0 < ms ≤ 500; flush(): genau ein weiteres layout mit "pri" in hidden
// init mit layout {order: …, hidden: […], widths: {cpu: 90}, split: 0.5}: ids folgen order, Spalte cpu 90 px breit
// Review Focus 3: nach "nice" sortiert, nice ausblenden → th("cpu") aria-sort "descending" und Zeilen nach CPU absteigend;
//                 nach CPU sortiert, cpu ausblenden → Zeilen weiter nach CPU absteigend, Auswahl bleibt
```

Die bisherigen Prüfungen „400 Zeichen“ und „lange Namen“ bleiben: Die Seite und das Detail scrollen nie waagerecht. In der Standardauswahl bei 1600×1000 scrollt auch die Tabelle nicht.

- [ ] **Step 2:** `pytest tests/test_layout.py::test_js_columns_match_python tests/test_ui.py -q` → FAIL
- [ ] **Step 3:** umsetzen laut Interfaces, danach `pytest tests/test_i18n.py -q` (gleiche Schlüssel, gleiche Platzhalter).
- [ ] **Step 4: Demodaten neu erzeugen** (5 min, auf dem Referenzrechner):

```bash
mkdir -p $SCRATCH/task3 && cd $SCRATCH/task3
LANG=de_DE.UTF-8 python3 <repo>/scripts/dump-snapshot.py --anonymize --js --view procs --ticks 300 > <repo>/tests/ui/demo-data.js
```

Danach enthält `demo-data.js` die neuen Felder und Texte, `shr` ist gefüllt, und es gibt keine echten Prozessnamen.
- [ ] **Step 5:** `pytest tests/test_layout.py tests/test_ui.py -q` → PASS
- [ ] **Step 6: Sichtprüfung:**

```bash
google-chrome --headless=new --hide-scrollbars --window-size=1600,1000 --screenshot=$SCRATCH/task3/procs.png "file://<repo>/tests/ui/demo.html#procs"
```

Dazu in der App: `ORBITOP_SNAPSHOT=$SCRATCH/task3/app-procs.png ORBITOP_TAB=procs XDG_CONFIG_HOME=$SCRATCH/task3/cfg dbus-run-session -- timeout 12 <repo>/bin/orbitop`. Beide Bilder mit `code -r` öffnen und gegen `entwuerfe/prozesse.png` halten.
- [ ] **Step 7: Kurzmessung** nach dem Messverfahren: Prozess-Reiter mit Standardauswahl und mit allen Spalten, je 60 s. Werte in den Task-Bericht. Liegt eine Lage über dem Budget, wird das hier nicht behoben, das macht Task 5.
- [ ] **Step 8:** `pytest -q` und streng → grün
- [ ] **Step 9: Commit**

```bash
git add orbitop/ui/app.js orbitop/ui/style.css orbitop/locale/en.json orbitop/locale/de.json tests/ui/check.js tests/test_ui.py tests/test_layout.py tests/ui/demo-data.js
git commit -m "feat: Prozessspalten wie top, Sortieren je Spalte, Tooltips und Spaltenmenü per Maus und Tastatur" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Oberfläche B – Breite ziehen, Umordnen, waagerechtes Scrollen, Trenner

**Files:**
- Modify: `orbitop/ui/app.js`, `orbitop/ui/style.css`, `orbitop/locale/en.json`, `orbitop/locale/de.json`
- Modify: `tests/ui/check.js`, `tests/test_ui.py` (zweiter Lauf schmal), `tests/ui/demo.js` (`?cols=all`)

**Interfaces:**
- Consumes: `setWidth`, `saveLayout`, `applyLayout`, `state.layout`, `DEFAULT_SPLIT` und `th(id)` aus Task 3.
- Produces:
  - **Griff** `.grip` am rechten Rand jeder Kopfzelle, `aria-hidden`:
    - Ziehen ändert die Breite sofort, `setWidth` begrenzt sie (40 px, Prozess 120 px, höchstens 1200 px).
    - Doppelklick löscht `widths[id]` und stellt so die Standardbreite her.
    - Auf dem fokussierten Kopfknopf ändern Alt+← und Alt+→ die Breite um 16 px.
  - **Umordnen:**
    - Den Kopf waagerecht ziehen. Erst ab 6 px Bewegung gilt das als Ziehen.
    - Beim Ziehen zeigt eine Einfügemarke `.drop` die Zielgrenze zwischen sichtbaren Spalten. Abgelegt wird in der Gesamtreihenfolge vor der sichtbaren Spalte an dieser Grenze, oder nach der letzten.
    - Der Klick nach einem Ziehen wird verworfen und sortiert nicht. Unter 6 px bleibt es ein Klick zum Sortieren.
  - **Trenner** `.split` mit `role="separator"`:
    - Attribute: `aria-orientation="vertical"`, `tabindex="0"`, `aria-label` (`procs.splitter`), `aria-valuemin="20"`, `aria-valuemax="80"`, `aria-valuenow` = gerundete Prozent.
    - Ziehen mit der Maus. ← und → verschieben um 32 px, Doppelklick stellt 1,55 : 1 wieder her.
    - Das Raster wird `minmax(360px, <s>fr) <Trennerbreite = heutige Lücke 12 px> minmax(300px, <1−s>fr)`, gesetzt über CSSOM-Variablen auf `.procs`.
    - Beim Bewegen wird `s` auf [max(0,2; 360/Breite), min(0,8; 1 − 300/Breite)] begrenzt. Anzeigen erzwingt die Grenzen über CSS, ohne den gespeicherten Wert zu ändern.
    - Unter 1100 px gilt `display: none` und der heutige Stapel.
  - `saveLayout()` läuft nur am Ende eines Ziehens (pointerup) und bei jeder Tastenänderung, nie während des Ziehens.
  - Pointer-Ereignisse: `pointerdown` am Griff, Kopf oder Trenner, Bewegung und Ende am `document`. Die Prüfseite schickt synthetische Ereignisse mit `pointerId: 1`.
  - Aussehen laut Spec: ruhig, beim Ziehen und bei Fokus im vorhandenen Cyan-Akzent, keine neuen Farben, keine Animation außer der Rückmeldung beim Ziehen.
  - `demo.js`: `?cols=all` setzt vor `receive(init)` `init.layout = { order: [alle ids], hidden: [], widths: {}, split: 1.55 / 2.55 }` (für Sichtprüfung und Messung).
- Locale: `procs.splitter` = „Trenner zwischen Liste und Detail“ / „Divider between list and details“.

- [ ] **Step 1: Failing tests** in `tests/ui/check.js` (Lauf mit 1600×1000). Weitere Hilfen:
- `colW(id)` ist die Breite der `col` in px.
- `listW()` und `detailW()` sind die Breiten von `.frame.list` und `.frame.detail`.
- `sep` ist der Trenner.
- `layoutsDuringMove` zählt die `layout`-Nachrichten zwischen `pointerdown` und `pointerup`.

```js
// Breite: pointerdown auf .grip von cpu bei x, pointermove x+30, pointerup
eq(colW("cpu") + "/" + layoutsDuringMove, "82/0", "Griff zieht die Breite, gemeldet erst am Ende");
eq(layouts().length - before, 1, "genau ein layout nach dem Ziehen");          // ggf. nach flush()
// Ziehen um -1000: cpu 40 px; process um -1000: 120 px; dblclick auf .grip von cpu: 52 px, layoutMessage().widths ohne cpu
// Alt+→ auf dem cpu-Kopfknopf: +16; Alt+← zweimal: -32; bei 40 bleibt es 40
// Umordnen: 5 px ziehen, loslassen, click → sortiert um (aria-sort wechselt), Reihenfolge gleich
// cpu über die Mitte von last60 hinaus ziehen: .drop sichtbar während der Bewegung; danach click → keine Sortierung,
//   ids "pid,process,user,last60,cpu,ram,io,state"
// Waagerecht: alle Spalten zeigen, 300 Zeilen, scroller.scrollTop = 100 * pitch, scrollLeft = 200
eq(scroller.scrollWidth > scroller.clientWidth, true, "alle Spalten: Tabelle scrollt waagerecht");
eq(Math.abs(th("cpu").getBoundingClientRect().top - scroller.getBoundingClientRect().top) < 1, true, "Kopf bleibt oben");
eq(Math.abs(th("cpu").getBoundingClientRect().left - cell(rows()[0], "cpu").getBoundingClientRect().left) < 1, true, "Kopf scrollt waagerecht mit");
eq(document.documentElement.scrollWidth <= innerWidth, true, "die Seite selbst scrollt nie waagerecht");
// Trenner
eq([sep.tabIndex, sep.getAttribute("aria-orientation"), sep.getAttribute("aria-valuenow")].join("/"), "0/vertical/61", "Trenner fokussierbar mit Wert");
eq(Math.abs(listW() / detailW() - 1.55) < 0.02, true, "Standard 1,55 : 1");
// ← : listW um 32 ± 1 kleiner; Ziehen ganz nach links: listW 360 ± 1; ganz nach rechts: detailW 300 ± 1;
// dblclick: wieder 1,55 : 1; während des Ziehens kein layout, danach genau eins mit 0.2 ≤ split ≤ 0.8
// Review Focus 4: body per CSSOM 1150 px breit, applyLayout({...split: 0.8}): detailW ≥ 300 und layoutMessage().split === 0.8
```

`tests/test_ui.py` bekommt `test_ui_check_page_narrow`: lädt `check.html#narrow` mit `--window-size=1000,800`. In diesem Modus prüft `check.js` nur:
- Der Trenner ist nicht sichtbar (`getComputedStyle(sep).display === "none"`).
- Das Detail steht unter der Liste.
- Die Seite scrollt nicht waagerecht.
- Danach Titel `PASS`.

- [ ] **Step 2:** `pytest tests/test_ui.py -q` → FAIL
- [ ] **Step 3:** umsetzen laut Interfaces.
- [ ] **Step 4:** `pytest tests/test_ui.py tests/test_i18n.py -q` → PASS
- [ ] **Step 5: Sichtprüfung:** `demo.html?cols=all#procs` und `demo.html#procs` mit 1600×1000 als Screenshot nach `$SCRATCH/task4/`, dazu `demo.html#procs` mit 1000×800. Alle drei mit `code -r` öffnen. Zu prüfen: Griffe, Marke und Trenner ruhig und im Stil, der Kopf sitzt über den Spalten.
- [ ] **Step 6: Kurzmessung** wie in Task 3 Step 7.
- [ ] **Step 7:** `pytest -q` und streng → grün
- [ ] **Step 8: Commit**

```bash
git add orbitop/ui/app.js orbitop/ui/style.css orbitop/locale/en.json orbitop/locale/de.json tests/ui/check.js tests/test_ui.py tests/ui/demo.js
git commit -m "feat: Spaltenbreite und Reihenfolge per Ziehen, waagerechtes Scrollen und Trenner zum Detail" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Eigenlast messen und im Budget halten

**Files:**
- Modify: `docs/superpowers/specs/2026-11-17-orbitop-prozessspalten-readme-release-design.md` (neuer Abschnitt „Messung Eigenlast (2026-11-17)“)
- Nur falls ein Hebel nötig ist: `orbitop/procs.py`, `orbitop/sampler.py`, `orbitop/app.py`, `orbitop/shell.py`, `orbitop/ui/app.js` mit Tests in `tests/test_procs.py`, `tests/test_sampler.py`, `tests/test_app.py`, `tests/ui/check.js`

**Interfaces:**
- Consumes: Messverfahren (Global Constraints), `layout.COLUMNS`.
- Hebel, nur wenn nötig, in dieser Reihenfolge, jeweils mit Test und neuer Messung:
  1. **Nur die Felder eingeblendeter Spalten senden:**
     - `Shell` gibt `self._layouts.current["hidden"]` (sonst `DEFAULT_HIDDEN`) über `Worker.update(hidden=…)` an `Sampler.snapshot_json(view, hidden)`.
     - `ProcTable.rows(now, drop: frozenset[str])` lässt die Felder ausgeblendeter Spalten weg: pri, nice, virt, shr, s, time, user, io, spark für last60, rss nur wenn ram und mem beide fehlen.
     - Immer bleiben pid, start, name, args, own, state, since und cpu (Suche, Filter, Auswahl, Rückfall-Sortierung).
     - Das Detail bleibt vollständig.
     - Test: `test_rows_drop_hidden_fields`.
  2. **`statm` nur lesen, wenn SHR eingeblendet ist:** Der `shr`-Schalter des Workers ist dann zusätzlich an `"shr" not in hidden` gebunden. Test in `test_procs_tick_reads_shr_only_when_procs_tab_visible`.
  3. **Beim Zeichnen nur geänderte Zellen anfassen und weniger Pufferzeilen halten:** `BUFFER_ROWS` von 12 auf 6, kein Neuaufbau unveränderter Zeilen. Die bestehenden Prüfungen der Virtualisierung bleiben grün.

- [ ] **Step 1: Messen** in vier Lagen, jede „kurz“ (60 s nach 60 s Aufwärmen):

  | Lage | Start |
  |---|---|
  | ausgeblendet | mit `--hidden` |
  | Übersicht sichtbar | ohne Zusatz |
  | Prozess-Reiter, Standardauswahl | `ORBITOP_TAB=procs` |
  | Prozess-Reiter, alle Spalten | `ORBITOP_TAB=procs` mit `cfg-all` |

  Den Prozess-Reiter mit allen Spalten zusätzlich „Dauer“ messen: nach 5 Minuten mit vollen Puffern. Fenster 1600×1000, wie in Stufe 1. Alle Zeilen der Ausgabe festhalten, auch die Aufteilung je Prozess aus stderr.
- [ ] **Step 2:** Alle Lagen im Budget: weiter mit Step 4. Sonst die Hebel der Reihe nach umsetzen, jeweils `pytest -q` und neu messen.
- [ ] **Step 3: STOP-Bedingung:** Reißt „alle Spalten“ das Budget auch nach allen drei Hebeln, wird am Aussehen nichts geändert. Die Task endet ohne weiteren Umbau mit der Messtabelle (alle Lagen, alle Stände) als Bericht an den Controller, der den User entscheiden lässt.
- [ ] **Step 4: Dokumentieren:** In der Spec einen Abschnitt „Messung Eigenlast (2026-11-17)“ anlegen, im Aufbau der Stufe-1-Tabelle:
  - Stand mit Commit
  - CPU in % eines Kerns, in Klammern PSS in MB
  - eine Spalte je Lage
  - die Aufteilung je Prozess
  - die angewandten Hebel
- [ ] **Step 5:** `pytest -q` und streng → grün
- [ ] **Step 6: Commit**: `perf: …` mit allen geänderten Dateien, falls Hebel nötig waren; danach `docs: Messung Eigenlast mit Prozessspalten (Standard und alle Spalten)` für die Spec.

---

### Task 6: Setup für mehrere Distributionen und Laufzeitprüfung je Distribution

**Files:**
- Modify: `scripts/setup-privileges.sh`, `orbitop/app.py`, `orbitop/locale/en.json`, `orbitop/locale/de.json`
- Test: `tests/test_setup_script.py`, `tests/test_app.py`

**Interfaces:**
- Produces (`orbitop/app.py`):
  - `RUNTIME = (("Gtk", "4.0"), ("WebKit", "6.0"))`
  - `PACKAGES: dict[str, tuple[str, ...]]`: je Paketmanager zuerst PyGObject, GTK 4 und WebKitGTK 6.0, dahinter weitere Laufzeitpakete der Distribution:
    - `"apt-get": ("python3-gi", "gir1.2-gtk-4.0", "gir1.2-webkit-6.0")`
    - `"dnf": ("python3-gobject", "gtk4", "webkitgtk6.0")`
    - `"pacman": ("python-gobject", "gtk4", "webkitgtk-6.0")`
    - `"zypper": ("python3-gobject", "typelib-1_0-Gtk-4_0", "typelib-1_0-WebKit-6_0", "python3-gobject-Gdk")`
    - Die Namen außer Debian prüft Task 7 im Container.
  - `INSTALL_HINT = {"apt-get": "sudo apt install {package}", "dnf": "sudo dnf install {package}", "pacman": "sudo pacman -S {package}", "zypper": "sudo zypper install {package}"}`
  - `package_manager(root: str = "/") -> str`:
    - Liest `etc/os-release`, sonst `usr/lib/os-release` relativ zu `root` (os-release(5)). Werte ohne Anführungszeichen.
    - Prüft `ID`, dann die Wörter von `ID_LIKE` der Reihe nach: `debian`/`ubuntu` → `apt-get`, `fedora`/`rhel`/`centos` → `dnf`, `arch` → `pacman`, `suse`/`opensuse` sowie `opensuse-*` → `zypper`.
    - Sonst `apt-get`.
  - `check_runtime(require_version=None, root: str = "/", version=sys.version_info) -> str | None`:
    - Zuerst `version < (3, 12)` → `error.python_old` mit `{version}` = `"3.11.2"`.
    - Dann `gi` → `PACKAGES[m][0]`, `Gtk` → `[1]`, `WebKit` → `[2]`.
    - Text `error.runtime_missing` mit `{package}` und `{command}` = `INSTALL_HINT[m].format(package=…)`.
- Locale:
  - `error.runtime_missing` = „orbitop braucht das Paket {package}. Installieren mit: {command}“ / „orbitop needs the package {package}. Install it with: {command}“
  - `error.python_old` = „orbitop braucht Python 3.12 oder neuer, gefunden: {version}.“ / „orbitop needs Python 3.12 or newer, found {version}.“
- Produces (`setup-privileges.sh`):
  - Paketmanager: der erste von `apt-get dnf pacman zypper`, den `command -v` im festen PATH findet.
  - Nur mit `--dry-run` wirkt `ORBITOP_PKG_MANAGER`, wie `ORBITOP_SYSROOT`. Erlaubt sind `apt-get|dnf|pacman|zypper|none`, alles andere zählt wie `none`.
  - Installationszeilen (Dry-Run: `WOULD: …`):
    - `apt-get install -y …`
    - `dnf install -y …`
    - `pacman -S --needed --noconfirm …`
    - `zypper --non-interactive install …`
  - Die Paketlisten sind gleich `PACKAGES`. Bei Intel-Grafik kommt dazu: apt-get `intel-gpu-tools`, dnf `igt-gpu-tools`, pacman `intel-gpu-tools`, zypper `igt-gpu-tools` (Task 7 prüft).
  - Unbekannt: kein Installationsbefehl, sondern die Zeile `No supported package manager found (apt-get, dnf, pacman, zypper). Install PyGObject, GTK 4 and WebKitGTK 6.0 yourself (Debian names: python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0), see README.md.`
  - Der Root-Helfer wird in jedem Fall installiert, Exit 0.
  - Ein Index wird nicht aufgefrischt (`apt-get update`, `pacman -Syu`). Das steht als eigener Befehl in der README und in der Containerprüfung.

- [ ] **Step 1: Failing tests**

```python
# tests/test_setup_script.py: dry_run(tree, *args, manager="apt-get") setzt ORBITOP_PKG_MANAGER
INSTALL = {"apt-get": "apt-get install -y", "dnf": "dnf install -y", "pacman": "pacman -S --needed --noconfirm",
           "zypper": "zypper --non-interactive install"}
INTEL_TOOL = {"apt-get": "intel-gpu-tools", "dnf": "igt-gpu-tools", "pacman": "intel-gpu-tools", "zypper": "igt-gpu-tools"}
# test_intel_plans_webkit_igt_without_setcap_by_default erwartet jetzt
#   "WOULD: apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 intel-gpu-tools"
@pytest.mark.parametrize("manager", list(INSTALL))
def test_installs_runtime_packages_per_manager(manager):
    line = f"WOULD: {INSTALL[manager]} {' '.join(app.PACKAGES[manager])}"
    assert line in dry_run("vm", manager=manager).splitlines()
    assert f"{line} {INTEL_TOOL[manager]}" in dry_run("intel-laptop", manager=manager).splitlines()
@pytest.mark.parametrize("manager", ["none", "rm -rf /"])
def test_unknown_manager_names_packages_and_still_installs_helper(manager):
    lines = dry_run("vm", manager=manager).splitlines()
    assert any("No supported package manager" in ln and "python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0" in ln and "README" in ln for ln in lines)
    assert lines[lines.index(HELPER_LINES[0]):][:2] == HELPER_LINES
    assert not any(ln.startswith(("WOULD: apt-get", "WOULD: dnf", "WOULD: pacman", "WOULD: zypper")) for ln in lines)
```

```python
# tests/test_app.py: bestehende check_runtime-Tests übergeben root=str(tmp_path) (ohne os-release → apt-get)
#   und erwarten format(package=…, command="sudo apt install …")
@pytest.mark.parametrize("text,where,manager", [
    ('ID=ubuntu\nID_LIKE=debian\n', "etc", "apt-get"), ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', "etc", "apt-get"),
    ('ID=fedora\n', "etc", "dnf"), ('ID=arch\n', "etc", "pacman"), ("ID='manjaro'\nID_LIKE=arch\n", "etc", "pacman"),
    ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n', "etc", "zypper"), ('ID=gentoo\n', "etc", "apt-get"),
    ('ID=fedora\n', "usr/lib", "dnf"), (None, None, "apt-get")])
def test_package_manager_from_os_release(tmp_path, text, where, manager): ...
def test_check_runtime_names_package_of_running_distro(tmp_path, monkeypatch):
    # etc/os-release "ID=fedora", WebKit fehlt, LANG=en_US.UTF-8
    assert check_runtime(req, root=str(tmp_path)) == load_texts("en")["error.runtime_missing"].format(
        package="webkitgtk6.0", command="sudo dnf install webkitgtk6.0")
def test_check_runtime_python_too_old(tmp_path, monkeypatch):        # Review Focus 5
    assert check_runtime(lambda *a: None, root=str(tmp_path), version=(3, 11, 2)) == \
        load_texts("en")["error.python_old"].format(version="3.11.2")
@pytest.mark.skipif(not shutil.which("python3.11"), reason="kein Python 3.11")
def test_python_3_11_gets_clear_message(tmp_path):                   # Review Focus 5 (Debian 12)
    code = f"import sys; sys.path.insert(0, {str(REPO)!r}); from orbitop.app import main; sys.exit(main([]))"
    r = subprocess.run(["python3.11", "-I", "-B", "-c", code], capture_output=True, text=True, cwd=tmp_path,
                       env={"LANG": "en_US.UTF-8", "PATH": "/usr/bin:/bin"})
    assert (r.returncode, "3.12" in r.stderr, "Traceback" in r.stderr) == (2, True, False), r.stderr
# test_without_pygobject_no_traceback erwartet app.PACKAGES[app.package_manager()][0] statt fest "python3-gi"
```

- [ ] **Step 2:** `pytest tests/test_setup_script.py tests/test_app.py -q` → FAIL
- [ ] **Step 3:** umsetzen laut Interfaces. Die Paketlisten im Skript tragen einen Kommentar, dass ein Test sie mit `orbitop/app.py` `PACKAGES` gleich hält.
- [ ] **Step 4:** `pytest tests/test_setup_script.py tests/test_app.py tests/test_i18n.py -q` → PASS, `test_shellcheck_clean` eingeschlossen.
- [ ] **Step 5:** `bash scripts/setup-privileges.sh --dry-run` auf dem Rechner (cwd `$SCRATCH/task6`, nie mit sudo) zeigt die apt-get-Zeile mit allen drei Paketen und `intel-gpu-tools`.
- [ ] **Step 6:** `pytest -q` und streng → grün
- [ ] **Step 7: Commit**

```bash
git add scripts/setup-privileges.sh orbitop/app.py orbitop/locale/en.json orbitop/locale/de.json tests/test_setup_script.py tests/test_app.py
git commit -m "feat: Setup erkennt apt-get, dnf, pacman und zypper; Laufzeitprüfung nennt Pakete der laufenden Distribution" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Prüfung in Docker-Containern

**Files:**
- Create: `scripts/check-distros.sh`, `docs/distro-check.md`
- Modify: `tests/test_setup_script.py` (shellcheck-Liste, Verweigern außerhalb eines Containers), `tests/test_gpu_tools.py` (Echttest braucht `/dev/dri/card1`)
- Nur wenn der Container es zeigt: `scripts/setup-privileges.sh`, `orbitop/app.py` `PACKAGES`, `tests/test_setup_script.py` `INTEL_TOOL`

**Interfaces:**
- Consumes: `setup-privileges.sh` und `PACKAGES` aus Task 6.
- Produces: `scripts/check-distros.sh` (klein, im Repository, damit die README-Angaben nachprüfbar sind):
  - **Rechner-Modus** `bash scripts/check-distros.sh [image …]`:
    - Standard-Images: `ubuntu:24.04`, `debian:trixie`, `fedora:latest`, `archlinux:latest`, `opensuse/tumbleweed`, `debian:bookworm`, `ubuntu:22.04`.
    - Je Image: `docker pull`, Digest über `docker image inspect --format '{{index .RepoDigests 0}}'`, dann `docker run --rm -v "<repo>:/src:ro" <image> bash /src/scripts/check-distros.sh --inside`.
    - Kein `--privileged`, keine weiteren Mounts, keine `--allow-*`.
    - Am Ende je Image eine Zeile `RESULT <image> <digest> <pass|fail> <erster fehlgeschlagener Schritt>`.
  - **`--inside`:**
    - Verweigert mit Exit 1, wenn `/.dockerenv` fehlt oder die uid nicht 0 ist. Die Meldung nennt „container“.
    - Schritte, jeder als `STEP <name> ok|fail`:
      1. Index auffrischen wie in der README: `apt-get update`, `pacman -Syu --noconfirm`, bei dnf und zypper nichts.
      2. `bash /src/scripts/setup-privileges.sh` echt als root, ohne Optionen.
      3. `python3 -c` mit `gi.require_version("Gtk","4.0")`, `gi.require_version("WebKit","6.0")`, `from gi.repository import Gtk, WebKit`.
      4. Testwerkzeuge installieren: pytest, shellcheck, desktop-file-utils, appstream mit den Namen der Distribution.
      5. Repository nach `/home/tester/orbitop` kopieren und `python3 -m pytest -q` als Benutzer `tester` (nicht root). Die Browser-Tests überspringen sich ohne Chrome selbst.
      6. `bash scripts/setup-privileges.sh --dry-run` als `tester`.
      7. `python3 bin/orbitop --version`.
    - Ausgabe der installierten Paketnamen und Versionen (Python, PyGObject, GTK, WebKitGTK) für die Ergebnisdatei.
  - `docs/distro-check.md` (Englisch, öffentlich lesbar): Datum, Docker-Version und eine Tabelle `| Distribution | Image | Digest | Date | Packages | Result |`. `Result` ist `pass` oder `fail (expected)` mit Schritt und Meldung. Darunter Hinweise je Distribution, etwa Fedora mit `VERSION_ID`. Task 8 liest diese Tabelle (Test).

- [ ] **Step 1: Failing tests**

```python
# tests/test_setup_script.py
def test_check_distros_refuses_outside_container(tmp_path):   # skip als root
    r = subprocess.run(["bash", str(ROOT / "scripts" / "check-distros.sh"), "--inside"], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 1 and "container" in r.stderr and "STEP" not in r.stdout
# test_shellcheck_clean prüft zusätzlich scripts/check-distros.sh
```

`tests/test_gpu_tools.py::test_real_intel_gpu_top_delivers_within_3s` überspringt sich zusätzlich ohne `/dev/dri/card1`. Im Container sind sysfs und `intel_gpu_top` da, das Gerät aber nicht; der Test meint nur den Referenzrechner.
- [ ] **Step 2:** `pytest tests/test_setup_script.py -q` → FAIL
- [ ] **Step 3:** `scripts/check-distros.sh` schreiben (SPDX-Kopf, `set -euo pipefail`, Argumentlisten, Quoting). → `pytest tests/test_setup_script.py tests/test_gpu_tools.py -q` → PASS
- [ ] **Step 4: Prüfung laufen lassen**, cwd `$SCRATCH/task7`:

```bash
bash <repo>/scripts/check-distros.sh 2>&1 | tee $SCRATCH/task7/check.log
```

Ergebnisse:
- Erwartet `pass` für Ubuntu 24.04, Debian 13, Fedora, Arch und openSUSE Tumbleweed.
- Erwartet `fail (expected)` für Debian 12 (Python 3.11: die Meldung aus Task 6) und Ubuntu 22.04 (kein WebKitGTK 6.0, kein Python 3.12).
- Schlägt eine erwartete `pass`-Distribution fehl, die Ursache am Log klären:
  - falscher Paketname → `PACKAGES`, Skript und `INTEL_TOOL` angleichen
  - Test, der eine Anzeige oder den Referenzrechner braucht → dort sauber überspringen, mit Begründung im Code
  - echter Fehler → beheben, mit Test
  - Danach erneut laufen lassen.
- Eine Distribution, die nach ehrlicher Ursachensuche nicht durchläuft, gilt als nicht unterstützt und steht so in der Ergebnisdatei.
- [ ] **Step 5:** `docs/distro-check.md` aus `check.log` schreiben: Digest, Datum, Paketzeile von `setup-privileges.sh` und Ergebnis je Distribution.
- [ ] **Step 6:** `pytest -q` und streng auf dem Rechner → grün
- [ ] **Step 7: Commit**

```bash
git add scripts/check-distros.sh docs/distro-check.md tests/test_setup_script.py tests/test_gpu_tools.py  # dazu ggf. setup-privileges.sh, orbitop/app.py
git commit -m "test: Containerprüfung für Ubuntu, Debian, Fedora, Arch und openSUSE mit Ergebnissen" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: README auf Englisch und Deutsch, Screenshots

**Files:**
- Modify: `README.md` (Englisch, neu geschrieben)
- Create: `README.de.md`, `docs/screenshot-overview.png`, `docs/screenshot-procs.png`, `tests/test_readme.py`
- Delete: `docs/screenshot.png` (danach unbenutzt)
- Lokal, **nie committen**: `CLAUDE.md`. Ergänzen: Verweis auf diesen Plan für den erweiterten Vertrag, `layout.json` und Live-Läufe mit `XDG_CONFIG_HOME` und `dbus-run-session`, `scripts/check-distros.sh`.

**Interfaces:**
- Consumes: `docs/distro-check.md` (Task 7), Messwerte aus der Spec (Task 5), `app.PACKAGES` (Task 6).
- Produces:
  - **Gegenseitige Links** in der ersten Zeile unter dem Titel: `README.md` hat `[Deutsch](README.de.md)`, `README.de.md` hat `[English](README.md)`.
  - **Abschnitte** in beiden Sprachen gleich und in der Reihenfolge der Spec:
    1. Was orbitop ist und wofür
    2. Funktionen
    3. Screenshots
    4. Tech-Stack-Analyse: Sprache und Bibliotheken; Oberfläche (GTK 4, WebKitGTK 6.0, Schema `orbitop://`, CSP); Datenquellen (`/proc`, `/sys`, hwmon, powercap, DRM-fdinfo, `intel_gpu_top`, `nvidia-smi`); Threads und Takte (`orbitop-worker` 1 s, `orbitop-procs` 2 s, Werkzeuge, langsame hwmon-Chips 5 s, `status` alle 10 s); Sicherheitsmodell (Schleuse `parse_message`, Root-Helfer, `lstat`-Kette, `pkexec`); Tests (pytest, Testbäume, Prüfseite im kopflosen Chrome, Containerprüfung); ein kleines Architekturbild in Text
    5. Voraussetzungen, mit Paketnamen je Distribution
    6. Installation je Distribution
    7. Rechte und Risiken (wie heute)
    8. Deinstallation
    9. Eigenlast (Zahlen aus Task 5, Standard und alle Spalten)
    10. Lizenz
  - **Installation:**
    - Herunterladen aus dem Release: `curl -LO …/releases/download/v0.1.0/orbitop-0.1.0.tar.gz` und `SHA256SUMS`, dann `sha256sum -c SHA256SUMS`, Entpacken an einen dauerhaften Ort (`~/.local/opt`), weil `install-user.sh` diesen Pfad einträgt.
    - Oder `git clone https://github.com/zappelmann-sketch/orbitop.git`.
    - Je geprüfter Distribution: Index auffrischen wie im Container (`sudo apt-get update`, Arch `sudo pacman -Syu`), `sudo bash scripts/setup-privileges.sh`, `bash scripts/install-user.sh`.
  - **Tabelle der unterstützten Distributionen** zwischen `<!-- supported:start -->` und `<!-- supported:end -->`: erste Spalte die geprüfte Distribution, wörtlich wie in `docs/distro-check.md`, zweite Spalte die abgeleiteten ohne eigenen Test (Linux Mint 22 und Pop!_OS 24.04 bei Ubuntu 24.04, Manjaro und EndeavourOS bei Arch Linux). Nicht unterstützt: Debian 12 und Ubuntu 22.04 mit Grund und Verweis auf `docs/distro-check.md`.
  - **Screenshots:** `docs/screenshot-overview.png` aus `tests/ui/demo.html` und `docs/screenshot-procs.png` aus `tests/ui/demo.html#procs`, beide 1600×1000. Darunter der Hinweis: Demodaten, Prozesse anonymisiert, Hardwarenamen vom Referenzlaptop.
  - Keine privaten Daten, keine E-Mail-Adresse außer den noreply-Adressen.

- [ ] **Step 1: Failing tests** in `tests/test_readme.py`

```python
def test_readmes_link_each_other():
    assert "[Deutsch](README.de.md)" in head(EN, 5) and "[English](README.md)" in head(DE, 5)
def test_readmes_mirror_each_other():
    assert len(headings(EN, "## ")) == len(headings(DE, "## ")) == 10 and len(headings(EN, "### ")) == len(headings(DE, "### "))
    assert code_blocks(EN) == code_blocks(DE)                     # gleiche Befehle in beiden Sprachen
def test_supported_distros_were_checked():                      # Anti-Ziel: nichts Ungeprüftes als unterstützt
    passed = {row[0] for row in table(CHECK) if row[-1] == "pass"}
    for text in (EN, DE):
        assert set(first_column(between(text, "<!-- supported:start -->", "<!-- supported:end -->"))) <= passed
def test_readmes_name_the_package_names():
    for m, names in app.PACKAGES.items(): assert all(n in EN and n in DE for n in names)
def test_no_old_screenshot_and_images_exist():
    assert not (REPO / "docs" / "screenshot.png").exists() and all((REPO / "docs" / f).stat().st_size > 0 for f in ("screenshot-overview.png", "screenshot-procs.png"))
```

`head`, `headings`, `code_blocks`, `table`, `between` und `first_column` sind kleine Hilfen in der Testdatei.
- [ ] **Step 2:** `pytest tests/test_readme.py -q` → FAIL
- [ ] **Step 3: Screenshots**, cwd `$SCRATCH/task8`:

```bash
google-chrome --headless=new --hide-scrollbars --window-size=1600,1000 --screenshot=$SCRATCH/task8/overview.png file://<repo>/tests/ui/demo.html
google-chrome --headless=new --hide-scrollbars --window-size=1600,1000 --screenshot=$SCRATCH/task8/procs.png "file://<repo>/tests/ui/demo.html#procs"
```

Beide mit `code -r` öffnen und auf anonymisierte Prozessnamen prüfen. Dann nach `docs/screenshot-overview.png` bzw. `docs/screenshot-procs.png` kopieren und `git rm docs/screenshot.png`.
- [ ] **Step 4:** `README.md` und `README.de.md` schreiben laut Interfaces. Danach `git grep -nIE '[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}' -- README.md README.de.md docs/distro-check.md`: Es dürfen nur die noreply-Adressen erscheinen.
- [ ] **Step 5:** `pytest tests/test_readme.py -q` → PASS
- [ ] **Step 6:** `CLAUDE.md` lokal ergänzen. `git status --ignored` zeigt sie als ignoriert.
- [ ] **Step 7:** `pytest -q` und streng → grün
- [ ] **Step 8: Commit**

```bash
git add README.md README.de.md docs/screenshot-overview.png docs/screenshot-procs.png tests/test_readme.py  # Löschung von docs/screenshot.png ist seit Step 3 vorgemerkt
git commit -m "docs: README auf Englisch und Deutsch mit Tech-Stack, Installation je Distribution und Screenshots" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Release v0.1.0 — **nur durch den Controller freigegeben**

> **Gate:** Diese Task beginnt erst, wenn der Controller Folgendes abgeschlossen und gemeldet hat:
> - Schluss-Review des ganzen Zweigs
> - Security-Audit (Skill `security-audit`, voller Modus) mit Fix-Welle
> - erneute Lastmessung, falls die Fix-Welle UI-, Sampler- oder Procs-Code geändert hat; dann sind Spec und README angeglichen
> - Merge von `prozess-spalten` in `main`
>
> Ohne diese Meldung: nicht anfangen.

**Files:**
- Modify: `data/io.github.zappelmann_sketch.orbitop.metainfo.xml` (`<release version="0.1.0" date="…">`)
- Release-Dateien nur in `$SCRATCH/task9/`, nie im Repository: `orbitop-0.1.0.tar.gz`, `SHA256SUMS`, `notes.md`

**Interfaces:**
- Consumes: `main` mit allem aus Task 1–8; `orbitop.__version__ == "0.1.0"`.
- Produces:
  - annotierter Tag `v0.1.0` auf `main`
  - GitHub-Release `v0.1.0` im privaten Repository `zappelmann-sketch/orbitop` mit `orbitop-0.1.0.tar.gz`, `SHA256SUMS` und einer Notiz auf Englisch und Deutsch

- [ ] **Step 1: Vorprüfung:**
  - `git switch main && git status --short` → leer (CLAUDE.md ist ignoriert).
  - `gh repo view zappelmann-sketch/orbitop --json visibility -q .visibility` → `PRIVATE`.
  - `pytest -q` und streng → grün.
  - `git grep -nIE '[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}'`: Jeder Treffer ist eine noreply-Adresse, eine Lizenz- bzw. Schriften-Kontaktadresse oder ein offensichtliches Testbeispiel. Sonst STOP und an den Controller melden.
- [ ] **Step 2: metainfo-Datum** auf den heutigen Tag (Tag des Release-Tags) setzen.
  - `appstreamcli validate --no-net data/io.github.zappelmann_sketch.orbitop.metainfo.xml` → ok.
  - `pytest tests/test_install.py -q` → grün.
  - Commit auf `main`:

```bash
git add data/io.github.zappelmann_sketch.orbitop.metainfo.xml
git commit -m "chore: Release 0.1.0 (Datum in der metainfo)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: Tag und Push:**
  - `git tag -a v0.1.0 -m "orbitop 0.1.0"`
  - `git push origin main v0.1.0`
  - `git cat-file -t v0.1.0` → `tag`.
- [ ] **Step 4: Paket und Prüfsummen**, cwd `$SCRATCH/task9`:

```bash
git -C <repo> archive --format=tar.gz --prefix=orbitop-0.1.0/ -o "$SCRATCH/task9/orbitop-0.1.0.tar.gz" v0.1.0
sha256sum orbitop-0.1.0.tar.gz > SHA256SUMS && sha256sum -c SHA256SUMS
tar -tzf orbitop-0.1.0.tar.gz | grep -cE 'CLAUDE|\.claude/|\.mcp\.json'   # erwartet 0
```

  Probe: In `$SCRATCH/task9/x/` entpacken, `python3 orbitop-0.1.0/bin/orbitop --version` → `orbitop 0.1.0`, `bash orbitop-0.1.0/scripts/setup-privileges.sh --dry-run` → Helfer-Zeilen (ohne sudo).
- [ ] **Step 5: Release-Notiz** `notes.md`, erst Englisch, dann Deutsch, je:
  - was orbitop ist (ein Satz)
  - Neues in 0.1.0: Prozessspalten wie `top`, einrichtbare Tabelle, Layout gespeichert, Setup für Debian/Ubuntu, Fedora, Arch, openSUSE
  - geprüfte Distributionen laut `docs/distro-check.md`
  - Installation: Verweis auf README, `sha256sum -c SHA256SUMS`
  - keine privaten Daten
- [ ] **Step 6: Release anlegen:**

```bash
gh release create v0.1.0 --repo zappelmann-sketch/orbitop --verify-tag --title "orbitop 0.1.0" \
  --notes-file "$SCRATCH/task9/notes.md" "$SCRATCH/task9/orbitop-0.1.0.tar.gz" "$SCRATCH/task9/SHA256SUMS"
```

- [ ] **Step 7: Nachprüfung:**
  - `gh release view v0.1.0 --repo zappelmann-sketch/orbitop --json assets -q '.assets[].name'` → beide Dateien.
  - `gh release download v0.1.0 --repo zappelmann-sketch/orbitop -D $SCRATCH/task9/dl && (cd $SCRATCH/task9/dl && sha256sum -c SHA256SUMS)` → OK.
  - Sichtbarkeit erneut `PRIVATE`.
  - Release-URL und Prüfsumme an den Controller melden.
