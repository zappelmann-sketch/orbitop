# orbitop – Stufe 2: Pakete, Paketquellen und Update-Kanal (Design)

Stand: 2026-11-18 · Status: **vom User freigegeben** (2026-11-18), einschließlich Builder-Check.

Ersetzt den Abschnitt „Stufe 2“ in `docs/superpowers/specs/2026-11-16-orbitop-design.md`. Die dort geplante eingebaute Update-Prüfung ist gestrichen. Weiter gelten die Regeln der Specs vom 2026-11-16 und 2026-11-17, vor allem:
- Budget: ausgeblendet ≤ 3 % eines Kerns, sichtbar ≤ 9 %, PSS < 275 MB.
- Sicherheitsmodell: Seite → Python nur über `parse_message`, Seite unter `orbitop://ui/`, Root-Helfer nur root-eigen und geprüft (`_trusted`).
- Sichtbare Texte nur über `orbitop/locale/{en,de}.json`.
- `root`-Prinzip für alle Leser.
- Keine persönlichen Daten in Repo, Paketen, Paketquelle und Releases.
- Review-Pflicht nach jedem Bauschritt.

## Wozu

Wer orbitop auf Ubuntu, Debian, Fedora, openSUSE oder Arch installiert, soll neue Versionen beim normalen System-Update bekommen, so wie bei Chrome. Dafür gibt es keine zweite Plattform und keinen eigenen Updater. Alles folgt den üblichen Wegen der jeweiligen Distribution (globale Regel des Users „Entwicklung nach Best Practice“). Der User kennt sich mit Linux-Paketierung nicht aus und verlässt sich darauf, dass der Standardweg genommen wird. Er will außerdem, dass orbitop mit jeder Grafik voll funktioniert, und dass alles mit so wenig Angriffsfläche wie möglich gebaut wird.

Erfolg heißt:
- Auf Ubuntu einmal `sudo apt install ./orbitop_0.2.0-1_all.deb`, danach erscheint jede neue Version in `apt upgrade` und in der Aktualisierungsverwaltung. Auf Fedora und openSUSE gilt das Gleiche mit `dnf` und `zypper`, auf Arch nach einem einmaligen Eintrag mit `pacman -Syu`.
- Eine Deinstallation hinterlässt nichts außer den Daten der Benutzer. Ein Purge entfernt auch die Konfiguration.
- Ein verändertes Paket oder eine veränderte Paketquelle lehnt die Paketverwaltung ab.

## Entscheidungen des Users (2026-11-18)

1. Das Repository ist seit 2026-11-18 öffentlich. Es werden nur kostenlose Werkzeuge genutzt (GitHub Free). Betrieben wird nur dieses eine Repository, keine weitere Plattform.
2. Updates kommen nur über die Paketverwaltung. orbitop geht zur Laufzeit nie ins Internet.
3. Es gibt einen Signierschlüssel, Ed25519. Er liegt nur auf dem Notebook des Users. Der öffentliche und der geheime Teil kommen zusätzlich in seine KeePassXC-Datei, damit sie nicht verloren gehen.
4. Unterstützt werden Ubuntu, Debian, Fedora und openSUSE. Arch bleibt unterstützt, weil es ohne fremde Plattform geht (eigene pacman-Quelle). Das AUR wird nicht genutzt.
5. Installiert wird systemweit für den ganzen Rechner, damit alle Benutzer die Updates bekommen. Eine Installation nur für einen Benutzer gibt es nicht.
6. Das Paket richtet nie einen Autostart ein. Jeder Benutzer schaltet ihn selbst ein: per Schalter in der App, oder mit den Befehlen aus der README, dort für einen oder für alle Benutzer. Auf dem Notebook des Users bleibt der Autostart an.
7. orbitop soll mit jeder Grafik voll funktionieren. Fehlende Werkzeuge erkennt orbitop an der Hardware und bietet sie zum Installieren an.
8. Die Freigabe der Messzähler (perfmon, RAPL; CVE-2020-8694) kommt nie von uns aus. Sie soll aber per Schalter mit Admin-Passwort auslösbar sein. Vor ihrem Bau gibt es eine eigene Security-Review-Runde: prüfen, bewerten, dann bauen. Die Vorgabe lautet: so wenig Angriffsfläche wie möglich, stark geschützt.
9. Ein root-Lesedienst für volle Intel-Werte ohne Freigabe kommt später in einer eigenen Runde, nicht in Stufe 2.
10. Stufe 2 kommt in zwei Releases (Vorschlag des Planers, vom User gewählt):
    - **0.2.0:** Pakete, Paketquellen und Update-Kanal, der Autostart-Schalter (6.1) und der Kill-Helfer mit polkit-Action (6.4). Dazu der Wegfall der Stufe-1-Skripte, die README und der Umstieg auf dem Notebook.
    - **0.3.0:** zuerst die Security-Runde, dann der Knopf „Installieren“ (6.2) und der Freigabe-Schalter (6.3). 0.3.0 kommt schon über den Update-Kanal und ist dessen erster echter Test.
    - Bis 0.3.0 nennt die README die Freigabe als Befehl mit Risikohinweis, wie bisher `setup-privileges.sh`. Auf dem Notebook des Users bleibt sie gesetzt.

Das Wie hat der User dem Planer überlassen. Der Weg zur Veröffentlichung (unten „Wege“) ist daher die Wahl des Planers.

## Ziele, Nicht-Ziele, Anti-Ziele

**Ziele**
- Pakete in vier Formaten: `.deb`, RPM für Fedora, RPM für openSUSE, Arch-Paket.
- Signierte Paketquellen für apt, dnf, zypper und pacman als statische Dateien auf GitHub Pages.
- Ein lokaler Release-Ablauf, der baut, prüft, in frischen Containern testet, signiert und veröffentlicht.
- Drei Änderungen in der App: ein Schalter für den Autostart (0.2.0), ein Knopf „Installieren“ für fehlende Werkzeuge und ein Schalter für die Freigabe (beide 0.3.0).
- Der Umstieg auf dem Notebook des Users von 0.1.0 (Checkout) auf das Paket.
- Eine überarbeitete README in beiden Sprachen.

**Nicht-Ziele**
- Flatpak, Snap, AUR, PPA oder eine Aufnahme in die offiziellen Archive.
- Weitere Distributionen. Abgeleitete wie Linux Mint nutzen das Ubuntu-Paket, ohne eigens geprüft zu sein.
- ARM-Rechner.
- Der root-Lesedienst (siehe Entscheidung 9).

**Anti-Ziele**, die das Ergebnis auch dann zum Fehlschlag machen, wenn es technisch läuft:
- Ein Updater oder eine Installation am Paketmanager vorbei.
- Autostart oder Freigaben, die ungefragt eingeschaltet werden.
- Ein Paket ändert Dateien anderer Pakete, etwa `/etc/pacman.conf`. Einzige Ausnahme ist die vom Admin per Schalter ausdrücklich eingeschaltete Fähigkeit auf `intel_gpu_top`; die Security-Runde bewertet sie.
- Schlüssel oder Passphrase im Repository, in einem Container-Image oder bei GitHub.
- Persönliche Daten in Paketen, Paketquelle, Release-Dateien oder Bildern.

## Rahmen (geprüft)

- **GitHub Pages:**
  - Auf GitHub Free nur für öffentliche Repos.
  - Seite höchstens 1 GB, weiches Limit 100 GB Datenverkehr im Monat.
  - Veröffentlichen aus einem Zweig geht ohne GitHub Actions.
  - Quellen: docs.github.com, Seiten „GitHub Pages limits“, „Creating a GitHub Pages site“ und „Configuring a publishing source“.
- **apt (Debian-Wiki `DebianRepository/UseThirdParty`):**
  - Den Schlüssel eines Pakets legt das Paket nach `/usr/share/keyrings/`, nie nach `/etc/apt/trusted.gpg.d`, nie per `apt-key`.
  - `Signed-By` zeigt auf eine Datei, nicht auf einen Fingerabdruck.
  - Das Paket darf seine `.sources`-Datei (deb822) mitliefern.
- **Debian Policy 9.1.2:** Pakete legen nichts unter `/usr/local` ab. Der Root-Helfer zieht deshalb aus `/usr/local/libexec/orbitop/` an einen Ort des Pakets um.
- **Ed25519 im Container-Test (2026-11-18), alle mit Wegwerfschlüssel und Installation erfolgreich:**

  | System | Werkzeug und Version | Signaturprüfung | Manipulation |
  |---|---|---|---|
  | Ubuntu 24.04 | apt 2.8.4 | gpgv | |
  | Ubuntu 26.04 | apt 3.2.1 | gpgv | verändertes `Release` und `Packages.gz` abgelehnt |
  | Debian 13 | apt 3.0.4 | sqv | |
  | Fedora 45 | rpm 6.1.0, dnf5 5.4.6 | Pakete und `repomd.xml.asc` | |
  | openSUSE Tumbleweed | rpm 4.20.1, zypper 1.14.102 | Pakete und `repomd.xml.asc` | |
  | Arch | pacman 7.1.0 | Paket-`.sig` und Datenbank-`.sig` | ohne bestätigten Schlüssel abgelehnt |

- **Fedora und openSUSE** benennen die Abhängigkeiten verschieden. Nur openSUSE kennt `typelib(Gtk) = 4.0` und `typelib(WebKit) = 6.0`; Fedora braucht die Paketnamen `gtk4` und `webkitgtk6.0`. Es gibt also ein Bau-Rezept mit `%if 0%{?suse_version}` und daraus zwei RPM-Dateien.
- **Paketgröße:** etwa 110 KB je Paket. Ein Release mit vier Paketen und den Metadaten bringt etwa 0,5 MB.

## Wege

**A: Alles lokal, Pages aus dem Zweig `gh-pages` (gewählt).**
- Ein Release-Skript auf dem Notebook baut die Pakete in Wegwerf-Containern, prüft und testet sie und signiert auf dem Notebook.
- Es legt die fertige Paketquelle in einen verwaisten Zweig `gh-pages` im selben Repository. Pages zeigt diesen Zweig.
- Es gibt keinen GitHub-Workflow mit Schreibrecht, also die kleinste Angriffsfläche und am wenigsten Technik.
- Der Git-Verlauf wächst um etwa 0,5 MB je Release; nach 100 Releases sind es rund 50 MB.

**B: Lokal signieren, ein GitHub-Workflow stellt die Dateien aus dem Release auf Pages.**
- Der Git-Verlauf bleibt frei von Paketdateien.
- Dafür braucht es einen Workflow mit Schreibrecht auf Pages. Das ist zusätzliche Technik und Angriffsfläche, auch wenn die Signaturen jede Manipulation verraten würden.
- Nicht gewählt: Der Vorteil ist bei 0,5 MB je Release klein.

**C: In GitHub Actions bauen, nur lokal signieren.** Verworfen: Signiert wird ohnehin lokal, und die Pakete hin und her zu laden bringt nur weitere Teile.

## Design

### 1. Pakete

| Format | Für | Datei |
|---|---|---|
| `.deb`, `Architecture: all` | Ubuntu 24.04 und 26.04, Debian 13 und Nachfolger | `orbitop_<version>-<rev>_all.deb` |
| RPM `noarch`, Fedora-Variante | Fedora 45 und Nachfolger | `orbitop-<version>-<rev>.noarch.rpm` |
| RPM `noarch`, openSUSE-Variante | openSUSE Tumbleweed | `orbitop-<version>-<rev>.noarch.rpm` (eigenes Verzeichnis) |
| Arch, `arch=any` | Arch Linux | `orbitop-<version>-<rev>-any.pkg.tar.zst` |

- **Ein Paket je Familie für alle Versionen**, weil orbitop reines Python ist. Eine neue Ubuntu-Version braucht kein neues Paket, nur einen Container-Test. Das ist der Wartungsablauf bei neuen Distributionsversionen.
- **Untergrenze** über die Abhängigkeit „Python ≥ 3.12“. Auf Debian 12 oder Ubuntu 22.04 bricht die Installation dann mit der Meldung der Paketverwaltung ab.
- **Versionen:**
  - Die Upstream-Version steht nur in `orbitop/__init__.py`.
  - Das erste Paket-Release ist 0.2.0: Debian `0.2.0-1`, RPM `Version: 0.2.0` mit `Release: 1`, Arch `pkgver=0.2.0` mit `pkgrel=1`.
  - Bei Änderungen nur am Paket steigt die Revision.
- **Abhängigkeiten:** Die Namen kommen aus der Pakettabelle der README und aus `setup-privileges.sh`. Der Builder prüft jede Zeile im Container.

  | | Debian/Ubuntu | Fedora | openSUSE | Arch |
  |---|---|---|---|---|
  | Python ≥ 3.12 | `python3 (>= 3.12)` | `python3 >= 3.12` | `python3 >= 3.12` | `python>=3.12` |
  | PyGObject | `python3-gi` | `python3-gobject` | `python3-gobject`, `python3-gobject-Gdk` | `python-gobject` |
  | GTK 4 | `gir1.2-gtk-4.0` | `gtk4` | `typelib(Gtk) = 4.0` | `gtk4` |
  | WebKitGTK 6.0 | `gir1.2-webkit-6.0` | `webkitgtk6.0` | `typelib(WebKit) = 6.0` | `webkitgtk-6.0` |
  | pkexec | `pkexec` | `polkit` | `polkit` | `polkit` |
  | `setcap` (Freigabe, ab 0.3.0) | `libcap2-bin` | `libcap` | `libcap-progs` | `libcap` |
  | nur vorgeschlagen | `Suggests: intel-gpu-tools` | `Suggests: igt-gpu-tools` | `Suggests: igt-gpu-tools` | `optdepends: intel-gpu-tools` |

  Die Intel-Werkzeuge sind nur vorgeschlagen und werden nicht automatisch mitinstalliert. orbitop bietet sie bei Bedarf an (6.2).
- **Inhalt und Orte** nach dem FHS:

  | Inhalt | Ort |
  |---|---|
  | Starter | `/usr/bin/orbitop` |
  | Programm (Python, Oberfläche, Schriften, `locale`) | privates Verzeichnis, Vorschlag `/usr/share/orbitop/` |
  | Root-Helfer | Vorschlag `/usr/libexec/orbitop/` |
  | polkit-Actions | `/usr/share/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy` (polkit(8) erlaubt keinen Unterstrich im Namensraum; Plan K8) |
  | Starter-Eintrag, Symbol, AppStream | `/usr/share/applications/`, `/usr/share/icons/hicolor/…`, `/usr/share/metainfo/` |
  | Autostart-Vorlage (nicht aktiv) | `/usr/share/orbitop/autostart.desktop` mit `Exec=orbitop --hidden` und `TryExec=orbitop` |
  | Lizenz, Copyright | `/usr/share/doc/orbitop/` oder `%license`, je nach Format |

  Der Builder prüft beide Vorschläge vor dem Bau gegen die Regeln aller vier Formate: das private Verzeichnis gegen die Debian Python Policy, `/usr/libexec` gegen die Debian Policy. Er nimmt den Ort, den alle erlauben. Sonst schlägt er einen Ort je Format vor.
- **Gleicher Code wie aus dem Checkout:** Das Programm läuft aus `/usr` mit demselben Code wie aus dem Checkout. Die Pfade werden relativ zum Programm ermittelt; das war schon in Stufe 1 so vorbereitet.

### 2. Paketquellen auf GitHub Pages

Adresse ist `https://zappelmann-sketch.github.io/orbitop/`. Der Zweig `gh-pages` ist verwaist, enthält nur die Seite und eine `.nojekyll`-Datei:

```
index.html                         kurze Seite: was das ist, Fingerabdruck, Verweis auf die README
orbitop-archive-keyring.asc        öffentlicher Schlüssel (dazu die Binärform .pgp)
apt/dists/stable/InRelease, Release, Release.gpg
apt/dists/stable/main/binary-all/Packages, Packages.gz
apt/pool/main/o/orbitop/orbitop_<version>-<rev>_all.deb
rpm/fedora/repodata/…  (repomd.xml, repomd.xml.asc, repomd.xml.key)  + orbitop-<version>-<rev>.noarch.rpm
rpm/opensuse/repodata/…  + orbitop-<version>-<rev>.noarch.rpm
arch/x86_64/orbitop.db, orbitop.db.sig, orbitop.files, orbitop.files.sig, orbitop-<version>-<rev>-any.pkg.tar.zst, .sig
```

- **apt:**
  - Suite `stable`, Komponente `main`, ein Stand für alle Debian- und Ubuntu-Versionen.
  - Signiert als `InRelease` (clearsign) und `Release.gpg`.
  - Kein `Valid-Until`. Damit müsste die Quelle regelmäßig neu signiert werden, also ständig mit der Passphrase des Users. Das Restrisiko ist eine „Freeze“-Attacke: Ein Angreifer, der die Seite kontrolliert, könnte alte, gültig signierte Stände ausliefern und so Updates zurückhalten. Bei HTTPS von GitHub ist das gering und wird hingenommen.
- **RPM:** Pakete mit `rpmsign` signiert, `repomd.xml.asc` daneben, in der `.repo`-Datei `gpgcheck=1` und `repo_gpgcheck=1`.
- **Arch:** Paket und Datenbank je mit `.sig` signiert, `SigLevel = Required DatabaseRequired`.
- **Nur die neueste Version** liegt in der Paketquelle. Ältere bleiben in den GitHub-Releases.

### 3. Erste Installation, Updates, Deinstallation

Je Distribution gibt es in der README einen Weg:

- **Ubuntu, Debian:**
  - Das `.deb` aus dem Release laden und mit `sudo apt install ./orbitop_….deb` installieren.
  - Das Paket bringt `/etc/apt/sources.list.d/orbitop.sources` (deb822, `Signed-By: /usr/share/keyrings/orbitop-archive-keyring.pgp`) und den Schlüssel mit.
  - **Umsetzung (Plan K3, Rulings aus Task 3):** Quelle, Schlüssel und Pinning stecken im kleinen Paket `orbitop-apt-source`, alle als Conffiles unter `/etc/apt/` (Schlüssel `/etc/apt/keyrings/orbitop-archive-keyring.pgp`). So bleibt nach `apt remove` nie eine Quelle ohne Schlüssel zurück, und ein Purge entfernt alles.
  - Updates kommen über `apt upgrade` und die Aktualisierungsverwaltung.
  - **Pflicht:** Nach `apt remove orbitop` darf `apt update` keinen Fehler zeigen. Eine verwaiste Quelle mit fehlendem Schlüssel ist nicht erlaubt. Der Builder löst das und testet es.
  - Nach `apt purge` bleibt nichts.
  - **Zu prüfen:** Beim Upgrade auf eine neue Ubuntu-Version schaltet Ubuntu Fremdquellen ab. Die README erklärt, wie man die Quelle wieder einschaltet. Weil die Suite `stable` unabhängig von der Ubuntu-Version ist, ist das ungefährlich. Der Builder prüft das Verhalten.
- **Fedora:**
  - `sudo dnf install ./orbitop-….noarch.rpm`.
  - Das Paket bringt `/etc/yum.repos.d/orbitop.repo` (`gpgcheck=1`, `repo_gpgcheck=1`, `gpgkey=file:///…`) und den Schlüssel mit.
  - dnf fragt beim ersten Update einmal, ob es den Schlüssel übernehmen soll. Die README zeigt den Fingerabdruck zum Vergleich.
- **openSUSE:** wie Fedora mit `zypper`. Das Paket bringt `/etc/zypp/repos.d/orbitop.repo` mit (`autorefresh=1`, `gpgcheck=1`, `repo_gpgcheck=1`). Wie die erste Installation einer lokalen, signierten RPM mit noch unbekanntem Schlüssel ohne Warnung klappt, klärt der Builder im Container: zuerst `rpm --import`, oder direkt installieren.
- **Arch:**
  - Einmal von Hand: Schlüssel von der Seite laden, Fingerabdruck mit der README vergleichen, `pacman-key --add` und `pacman-key --lsign-key`, einen Abschnitt `[orbitop]` mit `Server = https://zappelmann-sketch.github.io/orbitop/arch/$arch` an `/etc/pacman.conf` anhängen, dann `pacman -Syu orbitop`.
  - Das Paket bringt seinen Schlüssel für `pacman-key --populate` mit, damit spätere Schlüsseländerungen wie eine verlängerte Laufzeit mit dem Update ankommen.
  - Zur Deinstallation erklärt die README `pacman -R orbitop`, das Entfernen des Abschnitts und `pacman-key --delete`.

**Vor dem Bau prüfen:**
- Fedora und openSUSE: Der Builder liest ihre Paketierungsregeln. Verlangen sie für Fremdquellen ein eigenes `*-release`-Paket statt der `.repo`-Datei im Hauptpaket, schlägt er das vor.
- Fingerabdruck und Prüfsummen:
  - Der Fingerabdruck steht in der README im Repository, nicht nur auf der Seite.
  - Jedes Release hat `SHA256SUMS` und eine Signatur `SHA256SUMS.asc`.

### 4. Signierschlüssel

- **Der Schlüssel** (Wahl des Planers):
  - Ein Ed25519-Hauptschlüssel, der direkt signiert, ohne Unterschlüssel. Verlangt ein Werkzeug einen Unterschlüssel, schlägt der Builder das vor.
  - User-ID `orbitop archive signing key`, ohne Mail-Adresse.
  - Laufzeit 3 Jahre. Das Release-Skript warnt, wenn weniger als 6 Monate bleiben. Eine Verlängerung kommt als neuer öffentlicher Schlüssel mit einem Paket-Update, solange der alte noch gilt.
  - Dazu ein Widerrufszertifikat.
- **Aufbewahrung und Schutz:**
  - Eine Passphrase ist Pflicht. Der gpg-agent fragt per Pinentry, und eine Eingabe reicht für ein ganzes Release.
  - Der Schlüssel liegt auf dem Notebook des Users in einem eigenen GnuPG-Ordner mit eigenem gpg-agent, in dem nur er liegt (geändert nach dem Security-Audit von Task 5: der für `rpmsign` eingehängte Agent-Socket könnte sonst mit jedem anderen Schlüssel im Agent signieren und entschlüsseln).
  - Er liegt nie im Repository, in einem Container oder bei GitHub. Für `rpmsign` im Container bekommt dieser höchstens den eingeschränkten Zusatz-Socket des gpg-agent (`extra-socket`), nie die Schlüsseldatei. Der Builder prüft den Weg; eine Alternative ist `rpmsign` auf dem Notebook.
- **Erzeugung:** Einmalig mit dem User, nach einer Anleitung im Repository (`docs/release.md`, ohne persönliche Daten).
- **Sicherung in KeePassXC:**
  - Exportiert werden drei Dateien in `$XDG_RUNTIME_DIR`, das im Arbeitsspeicher liegt: der geheime Schlüssel (armored, durch die Passphrase geschützt), der öffentliche Schlüssel und das Widerrufszertifikat.
  - Der User hängt sie an einen Eintrag, per Oberfläche oder mit `keepassxc-cli attachment-import`. Die Passphrase ist das Passwort des Eintrags. Die KeePass-Datei öffnet nur der User.
  - Danach werden die Exporte gelöscht.
  - Die Anleitung beschreibt auch die Wiederherstellung.
- **Entwicklung:** Bis zum ersten echten Release testet alles mit einem Wegwerfschlüssel. Den echten Schlüssel gibt es erst kurz vor 0.2.0.

### 5. Release-Ablauf

Ein Skript im Repository, Name nach Wahl des Builders, etwa `scripts/release.sh <version>`:

1. **Vorprüfung:**
   - Sauberer Stand auf `main`, die Version passt.
   - Die strenge Testsuite läuft durch.
   - Die Laufzeit des Schlüssels ist geprüft.
   - Die Changelogs der Formate entstehen aus einer Quelle.
2. **Bauen:** in Wegwerf-Containern, `docker run --rm` ohne `--privileged` und ohne Zusatzrechte, mit einer schreibgeschützten Kopie der verfolgten Dateien.
3. **Lint:** `lintian`, `rpmlint` und `namcap` ohne Fehler. Verbleibende Warnungen sind in `docs/release.md` begründet.
4. **Signieren:** auf dem Notebook (siehe 4).
5. **Seite zusammenstellen:** der Baum für `gh-pages`, nur mit der neuesten Version.
6. **Container-Test:** gegen die signierte, lokale Seite auf frischen Images, nämlich Ubuntu 24.04, Ubuntu 26.04, Debian 13, Fedora, Tumbleweed und Arch. Getestet werden:
   - erste Installation wie in der README
   - Update von der vorigen Version über die Paketverwaltung, mit einer lokalen Testversion, die nie veröffentlicht wird
   - `orbitop --version`
   - Deinstallation und Purge, ohne Reste (Vergleich der Dateilisten)
   - manipulierte Metadaten, die abgelehnt werden müssen

   Die Ergebnisse stehen in `docs/distro-check.md`. Diese Matrix ersetzt die bisherige Prüfung von `setup-privileges.sh`.
7. **Veröffentlichen:**
   - Ein annotierter Tag `v<version>`.
   - Ein GitHub-Release mit Quellarchiv, den vier Paketen, `SHA256SUMS` und `SHA256SUMS.asc`.
   - Ein Push von `main`, Tag und `gh-pages`, jeweils mit ausdrücklich genannten Refs, nie `--all` oder `--mirror`.
   - Am Ende wird geprüft, dass Pages den neuen Stand ausliefert.

Ohne den User wird nichts veröffentlicht, weil nur er die Passphrase kennt.

**Haltepunkte mit dem User** (Wahl des Planers): Schlüssel erzeugen, Sicherung in KeePassXC, Passphrase bei jedem Release, alle Befehle mit `sudo` auf dem Notebook. Bis dahin ist alles mit dem Wegwerfschlüssel geprüft, und die Befehle für den User liegen fertig vor. GitHub Pages schaltet der Planer beim ersten Release per `gh api` auf den Zweig `gh-pages` ein, nach dem Go des Users zum Release.

**Images:** Getestet wird auf den genannten Images. Gibt es ein Tag nicht mehr oder zeigt `fedora:latest` auf eine neuere Version, nimmt der Builder das aktuelle Image und trägt die tatsächlich geprüfte Version in `docs/distro-check.md` ein; die README übernimmt nur, was dort `pass` hat (Wahl des Planers).

### 6. Änderungen in der App

**6.1 Schalter „Beim Anmelden starten“ (0.2.0)**
- Der Schalter ist anfangs aus und gilt nur für den eigenen Benutzer.
- Eingeschaltet legt orbitop `~/.config/autostart/io.github.zappelmann_sketch.orbitop.desktop` an, als Kopie der Vorlage. Ausgeschaltet entfernt es die Datei wieder. Geschrieben wird atomar wie in `layout.py`, und nur in `$XDG_CONFIG_HOME` (sonst `~/.config`).
- Hat der Admin den Autostart für alle eingeschaltet (`/etc/xdg/autostart/…`), schreibt „aus“ eine eigene Datei mit `Hidden=true`, wie es die freedesktop-Autostart-Spezifikation vorsieht.
- Die Seite meldet nur „an“ oder „aus“, nie einen Pfad.
- Ort in der Oberfläche (Wahl des Planers): ein Bereich „Einstellungen“ beim Dialog „Über“, im Stil der bestehenden Oberfläche. Er wird per Screenshot gegen den Stil geprüft.
- Texte in beiden Sprachen, danach eine Eigenlast-Messung.

**6.2 Fehlende Werkzeuge (0.3.0)**
- **Intel ohne `intel_gpu_top`:** Der bestehende Hinweis bekommt den Knopf „Installieren“. Er übergibt den Wunsch über den System-D-Bus an PackageKit, mit einem festen Paketnamen je Distribution; die Seite gibt keinen Namen vor. PackageKit fragt nach seiner eigenen polkit-Regel. Fehlt PackageKit oder scheitert der Auftrag, zeigt der Hinweis den Befehl der Distribution, wie heute bei fehlenden Laufzeitpaketen.
- **NVIDIA ohne `nvidia-smi`:** Der Hinweis erklärt, wie man den proprietären Treiber bekommt, etwa unter Ubuntu über „Zusätzliche Treiber“. Es gibt keinen Knopf, denn den Treiber wählt der Benutzer.
- **AMD:** Es braucht nichts.
- Der Knopf gehört mit in die Security-Runde (6.3).

**6.3 Schalter für die Freigabe der Messzähler (perfmon, RAPL; 0.3.0)**
- Sichtbar für alle, anfangs aus.
- Vor der Passwortabfrage erklärt ein kurzer Text das Risiko (CVE-2020-8694, Platypus). Danach folgt polkit mit `auth_admin` bei jedem Umschalten, nie `auth_admin_keep`.
- Der Schalter zeigt den aktuellen Zustand, gelesen ohne root.
- **Vor dem Bau die Security-Review-Runde:**
  - Bedrohungsmodell, Prüfung und Bewertung jeder Stelle.
  - Das Ergebnis steht in einem eigenen Dokument, bevor Code für 6.2 oder 6.3 entsteht.
  - Erst dann wird gebaut, danach folgen Review und Audit wie immer.
- Das Dokument liegt unter `docs/superpowers/specs/` als eigene Datei (Wahl des Planers).
- Ändert die Runde nur den Mechanismus, baut der Planer die bessere Lösung selbst; das hat der User so vorgegeben. Würde sie eine Funktion streichen oder für den Benutzer sichtbar ändern, etwa RAPL weglassen, entscheidet der User vorher (Wahl des Planers).
- **Vorschlag, den die Runde bewertet:**
  - **Fester Helfer:** Ein root-Helfer aus dem Paket kennt genau vier Aufträge: perfmon an, perfmon aus, RAPL an, RAPL aus. Er nimmt keine Pfade und keine freien Argumente. Der Ort von `intel_gpu_top` steht fest, und `_trusted` prüft wie beim Kill-Helfer.
  - **Zustand:** Der Zustand steht in root-eigenen Merkdateien unter `/etc/orbitop/`.
  - **RAPL:** Die udev-Regel liefert das Paket fest mit (`/usr/lib/udev/rules.d/`). Sie greift nur, wenn die Merkdatei da ist (`TEST==`). Der Helfer schreibt also keinen Regeltext, er legt nur die Merkdatei an oder entfernt sie und löst udev aus. Bei „aus“ setzt er die Rechte von `energy_uj` auf den Kernel-Standard zurück.
  - **perfmon:** `setcap cap_perfmon=ep` auf den festen Pfad. Nach einem Update der Intel-Werkzeuge setzt ein Auslöser der Paketverwaltung die Fähigkeit wieder, wenn die Merkdatei da ist: ein dpkg-Trigger, ein RPM-Dateitrigger, ein pacman-Hook.
  - **Deinstallation:** Sie nimmt beide Freigaben zurück. Ein Purge entfernt `/etc/orbitop/`.

**6.4 Kill-Helfer (0.2.0)**
- Der Kill-Helfer zieht an den Ort des Pakets (siehe 1). Die Prüfung `_trusted` bleibt.
- Er bekommt seine eigene polkit-Action mit `auth_admin` und einer passenden `exec.path`-Annotation; das verlangt schon die Stufe-1-Spec.
- Aus einem Checkout ohne installiertes Paket gibt es keinen Helfer, das Ergebnis ist `nohelper`.

**6.5 Übergang bis 0.3.0**
- Die Hinweise `hint.igt_noperm` und der Hinweis auf fehlende Laufzeitpakete nennen heute `setup-privileges.sh`. In 0.2.0 verweisen sie stattdessen auf die README, in beiden Sprachen.
- Die README nennt für perfmon und RAPL die Befehle zum Ein- und Ausschalten mit dem Risiko, so wie sie `setup-privileges.sh` bisher ausgeführt hat. 0.3.0 ersetzt das durch den Schalter.

### 7. Die Skripte aus Stufe 1

`scripts/install-user.sh` und `scripts/setup-privileges.sh` entfallen (Wahl des Planers). Ihre Aufgaben übernehmen:
- das Paket: Abhängigkeiten, Helfer, Starter, Symbol
- die App: Autostart und Freigabe
- die README: Autostart für alle Benutzer

`scripts/check-distros.sh` prüft künftig die Pakete (5.6). Tests und Dokumente ziehen mit, toter Code fällt weg. Aus einem Checkout zu starten bleibt für die Entwicklung möglich: die Laufzeitpakete aus der README-Tabelle installieren, dann `bin/orbitop`.

### 8. Umstieg auf dem Notebook des Users

Die Befehle mit `sudo` führt der User aus; der Planer bereitet sie vor und prüft danach.

Mit 0.2.0:

1. **Stand festhalten:** Ist der Autostart an? Hat `intel_gpu_top` die Fähigkeit `cap_perfmon` (`getcap`)? Gibt es die RAPL-Regel aus 0.1.0?
2. **Alte Teile entfernen:**
   - `scripts/install-user.sh --uninstall`, solange es das Skript noch gibt.
   - `sudo rm -r /usr/local/libexec/orbitop`.
   - Die Fähigkeit auf `intel_gpu_top` und eine vorhandene RAPL-Regel bleiben bis 0.3.0 unverändert.
3. **Neu einrichten:** das Paket installieren und in der App den Autostart einschalten.
4. **Prüfen:** `apt policy orbitop` zeigt die eigene Quelle.

Mit 0.3.0: Fähigkeit und alte RAPL-Regel entfernen, dann in der App den Freigabe-Schalter einschalten, damit Merkdateien und Zustand zusammenpassen.

Die README bekommt einen kurzen Abschnitt „Umstieg von 0.1.0“, denn 0.1.0 ist öffentlich.

Der Umstieg wird mit dem User wirklich durchgeführt und ist Teil der Abnahme, nicht nur dokumentiert.

### 9. README

Beide Sprachen sind gleich aufgebaut (`tests/test_readme.py`). Sie enthalten:
- je Distribution die erste Installation und das Prüfen von Fingerabdruck und `SHA256SUMS.asc`
- Updates
- Autostart für einen oder für alle Benutzer, mit Ein- und Ausschalten
- je Grafik, was gebraucht wird, sowie der Freigabe-Schalter und sein Risiko
- Deinstallation und Purge je Distribution, für Arch mit dem Entfernen des Abschnitts
- den Umstieg von 0.1.0
- „Aus dem Quellcode starten“ für die Entwicklung

Als unterstützt gilt nur, was in `docs/distro-check.md` mit `pass` steht.

### 10. Sicherheit, Grundlage für das Audit

| Gefahr | Antwort |
|---|---|
| Schlüssel gestohlen oder verloren | Passphrase, Sicherung in KeePassXC, Widerrufszertifikat, Ablauf in `docs/release.md` |
| Seite oder Release verändert | Signaturen; Fingerabdruck in der README im Repository; `SHA256SUMS.asc` |
| Vertrauen bei der ersten Installation | HTTPS von GitHub und der Fingerabdruck zum Vergleich |
| Alte Stände ausgeliefert (Freeze) | Restrisiko ohne `Valid-Until`, hingenommen (siehe 2) |
| root-Code in Paketskripten, Triggern, Hooks | so wenig wie möglich, feste Pfade, kein Netz, keine Eingaben von Benutzern |
| Helfer | root-eigen, `_trusted`, polkit `auth_admin` bei jedem Aufruf, feste Aufträge |
| PackageKit-Auftrag | feste Paketnamen, nichts von der Seite |
| Autostart-Schalter | schreibt nur im eigenen Konfigurationsordner, kein Pfad von der Seite |
| Persönliche Daten | Review prüft Dateilisten der Pakete, die Seite, die Release-Dateien und Bilder |

### 11. Abnahme

- Die strenge Testsuite ist grün. Neue Tests decken ab:
  - den Autostart-Schreiber (auch mit `Hidden=true`)
  - den PackageKit-Auftrag gegen einen Fake-Bus
  - die Aufträge des Freigabe-Helfers
  - die Dateilisten der Pakete
- `lintian`, `rpmlint` und `namcap` laufen ohne Fehler.
- Die Container-Matrix aus 5.6 ist auf allen Zielen `pass`.
- Die Eigenlast bleibt nach den Änderungen an der Oberfläche im Budget.
- **0.2.0:** auf dem Notebook des Users über die Paketquelle installiert, `apt policy orbitop` zeigt die Quelle, Audit über alles in 0.2.0.
- **0.3.0:** Die Security-Runde für 6.2 und 6.3 ist dokumentiert, bevor gebaut wird. 0.3.0 kommt auf dem Notebook über `apt upgrade` an. Am Ende gibt es ein Audit über ganz Stufe 2.

### 12. Quellen

**Gelesen:**
- Debian-Wiki `DebianRepository/UseThirdParty` und `DebianRepository/Format`
- Debian Policy 9.1.2
- GitHub Docs zu Pages: Grenzen, Free-Tarif, Veröffentlichungsquelle
- `pacman.conf(5)`, `repo-add(8)`, `pacman-key(8)`
- `dnf5.conf(5)`
- der Container-Test vom 2026-11-18

**Prüft der Builder vor dem Bau** (globale Regel):
- ArchWiki „Unofficial user repositories“ und „Pacman/Package signing“; der Abruf war blockiert.
- die Fedora Packaging Guidelines zu Fremdquellen und `.repo`-Dateien
- die openSUSE Packaging Guidelines
- die Debian Python Policy zu privaten Modulen und die Debian Policy zu `/usr/libexec`
- die freedesktop-Spezifikation „Desktop Application Autostart“
- polkit (`exec.path`)
- die PackageKit-D-Bus-Schnittstelle
- das Verhalten von `ubuntu-release-upgrader` bei Fremdquellen

### 13. Dem Builder überlassen

- Namen der Skripte und die Ordnerstruktur für die Paketdateien, etwa `packaging/debian/`, `packaging/rpm/orbitop.spec`, `packaging/arch/PKGBUILD`.
- Debian-Bau mit `debian/`-Verzeichnis oder schlankem `dpkg-deb`, solange `lintian` ohne Fehler bleibt.
- Das RPM-Dist-Kürzel, die Erzeugung der Changelogs und die Gestaltung von `index.html`.
- Der genaue Ort der Einstellungen in der Oberfläche (6.1), im Stil der bestehenden Oberfläche.
- Wie `rpmsign` signiert, solange die Schlüsseldatei den GnuPG-Schlüsselbund nicht verlässt.

### 14. Reihenfolge, Vorschlag für den Plan

**0.2.0** (eigener Plan):
1. Pakete, Paketquelle, Release-Skript und Container-Matrix, mit Wegwerfschlüssel.
2. Der Autostart-Schalter, der Umzug des Kill-Helfers mit polkit-Action, der Wegfall der Stufe-1-Skripte und der Übergang aus 6.5.
3. Die README und `docs/distro-check.md`.
4. Der echte Schlüssel mit dem User, mit der Sicherung in KeePassXC.
5. Der Umstieg auf dem Notebook und das Release 0.2.0.

**0.3.0** (eigener Plan nach der Security-Runde):
1. Die Security-Runde für Knopf und Freigabe-Schalter, mit Dokument.
2. Der Bau von 6.2 und 6.3, die Paket-Auslöser und die README.
3. Das Release 0.3.0 über den Update-Kanal und der Umstieg der Freigabe auf dem Notebook.
