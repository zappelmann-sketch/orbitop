# orbitop – Prozess-Spalten, README und erstes Release (Design)

Stand: 2026-11-17 · Status: **vom User freigegeben** (2026-11-17), einschließlich Builder-Check.

Baut auf `docs/superpowers/specs/2026-11-16-orbitop-design.md` (Stufe 1) auf. Dessen Regeln gelten weiter, vor allem:
- Budget: ausgeblendet ≤ 3 % eines Kerns, sichtbar ≤ 9 %, PSS < 275 MB.
- Sicherheitsmodell: Seite → Python nur über `parse_message`, Seite unter `orbitop://ui/`, Root-Helfer nur root-eigen.
- Sichtbare Texte nur über `orbitop/locale/{en,de}.json`.
- `root`-Prinzip für alle Leser.
- Keine privaten Adressen.

## Wozu

**Prozess-Reiter.** Der User vergleicht den Reiter mit `top`. Dort sieht er je Prozess deutlich mehr: PID, USER, PR, NI, VIRT, RES, SHR, S, %CPU, %MEM, TIME+ und COMMAND. Er will diese Angaben auch in orbitop, damit er zu einem Prozess mehr erfährt. Außerdem will er die Ansicht selbst einrichten:
- Spalten verbreitern und schmaler machen
- Spalten per Ziehen umordnen
- Spalten ein- und ausblenden (Rechtsklick auf den Tabellenkopf; seine Wahl vom 2026-11-17)
- eine waagerecht scrollbare Tabelle, wenn viele Spalten sichtbar sind
- einen verschiebbaren Trenner zwischen Liste und Detailbereich, damit die Liste bei Bedarf mehr Platz bekommt

**README und Release.** Andere sollen orbitop installieren können, auf den wichtigsten Distributionen, auf denen es läuft. Dafür:
- je eine vollständige README auf Deutsch und auf Englisch: was das Werkzeug ist, wofür es da ist, Tech-Stack-Analyse und Installationsbefehle je Distribution
- ein erstes Release-Paket

## Ziele

1. **Neue Spalten wie in `top`.** Die Spalten aus `top` kommen zu den heutigen orbitop-Spalten dazu. Die heutigen sind: Prozess, CPU, Letzte 60 s, RAM, E/A, Zustand.
2. **Spalten ein- und ausblenden.** Ein Rechtsklick auf den Tabellenkopf öffnet ein Menü mit Häkchen. Dasselbe geht per Tastatur.
3. **Breite und Reihenfolge per Maus.** Die Spaltenbreite lässt sich ziehen, und Spalten lassen sich durch Ziehen des Kopfes umordnen. Ist die Summe der Breiten größer als der Platz, scrollt die Tabelle waagerecht.
4. **Trenner.** Ein ziehbarer Trenner sitzt zwischen Prozessliste und Detailbereich.
5. **Layout bleibt erhalten.** Spaltenauswahl, Reihenfolge, Breiten und die Trennerposition überstehen einen Neustart.
6. **README in zwei Sprachen.** `README.md` (englisch) und `README.de.md` (deutsch) sind inhaltlich gleich und gegenseitig verlinkt.
7. **Setup für mehrere Distributionen.** `scripts/setup-privileges.sh` funktioniert auf Debian/Ubuntu, Fedora, Arch und openSUSE, nicht nur mit `apt-get`.
8. **Erstes Release.** Release v0.1.0 im (weiter privaten) GitHub-Repository, mit Quellpaket und Prüfsummen.

## Nicht-Ziele

- Paketformate: `.deb`, `.rpm`, AUR oder Flatpak, außerdem der Update-Kanal. Das bleibt Stufe 2 mit eigener Design-Runde.
- Weitere Spalten über die `top`-Standardspalten hinaus, etwa PPID, Threads oder SWAP. PPID und Threads zeigt der Detailbereich schon.
- Filter je Spalte und mehrstufiges Sortieren.
- Distributionen mit Python < 3.12 oder ohne WebKitGTK 6.0.
- Das Repository öffentlich machen. Es bleibt privat (Entscheidung des Users). Die README ist trotzdem für die öffentliche Nutzung geschrieben (`git clone`, Release-Download über die normalen URLs); diese Befehle funktionieren, sobald der User das Repository öffentlich macht. Das Veröffentlichen ist ein eigener Schritt nur mit seinem ausdrücklichen OK.

## Anti-Ziele (Fehlschlag, auch wenn es technisch läuft)

- Das Budget wird gerissen, vor allem im Hintergrund: Heute sind es 2,8 % bei erlaubten 3 %, im Prozess-Reiter 8,3 % bei erlaubten 9 %.
- Die neue Layout-Nachricht öffnet die Schleuse für mehr als das Layout, etwa für freie Pfade, freie Schlüssel oder beliebige Größe.
- Etwas ist nur mit der Maus bedienbar.
- Systemdaten landen als HTML in der Seite.
- Die README nennt eine Distribution als unterstützt, die nicht geprüft wurde, oder enthält private Daten.

## Ansätze

| Frage | Gewählt | Verworfen |
|---|---|---|
| Viele Spalten | Auswahl per Rechtsklick, schlanker Standard (Wahl des Users) | Alle Spalten immer sichtbar: Last steigt dauerhaft, Tabelle unlesbar breit |
| Layout merken | Python schreibt eine Datei unter `~/.config/orbitop/`, die Seite meldet über die geprüfte Schleuse | `localStorage` der WebView: Die Seite schreibt bewusst nichts auf die Platte, die Sitzung ist ephemer. Gar nicht merken: Jeder Neustart würde die Einrichtung verwerfen |
| SHR | `statm` nur lesen, solange der Prozess-Reiter sichtbar ist | Immer lesen: zusätzliche Datei je Prozess alle 2 s auch im Hintergrund, dort fehlt der Spielraum. Weglassen: Der User will die `top`-Spalten |
| Andere Distributionen | Das Setup-Skript erkennt den Paketmanager | Nur README-Befehle: Das Skript bricht heute mit `apt-get` ab, bevor es den Root-Helfer installiert |
| Release-Paket | Quellpaket als GitHub-Release, unabhängig von der Distribution („erstmal“) | `.deb` jetzt: gehört mit Root-Helfer und polkit in die Paket-Runde von Stufe 2 |

## Entwurf

### Daten (Python)

Die Zeile eines Prozesses (`ProcRow`) bekommt neue Felder. Fast alles steht in der Zeile `/proc/<pid>/stat`, die orbitop schon je Prozess liest. Dafür ist kein zusätzlicher Dateizugriff nötig.

| Feld | Bedeutung | Quelle |
|---|---|---|
| `pri` | Priorität (PR) | stat Feld 18 |
| `nice` | Nice-Wert (NI) | stat Feld 19 |
| `virt` | virtueller Speicher in Bytes (VIRT) | stat Feld 23 |
| `s` | Zustandsbuchstabe des Kernels (S) | stat Feld 3, schon gelesen |
| `time` | verbrauchte CPU-Zeit in Sekunden (TIME+) | (utime + stime) / CLK_TCK, schon gelesen |
| `shr` | gemeinsam genutzter Speicher in Bytes (SHR) | `/proc/<pid>/statm` Feld 3 × Seitengröße |

Zu `shr`:
- `shr` ist `null`, solange der Prozess-Reiter nicht sichtbar ist. Dazu zählt auch ein ausgeblendetes Fenster, wenn der Prozess-Reiter darin gewählt ist. Die Seite zeigt dann „–“.
- Der Sampler kennt den sichtbaren Reiter schon aus der `view`-Nachricht.

Was sonst gilt:
- Die Spalte RES ist das bisherige Feld `rss`.
- %MEM rechnet die Seite aus `rss` und dem Gesamtspeicher, der im Schnappschuss schon enthalten ist.
- Der Schnappschuss-Vertrag im Plan („Global Constraints“) wird um diese Felder ergänzt.

### Spalten

| id | Kopf | Erklärung im Tooltip (de/en) | Standard |
|---|---|---|---|
| `pid` | PID | Prozessnummer | sichtbar |
| `process` | Prozess | Name und Argumente (COMMAND) | sichtbar, nicht ausblendbar |
| `user` | Benutzer | Eigentümer | sichtbar |
| `cpu` | CPU | wie heute | sichtbar |
| `last60` | Letzte 60 s | wie heute | sichtbar |
| `ram` | RAM | belegter Arbeitsspeicher (RES), wie heute | sichtbar |
| `io` | E/A | wie heute | sichtbar |
| `state` | Zustand | orbitop-Einstufung, wie heute | sichtbar |
| `pri` | PR | Priorität | aus |
| `nice` | NI | Nice-Wert | aus |
| `virt` | VIRT | virtueller Speicher | aus |
| `shr` | SHR | gemeinsam genutzter Speicher | aus |
| `s` | S | Kernel-Zustand (R, S, D, Z, T, I …) | aus |
| `mem` | %MEM | Anteil am Arbeitsspeicher | aus |
| `time` | TIME+ | verbrauchte CPU-Zeit | aus |

Reihenfolge und Darstellung:
- Die Grundreihenfolge entspricht der Tabelle. Die heutige Reihenfolge bleibt damit erhalten; neu sind PID vorn und Benutzer hinter Prozess.
- Eine eingeblendete Spalte erscheint an ihrem Platz in der Gesamtreihenfolge, die neuen also zunächst hinten. Orbitop führt intern eine Reihenfolge aller Spalten und daneben, welche ausgeblendet sind.
- Die Köpfe verwenden die `top`-Kürzel, die Tooltips erklären sie in der Sprache der Oberfläche.
- Zahlen stehen rechtsbündig. Speicherwerte erscheinen mit Einheit wie die heutige RAM-Spalte, TIME+ als `m:ss.hh` wie in `top`.
- Sortieren per Klick auf den Kopf geht für jede Spalte.

### Bedienung

**Menü zum Ein- und Ausblenden:**
- Es öffnet sich per Rechtsklick auf einen Spaltenkopf. Per Tastatur: Kontextmenü-Taste oder Umschalt+F10 auf einem fokussierten Kopf.
- Inhalt: ein Häkchen je Spalte (Prozess fest an), ein Trennstrich, dann für die angeklickte Spalte „Nach links“ und „Nach rechts“, zuletzt „Standard wiederherstellen“.
- Bedienung mit Pfeiltasten, Eingabe und Escape. Ein Klick daneben schließt das Menü.

**Breite:**
- Jede Kopfzelle hat am rechten Rand einen Griff zum Ziehen.
- Mindestbreite 40 px, für Prozess 120 px.
- Doppelklick auf den Griff stellt die Standardbreite wieder her.
- Per Tastatur: Alt+← und Alt+→ auf einem fokussierten Kopf ändern die Breite um 16 px.

**Umordnen:**
- Den Kopf waagerecht ziehen. Erst ab 6 px Bewegung gilt das als Ziehen, sonst bleibt es ein Klick zum Sortieren.
- Eine Einfügemarke zeigt, wo die Spalte landet.
- Per Tastatur geht das über die Menüpunkte „Nach links“ und „Nach rechts“.

**Scrollen:**
- Die Tabelle ist so breit wie die Summe der sichtbaren Spaltenbreiten.
- Ist sie breiter als der Bereich, scrollt sie waagerecht. Der Kopf bleibt oben stehen und scrollt waagerecht mit.
- Das senkrechte Virtualisieren der Zeilen bleibt.

**Trenner:**
- Eine senkrechte Leiste zwischen Liste und Detailbereich, mit der Maus ziehbar.
- Per Tastatur fokussierbar (`role="separator"`). ← und → verschieben ihn um 32 px.
- Doppelklick stellt das heutige Verhältnis 1,55 : 1 wieder her.
- Grenzen: Die Liste ist mindestens 360 px breit, der Detailbereich mindestens 300 px.
- Unter 1100 px Fensterbreite stapelt sich das Layout wie heute, der Trenner ist dann ausgeblendet.

**Aussehen:** Griffe, Einfügemarke und Trenner im bestehenden Stil. Ruhig, beim Ziehen und bei Fokus im vorhandenen Cyan-Akzent. Keine neuen Farben, keine Animationen außer der Rückmeldung beim Ziehen.

### Layout speichern

**Nachricht von der Seite an Python:**

```
{"type": "layout", "order": [id, …], "hidden": [id, …], "widths": {id: int, …}, "split": float}
```

**`parse_message` prüft streng:**
- Die ids stammen nur aus einer festen Liste. Python und Seite verwenden dieselben ids, ein Test hält beide gleich.
- `order` ist eine Permutation aller ids.
- `hidden` enthält nie `process`.
- Breiten sind ganzzahlig, von 40 bis 1200.
- `split` liegt zwischen 0,2 und 0,8 und ist der Anteil der Liste an der Breite.
- Alles andere wird verworfen.

**Python speichert die Datei:**
- Ziel ist `$XDG_CONFIG_HOME/orbitop/layout.json`, Standard `~/.config/orbitop/layout.json`.
- Geschrieben wird atomar: erst eine temporäre Datei im selben Verzeichnis, dann `os.replace`.
- Python schreibt nur, wenn sich etwas geändert hat.
- Die Seite meldet erst am Ende eines Ziehens, höchstens einmal je 500 ms.

**Beim Start:**
- Python liest die Datei und prüft sie mit derselben Funktion.
- Ist sie gültig, geht sie in der `init`-Nachricht mit. Fehlt sie oder ist sie kaputt, gilt der Standard.
- Kennt die Datei eine id nicht mehr, entfällt sie. Fehlt eine id, etwa nach einem Update mit neuer Spalte, kommt sie an ihren Standardplatz.

### Eigenlast

**Was hinzukommt:**
- Die neuen Felder kommen aus der schon gelesenen stat-Zeile.
- Die einzige neue Leseoperation ist `statm`, und auch die nur bei offenem Prozess-Reiter.
- Im Prozess-Reiter steigen JSON-Menge und Zeichenarbeit mit der Zahl der Felder und der sichtbaren Spalten.

**Messung nach dem Bau:**
- Mit `scripts/measure-load.py` wie in Stufe 1, in drei Lagen: ausgeblendet, Übersicht sichtbar, Prozess-Reiter mit **allen** Spalten eingeblendet.
- Das Budget bleibt unverändert.

**Das Budget gilt für beide Fälle:** für die Standardauswahl und für alle eingeblendeten Spalten (Entscheidung des Planers nach dem Builder-Check).

**Hebel, falls das Budget reißt** (in dieser Reihenfolge):
1. nur die Felder eingeblendeter Spalten senden
2. `statm` nur lesen, wenn SHR eingeblendet ist
3. beim Zeichnen nur geänderte Zellen anfassen und weniger Pufferzeilen außerhalb des Sichtbereichs halten

Reicht das für „alle Spalten“ nicht, wird nichts am Aussehen geändert. Die Arbeit hält dann an, und der User bekommt die Messtabelle zur Entscheidung, wie in Stufe 1.

### Mehrere Distributionen

**`setup-privileges.sh`:**
- Das Skript erkennt den Paketmanager: `apt-get`, `dnf`, `pacman` oder `zypper`, gesucht im festen PATH.
- Es installiert die Laufzeitpakete mit den Namen dieser Distribution. Die Intel-Werkzeuge kommen nur bei einer Intel-GPU dazu.
- Bei unbekanntem Paketmanager nennt es die nötigen Pakete und verweist auf die README. Den Root-Helfer installiert es trotzdem.
- Der Dry-Run zeigt die Installationszeile.
- Für Tests lässt sich der Paketmanager über eine Variable festlegen. Sie wirkt nur im Dry-Run, wie heute `ORBITOP_SYSROOT`.

**`check_runtime`** nennt fehlende Pakete mit den Namen der laufenden Distribution. Grundlage ist `ID`/`ID_LIKE` aus `/etc/os-release`. Ist die Distribution unbekannt, nennt es die Debian-Namen.

**Prüfung in Docker-Containern.** Geprüft werden:

| Distribution | Bemerkung |
|---|---|
| Ubuntu 24.04 | |
| Debian 13 | |
| Fedora | aktuelle Version |
| Arch Linux | |
| openSUSE Tumbleweed | |
| Debian 12 | Gegenprobe, erwartet: nicht lauffähig |
| Ubuntu 22.04 | Gegenprobe, erwartet: nicht lauffähig |

Je Container:
1. Pakete wie in der README installieren, also `setup-privileges.sh` echt als root ausführen. Der User hat das am 2026-11-17 erlaubt, aber **nur** in wegwerfbaren Containern: `docker run --rm`, ohne `--allow-*`-Optionen, ohne Zugriff auf den Rechner außer einer schreibgeschützten Kopie des Repositorys. Auf dem echten Rechner gilt weiter: nur `--dry-run`.
2. Gtk 4 und WebKit 6.0 über `gi` importieren.
3. `pytest` ohne die Browser-Tests laufen lassen.
4. `setup-privileges.sh --dry-run` ausführen.

Nur was dort durchläuft, nennt die README als unterstützt. Abgeleitete Distributionen erscheinen mit ihrer Basis, ohne eigenen Test, zum Beispiel Linux Mint 22 und Pop!_OS 24.04 (Ubuntu 24.04) sowie Manjaro und EndeavourOS (Arch).

### README

**Dateien:** `README.md` (englisch) und `README.de.md` (deutsch), gleicher Inhalt, oben gegenseitig verlinkt.

**Abschnitte:**
1. Was orbitop ist und wofür
2. Funktionen
3. Screenshots: Übersicht und Prozess-Reiter, aus der Demoseite, anonymisiert
4. Tech-Stack-Analyse:
   - Sprache und Bibliotheken
   - Oberfläche (GTK 4, WebKitGTK 6.0, eigenes Schema, CSP)
   - Datenquellen: `/proc`, `/sys`, hwmon, powercap, DRM-fdinfo, `intel_gpu_top`, `nvidia-smi`
   - Threads und Takte
   - Sicherheitsmodell (Schleuse, Root-Helfer, pkexec)
   - Tests
   - ein kleines Architekturbild in Text
5. Voraussetzungen
6. Installation je Distribution: Befehle, aus dem Release-Paket oder per `git clone`
7. Rechte und Risiken (wie heute)
8. Deinstallation
9. Eigenlast
10. Lizenz

**Regeln:**
- Keine privaten Daten.
- Hardwarenamen im Screenshot nur vom Referenzlaptop, wie bisher.

### Release

- Version 0.1.0. Sie steht schon in `orbitop/__init__.py` und in der metainfo; das Datum in der metainfo wird auf den Release-Tag gesetzt.
- Annotierter Tag `v0.1.0` auf `main`.
- GitHub-Release im privaten Repository mit:
  - `orbitop-0.1.0.tar.gz`: der ganze Stand des Tags aus `git archive`
  - `SHA256SUMS`
  - kurzer Release-Notiz auf Englisch und Deutsch
- Das Release entsteht erst nach der Schlussprüfung.

### Ablauf

Wie in Stufe 1, gesteuert über Subagenten:
1. Plan schreiben.
2. Je Task: Implementer, danach Review mit Code-Review, Security und totem Code.
3. Schluss-Review des ganzen Zweigs mit dem stärksten Modell.
4. Security-Audit mit dem Skill security-audit, danach eine Fix-Welle.
5. Lastmessung.
6. Merge in `main`, Push, Release.

Der Zweig heißt `prozess-spalten` und beginnt auf `main` `1c86566`.

### Dem Bauenden überlassen

- DOM-Aufbau von Menü, Griffen und Trenner
- Details der Pointer-Events
- genaue Pixel von Griff und Einfügemarke
- Aufbau der Tests
- Container-Images und Befehle der Prüfung
