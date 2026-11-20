# orbitop: Umbau und Version 0.3.0

Stand: 2026-11-19. Baut auf der Spec von Stufe 2 auf (`2026-11-18-orbitop-stufe-2-pakete-update-kanal-design.md`, im Folgenden „Stufe-2-Spec“), vor allem auf deren Abschnitten 6.2, 6.3 und 14.

## Wozu

0.2.0 ist veröffentlicht. Zwei Rechner beziehen orbitop aus der eigenen Paketquelle: das Notebook des Users und der Rechner eines Kollegen. Diese Runde endet mit Version 0.3.0. Die Version kommt über den Update-Kanal, ist also dessen erster echter Test.

0.3.0 bringt, was die Stufe-2-Spec für diese Version vorsieht. Der User will, dass orbitop mit jeder Grafik voll funktioniert, und zwar mit so wenig Angriffsfläche wie möglich:
- Fehlende Intel-Werkzeuge lassen sich aus orbitop heraus installieren.
- Die gesperrten Messzähler (Grafik-Zähler über `intel_gpu_top`, Energiezähler des CPU-Pakets) lassen sich per Schalter mit Admin-Passwort freigeben und wieder sperren.

Vorher kommt ein Umbau, wie der User am 2026-11-18 beschlossen hat. Grund ist die globale Regel „Modularer, kleiner Code“: Je Datei gibt es eine Aufgabe, Richtwert sind höchstens etwa 300 Zeilen. `ui/app.js` hat heute 1378 Zeilen. Dazu kommen die Punkte, die Review, Audit und Release von 0.2.0 geparkt haben, und die Rückmeldung aus der ersten fremden Installation (Issue #1).

Erfolg heißt:
- Auf dem Notebook des Users und beim Kollegen erscheint 0.3.0 in der normalen Aktualisierung und installiert sich ohne Handgriffe.
- Danach blendet ein Schalter in orbitop die Freigabe ein und aus, jedes Mal nach dem Admin-Passwort. Die Hinweise zeigen auf diesen Schalter und lassen sich ausblenden.
- Auf einem Intel-Rechner ohne `intel_gpu_top` installiert ein Knopf das Werkzeug über die Paketverwaltung.
- Der Code ist modular, und das Verhalten der Oberfläche hat sich durch den Umbau nicht geändert.

## Entscheidungen des Users

Bestehende, weiter gültig: die Entscheidungen 1 bis 9 der Stufe-2-Spec. Besonders wichtig:
- Die Freigabe kommt nie von uns aus.
- Vor ihrem Bau gibt es eine Security-Runde: prüfen, bewerten, dann bauen. Vorgabe ist „absolut safe“, „stark geschützt“, so wenig Angriffsfläche wie möglich.
- Ein root-Lesedienst gehört nicht in diese Runde.

Neu am 2026-11-19:
1. Diese Runde reicht bis zum Release 0.3.0: Umbau, Security-Runde, Bau, Release und Umstieg auf dem Notebook.
2. Der User hat dem Planer die folgenden Vorschläge überlassen („mach es mit deinen eigenen Vorschlägen“). Sie gelten damit als entschieden:
   - Eine Spec für die ganze Runde, danach zwei Pläne: zuerst der Umbau, dann 0.3.0, sobald das Dokument der Security-Runde vorliegt.
   - Die Security-Analyse läuft parallel zum Umbau. Sie liest nur und schreibt ihr eigenes Dokument.
   - Es gibt **einen** Schalter „Messzähler freigeben“ für beide Freigaben. Er schaltet nur, was der Rechner hat.
   - Die Hinweise aus Issue #1 zeigen auf den Schalter und lassen sich ausblenden.
3. Nach dem Builder-Check, beide am 2026-11-19:
   - **Testversion vor dem Release** (Teil D): Schalter und Knopf werden mit einer Testversion auf dem Notebook auf echter Hardware geprüft, bevor 0.3.0 veröffentlicht wird.
   - **„An“ ist eine Regel für den ganzen Rechner:** Was später dazukommt, wird mit freigegeben, etwa ein später installiertes `intel_gpu_top`.
4. Der Ablauf bleibt wie gewohnt:
   - eigener Worktree;
   - Subagenten nur mit Opus;
   - nach jedem Bauschritt Review und Security-Audit;
   - Schlussprüfung des ganzen Zweigs;
   - Merge, Push und Release erst nach dem Go des Users;
   - den Release-Lauf startet der User selbst im Terminal.

## Ziele, Nicht-Ziele, Anti-Ziele

**Ziele**
- Umbau ohne Änderung des Verhaltens: `app.js` als ES-Module, Kachelbau aus `sampler.py` in `tiles.py`, `style.css` nach Bereichen. Dazu werden die großen Testdateien aufgeteilt (Teil A).
- Die geparkten Punkte aus 0.2.0 sind behoben oder entschieden (Teil A).
- Ein Dokument der Security-Runde bewertet Knopf, Schalter, Helfer und Paket-Auslöser (Teil B).
- 0.3.0 enthält: den Knopf „Installieren“, den Schalter „Messzähler freigeben“, ausblendbare Hinweise, Paket-Auslöser, Rücknahme bei Deinstallation, README und Matrix (Teil C).
- Release 0.3.0 über den Update-Kanal und Umstieg der Freigabe auf dem Notebook (Teil D).

**Nicht-Ziele**
- Der root-Lesedienst für volle Intel-Werte ohne Freigabe.
- Ein Knopf für NVIDIA-Treiber. Den Treiber wählt der Benutzer, der Hinweis erklärt den Weg.
- Neue Distributionen, ARM.
- Neue Funktionen der Oberfläche über das hier Genannte hinaus.
- Ein Build-Schritt oder npm für die Oberfläche.

**Anti-Ziele**, die das Ergebnis auch dann zum Fehlschlag machen, wenn es technisch läuft:
- Eine Freigabe, die ohne ausdrückliches Einschalten durch einen Admin aktiv wird. Das gilt auch nach Updates, Neuinstallation oder Umstieg.
- Ein root-Helfer, der Pfade, freie Argumente oder Text von der Seite oder vom Benutzer annimmt.
- `auth_admin_keep`, `yes` oder eine andere polkit-Regel, die das Passwort spart, für orbitops eigene polkit-Actions. Die Regel von PackageKit fürs Installieren (upstream `allow_active=auth_admin_keep`, auf Ubuntu ergänzt durch eine eigene Regel der Distribution) gehört der Distribution. orbitop ändert sie nicht, denn ein Paket ändert keine Dateien anderer Pakete (Stufe-2-Spec). Die Security-Runde beschreibt sie je Distribution (Wahl des Planers).
- Ein Hinweis, der sich ausblenden, aber nie wieder einblenden lässt.
- Ein Umbau, der Aussehen oder Verhalten ändert. Was sich ändert, ist ein Fehler im Umbau.
- Persönliche Daten in Repo, Paketen, Paketquelle oder Bildern.

## Wege

Die folgenden Wege hat der User dem Planer überlassen und mit „mach es mit deinen eigenen Vorschlägen“ bestätigt.

**Schalter**
- **Ein Schalter für beide Freigaben (gewählt).** Er schaltet je Rechner nur, was es gibt: die Grafik-Zähler bei Intel-Grafik mit installiertem `intel_gpu_top`, die Energiezähler, wenn RAPL-Zonen da sind (Intel und AMD). Beide Freigaben haben dasselbe Risiko (CVE-2020-8694). Eine Passwortabfrage, einfache Bedienung.
- **Zwei Schalter:** feiner, etwa „Grafik ja, CPU-Leistung nein“. Nicht gewählt, weil das Risiko gleich ist und die Bedienung doppelt.

**Module der Oberfläche**
- **ES-Module ohne Build-Schritt (gewählt).** Das ist der übliche Weg in JavaScript (globale Regel). Die Seite lädt `<script type="module">`, die CSP bleibt bei `script-src 'self'`.
- **Klassische Skripte mit einem gemeinsamen Namensraum:** nur als Rückfall, wenn Module unter `orbitop://` oder in den Chrome-Tests technisch nicht laden. Dann entscheidet der User vorher.
- **Bundler:** verworfen. Er bringt einen Build-Schritt und Abhängigkeiten aus npm ins Paket.

**Ablauf**
- **Security-Analyse parallel zum Umbau (gewählt).** Die Analyse fasst keinen Code an, der Umbau ändert kein Verhalten. Beide berühren sich nicht.
- Nacheinander wäre sicherer gegen Verwechslungen, aber langsamer. Das bringt keinen Gewinn, weil die Analyse nur liest.

## Design

### Teil A: Umbau und geparkte Punkte (Plan 1)

**A1. Erste Aufgabe: Probe für ES-Module.** Bevor etwas aufgeteilt wird, zeigt eine kleine Probe, dass Module laden. Geprüft wird an zwei Stellen:
1. in der laufenden App unter `orbitop://` (WebKitGTK 6.0), mit eigener D-Bus-Sitzung und eigenem `XDG_CONFIG_HOME`;
2. in den Chrome-Tests (`tests/test_ui.py`, heute `file://`).

Erwartete Stellschrauben:
- In WebKitGTK das Schema als CORS-fähig registrieren (`WebKitSecurityManager`). Die Auslieferung muss weiter auf `orbitop/ui/` beschränkt bleiben, und die Seite darf nur reguläre Dateien bekannten Typs nachladen (`ui_file`).
- In den Tests ein lokaler HTTP-Server nur auf `127.0.0.1` mit dem Testverzeichnis, oder eine Startoption von Chrome.

Die Wahl trifft der Builder. Scheitert beides, hält die Arbeit an, und der User entscheidet über den Rückfall.

**A2. `app.js` in ES-Module.**
- Die Grenzen folgen den bestehenden Abschnitten:
  - Texte und Zahlen
  - DOM-Hilfen
  - Lastzeile
  - Kacheln
  - Fußzeile
  - Prozessliste
  - Spalten-Layout
  - Ziehen
  - Spaltenmenü
  - Dialoge
  - Brücke zu Python
- Abhängigkeiten laufen in eine Richtung; Zustand lebt in klar umgrenzten Modulen, nicht in globalen Variablen.
- Jede Datei hat höchstens etwa 300 Zeilen. `chart.js` wird Modul wie die anderen.
- Die Sicherheitsregeln bleiben:
  - Alles aus Schnappschuss und Texten kommt per `textContent` ins DOM.
  - Es gibt keine Inline-Stile.
  - `terminate` sendet genau eine Stelle, und nur der Bestätigungsknopf ruft sie auf. Der Test dafür liest künftig das Modul, das sie enthält.
- `tests/ui/check.js` (1078 Zeilen) wird entlang derselben Module aufgeteilt. `demo.html` und `check.html` laden die Module.

**A3. `tiles.py`.**
- Der Kachelbau zieht aus `sampler.py` in ein eigenes Modul: `_tile`, `_cpu_tile` bis `_disk_tile` und die Formathilfen `_num`, `_kv` usw. Er wird zu Funktionen, die Werte und Verläufe bekommen und Kacheln liefern.
- `sampler.py` behält Lesen, Raten und Verläufe.
- Der Schnappschuss-Vertrag (`tick`) bleibt Byte für Byte gleich. Ein Test vergleicht den JSON-Schnappschuss eines Testbaums vor und nach dem Umbau.

**A4. `style.css` nach Bereichen.**
- Aufgeteilt wird in mehrere Dateien: Grundlagen und Farben, Kopf- und Lastzeile, Kacheln, Prozesse, Dialoge. `index.html` bindet sie mit mehreren `<link>` ein.
- Die Auflösung der Regeln bleibt gleich: gleiche Reihenfolge, keine neuen Selektoren.

**A5. Große Testdateien.**
- Tests über etwa 400 Zeilen werden nach Themen aufgeteilt: `test_sampler.py` (1007 Zeilen), `test_app.py`, `test_shell.py`, `test_procs.py`, `test_sensors.py` und `test_actions.py`.
- Dateien zwischen 300 und 400 Zeilen werden aufgeteilt, sobald diese Runde etwas hinzufügt. Das betrifft etwa `test_gpu_tools.py` und `test_gpu.py`.
- Vorher und nachher gilt dieselbe Zahl an Tests mit denselben Namen. Ein Vergleich der gesammelten Test-IDs belegt das.

**A6. Belege für „gleiches Verhalten“.**
- beide vollen pytest-Läufe und die Chrome-Prüfseite grün;
- Screenshots von Übersicht und Prozess-Reiter mit den anonymisierten Demo-Daten vor und nach dem Umbau, pixelgleich oder mit erklärten Unterschieden;
- Eigenlast nach dem Messverfahren, im Wechsel mit dem Stand vor dem Umbau.

**A7. Geparkte Punkte aus 0.2.0.** Die vollständige Liste stammt aus dem Ledger von 0.2.0.
1. **Eigenlast ausgeblendet**:
   - Gemessen am 2026-11-19: 3,07 bis 3,17 % statt höchstens 3 %. 0.1.0 lag gleich (3,08 %).
   - Aufteilung: orbitop ≈ 1,9 % und `intel_gpu_top` ≈ 1,2 %; am 2026-11-17 waren es 1,78 % und 1,03 %.
   - Die Ursache wird untersucht.
   - Liegt sie in orbitop, wird sie behoben. Liegt sie in `intel_gpu_top` selbst, bekommt der User die Messtabelle mit den Möglichkeiten und entscheidet. Möglich wäre etwa, `intel_gpu_top` bei ausgeblendetem Fenster anzuhalten, dafür fehlt dann dort der Verlauf.
2. **Matrix:** Kurze Netzaussetzer der Spiegel (Fedora „Curl error (56)“, connection reset) werden wiederholt oder eigens eingestuft, statt als `fail` zu zählen. Ein echter Fehler des Pakets muss weiter `fail` bleiben; Tests zeigen beides.
3. **Release-Skript:**
   - `check_origin` prüft auch die Fetch-Adressen.
   - Die Bauten nehmen den festgehaltenen Commit statt `HEAD` (`tracked_files`).
   - Der gh-Stub lehnt `--notes-from-tag` mit `--repo` in jeder Reihenfolge ab.
   - Der Trockenlauf prüft die Identität im gh-pages-Worktree.
   - `release_stub.run()` erbt keine Autor-Variablen aus der Shell.
4. **Alle externen Aufrufe** von Release-Skript und Matrix (gh, curl, git, docker) werden einmal gefahrlos gegen die installierten Versionen geprüft, so wie nach dem Abbruch in Lauf 1 von 0.2.0.
5. **Kleinigkeiten:**
   - Kommentar in `tests/test_rpm_same.py:45`;
   - Kommentar in `packaging/container-prologue.sh`;
   - der Test der vertrauenswürdigen Datei prüft das Artefakt statt des Quelltexts;
   - der K3-Wächter erkennt auch Alternativen (`foo | orbitop-apt-source`);
   - `build-inside.sh` hinterlässt außerhalb eines Containers keine Schlüsseldatei;
   - der apt-`Release` nennt nur SHA256 und SHA512, falls apt und die Matrix das zulassen.
6. **App:**
   - Schreibfehler bei Autostart und Layout werden einmal auf stderr gemeldet statt still verworfen;
   - `HOME=""` und die Mischung aus XDG-Umgebung und `os.environ` in `config_home` werden geklärt;
   - `makedirs` legt alle neuen Ebenen mit 0700 an.

   Dass der Admin-Dialog keinen Prozessnamen zeigt, bleibt so, wie es die Stufe-1-Spec hinnimmt.

Was beim Schlüsselwechsel zu tun ist (N1, Übergangs-Release), gehört nicht in diese Runde. Es bleibt in der Doku und in der Memory vermerkt.

### Teil B: Security-Runde (parallel zu Plan 1)

**B1. Ergebnis.** Das Ergebnis ist ein Dokument `docs/superpowers/specs/2026-11-19-orbitop-0.3.0-security-runde.md`. Es entsteht vor jedem Code für Knopf und Schalter und enthält:
- das Bedrohungsmodell: Wer greift an (lokales Konto, Prozess des Benutzers, kompromittierte Seite in der WebView, manipuliertes Paket eines Spiegels), was ist zu schützen, wo liegen die Vertrauensgrenzen;
- je Baustein eine Bewertung mit Fundstellen in den offiziellen Quellen (polkit, PackageKit, udev, capabilities, dpkg-Trigger, RPM-Dateitrigger, pacman-Hooks);
- eine empfohlene Bauweise je Baustein mit den Tests, die sie absichern müssen;
- eine Liste dessen, was eine Funktion streichen oder für den Benutzer sichtbar ändern würde. Darüber entscheidet der User vor dem Bau (Stufe-2-Spec 6.3).

**B2. Bausteine, die sie bewertet.** Ausgangspunkt ist der Vorschlag der Stufe-2-Spec 6.3:
1. Der **Freigabe-Helfer** als root-Helfer aus dem Paket:
   - Er kennt nur feste Aufträge, ohne Pfade und ohne freie Argumente.
   - Mit einem Schalter genügen zwei Aufträge: „an“ und „aus“. Jeder schaltet alles, was der Rechner hat. Die Runde bewertet, ob das besser ist als vier getrennte Aufträge.
   - Dazu kommen eine eigene polkit-Action mit `auth_admin` und `exec.path` sowie die Prüfung `_trusted` wie beim Kill-Helfer.
2. Die **Merkdateien:** Ort (`/etc/orbitop/` oder, als Zustand statt Konfiguration, `/var/lib/orbitop/` nach FHS und Debian Policy), Rechte und Format. Vorgabe (Wahl des Planers, aus dem Anti-Ziel „auch nach Neuinstallation“): Eine Deinstallation löscht sie in allen vier Formaten, so dass eine Neuinstallation nichts wieder freigibt. Ein Purge entfernt zusätzlich das Verzeichnis.
3. Die **RAPL-Freigabe**:
   - Eine feste udev-Regel aus dem Paket (`/usr/lib/udev/rules.d/`) mit `TEST==` auf die Merkdatei. Bei „aus“ gehen die Rechte von `energy_uj` auf den Kernel-Standard zurück.
   - Geklärt wird, welche Dateien unter `/sys/class/powercap/` auf Intel und AMD betroffen sind.
4. Die **perfmon-Freigabe:**
   - `setcap cap_perfmon=ep` auf den festen Pfad von `intel_gpu_top` je Distribution.
   - Die Paket-Auslöser setzen die Fähigkeit, wenn die Intel-Werkzeuge installiert oder aktualisiert werden, aber nur, wenn die Merkdatei da ist: dpkg-Trigger, RPM-Dateitrigger, pacman-Hook. Das gilt auch für eine Erstinstallation nach dem Einschalten, denn „an“ ist eine Regel für den Rechner (Entscheidung des Users).
   - Geklärt wird, ob ein Auslöser die Fähigkeit auch ohne Merkdatei setzen kann, also ohne dass ein Admin sie gewollt hat (Anti-Ziel).
5. Der **Zustand ohne root:** Woran erkennt die App „an“, „aus“ und „teilweise“, ohne root-Rechte?
6. Der **Knopf „Installieren“ über PackageKit:**
   - Er ruft den System-D-Bus mit einem festen Paketnamen je Distribution auf.
   - PackageKit fragt nach seiner eigenen polkit-Regel. Die Runde prüft, was diese auf den Distributionen erlaubt, etwa ohne Passwort für aktive Admin-Sitzungen.
   - Fehlt PackageKit oder scheitert der Auftrag, zeigt orbitop den Befehl.
7. Die **Seite als Angreifer:** Was darf eine kompromittierte WebView über `parse_message` anstoßen, und wie wird das begrenzt? Beispiele sind Dauerschleifen von Passwortdialogen oder Installationen.
8. **Deinstallation und Purge:** Beide nehmen die Freigaben zurück und löschen die Merkdateien, in allen vier Formaten gleich. Ein Purge entfernt zusätzlich das Verzeichnis.
9. **Von Hand gesetzte Freigaben** nach der README von 0.2.0, also `setcap` und `/etc/udev/rules.d/70-orbitop-rapl.rules`. Vorgabe (Wahl des Planers): Der Helfer löscht nie Dateien, die ein Admin angelegt hat. Bei „aus“ nimmt er die Fähigkeit am festen Pfad zurück; eine von Hand gesetzte Fähigkeit fällt dabei mit weg. Eine Regel von Hand erkennt die App und zeigt „von Hand freigegeben“ mit Verweis auf den Umstieg in der README. Die Runde prüft, ob eine gleichnamige Regel in `/etc` die Regel des Pakets verdeckt, und wählt den Namen der Paketregel so, dass das nicht geschieht.

**B3. Wie sie entsteht.**
- Ein Subagent (Opus) erarbeitet das Dokument. Er lädt die Skills `security-audit` (Leitfaden-Modus) und `cybersecurity-katalog` (passende Einträge zu polkit/pkexec, Linux-Rechtegrenzen, Paketierung) und belegt jede Aussage mit Quellen.
- Ein zweiter Subagent (Opus) prüft das Dokument unabhängig.
- Der Controller prüft beide Ergebnisse selbst gegen.
- Das Dokument wird committet. Der User bekommt eine kurze deutsche Zusammenfassung und entscheidet die Punkte aus B1, letzter Spiegelstrich.

### Teil C: Bau von 0.3.0 (Plan 2, nach Teil B)

Die genaue Bauweise legt das Dokument aus Teil B fest. Sichtbar für den Benutzer gilt:

**C1. Schalter „Messzähler freigeben“.**
- **Ort:** im Bereich „Einstellungen“ beim Dialog „Über“, unter „Beim Anmelden starten“, im selben Stil. Anfangs aus, sichtbar für alle.
- **Bedeutung:** Der Schalter gilt für den ganzen Rechner. Das sagt der Text dazu, im Gegensatz zum Autostart, der nur für den eigenen Benutzer gilt.
- **Erklärung vor dem Passwort:** Vor der Passwortabfrage erklärt ein kurzer Text in beiden Sprachen das Risiko (Platypus, CVE-2020-8694): Dann kann jedes Konto auf dem Rechner diese Zähler lesen. Erst nach „Freigeben“ folgt polkit mit `auth_admin`. „Sperren“ fragt ebenfalls nach dem Passwort.
- **Bedeutung von „an“** (Entscheidung des Users): Der Schalter ist eine Regel für den ganzen Rechner. Was später dazukommt, wird mit freigegeben, etwa ein über den Knopf oder die Paketverwaltung installiertes `intel_gpu_top`. Dafür genügt eine Merkdatei.
- **Zustand:** Der Schalter zeigt „an“ oder „aus“, gelesen ohne root. Darunter steht je Teil, ob er wirkt oder warum nicht, etwa „Grafik-Zähler: `intel_gpu_top` ist nicht installiert“ oder „von Hand freigegeben“ (B2.9).
- **Ohne Paket:** Aus einem Checkout ohne installiertes Paket ist der Schalter nicht bedienbar. Der Text verweist dann auf die README.

**C2. Knopf „Installieren“.**
- Er steht beim Hinweis „`intel_gpu_top` fehlt“, nur auf Rechnern mit Intel-Grafik.
- Der Paketname ist fest je Distribution (`intel-gpu-tools` bzw. `igt-gpu-tools`); die Seite gibt keinen Namen vor.
- Während des Auftrags ist der Knopf gesperrt. Danach erkennt orbitop das Werkzeug ohne Neustart, oder es sagt, dass ein Neustart nötig ist (Wahl des Builders).
- Scheitert der Auftrag, zeigt der Hinweis den Befehl der Distribution.

**C3. Hinweise (Issue #1).**
- Jeder Hinweis der Fußzeile hat ein „Ausblenden“.
- Ausgeblendete Hinweise merkt sich orbitop je Benutzer, wie das Layout: atomar über `userfile.py`, nur die Kennung des Hinweises.
- In den Einstellungen holt „Ausgeblendete Hinweise wieder zeigen“ alle zurück.
- Ändert sich die Lage, erscheint ein neuer Hinweis auch nach dem Ausblenden des alten, etwa „fehlt“ statt „darf nicht lesen“.
- Die Hinweise zu den gesperrten Zählern nennen statt der README den Schalter („Einstellungen im Dialog Über“). Die README bleibt für Starts ohne Paket.

**C4. Pakete.**
- Helfer, polkit-Action und udev-Regel kommen in alle vier Formate, dazu die Paket-Auslöser gemäß Teil B.
- Eine Deinstallation nimmt die Freigaben zurück und löscht die Merkdateien, in allen Formaten gleich. Ein Purge entfernt zusätzlich das Verzeichnis (B2.2, B2.8).
- Lintian, rpmlint und namcap bleiben ohne neue Fehler. Neue geduldete Meldungen werden einzeln begründet, wie in 0.2.0.

**C5. Matrix.** Sie prüft in den Containern zusätzlich:
- Freigabe an und aus über den Helfer, ohne polkit, als root im Container;
- den Auslöser nach einem neu installierten Intel-Paket;
- dass ohne Merkdatei nichts freigegeben wird;
- die Rücknahme bei Deinstallation und Purge.

**C6. README.** Die README bekommt dieselben Abschnitte in beiden Sprachen:
- „Grafik und Leistung“ beschreibt den Schalter und das Risiko.
- Die Befehle von Hand bleiben nur für Starts ohne Paket.
- Den Umstieg von 0.2.0 auf 0.3.0 für alle, die die Freigabe von Hand gesetzt haben: Fähigkeit und Regel entfernen, dann den Schalter einschalten.

**C7. Texte** stehen nur in `locale/{en,de}.json`, in beiden Sprachen.

**C8. Eigenlast.** Nach den Änderungen an der Oberfläche wird gemessen, Budget wie bisher.

### Teil D: Testversion, Release 0.3.0 und Umstieg

0. **Testversion auf echter Hardware** (Entscheidung des Users), nach der Schlussprüfung und vor dem Go:
   - Der Controller baut nur das `.deb` als Testversion `0.3.0~rc1`. Es bleibt unsigniert, unveröffentlicht und kommt nicht nach `main`; wie es seine Nummer bekommt, entscheidet der Builder. `~rc1` sortiert bei dpkg vor `0.3.0`, deshalb kommt 0.3.0 danach als normales Update. Bei pacman sortiert `~rc1` nach `0.3.0` (zweite Prüfung der Security-Runde, M-11); eine Arch-Testversion gäbe es deshalb nur als `0.3.0rc1`.
   - Der User installiert sie mit `sudo apt install ./<datei>.deb`.
   - Er prüft den Schalter: an, aus, Passwortdialog, Zustand. Beim ersten „aus“ fällt die von Hand gesetzte Fähigkeit auf `intel_gpu_top` weg. Damit ist der Umstieg der Freigabe (Punkt 5) schon erledigt.
   - Für den Knopf „Installieren“ entfernt er kurz die Intel-Werkzeuge (`sudo apt remove intel-gpu-tools`) und lässt orbitop sie neu installieren.
   - Dazu kommt das Ausblenden und Einblenden der Hinweise.
   - Der Controller prüft Merkdatei, Fähigkeit, Rechte von `energy_uj` und Oberfläche.
   - Fehler werden behoben, mit Review und Audit. Dann folgt eine `~rc2`, bis alles passt.
1. **Schlussprüfung des Zweigs:** Review auf Opus, volles Security-Audit mit einer Fix-Welle, Eigenlast-Messung, Prüfung auf persönliche Daten.
2. **Go des Users,** dann Merge nach `main`.
3. **Release-Lauf:** `scripts/release.sh 0.3.0`, gestartet vom User in seinem Terminal, mit zwei Passphrase-Abfragen. Der Release-Eintrag der Metainfo trägt das Datum des Release-Tags. `orbitop-apt-source` behält seine Bytes, weil `keyring.version` gleich bleibt.
4. **Update-Kanal:** Auf dem Notebook kommt 0.3.0 über die normale Aktualisierung. Der Controller prüft `apt policy`, die Version und den Helfer.
5. **Freigabe auf dem Notebook:** Die von Hand gesetzte Fähigkeit ist mit dem Test der Testversion weg; eine RAPL-Regel gab es nicht. Nach dem Update auf 0.3.0 ist der Schalter so, wie der User ihn im Test verlassen hat. Er schaltet ihn ein, falls nötig, und der Controller prüft Merkdatei, Fähigkeit und Zustand der Oberfläche.
6. **Issue #1:** Nach dem Release schreibt der Controller einen Kommentar. Er nennt den Schalter und die ausblendbaren Hinweise und bittet den Kollegen um eine kurze Bestätigung, dass 0.3.0 über die Aktualisierung kam. Geschlossen wird das Issue, sobald er bestätigt oder der User es sagt. Für die Abnahme zählt das Notebook (Wahl des Planers).
7. **Nacharbeiten:** Die lokale `CLAUDE.md` und die Memory werden nachgezogen, Worktree und Arbeitsordner aufgeräumt.

## Rahmen

- Python ≥ 3.12, nur Standardbibliothek und PyGObject. PackageKit wird über `Gio` (D-Bus) angesprochen, nicht über eine neue Bibliothek.
- Oberfläche ohne Build-Schritt; die CSP bleibt so streng wie heute.
- Eigenlast-Budget: ≤ 9 % eines Kerns sichtbar, ≤ 3 % ausgeblendet, PSS < 275 MB. Die Ausnahme für „alle Spalten“ (bis etwa 9,4 %) bleibt.
- Best Practice je Plattform (globale Regel): Auslöser, Regeln und Pfade nach Debian Policy, Fedora- und openSUSE-Richtlinien und Arch-Wiki. Quellen werden genannt.
- Keine persönlichen Daten in Repo, Paketen, Paketquelle, Bildern und Commit-Nachrichten. Git-Identität nur die noreply-Adresse.
- Live-Läufe nur mit eigener D-Bus-Sitzung und eigenem `XDG_CONFIG_HOME`. Nie die laufende Instanz des Users beenden, nie einen echten Prozess beenden, nie das echte `pkexec` aus Tests.
- Kein `sudo` und keine Paketinstallation auf dem Rechner durch den Controller. Root-Schritte gibt es nur in wegwerfbaren Containern (`docker run --rm`, ohne `--privileged`, `--cap-add`, `--network=host`) oder beim User selbst.
- Den Release-Schlüsselordner und `~/.gnupg` fasst der Controller nie an.

## Dem Builder überlassen

- Die genauen Grenzen und Namen der JS-Module, der CSS-Dateien und der aufgeteilten Testdateien.
- Wie Module in WebKitGTK und Chrome laden (A1), innerhalb der Grenzen dort.
- Wie die Matrix Netzaussetzer erkennt und wiederholt.
- Die Bauweise von Helfer, Auslösern und PackageKit-Aufruf, wie Teil B sie empfiehlt.
- Ob orbitop ein frisch installiertes `intel_gpu_top` ohne Neustart erkennt.
- Wie die Testversion ihre Versionsnummer bekommt, ohne dass sie in `main` landet.
- Texte der Oberfläche im Stil der bestehenden.

## Reihenfolge

1. Spec freigegeben → Worktree `.worktrees/umbau-0.3.0`, Plan 1 (Teil A).
2. Plan 1 ausführen, Aufgabe A1 zuerst. Parallel dazu Teil B: Analyse, unabhängige Prüfung, Gegenprüfung, Zusammenfassung an den User.
3. Plan 2 (Teil C) nach dem Dokument aus Teil B und den Entscheidungen des Users dazu.
4. Plan 2 ausführen.
5. Teil D: Schlussprüfung, Testversion auf dem Notebook, Go, Release, Update auf dem Notebook, Freigabe prüfen, Issue #1, Nacharbeiten.

## Messung Eigenlast (Umbau)

Gemessen am 2026-11-20 nach Task 6 (9a3518f), Verfahren wie in der Spec vom 2026-11-17, Abschnitt „Messung Eigenlast (2026-11-17)“: `scripts/measure-load.py --pid <orbitop> --seconds 60` über den Prozessbaum, 60 s nach 60 s Aufwärmen, Fenster 1600×1000, Skalierung 1,25. „Alle Spalten“ = Layout mit allen 15 Spalten sichtbar. Jede Lage in eigener Instanz mit eigenem `XDG_CONFIG_HOME` und eigener D-Bus-Sitzung. Zweig und `main` (Stand 0.2.0, die Laufzeitdateien gleich `v0.2.0`) liefen in derselben Sitzung abwechselnd (Zweig, `main`, `main`, Zweig), dazu ein drittes Paar „Prozesse Standard“. Aufteilung je Thread aus `/proc/<pid>/task/*/stat` über dasselbe Fenster. Alle Läufe sind ungestört (GTK-Hauptthread ≤ 0,15 %, Compositor ≤ 0,10 %), keiner wurde verworfen. Lastmittel (1 min) 0,03 bis 1,20. Auf dem Rechner liefen dabei rund 390 Prozesse mit rund 2 000 Threads.

CPU in % eines Kerns, in Klammern PSS in MB:

| Stand | Ausgeblendet | Übersicht kurz | Prozesse Standard kurz | Prozesse alle Spalten kurz |
|---|---|---|---|---|
| Umbau (9a3518f) | 3,05 (170); 2,93 (169) | 7,23 (234); 7,26 (231) | 8,04 (230); 8,30 (235); 8,08 (229) | 9,00 (233); 8,93 (234) |
| `main` (Stand 0.2.0), abwechselnd in derselben Sitzung | 3,02 (169); 3,00 (169) | 7,26 (239); 7,26 (235) | 8,01 (231); 7,95 (231); 8,00 (230) | 8,98 (232); 8,96 (234) |
| **Budget (User)** | **≤ 3** | **≤ 9** | **≤ 9** | **≤ 9** (Ausnahme bis etwa 9,4); PSS **< 275** |

Der Umbau liegt in allen Lagen im Rahmen der Streuung gleich auf mit `main`. Mittel Umbau / `main`: ausgeblendet 2,99 / 3,01, Übersicht 7,25 / 7,26, Prozesse Standard 8,14 / 7,99, alle Spalten 8,97 / 8,97. Der Lauf 8,30 ist ungestört nach der Regel (GTK-Hauptthread 0,10 %, Compositor 0,03 %). Während dieses Laufs stieg aber das Lastmittel von 0,12 auf 0,98, und alle Prozesse lagen höher, auch `intel_gpu_top` (1,23 statt 1,15). Ohne ihn liegt der Umbau bei 8,06.

Aufteilung je Prozess (Mittel), Umbau / `main`:
- Ausgeblendet: orbitop 1,86 / 1,86 (`orbitop-worker` 0,93 / 0,92, `orbitop-procs` 0,89 / 0,89, GTK-Hauptthread 0,00), `intel_gpu_top` 1,13 / 1,15, WebKit 0 %.
- Übersicht: WebKit 3,51 / 3,48, orbitop 2,58 / 2,60, `intel_gpu_top` 1,16 / 1,19.
- Prozesse Standard: orbitop 3,76 / 3,72, WebKit 3,20 / 3,11, `intel_gpu_top` 1,18 / 1,16.
- Prozesse alle Spalten: WebKit 4,13 / 4,10, orbitop 3,69 / 3,73, `intel_gpu_top` 1,14 / 1,15.

PSS ausgeblendet 169 bis 170 MB statt 137 bis 138 MB am 2026-11-19, in beiden Ständen gleich (WebKit-Webprozess 85 statt 64 MB, orbitop 67 statt rund 60 MB). Die Ursache ist nicht untersucht, das Budget hält.

### Ausgeblendet untersucht (A7.1)

- **Versionen:** `intel_gpu_top` 2.3-1 und Kernel 7.0.0-43 sind seit dem 2026-11-16 unverändert. Alle Messungen vom 2026-11-17 bis heute liefen im selben Bootvorgang. Seitdem kamen nur WebKitGTK (2026-11-18), das Paket orbitop 0.2.0 selbst und Pakete ohne Bezug zur Messung neu. WebKit liegt ausgeblendet bei 0 %.
- **Gleicher Code, andere Werte:** a568c23 und 0.1.0 haben denselben Programmcode (`orbitop/`, `bin/`). Gemessen wurden 2,65 % am 2026-11-18 und 3,08 % am 2026-11-19. Die Schwankung stammt also nicht aus dem Code.
- **Je Thread:** Der GTK-Hauptthread steht ausgeblendet. `orbitop-worker` (Systemtakt) und `orbitop-procs` (Prozess-Takt alle 2 s, auch ausgeblendet) tragen je etwa die Hälfte. orbitop liegt mit 1,86 % nahe am Wert vom 2026-11-17 (1,78 bis 1,80 %).
- **Ohne `intel_gpu_top`:** `gpu_tools.py` sucht das Werkzeug nur im festen `TOOL_PATH`, nicht im `PATH`. Darum lief diese Messung über die Test-Naht: `TOOL_PATH` zeigt auf einen leeren Ordner. Ergebnis 2,58 % statt rund 3,0 %. Dabei steigt aber `orbitop-worker` von 0,92 auf 1,62 %: Ohne Werte des Werkzeugs liest `gpu.py` die Auslastung jede Sekunde aus den fdinfo-Dateien der eigenen Prozesse (Hinweis `hint.igt_missing`). Netto spart das Weglassen also nur rund 0,4 Punkte.
- **`intel_gpu_top` allein** (`-J -s 2000` wie in orbitop): 1,10 %. Mit 20 000 zusätzlich offenen Dateien in einem Probeprozess steigt der Wert auf 3,18 %, also rund 0,1 Punkte je 1 000 offene Dateien. Das passt dazu, dass das Werkzeug je Takt in den Dateilisten aller lesbaren Prozesse nach Grafik-Clients sucht (Block `clients`). orbitop verwirft diesen Block; Version 2.3 hat keinen Schalter, der die Suche abstellt.
- **Mit 300 zusätzlichen schlafenden Prozessen**, ausgeblendet: 4,08 % statt rund 3,0 %. `orbitop-procs` liegt bei 1,68 statt 0,89 % (rund 0,26 Punkte je 100 Prozesse), `intel_gpu_top` bei 1,38 statt 1,13 %. `orbitop-worker` bleibt etwa gleich (0,97 %).

**Ergebnis:** Die Ursache ist keine Änderung in orbitop, sondern der Zustand des Rechners. Beide großen Posten der ausgeblendeten Last wachsen mit der Zahl der Prozesse und der offenen Dateien: `orbitop-procs` und `intel_gpu_top`. Der Anteil von orbitop ist seit dem 2026-11-17 im Rahmen gleich geblieben. Der Mehrbedarf gegenüber dem 2026-11-17 (`intel_gpu_top` +0,1) hängt am selben Zustand. Mit rund 390 Prozessen liegt der Wert genau an der Grenze von 3 %. Mit mehr offenen Programmen steigt er, mit weniger sinkt er (2,65 % am 2026-11-18).

Möglichkeiten, über die der User entscheidet (Werte für ausgeblendet, geschätzt aus den Messungen oben):
1. **So lassen.** Kein Aufwand, kein Verlust. Das Budget von 3 % gilt dann für einen Rechner mit etwa 400 Prozessen; jedes weitere offene Programm hebt die Last.
2. **`intel_gpu_top` bei ausgeblendetem Fenster anhalten**, dabei auch den Ersatzweg über fdinfo auslassen (sonst kostet er 0,7 Punkte zurück). Ergebnis rund 1,9 %.
   - Verlust: Im Verlauf der Grafik-Kachel (Auslastung, Takt, Leistung) fehlt die ausgeblendete Zeit. Nach dem Einblenden fehlen die Grafikwerte rund 2 s lang.
   - Aufwand: Start und Stopp im `ToolReader` (heute startet er höchstens alle 30 s neu), Sichtbarkeit bis zum Sampler, Tests.
3. **`intel_gpu_top` ausgeblendet mit längerem Takt neu starten**, etwa 4 s. Ersparnis rund 0,55 Punkte.
   - Verlust: gröbere Grafikwerte für die ausgeblendete Zeit und eine kurze Lücke beim Umschalten.
   - Aufwand: wie bei 2.
4. **Prozess-Takt ausgeblendet seltener**, etwa 4 s statt 2 s. Ersparnis rund 0,45 Punkte; der Anteil, der mit der Prozesszahl wächst, halbiert sich.
   - Verlust: Der Verlauf je Prozess (5 min, „Letzte 60 s“) wird für die ausgeblendete Zeit gröber.
   - Aufwand: mittel, denn die Verläufe nehmen heute feste 2-s-Schritte an.
5. **2 und 4 zusammen:** rund 1,4 %.

**Entscheidung (Controller im Auftrag des Users, 2026-11-20): Möglichkeit 4.**
- Ausgeblendet läuft der Prozess-Takt alle 4 s statt alle 2 s (`PROCS_PERIOD_HIDDEN_S`). Beim Einblenden kommt der nächste Takt spätestens 2 s nach dem letzten, bei älteren Daten also sofort; danach wieder alle 2 s. Alles andere bleibt, auch `intel_gpu_top` und der Systemtakt.
- Grund: kleinste sichtbare Wirkung. Der Verlauf der Grafik-Kachel bleibt vollständig, weil `intel_gpu_top` weiterläuft.
- Was der User merkt: Der Verlauf je Prozess („Letzte 60 s“, 5-min-Kurve im Detail) zeigt für die ausgeblendete Zeit eine Treppe. Jeder 4-s-Wert steht doppelt darin (9ec7719), ebenso ein verspäteter sichtbarer Takt ab 3 s.
- Die Zeitachse stimmt: Es bleibt ein Punkt je 2 s, und beide Verläufe decken auch direkt nach dem Einblenden die richtige Zeit ab.

Messung nach der Entscheidung, 2026-11-20, zweite Sitzung. Verfahren wie oben, abwechselnd mit `main`. Alle Läufe ungestört (GTK-Hauptthread ≤ 0,17 %, Compositor ≤ 0,12 %), Lastmittel (1 min) 0,01 bis 1,52:

| Stand | Ausgeblendet | Übersicht kurz | Prozesse Standard kurz |
|---|---|---|---|
| Möglichkeit 4 (86bc21d) | 2,60 (170); 2,55 (169) | 7,30 (236); 7,21 (230) | 8,11 (231); 7,99 (230) |
| `main` (Stand 0.2.0), abwechselnd in derselben Sitzung | 2,98 (170); 3,02 (169) | 7,18 (235); 7,13 (237) | 8,08 (231); 7,98 (230) |

- Ausgeblendet im Mittel 2,58 statt 3,00 %. `orbitop-procs` liegt bei 0,48 statt 0,90 %, `orbitop-worker` und `intel_gpu_top` sind unverändert.
- Nach 9ec7719 (doppelte Verlaufspunkte) ausgeblendet 2,58 (169) gegen `main` 3,02 (169), je ein Lauf: unverändert.
- Sichtbar gleich auf mit `main`: Übersicht +0,10 (WebKit +0,06, orbitop +0,04, innerhalb der Streuung von rund ±0,2), Prozesse Standard +0,02.
- Zwischenstand 7475670 tickte bei jedem Einblenden sofort. Im Prozess-Reiter lag er bei 8,27 bis 8,33 % statt 7,94 bis 8,02 %.
  - Ursache war der Ablauf der Messung: Kurz nach dem Start gab der sofortige Takt Raten über Bruchteile einer Sekunde. Die Sichtprüfung (`#procs`) wählte deshalb orbitop statt PID 1 als gewählten Prozess, und dessen Detailansicht kostet mehr Zeichenarbeit.
  - Die Vermutung, die Phase gegenüber dem Systemtakt sei schuld (3a8ffd3), hat die Messung widerlegt.
  - 86bc21d nimmt 3a8ffd3 zurück und tickt beim Einblenden nur sofort, wenn der letzte Takt älter als 2 s ist. Der Start verhält sich so wie in `main`.
