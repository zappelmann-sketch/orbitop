# orbitop – Design

Stand: 2026-11-16 · Status: **Stufe 1 vom User freigegeben**, einschließlich Builder-Check, Projektdaten, Hardware-Unabhängigkeit und Zweisprachigkeit.

Arbeitstitel war „Systemstatus“. Der Projektordner `Systemstatus` behält seinen Namen, das Programm und das Repository heißen **orbitop**.

## Wozu

Der User will sehen, was sein Rechner tut, wenn er ausgelastet ist, und zwar **warum**: welcher Prozess die Last verursacht und ob dieser Prozess nur rechnet oder wirklich hängt. Hängt er, will der User ihn beenden können.

Mission Center (Flatpak, liegt im Autostart) reicht nicht. Es zeigt dort nur CPU-Auslastung und -Temperatur, weil seine Sandbox ihm den Zugriff auf die meisten Sensoren verwehrt. Daher entsteht ein eigenes Programm.

orbitop soll später als Open-Source-Paket veröffentlicht werden. Es muss deshalb nicht nur auf dem Notebook des Users laufen, sondern **auf beliebiger Hardware** (Intel, AMD, ARM, verschiedene Grafikchips und Hersteller) und auf Linux-Distributionen mit .deb-Paketen.

## Projektdaten (vom User entschieden)

| Punkt | Festlegung |
|---|---|
| Name | `orbitop`: Orbit plus „top“, angelehnt an top, htop und btop. Im Ubuntu-Archiv frei, bei GitHub gibt es kein gleichnamiges Projekt (geprüft am 2026-11-16) |
| Lizenz | **GPL-3.0-or-later**. Die gebündelten Schriften Orbitron und Oxanium stehen unter der SIL Open Font License 1.1, ihr Lizenztext wird mitgeliefert |
| Urheberhinweis | `Copyright © 2026 zappelmann-sketch` |
| E-Mail in Commits und Paketdaten | GitHub-noreply-Adresse `235797375+zappelmann-sketch@users.noreply.github.com`. **Nie** die private Mail-Adresse des Users |
| Repository | `github.com/zappelmann-sketch/orbitop`, **privat**, bis die Arbeit am Update-Kanal beginnt. Dann öffentlich, weil der Update-Kanal Releases ohne Anmeldung abrufen muss |
| Paketform | Klassisches **.deb-Paket**. Flatpak und Snap scheiden aus: Ihre Sandbox verwehrt den Zugriff auf `/proc`, `/sys` und das Beenden fremder Prozesse, genau das Problem von Mission Center |

Geprüfte Lizenzen der Abhängigkeiten: PyGObject LGPL-2.1+, GTK 4 LGPL-2.1+, WebKitGTK LGPL/BSD, psutil BSD-3-Clause. Sie werden nur genutzt, nicht mitgeliefert, und schränken die Lizenzwahl nicht ein. Hinweis aus der Lizenzrunde: Überwiegend KI-geschriebener Code ist in Deutschland urheberrechtlich nicht sicher geschützt. Die Lizenz wird trotzdem wie üblich gesetzt.

## Stufen

1. **Stufe 1 – das Programm** (dieses Dokument, Ziele unten). Läuft auf dem Notebook des Users und ist für fremde Hardware gebaut.
2. **Stufe 2 – Paket, Release und Update-Kanal.** Wird **vor ihrer Umsetzung in einer eigenen Design-Runde** festgelegt. Bisheriger Stand der Absprache:
   - GitHub-Release mit `.deb`-Datei zum Herunterladen.
   - Eingebaute Update-Prüfung: orbitop fragt bei GitHub nach einem neueren Release, zeigt „Update verfügbar“, lädt das Paket nach Klick herunter und installiert es nach Passworteingabe.
   - Offen für Stufe 2: Signatur und Prüfsumme der Downloads, Bauen in GitHub Actions, eigene APT-Quelle ja oder nein, Mindestversion von Ubuntu und Debian, Wartungsablauf bei neuen Ubuntu-Versionen.

Stufe 1 muss nur so gebaut sein, dass Stufe 2 nichts umbauen muss (siehe „Für Stufe 2 vorbereitet“).

## Referenzrechner (Entwicklung und Abnahme)

| Bereich | Hardware / Quelle |
|---|---|
| System | Dell-Notebook, Ubuntu 26.04, GNOME 50 auf Wayland, 1920×1080, Systemthema dunkel |
| CPU | Intel Core i7-7600U, 2 Kerne / 4 Threads |
| Grafik | Intel HD 620 (i915), keine dedizierte GPU. Takt: `/sys/class/drm/card*/gt_act_freq_mhz` |
| RAM | 14 GB, Swap 32 GB (Partition) |
| Datenträger | NVMe Micron 2300, 1 TB (`nvme0n1`). Partitionen `/`, `/data`, `/data/projects` |
| Netzwerk | `wlp2s0` (WLAN, aktiv), `enp0s31f6` (LAN), `docker0`, `lo` |
| Temperaturen (hwmon) | `coretemp`, `nvme`, `pch_skylake`, `iwlwifi_1`, `dell_smm` (temp1–4 ohne Label), `acpitz` |
| Lüfter | `dell_smm` `fan1_input` |
| Akku | `BAT0`, `AC` |
| Python | System-Python 3.14 mit `python3-gi` (GTK 4, libadwaita), psutil 7.1 (Debian-Paket), pytest 9 |

## Hardware-Unabhängigkeit (Ergänzung, Vorschlag des Planers)

- **Keine fest verdrahteten Pfade oder Gerätenamen.** Alle Quellen werden beim Start gesucht und, wo sich etwas ändern kann (Netz, USB-Datenträger), regelmäßig neu erkannt. Die Tabelle oben ist nur das Beispiel des Referenzrechners.
- **Python ohne kompilierte eigene Teile:** Ein Paket (`Architecture: all`) läuft auf amd64, arm64 und anderen Architekturen.
- **Quellen je Bereich**, jeweils mit Ausweichweg. Was fehlt, liefert „nicht vorhanden“ statt eines Fehlers:

  | Bereich | Quellen |
  |---|---|
  | CPU | `/proc/stat`, Takt aus `/sys/devices/system/cpu/*/cpufreq`. Läuft gleich auf x86 (Intel, AMD, VIA/Zhaoxin), ARM und RISC-V |
  | CPU-Temperatur | hwmon `coretemp` (Intel, Zhaoxin), `k10temp`/`zenpower` (AMD Ryzen/EPYC), `k8temp` (ältere AMD), `via_cputemp` (VIA), `macsmc_hwmon` (Apple Silicon unter Asahi Linux). Sonst `/sys/class/thermal/thermal_zone*` (ARM-SoCs wie Raspberry Pi, Rockchip, MediaTek, Qualcomm, Allwinner, NVIDIA Jetson; RISC-V) |
  | Grafik | **Intel** (`i915`, `xe`) über `intel_gpu_top -J`. **AMD** (`amdgpu`) über sysfs `gpu_busy_percent`, VRAM und hwmon-Leistung; ältere Karten mit `radeon` nur Takt und Temperatur. **NVIDIA** proprietär über `nvidia-smi`, mit freiem Treiber `nouveau` nur Temperatur und Lüfter aus hwmon. **ARM-Grafik**: Mali (`panfrost`, `panthor`, `lima`), Adreno (`msm`), Raspberry Pi (`v3d`, `vc4`), Apple Silicon (`asahi`), PowerVR, Vivante (`etnaviv`): Auslastung und Takt über devfreq (`/sys/class/devfreq/*`), wo vorhanden. Allgemeiner Ausweichweg für alle DRM-Treiber: Belegungszähler `drm-engine-*` aus `/proc/<pid>/fdinfo`. Sonst nur der Takt oder „nicht vorhanden“ |
  | Leistung | RAPL über powercap (Intel, AMD Zen), GPU-Leistung aus der Grafikquelle, jedes hwmon `power*_input`/`power*_average` (z. B. Strommess-Chips `ina2xx` auf ARM-Boards, `fam15h_power` bei älteren AMD), Akku über jedes `BAT*` im Entladebetrieb |
  | Lüfter | jedes hwmon `fan*_input`. Das deckt Notebook-Treiber ab (Dell `dell_smm`, Lenovo `thinkpad`, ASUS `asus_wmi_sensors`/`asus-nb-wmi`, HP `hp-wmi-sensors`, Framework `cros_ec`, Intel-Macs `applesmc`), Mainboard-Chips (Nuvoton `nct6775`, ITE `it87`, `gigabyte_wmi`) und Grafikkarten-Lüfter |
  | Weitere Temperaturen | jedes hwmon `temp*_input`, z. B. `nvme`, `drivetemp` (SATA-Laufwerke), `pch_*`, WLAN-Chips, `acpitz` |
  | Netzwerk | alle physischen Schnittstellen. Virtuelle (`lo`, `docker*`, `veth*`, `br-*`, `virbr*`, `tun*`, `wg*`) werden ausgelassen |
  | Datenträger | alle physischen Laufwerke (NVMe, SATA/SAS, eMMC/SD, USB, in VMs `vd*`/`xvd*`). Partitionen, Loop-, RAM- und zram-Geräte werden ausgelassen |

- **Virtuelle Maschinen:** Dort gibt es meist keine Sensoren. Die betroffenen Kacheln werden ausgeblendet, wie bei jedem fehlenden Bereich.
- **KI-Beschleuniger (NPU)**, z. B. Intel und AMD unter `/sys/class/accel`, sind in Stufe 1 nicht enthalten.

- **Mehrfach vorhandene Geräte:**
  - Je Grafikchip eine eigene Kachel, z. B. bei Notebooks mit Intel- und NVIDIA-Grafik.
  - Netzwerk und Datenträger zeigen in der Kachel die Summe und darunter die Liste je Gerät.
- **Fehlende Bereiche:** Eine Kachel ohne jede Datenquelle wird ausgeblendet, das Raster schließt die Lücke. In der Fußzeile steht, was auf diesem Gerät nicht verfügbar ist, z. B. „Kein Lüftersensor, keine Leistungsdaten“.
- **Viele Threads:** Bis 8 Threads gibt es Mini-Verläufe wie im Entwurf. Ab 9 Threads ersetzt eine kompakte Balkenreihe (aktuelle Last je Thread) die Mini-Verläufe. Sie bleibt bis 64 Threads lesbar.
- **Sensor-Beschriftung:** Hat ein Sensor kein Label, wird der Treibername benutzt (z. B. „dell_smm 2“). Es gibt keine erfundenen Namen.
- **Desktop:** Entwickelt und abgenommen auf GNOME. Auf anderen Desktops mit GTK 4 und WebKitGTK läuft orbitop ebenfalls. Der Autostart nutzt den XDG-Standard und funktioniert damit desktopübergreifend.
- **Rechte-Einrichtung je Hardware:** Die einmalige Einrichtung macht nur, was die Hardware braucht:
  - `intel-gpu-tools` plus `setcap` nur bei Intel-Grafik.
  - **Keine allgemeine RAPL-Freigabe (vom User entschieden, 2026-11-16).** Auf Intel liefert das mit `cap_perfmon` ausgestattete `intel_gpu_top` die Watt für CPU-Paket und Grafik. Nur dieses eine Programm bekommt Zugriff. Die Freigabe von `energy_uj` für alle gibt es nur auf ausdrücklichen Wunsch mit `--allow-rapl` und vorheriger Warnung. Sie ist für Rechner ohne andere Leistungsquelle gedacht, etwa AMD, und erfolgt dauerhaft über eine udev-Regel.
  - AMD- und NVIDIA-Grafik brauchen keine Zusatzrechte.
- **Tests:** Fremde Hardware steht nicht zur Verfügung. Die Erkennung wird deshalb mit nachgebauten `/sys`- und `/proc`-Verzeichnisbäumen getestet (Intel-Notebook, AMD-Desktop mit amdgpu, ARM-Board mit thermal_zone, Rechner ohne Lüfter und ohne Akku). Abgenommen wird auf dem Referenzrechner.

## Ziele (Stufe 1)

1. **Übersicht:** Bis zu acht Bereiche gleichzeitig als Kacheln, mehr bei mehreren Grafikchips. Jede Kachel zeigt einen 5-Minuten-Verlauf als Flächendiagramm, aktualisiert jede Sekunde, also 300 Punkte je Kurve.
   - **CPU:** gesamt plus Thread-Ansicht (siehe oben). Daneben Takt, Temperatur, Prozesse und Threads.
   - **Grafik:** Auslastung in %, Takt, Leistung, soweit die Quelle sie liefert.
   - **Arbeitsspeicher:** belegt, dazu Swap als zweite Linie, außerdem „verfügbar“.
   - **Leistung:** Watt des CPU-Pakets mit Aufteilung, soweit verfügbar. Dazu Akku und Netz- oder Akkubetrieb, im Akkubetrieb die Entladeleistung.
   - **Temperaturen:** CPU gefüllt, die zwei wichtigsten weiteren Sensoren als Linien, der Rest als Werteliste.
   - **Lüfter:** U/min mit Minimum und Maximum der letzten 5 Minuten.
   - **Netzwerk:** Empfangen gefüllt, Senden als Linie, dazu die Summe seit Systemstart.
   - **Datenträger:** Lesen gefüllt, Schreiben als Linie, dazu Belegung und Laufwerkstemperatur.
2. **Zeile „Höchste Last“** über den Kacheln: die Prozesse mit der höchsten CPU-Last und der Prozess mit dem meisten RAM. Ein Klick wechselt in den Reiter „Prozesse“ und wählt diesen Prozess aus.
3. **Reiter „Prozesse“:**
   - Liste mit Spalten Prozess, CPU, Mini-Verlauf der letzten 60 s, RAM, E/A und Zustand. Sortierbar, standardmäßig nach CPU. Mit Suchfeld und den Filtern „Alle“, „Nur meine“ und „Auffällige“.
   - Rechts eine Detailansicht: Befehlszeile, PID, Benutzer, CPU-Verlauf über 5 Minuten, RAM, Lesen/Schreiben, Threads, Kontextwechsel und Startzeit. Darunter eine Befundbox in Klartext und die Knöpfe „Beenden“ und „Sofort beenden“.
4. **Zustandseinstufung**, ehrlich als Hinweis und nicht als Urteil (vom User abgenommen):
   - **arbeitet:** CPU- oder E/A-Aktivität mit sich ändernden Werten.
   - **wartet:** schläft, Zustand S ohne Aktivität. Grenze: Ein interner Deadlock sieht genauso aus, Fensterprogramme meldet der Desktop selbst als „reagiert nicht“.
   - **Dauerlast, keine E/A:** eigener Prozess, mindestens 2 Minuten lang ≥ 90 % eines Kerns, keine Lese- oder Schreibbytes, praktisch keine freiwilligen Kontextwechsel. Gelb, mit dem Hinweis „Endlosschleife oder lange Berechnung, von außen nicht unterscheidbar“.
   - **Dauerlast, E/A unbekannt:** dasselbe bei fremden Prozessen, deren E/A nicht lesbar ist (siehe „Nach dem Builder-Check entschieden“).
   - **hängt im Kernel:** Zustand D seit über 10 s. Rot. Hinweis, dass auch „Sofort beenden“ erst greift, wenn der Kernel den Prozess freigibt.
   - **angehalten:** Zustand T/t.
   - **Zombie:** Zustand Z. Er lässt sich nicht beenden, der Elternprozess wird genannt.
5. **Beenden:**
   - Vor jedem Beenden kommt eine Rückfrage.
   - „Beenden“ sendet SIGTERM. Lebt der Prozess nach 5 s noch, wird „Sofort beenden“ (SIGKILL) hervorgehoben.
   - Eigene Prozesse werden direkt beendet, fremde und Root-Prozesse nur über `pkexec` mit Passwortdialog.
   - Bei Zombies ist der Knopf deaktiviert.
   - Unmittelbar vor dem Signal werden PID **und** Startzeit geprüft.
6. **Autostart:**
   - Start bei der Anmeldung ohne Fenster (`--hidden`), das Sammeln beginnt sofort.
   - Nur eine Instanz: Ein zweiter Start holt das Fenster nach vorne.
   - Das Fenster zu schließen blendet es nur aus. Ganz beenden geht nur ausdrücklich.
7. **Zweisprachig (vom User entschieden):**
   - Deutsch und Englisch.
   - Die Sprache wird beim Start aus der Systemsprache bestimmt: `LC_ALL`, `LC_MESSAGES`, `LANG` und `LANGUAGE` in der üblichen Vorrangfolge.
   - Deutsch nur, wenn das System auf Deutsch läuft (`de`, `de_DE`, `de_AT`, `de_CH` usw.). Für jede andere Sprache gilt Englisch.
   - Übersetzt werden alle sichtbaren Texte: Oberfläche, Befundboxen, Rückfragen, Starter-Eintrag (`Name[de]`, `Comment[de]`) und AppStream-Metadaten.
   - Zahlen- und Einheitenformat folgen der Sprache: Deutsch `1,2 GB`, Englisch `1.2 GB`.
   - Die Texte liegen in einer Datei je Sprache. Fehlt in einer Sprache ein Text, wird der englische angezeigt. Ein Test stellt sicher, dass beide Sprachen dieselben Schlüssel haben.
8. **Einmalige sudo-Einrichtung** (vom User genehmigt, Umfang je nach Hardware, siehe oben):
   - `gir1.2-webkit-6.0` installieren.
   - Bei Intel-Grafik `intel-gpu-tools` installieren und `intel_gpu_top` mit `setcap cap_perfmon=ep` ausstatten.
   - RAPL `energy_uj` **nicht** standardmäßig freigeben. Grund: Laut Security-Audit vom 2026-11-16 wären die Zähler sonst für alle Programme lesbar, auch für Flatpak-Apps (Seitenkanal CVE-2020-8694). Nur mit `--allow-rapl`, nach einer Warnung, die nennt, wer Zugriff erhält und wie man es rückgängig macht. Dauerhaft wird es über eine udev-Regel unter `/etc/udev/rules.d/`, weil tmpfiles beim Booten vor dem RAPL-Treiber laufen kann.

## Nicht-Ziele

- Anzeige in der GNOME-Leiste (Variante C). Sie kommt später als eigenes Projekt, in Stufe 1 entsteht kein Code „für später“.
- Ein kleines Dauerfenster mit „immer im Vordergrund“ (Variante B), vom User ausgeschlossen.
- Verlauf länger als 5 Minuten, Speicherung auf Platte, Protokolle mit Messwerten.
- Warnmeldungen oder Benachrichtigungen bei Grenzwerten.
- Helles Thema.
- RPM-, Arch- oder Flatpak-Pakete. Die Hardware-Unabhängigkeit gilt trotzdem, nur verpackt wird zunächst als .deb.
- Fernzugriff oder Weboberfläche im Browser.
- Weitere Sprachen außer Deutsch und Englisch. Der Aufbau erlaubt sie später ohne Umbau.

## Anti-Ziele (wäre ein Fehlschlag, auch wenn es technisch läuft)

- Das Programm erzeugt selbst spürbare Last. Richtwerte gelten **insgesamt, einschließlich aller WebKit-Prozesse und Hilfsprogramme wie `intel_gpu_top`**: im Mittel höchstens 5 % eines Kerns bei geöffnetem Fenster, höchstens 1,5 % ausgeblendet, RAM unter etwa 250 MB. Gemessen wird auf dem Referenzrechner.
- Es behauptet „hängt“ oder „keine E/A“, wo es das nicht wissen kann.
- Es beendet einen Prozess ohne Rückfrage, oder es trifft wegen einer neu vergebenen PID den falschen Prozess.
- Es öffnet einen Netzwerk-Port oder eine andere Schnittstelle, über die Dritte Prozesse beenden könnten.
- Es stürzt ab oder zeigt Unsinn, weil ein Sensor fehlt oder anders heißt.
- Der Look weicht spürbar von den abgenommenen Entwürfen ab.

## Aussehen (abgenommen)

Verbindliche Vorlage sind die Entwürfe in `docs/superpowers/specs/entwuerfe/`:

- `uebersicht.png` / `uebersicht.html`: Reiter „Übersicht“ (Entwurf 4)
- `prozesse.png` / `prozesse.html`: Reiter „Prozesse“ (Entwurf 5)

Die HTML-Dateien sind Fragmente aus dem Brainstorming-Werkzeug. Ihre Darstellung steckt vollständig im eigenen `<style>`. Im Kopf der Entwürfe steht noch „SYSTEMSTATUS“, im Programm steht dort **ORBITOP**.

Kernpunkte des Stils („Raumstation-Konsole mit Cockpit-Schrift“):

- Immer dunkel, unabhängig vom Systemthema. Hintergrund `#0c1115` → `#06080a`.
- Kacheln, Reiter und Lastzeile mit **abgeschrägten Ecken** (clip-path). Kachelrahmen als Farbverlauf in der Bereichsfarbe.
- **Schriften:** Orbitron für Zahlen und Titel, Oxanium für Text. Beide unter OFL, als Dateien im Projekt, lokal per `@font-face` geladen. Zur Laufzeit gibt es keinen Internetzugriff, abgesehen von der Update-Prüfung in Stufe 2.
- **Eine Farbe je Bereich,** durchgezogen über Rahmen, Titel, Segmente, Kurve und Glanz der großen Zahl:

  | Bereich | Farbe |
  |---|---|
  | CPU | `#4fd8ff` |
  | Grafik | `#c48bff` |
  | RAM | `#3dffa8` |
  | Leistung | `#ffd84f` |
  | Temperatur | `#ff5f7a` |
  | Lüfter | `#ff7ad9` |
  | Netzwerk | `#5b8cff` |
  | Datenträger | `#2ff0d0` |
  | Zweitlinie (Swap, Senden, Schreiben) | `#ffb347` |
  | Warnton | Bernstein `#ffb54a` |

  Weitere Grafikchips bekommen Abstufungen der Grafikfarbe.
- **Segmentanzeige** mit 20 Segmenten über jedem Verlauf, ab 80 % bernsteinfarben.
- **Flächendiagramm:** Fläche mit Farbverlauf bis zur Grundlinie, 1,8 px Linie mit Leuchtsaum, Gitternetz mit 4 waagerechten Linien und einer senkrechten alle 30 s, feine Rasterlinien-Textur. Beschriftung oben links, am rechten Ende ein leuchtender Punkt für den aktuellen Wert.
- Zustände stehen als Plakette mit Symbol **und** Text, nie nur als Farbe.

## Bauweise

### Betrachtete Wege

| Weg | Kurz | Ergebnis |
|---|---|---|
| **1. Python + GTK-4-Fenster mit eingebetteter WebKit-Ansicht** | Python misst, die Oberfläche ist HTML/CSS in `WebKit.WebView`, Datenaustausch über die WebKit-Brücke, kein Port | **Gewählt vom User.** Look 1:1 aus den Entwürfen, keine Angriffsfläche über das Netz, ein Prozess, architekturunabhängig. Kosten: Paket `gir1.2-webkit-6.0` |
| 2. Python-Dienst + Chrome im App-Modus | Lokaler HTTP-Server, Chrome `--app` als Fenster | Verworfen: hängt an Chrome, mehr RAM, offener Port mit Beenden-Funktion |
| 3. Reines GTK 4 mit Cairo-Diagrammen | Alles nativ gezeichnet | Verworfen: Der Konsolen-Look müsste mühsam nachgebaut werden und würde trotzdem abweichen |
| Electron / Tauri, Conky | – | Verworfen: zu schwer bzw. ohne Reiter und Interaktion |
| Flatpak / Snap als Paketform | – | Verworfen: Die Sandbox verhindert den Kern des Programms (siehe Projektdaten) |

### Vom User entschieden

Weg 1, Aufbau „Kachelraster“, Aussehen laut Entwürfen, zweiter Reiter „Prozesse“, ehrliche Zustandseinstufung, einmalige sudo-Einrichtung, Autostart mit der Anmeldung, Name, Lizenz, Repository und Urheberhinweis.

### Eckpunkte (Vorschlag des Planers)

- **Ein Prozess, eine Instanz:** `Gtk.Application` mit Anwendungs-ID `io.github.zappelmann_sketch.orbitop`. Der Mess-Takt läuft im Hauptprogramm und füllt Ringpuffer, egal ob das Fenster sichtbar ist.
- **Weg zur Oberfläche:** Bei sichtbarem Fenster schiebt Python jede Sekunde einen JSON-Schnappschuss per `evaluate_javascript` in die Seite, beim Öffnen zuerst den kompletten Puffer. Aktionen meldet die Seite über `window.webkit.messageHandlers` an Python. Die WebView lädt nur lokale Dateien.
- **Prozesse werden auch bei ausgeblendetem Fenster erhoben**, alle 2 s (siehe unten).
- **Installation in Stufe 1:** Ein Skript im Repository legt den Starter in `~/.local/share/applications/` und den Autostart-Eintrag in `~/.config/autostart/` an (mit `--hidden`). Die hardwareabhängige sudo-Einrichtung ist ein eigener, ausdrücklich aufzurufender Schritt.
- **Mission Center (vom User entschieden):** Erst wenn der User orbitop abgenommen hat, wird nur der Autostart-Eintrag `~/.config/autostart/io.missioncenter.MissionCenter.desktop` entfernt. Das Flatpak bleibt installiert. Bis zur Abnahme bleibt Mission Center im Autostart.

### Für Stufe 2 vorbereitet (ohne Stufe-2-Code)

- Die Versionsnummer steht an genau einer Stelle und ist im Programm sichtbar, etwa in einem Info-Dialog mit Lizenz und Urheberhinweis.
- Das Programm läuft unverändert aus dem Repository wie aus einer Installation unter `/usr`. Pfade zu Oberfläche, Schriften und Symbolen werden relativ zum Programm ermittelt, nicht fest verdrahtet.
- Starter, Symbol und AppStream-Metadaten (`.metainfo.xml`) liegen als Dateien im Repository, damit das Paket sie übernehmen kann.

### Dem Builder überlassen

- Modulaufteilung, Datei- und Ordnernamen, Diagramme in SVG oder Canvas (Hauptsache, Look und Last stimmen).
- Wie genau `intel_gpu_top -J`, `nvidia-smi` und die amdgpu-Werte gelesen werden, dazu RAPL `energy_uj`, falls lesbar (nach `--allow-rapl` oder ab Werk). Auf dem Referenzrechner prüfen, für fremde Hardware gegen nachgebaute Verzeichnisbäume testen.
- Wie „Programm ganz beenden“ erreichbar ist (z. B. Knopf in der Kopfzeile oder Strg+Q).
- Schwellen der Einstufung im Detail, solange sie den Definitionen oben entsprechen.
- Bezugswerte der Segmentanzeige für Netzwerk, Datenträger, Leistung und Lüfter.
- Tests mit pytest für Erkennung, Parser, Einstufung und Ringpuffer. Die Oberfläche wird per Screenshot gegen die Entwürfe geprüft.

## Nach dem Builder-Check entschieden (Entscheidungen des Planers, vom User am 2026-11-16 freigegeben)

**1. E/A fremder Prozesse ist nicht einsehbar.** Als normaler Benutzer ist `/proc/<pid>/io` für root-Prozesse und Prozesse anderer Benutzer nicht lesbar. Bei der Messung waren das 175 von 319 Prozessen.
- Für diese Prozesse zeigt die Spalte E/A „–“, die Detailansicht sagt „nicht einsehbar (fremder Prozess)“.
- Statt „Dauerlast, keine E/A“ bekommen sie die gelbe Variante **„Dauerlast, E/A unbekannt“**: mindestens 2 Minuten lang ≥ 90 % eines Kerns und praktisch keine freiwilligen Kontextwechsel. Die Befundbox sagt ausdrücklich, dass die E/A nicht geprüft werden konnte.
- Nicht gewählt: ein privilegierter Lesehelfer. Er kann später kommen, wenn der User das will.

**2. Last des Programms selbst.** Gemessen: psutil braucht für einen Durchlauf über alle Prozesse etwa 71 ms CPU, also rund 7 % eines Kerns bei 1 s Takt. Direktes Lesen von `/proc/<pid>/stat`, `status` und `io` braucht etwa 8 bis 16 ms.
- **Prozess-Erhebung durch direktes Lesen von `/proc`**, alle 2 s, auch bei ausgeblendetem Fenster. Die acht Kacheln bleiben bei 1 s.
- **Das Budget gilt insgesamt** (siehe Anti-Ziele), gemessen über `/proc/<pid>/stat` des Programms, aller WebKit-Kindprozesse und der Hilfsprogramme über mindestens 60 s.
- **Ausgeblendet wird nichts gezeichnet**, es werden keine Schnappschüsse an die WebView geschickt.
- **Der Look hat Vorrang.** Bei Überschreitung gibt zuerst nach, was am Look nichts ändert:
  1. Canvas statt SVG, Leuchtsaum ohne CSS-`filter:blur`.
  2. Nur sichtbare Tabellenzeilen zeichnen.
  3. Mini-Verläufe nur alle 2 s neu zeichnen.
- Reicht auch das nicht, wird der User gefragt.
- Die Messung der eigenen Last ist eine frühe Aufgabe im Plan.

## Offene Punkte

- Stufe 2 bekommt eine eigene Design-Runde.
