# orbitop

[English](README.md)

Ein Systemmonitor für Linux, der zeigt, was der Rechner unter Last tut und warum.

## Was orbitop ist und wofür

orbitop zeigt CPU, GPU, Arbeitsspeicher, Leistung, Temperaturen, Lüfter, Netzwerk und Datenträger als laufende Verläufe der letzten 5 Minuten. Die Prozessliste sagt, welcher Prozess die Last verursacht und ob er arbeitet, wartet, ohne Lebenszeichen rechnet oder im Kernel hängt. Hängt ein Prozess, lässt er sich aus der Liste beenden, immer erst nach einer Rückfrage.

orbitop ist ein GTK-4-Fenster mit einer WebKitGTK-6.0-Ansicht, geschrieben in Python, nur mit der Standardbibliothek und PyGObject. Es läuft auf jeder Hardware: Ein fehlender Sensor erscheint als „nicht vorhanden“ und führt zu keinem Fehler. Die Oberfläche gibt es auf Deutsch und Englisch, sie folgt der Systemsprache.

**Stand:** Version 0.2.0. orbitop gibt es als Paket für Ubuntu, Debian, Fedora, openSUSE und Arch Linux aus einer eigenen, signierten Paketquelle. Neue Versionen kommen mit dem normalen System-Update; orbitop selbst geht nie ins Internet.

## Funktionen

### Reiter „Übersicht“

- Je eine Kachel für CPU, jede GPU, Arbeitsspeicher, Leistung, Temperaturen, Lüfter, Netzwerk und Datenträger, mit einem Verlauf der letzten 5 Minuten, ein Wert je Sekunde. Die CPU-Kachel hat zusätzlich einen kleinen Verlauf je Thread.
- Eine Leiste oben nennt die drei Prozesse mit der höchsten CPU-Last und den mit dem meisten RAM. Ein Klick darauf öffnet den Prozess-Reiter.
- Sensoren, die der Rechner nicht hat, stehen unten unter „Nicht vorhanden“.

### Reiter „Prozesse“

- Spalten PID, Prozess, Benutzer, CPU, Letzte 60 s, RAM, E/A und Zustand. Die `top`-Spalten PR, NI, VIRT, SHR, S, %MEM und TIME+ gibt es auch, sie sind anfangs ausgeblendet.
- Ein Rechtsklick auf einen Spaltenkopf öffnet das Spaltenmenü: Spalten ein- und ausblenden, eine Spalte nach links oder rechts verschieben, den Standard wiederherstellen. Per Tastatur öffnet die Menütaste oder Umschalt+F10 auf einem Kopf dasselbe Menü.
- Einen Kopf ziehen verschiebt die Spalte, seinen rechten Rand ziehen ändert die Breite (per Tastatur Alt+Links und Alt+Rechts). Sind die Spalten breiter als die Liste, scrollt die Liste waagerecht.
- Der Trenner zwischen Liste und Detailbereich lässt sich ziehen oder mit den Pfeiltasten verschieben.
- Reihenfolge, ausgeblendete Spalten, Breiten und die Position des Trenners stehen in `~/.config/orbitop/layout.json` (unter `$XDG_CONFIG_HOME`, wenn das gesetzt ist) und überstehen einen Neustart.
- Suche in Namen und Argumenten, Filter „Alle“, „Nur meine“ und „Auffällige“ (jeder Zustand außer „arbeitet“ und „wartet“). Ein Klick auf einen Kopf sortiert nach dieser Spalte.
- Der Detailbereich zeigt zum gewählten Prozess die Befehlszeile, den CPU-Verlauf der letzten 5 Minuten, RAM, Lese- und Schreibrate, Threads, Kontextwechsel und Startzeit, bei Zombies dazu den Elternprozess.

### Die Zustände sind ein Hinweis, kein Urteil

Der Prozess-Reiter stuft jeden Prozess ein: arbeitet, wartet, Dauerlast, angehalten, Zombie, hängt im Kernel. Das ist eine Heuristik aus `/proc`, und orbitop sagt das auch. „Dauerlast, keine E/A“ heißt: mindestens 90 % eines Kerns über zwei Minuten, höchstens ein freiwilliger Kontextwechsel je Sekunde und keine E/A-Bytes. Von außen sieht das genauso aus wie eine lange Rechnung. „Hängt im Kernel“ heißt: Zustand D länger als 10 s ohne Fortschritt (keine CPU-Zeit und keine E/A dazwischen). Selbst „Sofort beenden“ wirkt erst, wenn der Kernel einen solchen Prozess freigibt.

### Prozesse beenden

- „Beenden“ schickt SIGTERM und sieht 5 s später nach, ob der Prozess noch läuft. Läuft er noch, wird „Sofort beenden“ (SIGKILL) hervorgehoben. Beides fragt vorher nach.
- Unmittelbar vor dem Signal prüft orbitop PID und Startzeit erneut. So trifft eine neu vergebene PID nie einen anderen Prozess.
- Eigene Prozesse bekommen das Signal direkt. Prozesse anderer Benutzer beendet orbitop nur über `pkexec` und den root-eigenen Helfer aus dem Paket, `/usr/lib/orbitop/killhelper`; polkit fragt jedes Mal nach dem Admin-Passwort. PID 1 und Kernel-Threads lassen sich nicht beenden.

Das Schließen des Fensters blendet es nur aus. orbitop liest die Prozessliste im Hintergrund weiter, damit die Zustände beim nächsten Öffnen schon feststehen. Strg+Q oder „orbitop beenden“ im Dialog „Über“ beendet es. Im Dialog „Über“ liegt auch der Schalter „Beim Anmelden starten“ (siehe [Start und Autostart](#start-und-autostart)).

## Screenshots

![Reiter Übersicht](docs/screenshot-overview.png)

![Reiter Prozesse](docs/screenshot-procs.png)

Beide Bilder zeigen Demodaten aus `tests/ui/demo.html`, kein laufendes System. Prozessnamen, Befehlszeilen und Benutzer sind anonymisiert; die Hardwarenamen (CPU, Schnittstellen, Datenträger, Sensoren) stammen vom Referenzlaptop. Die Demoseite zeigt die deutsche Oberfläche.

## Installation

orbitop wird für den ganzen Rechner installiert, aus seiner eigenen Paketquelle auf GitHub Pages, `https://zappelmann-sketch.github.io/orbitop/`. Ein kleines Paket aus dem Release richtet diese Quelle mit ihrem Signierschlüssel ein. Danach kommen orbitop und seine Updates aus der Quelle wie jedes andere Paket. Keines der Pakete schaltet einen Autostart oder eine Freigabe ein.

### Unterstützte Distributionen

<!-- supported:start -->
| Geprüfte Distribution | Davon abgeleitet, nicht eigens geprüft |
|---|---|
| Ubuntu 26.04 | |
| Ubuntu 24.04 | Linux Mint 22, Pop!_OS 24.04 |
| Debian 13 | |
| Fedora 45 | |
| Arch Linux | Manjaro, EndeavourOS |
| openSUSE Tumbleweed | |
<!-- supported:end -->

Geprüft am 2026-11-18 mit `scripts/check-distros.sh` in wegwerfbaren Docker-Containern: die erste Installation wie unten, die Testsuite, `orbitop --version`, das Update auf eine neuere Version, Deinstallation und Purge ohne Reste und ein veränderter Paketindex, den die Paketverwaltung ablehnen muss. Die Container haben keinen Bildschirm, deshalb gehörten das Fenster selbst und der Helfer über `pkexec` nicht zur Prüfung. Einzelheiten stehen in [`docs/distro-check.md`](docs/distro-check.md).

Nicht unterstützt: Debian 12 (Python 3.11) und Ubuntu 22.04 (Python 3.10). orbitop braucht Python 3.12 oder neuer, deshalb lehnt apt die Installation dort ab. Abgeleitete Distributionen nehmen die Schritte ihrer Basis. Auf anderen Distributionen lässt sich orbitop aus dem Quellcode starten (siehe [Aus dem Quellcode starten](#aus-dem-quellcode-starten)); dort ist es nicht geprüft.

### Signierschlüssel

Paketquelle und Release-Dateien sind mit einem Schlüssel signiert: Ed25519, User-ID `orbitop archive signing key`. Sein Fingerabdruck:

```text
<FINGERPRINT>
```

Der Fingerabdruck steht hier in der README im Repository, nicht nur auf der Seite der Paketquelle. Die Schritte unten brauchen `curl` und GnuPG (`gpg`, unter Debian und Ubuntu auch `gpgv`). Fehlt eines, installieren Sie es: `sudo apt install curl gnupg gpgv`, `sudo dnf install curl gnupg2`, `sudo zypper install curl gpg2` oder `sudo pacman -S curl gnupg`. Laden Sie den Schlüssel in einem neuen, privaten Verzeichnis in beiden Formen und lassen Sie ihn sich zeigen; das ändert nichts am Rechner:

```sh
cd "$(mktemp -d)"
curl -LO https://zappelmann-sketch.github.io/orbitop/orbitop-archive-keyring.asc
curl -LO https://zappelmann-sketch.github.io/orbitop/orbitop-archive-keyring.pgp
gpg --show-keys orbitop-archive-keyring.asc orbitop-archive-keyring.pgp
```

Jede Datei muss genau einen Schlüssel enthalten: Die Ausgabe zeigt genau zwei Schlüssel, einen je Datei, und unter jeder Zeile `pub` genau den Fingerabdruck oben. Zeigt sie mehr Schlüssel oder einen anderen Fingerabdruck, brechen Sie ab: Mit einem zweiten Schlüssel in der Datei könnte auch dieser signieren. Die Schritte Ihrer Distribution führen Sie im selben Terminal in diesem Verzeichnis aus.

### Ubuntu und Debian

Das Paket laden, das die Quelle einrichtet, und gegen die signierten Prüfsummen des Releases prüfen:

```sh
curl -LO https://github.com/zappelmann-sketch/orbitop/releases/latest/download/orbitop-apt-source.deb
curl -LO https://github.com/zappelmann-sketch/orbitop/releases/latest/download/SHA256SUMS
curl -LO https://github.com/zappelmann-sketch/orbitop/releases/latest/download/SHA256SUMS.asc
gpgv --keyring ./orbitop-archive-keyring.pgp SHA256SUMS.asc SHA256SUMS
sha256sum --ignore-missing -c SHA256SUMS
```

`gpgv` muss `using EDDSA key <FINGERPRINT>` mit genau dem Fingerabdruck oben und `Good signature from "orbitop archive signing key"` melden und `sha256sum` `orbitop-apt-source.deb: OK` ausgeben. Danach:

```sh
sudo apt install ./orbitop-apt-source.deb
sudo apt update
sudo apt install orbitop
```

`orbitop-apt-source` legt drei Dateien unter `/etc/apt/` an: die Quelle `sources.list.d/orbitop.sources`, ihren Schlüssel `keyrings/orbitop-archive-keyring.pgp` und das Pinning `preferences.d/orbitop.pref`. `apt policy orbitop` zeigt danach die Quelle mit Priorität 100. Meldet apt, dass der Download ohne Sandbox als root erfolgt, ist das harmlos: Der Benutzer `_apt` kann die Datei in Ihrem privaten Verzeichnis nicht lesen.

### Fedora

```sh
sudo rpm --import orbitop-archive-keyring.asc
curl -LO https://github.com/zappelmann-sketch/orbitop/releases/latest/download/orbitop-release-fedora.rpm
rpm -K orbitop-release-fedora.rpm
sudo dnf install ./orbitop-release-fedora.rpm
sudo dnf install orbitop
```

`rpm --import` übernimmt den Schlüssel, den Sie oben geprüft haben. `rpm -K` muss `orbitop-release-fedora.rpm: digests signatures OK` ausgeben. dnf selbst prüft lokale Pakete nicht und meldet, dass es die OpenPGP-Prüfung für ein Paket übersprungen hat; diese Prüfung hat `rpm -K` erledigt. `orbitop-release` legt die Quelle `/etc/yum.repos.d/orbitop.repo` und ihren Schlüssel `/etc/pki/rpm-gpg/RPM-GPG-KEY-orbitop` an. Bei der ersten Nutzung der Quelle fragt dnf einmal, ob es diesen Schlüssel für den signierten Paketindex übernehmen soll: den angezeigten Fingerabdruck vergleichen, dann mit `y` antworten.

### openSUSE

```sh
sudo rpm --import orbitop-archive-keyring.asc
curl -LO https://github.com/zappelmann-sketch/orbitop/releases/latest/download/orbitop-release-opensuse.rpm
rpm -K orbitop-release-opensuse.rpm
sudo zypper install ./orbitop-release-opensuse.rpm
sudo zypper install orbitop
```

`rpm -K` muss `orbitop-release-opensuse.rpm: digests signatures OK` ausgeben. Ohne vorheriges `rpm --import` lehnt zypper das Paket ab, weil sein Schlüssel fehlt. `orbitop-release` legt die Quelle `/etc/zypp/repos.d/orbitop.repo` und ihren Schlüssel an. zypper prüft danach den Paketindex und jedes Paket der Quelle: `zypper lr orbitop` zeigt bei `GPG Check` den Wert `(rp) Yes`.

### Arch Linux

Für Arch gibt es kein Paket der Quelle; sie wird einmal von Hand eingetragen. Auf einer normalen Arch-Installation ist der Schlüsselbund von pacman schon eingerichtet. Nur wenn er nie eingerichtet wurde (etwa in einem frischen Container, wo `pacman-key --lsign-key` scheitert), zuerst diese zwei Befehle ausführen:

```sh
sudo pacman-key --init
sudo pacman-key --populate archlinux
```

Den oben geprüften Schlüssel hinzufügen und lokal signieren:

```sh
sudo pacman-key --add orbitop-archive-keyring.asc
sudo pacman-key --lsign-key <FINGERPRINT>
```

Dann diesen Abschnitt ganz am Ende von `/etc/pacman.conf` anhängen, etwa mit `sudo nano /etc/pacman.conf`:

```ini
[orbitop]
SigLevel = Required DatabaseRequired
Server = https://zappelmann-sketch.github.io/orbitop/arch/$arch
```

Der Abschnitt muss der letzte sein: Haben zwei Repositorys ein Paket gleichen Namens, nimmt pacman es aus dem zuerst genannten, und so gewinnt immer ein Paket der offiziellen Repositorys. pacman prüft die Signaturen der Paketdatenbank und jedes Pakets. Dann orbitop installieren:

```sh
sudo pacman -Syu orbitop
```

Bei der Installation trägt orbitop seinen Schlüssel auch selbst in den Schlüsselbund von pacman ein (`pacman-key --populate orbitop`), damit ein erneuerter Schlüssel mit einem Update ankommt.

## Updates

Neue Versionen von orbitop kommen mit dem normalen System-Update:

| Distribution | Befehl |
|---|---|
| Ubuntu, Debian | `sudo apt update` und `sudo apt upgrade` oder die Aktualisierungsverwaltung |
| Fedora | `sudo dnf upgrade` |
| openSUSE Tumbleweed | `sudo zypper dup` |
| Arch Linux | `sudo pacman -Syu` |

Die Quelle kann keine Pakete Ihrer Distribution ersetzen. Unter Debian und Ubuntu ist sie auf Priorität 100 gepinnt, dnf und zypper ziehen ihr die Repositorys der Distribution vor (Priorität 99 statt 100), und unter Arch steht ihr Abschnitt zuletzt. orbitop selbst gibt es nur in dieser Quelle, deshalb wird es trotzdem aktualisiert.

### Nach einem Ubuntu-Release-Upgrade

Ein Upgrade auf eine neue Ubuntu-Version schaltet jede Paketquelle ab, die nicht von Ubuntu selbst stammt, auch diese: Es fügt `/etc/apt/sources.list.d/orbitop.sources` die Zeile `Enabled: no` hinzu. Die Quelle liefert jeder Ubuntu-Version dieselbe Suite `stable`, deshalb schalten Sie sie danach wieder ein:

```sh
sudo sed -i '/^Enabled: no$/d' /etc/apt/sources.list.d/orbitop.sources
sudo apt update
```

Damit ist die Datei wieder genau so, wie `orbitop-apt-source` sie angelegt hat.

## Start und Autostart

orbitop steht im Anwendungsmenü, und `orbitop` startet es aus einem Terminal. Die Pakete richten nie einen Autostart ein.

### Für den eigenen Benutzer

Im Dialog „Über“ (der Info-Knopf in der Kopfleiste) „Beim Anmelden starten“ einschalten. Ab der nächsten Anmeldung startet orbitop ausgeblendet (`--hidden`); ein Start aus dem Menü zeigt das Fenster. Der Schalter tut dasselbe wie diese Befehle:

```sh
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
cp /usr/share/orbitop/autostart.desktop "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/io.github.zappelmann_sketch.orbitop.desktop"
```

Zum Ausschalten den Schalter umlegen oder die Datei löschen:

```sh
rm "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/io.github.zappelmann_sketch.orbitop.desktop"
```

### Für alle Benutzer

Ein Admin schaltet den Autostart für alle Benutzer ein:

```sh
sudo cp /usr/share/orbitop/autostart.desktop /etc/xdg/autostart/io.github.zappelmann_sketch.orbitop.desktop
```

und wieder aus:

```sh
sudo rm /etc/xdg/autostart/io.github.zappelmann_sketch.orbitop.desktop
```

Wer ihn nicht möchte, legt den Schalter um. orbitop schreibt dann einen Eintrag mit `Hidden=true` unter demselben Namen in den eigenen Autostart-Ordner des Benutzers, und der geht dem in `/etc/xdg/autostart/` vor (freedesktop.org, „Desktop Application Autostart Specification“). Wer diese Datei löscht, hat den Autostart wieder. Die Datei in `/etc/xdg/autostart/` gehört dem Admin, nicht dem Paket: Sie bleibt nach einer Deinstallation liegen, startet dann aber nichts mehr (`TryExec=orbitop`).

## Grafik und Leistung

orbitop zeigt jede GPU mit den Werten, die der Kernel liefert. Was jede Grafik darüber hinaus braucht:

### AMD

Nichts. Last, Takt, Grafikspeicher, Temperatur und Leistung kommen vom Kernel-Treiber `amdgpu`.

### NVIDIA

Last, Speicher, Temperatur, Leistung und Takt kommen von `nvidia-smi`. Das Programm kommt mit dem proprietären Treiber von NVIDIA (unter Ubuntu etwa über „Zusätzliche Treiber“; der Befehl steckt in `nvidia-utils-<version>`). Fehlt es, zeigt orbitop statt der NVIDIA-Werte einen Hinweis.

### Intel

Ohne Werkzeug zeigt orbitop die Auslastung der Intel-Grafik durch eigene Prozesse. Die Last aller Prozesse und die Paketleistung kommen von `intel_gpu_top` aus den Intel-GPU-Werkzeugen. Die Pakete schlagen sie nur vor, deshalb installieren Sie sie selbst:

| Distribution | Befehl |
|---|---|
| Ubuntu, Debian | `sudo apt install intel-gpu-tools` |
| Fedora | `sudo dnf install igt-gpu-tools` |
| openSUSE | `sudo zypper install igt-gpu-tools` |
| Arch Linux | `sudo pacman -S intel-gpu-tools` |

Die Zähler aller Prozesse liest `intel_gpu_top` nur mit der Freigabe unten. Ohne sie zeigt orbitop weiter die eigenen Prozesse und einen Hinweis.

### Intel-GPU-Zähler für alle Prozesse (bis 0.3.0)

Der folgende Befehl gibt `/usr/bin/intel_gpu_top` die Datei-Fähigkeit `cap_perfmon`. Risiko: Danach kann jedes lokale Konto das Programm starten und die GPU-Zähler und die RAPL-Paketleistung lesen. Der Kernel sperrt diese Werte, weil sie Seitenkanalangriffe über den Stromverbrauch erlauben (Platypus, CVE-2020-8694). Schalten Sie das nur ein, wenn Sie das für jedes Konto auf dem Rechner hinnehmen. orbitop tut das nie von sich aus; Version 0.3.0 ersetzt diese Befehle durch einen Schalter, der nach dem Admin-Passwort fragt.

```sh
sudo setcap cap_perfmon=ep /usr/bin/intel_gpu_top
```

`getcap /usr/bin/intel_gpu_top` zeigt den Stand. Ein Update der Intel-GPU-Werkzeuge entfernt die Fähigkeit; danach den Befehl erneut ausführen. Rücknahme:

```sh
sudo setcap -r /usr/bin/intel_gpu_top
```

### Leistung des CPU-Pakets (bis 0.3.0)

orbitop liest die Leistung des CPU-Pakets aus den RAPL-Energiezählern (`/sys/class/powercap/intel-rapl:*`), die der Kernel nur root lesen lässt. Ohne sie kommt die Paketleistung von `intel_gpu_top`, wenn es `cap_perfmon` hat (oben). Diese udev-Regel macht die Zähler lesbar. Risiko: Dann kann jedes lokale Konto und jede Flatpak-App sie lesen, und das erlaubt Seitenkanalangriffe über den Stromverbrauch (Platypus, CVE-2020-8694).

```sh
echo 'ACTION=="add", SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", RUN+="/usr/bin/chmod 0444 /sys%p/energy_uj"' | sudo tee /etc/udev/rules.d/70-orbitop-rapl.rules
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=powercap --action=add
```

Rücknahme: die Regel löschen, dann den Rechner neu starten.

```sh
sudo rm /etc/udev/rules.d/70-orbitop-rapl.rules
```

## Deinstallation

Erst orbitop aus dem Anwendungsmenü starten, damit das Fenster erscheint (eine beim Anmelden gestartete Instanz läuft eventuell ausgeblendet), dann mit Strg+Q beenden.

### Ubuntu und Debian

```sh
sudo apt remove orbitop
```

Das entfernt orbitop und behält die Paketquelle mit ihrem Schlüssel. So läuft `apt update` weiter, und `sudo apt install orbitop` holt orbitop zurück. Die vollständige Deinstallation entfernt auch Quelle, Schlüssel und Pinning:

```sh
sudo apt purge orbitop orbitop-apt-source
```

### Fedora

```sh
sudo dnf remove orbitop
```

Das behält die Quelle. Die vollständige Deinstallation entfernt auch die Quelle, den Schlüssel in der rpm-Datenbank und die Kopie des Schlüssels, die dnf für die Quelle aufhebt:

```sh
sudo dnf remove orbitop-release
rpmkeys --list | grep -F 'orbitop archive signing key' | sed 's/[: ].*//' | xargs -r -n1 sudo rpmkeys --delete
sudo sh -c 'rm -rf /var/cache/libdnf5/orbitop-*'
```

`rpmkeys --list` zeigt jeden Schlüssel der rpm-Datenbank mit seiner User-ID, unter Fedora als Fingerabdruck in Kleinbuchstaben. Die zweite Zeile löscht jeden Schlüssel mit der User-ID `orbitop archive signing key`, auch einen erneuerten, den ein Update gebracht hat. Die dritte Zeile läuft als root, damit das Muster die Verzeichnisse findet.

### openSUSE

```sh
sudo zypper remove orbitop
```

Das behält die Quelle. Die vollständige Deinstallation entfernt auch die Quelle und den Schlüssel in der rpm-Datenbank:

```sh
sudo zypper remove orbitop-release
rpmkeys --list | grep -F 'orbitop archive signing key' | sed 's/[: ].*//' | xargs -r -n1 sudo rpmkeys --delete
```

`rpmkeys --list` zeigt jeden Schlüssel der rpm-Datenbank mit seiner User-ID, unter openSUSE als `<key id>-<date>`, Version und Release seines Pakets `gpg-pubkey-<key id>-<date>`. Die zweite Zeile löscht jeden Schlüssel mit der User-ID `orbitop archive signing key`, auch einen erneuerten, den ein Update gebracht hat.

### Arch Linux

```sh
cut -d: -f1 /usr/share/pacman/keyrings/orbitop-trusted | xargs -r -n1 sudo pacman-key --delete
sudo pacman -R orbitop
```

Die erste Zeile entfernt jeden Schlüssel von orbitop aus dem Schlüsselbund von pacman: alle Schlüssel in der Liste des Pakets, die mit `pacman -R` verschwindet. Darin steht der Schlüssel, den Sie bei der Installation hinzugefügt haben, und ein erneuerter, den ein Update gebracht hat. Danach meldet `pacman-key --list-keys 'orbitop archive signing key'` „No public key“. Dann den Abschnitt `[orbitop]` (seine drei Zeilen) aus `/etc/pacman.conf` löschen und die Datenbank der Quelle entfernen, die pacman bis `pacman -Sc` aufhebt. Nach einer Rückfrage leert `pacman -Sc` auch den Cache der nicht mehr installierten Pakete, nicht nur die von orbitop.

```sh
sudo pacman -Sc
```

### Eigene Dateien

Die Pakete fassen nie Dateien in Home-Verzeichnissen an. orbitop legt das Spaltenlayout in `~/.config/orbitop/` ab und, bei eingeschaltetem Schalter, einen Autostart-Eintrag. Beides entfernen:

```sh
rm -rf -- "${XDG_CONFIG_HOME:-$HOME/.config}/orbitop"
rm -f -- "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/io.github.zappelmann_sketch.orbitop.desktop"
```

Einen Autostart für alle Benutzer entfernen Sie wie unter [Für alle Benutzer](#für-alle-benutzer), eine Freigabe aus [Grafik und Leistung](#grafik-und-leistung) wie dort beschrieben.

## Umstieg von 0.1.0

orbitop 0.1.0 lief aus einem entpackten Archiv oder einem Checkout. Sein Setup hat einen Root-Helfer in `/usr/local/libexec/orbitop/` installiert und für den eigenen Benutzer einen Starter, ein Symbol und einen Autostart-Eintrag, die auf das Verzeichnis des Archivs oder Checkouts zeigen. Das Paket ersetzt all das, und die Skripte von 0.1.0 gibt es nicht mehr. Die alten Dateien entfernen Sie deshalb von Hand.

Halten Sie zuerst fest, was Sie hatten: den Autostart-Eintrag, die Fähigkeit `cap_perfmon` auf `intel_gpu_top` und die RAPL-Regel. Jeder dieser Befehle zeigt eines davon; ein Fehler oder keine Ausgabe heißt, es fehlt:

```sh
ls ~/.config/autostart/io.github.zappelmann_sketch.orbitop.desktop
getcap /usr/bin/intel_gpu_top
ls /etc/udev/rules.d/70-orbitop-rapl.rules
```

Dann orbitop 0.1.0 beenden (sein Fenster aus dem Anwendungsmenü zeigen, dann Strg+Q) und seine Dateien entfernen:

```sh
rm -f ~/.local/share/applications/io.github.zappelmann_sketch.orbitop.desktop
rm -f ~/.local/share/icons/hicolor/scalable/apps/io.github.zappelmann_sketch.orbitop.svg
rm -f ~/.config/autostart/io.github.zappelmann_sketch.orbitop.desktop
sudo rm -r /usr/local/libexec/orbitop
```

Der alte Starter heißt wie der des Pakets und würde ihn verdecken. Die Fähigkeit `cap_perfmon` und die RAPL-Regel bleiben, wie sie sind: Sie entsprechen denen in [Grafik und Leistung](#grafik-und-leistung), und 0.3.0 ersetzt beide durch einen Schalter. Danach können Sie das Verzeichnis von 0.1.0 löschen.

Dann das Paket wie unter [Installation](#installation) installieren und im Dialog „Über“ „Beim Anmelden starten“ einschalten, wenn der Autostart vorher an war. Unter Ubuntu und Debian zeigt `apt policy orbitop` danach die Paketquelle.

## Aus dem Quellcode starten

Für die Entwicklung läuft orbitop auch aus einem Checkout ohne das Paket. Die Laufzeitpakete Ihrer Distribution aus der Tabelle unten installieren, dann:

```sh
git clone https://github.com/zappelmann-sketch/orbitop.git
cd orbitop
bin/orbitop
```

Ohne installiertes Paket gehen zwei Dinge nicht: Prozesse anderer Benutzer zu beenden braucht den root-eigenen Helfer aus dem Paket (orbitop zeigt stattdessen einen Hinweis und fragt nach keinem Passwort), und der Schalter „Beim Anmelden starten“ bleibt gesperrt, solange der Befehl `orbitop` nicht installiert ist. Beim Start prüft orbitop die Python-Version, PyGObject, GTK 4 und WebKitGTK 6.0. Fehlt etwas, nennt es das Paket der laufenden Distribution und den Befehl zum Installieren; bei einer unbekannten Distribution nimmt es die Debian-Namen. Zu den Tests siehe [Tests](#tests).

### Paketnamen

| Distribution | Paketmanager | Laufzeitpakete | Intel-GPU-Werkzeuge |
|---|---|---|---|
| Debian, Ubuntu | `apt-get` | `python3-gi` `gir1.2-gtk-4.0` `gir1.2-webkit-6.0` | `intel-gpu-tools` |
| Fedora | `dnf` | `python3-gobject` `gtk4` `webkitgtk6.0` | `igt-gpu-tools` |
| Arch Linux | `pacman` | `python-gobject` `gtk4` `webkitgtk-6.0` | `intel-gpu-tools` |
| openSUSE | `zypper` | `python3-gobject` `typelib-1_0-Gtk-4_0` `typelib-1_0-WebKit-6_0` `python3-gobject-Gdk` | `igt-gpu-tools` |

Die Pakete von orbitop hängen von denselben Laufzeitpaketen und von polkit ab.

## Tech-Stack-Analyse

### Sprache und Bibliotheken

- Python 3.12 oder neuer, nur die Standardbibliothek, dazu PyGObject für GTK 4 und WebKitGTK 6.0. Kein psutil: orbitop liest `/proc` und `/sys` selbst.
- Die Oberfläche besteht aus HTML, CSS und reinem JavaScript in `orbitop/ui/`, ohne Frameworks. `chart.js` zeichnet die Verläufe auf ein Canvas.
- Die Schriften Orbitron und Oxanium liegen bei. Alle sichtbaren Texte stammen aus `orbitop/locale/en.json` und `orbitop/locale/de.json`.

### Oberfläche

- Ein GTK-4-Fenster enthält eine einzige WebKitGTK-6.0-Ansicht. Die Seite lädt über das eigene URI-Schema `orbitop://ui/`, nie über `file://`. Der Schema-Handler liefert nur reguläre Dateien bekannten Typs unterhalb von `orbitop/ui/`.
- Content Security Policy: `default-src 'none'`, Skripte, Stile und Schriften nur von der Seite selbst, `connect-src 'none'`. Die Seite hat keinen Netzzugriff.
- Die Ansicht nutzt eine flüchtige Netzwerksitzung und legt nichts auf der Platte ab. Sie navigiert nur zu orbitops eigenen Seiten; neue Fenster und Downloads werden abgelehnt.
- Solange das Fenster sichtbar ist, schickt Python jede Sekunde einen JSON-Schnappschuss an `window.orbitop.receive`. Python schickt Basiseinheiten, die Seite formatiert sie mit `Intl.NumberFormat`.

### Datenquellen

- `/proc`: `stat`, `meminfo`, `cpuinfo`, `diskstats`, `net/dev`, `mounts` und je Prozess `stat`, `status`, `statm`, `io` und `cmdline`.
- `/sys`: CPU-Takt, Blockgeräte, Netzwerkschnittstellen, Thermalzonen, Akkus, `devfreq` und die DRM-Karten (GPU-Last, Takt, Grafikspeicher).
- hwmon (`/sys/class/hwmon`): Temperaturen, Lüfter und Leistungswerte.
- powercap (`/sys/class/powercap/intel-rapl:*`): Leistung des CPU-Pakets aus den RAPL-Energiezählern, wenn sie lesbar sind.
- DRM-fdinfo (`/proc/<pid>/fdinfo`): GPU-Nutzung der eigenen Prozesse.
- `intel_gpu_top` (optional): Intel-GPU-Last aller Prozesse und die Paketleistung.
- `nvidia-smi` (optional): Last, Speicher, Temperatur, Leistung und Takt von NVIDIA-GPUs.

### Threads und Takte

- `orbitop-worker`: liest die Systemwerte jede Sekunde und baut den Schnappschuss.
- `orbitop-procs`: liest die Prozessliste alle 2 s, auch bei ausgeblendetem Fenster. Das Lesen von `/proc/<pid>/cmdline` kann blockieren (etwa bei einem hängenden FUSE- oder NFS-Mount); dann wartet nur die Prozessliste, die Kacheln laufen weiter.
- Werkzeuge: `intel_gpu_top` und `nvidia-smi` laufen als langlebige Kindprozesse, jedes von einem eigenen Thread gelesen. `intel_gpu_top` meldet alle 2 s, `nvidia-smi` jede Sekunde.
- Langsame hwmon-Chips (`dell_smm`, dort ist jeder Lesezugriff ein BIOS-Aufruf) liest orbitop höchstens alle 5 s.
- `/proc/<pid>/status` (Eigentümer, Kontextwechsel) liest orbitop je Prozess alle 10 s. Den gewählten Prozess und Prozesse ab 90 % eines Kerns liest es in jedem Prozess-Takt.
- Der GTK-Hauptthread bedient nur Fenster und Ansicht; der Worker übergibt das fertige JSON über `GLib.idle_add`.

### Sicherheitsmodell

- Die Seite spricht mit Python nur über `parse_message` in `orbitop/app.py`. Die Schleuse nimmt die Nachrichten `ready`, `view`, `layout`, `terminate`, `autostart` und `quit` an, prüft jeden Wert auf Typ und Wertebereich, verwirft unbekannte Schlüssel und begrenzt die Größe auf 4096 Zeichen. Alles andere wird verworfen.
- Prozessnamen, Befehlszeilen und Benutzer kommen nur als Text (`textContent`) in die Seite, nie als HTML.
- orbitop öffnet keinen Port und baut keine Netzwerkverbindung auf. Updates kommen nur über die Paketverwaltung.
- Einen Prozess eines anderen Benutzers beendet orbitop mit `pkexec /usr/lib/orbitop/killhelper <pid> <startzeit> <signal>`. Die polkit-Action `io.github.zappelmann-sketch.orbitop.terminate` gilt nur für dieses Programm (`org.freedesktop.policykit.exec.path`) und fragt jedes Mal nach dem Admin-Passwort (`auth_admin`); der Dialog zeigt PID, Startzeit und Signal. Vorher prüft orbitop per `lstat`, dass der Helfer eine reguläre Datei und kein Symlink ist und dass er und jedes Verzeichnis bis `/` root gehören und für Gruppe und andere nicht beschreibbar sind. Sonst zeigt es einen Hinweis und fragt nach keinem Passwort.
- Der Helfer öffnet ein pidfd, bevor er PID und Startzeit prüft. So erreicht das Signal genau den geprüften Prozess. PID 1 und Kernel-Threads lehnt er ab.
- Der Schalter „Beim Anmelden starten“ schreibt oder löscht nur seinen eigenen Eintrag im Autostart-Ordner des Benutzers, atomar; die Seite meldet nur an oder aus, nie einen Pfad.
- `intel_gpu_top` und `nvidia-smi` startet orbitop mit Argumentlisten, nie über eine Shell, und nur aus dem festen Pfad `/usr/local/bin:/usr/bin:/bin`.

### Tests

- pytest. Jeder Leser nimmt ein Argument `root`, deshalb laufen die Tests gegen nachgebaute `/proc`- und `/sys`-Bäume in `tests/fixtures/roots/`: `intel-laptop` (auf dem Referenzlaptop aufgenommen), `amd-desktop`, `arm-board` und `vm`.
- `tests/ui/check.html` prüft die Seite im kopflosen Chrome bei zwei Fenstergrößen. Ohne Chrome oder Chromium überspringen sich diese Tests.
- Die Testsuite ruft auch ShellCheck, `desktop-file-validate` und `appstreamcli` auf und braucht deshalb pytest, ShellCheck, desktop-file-utils und AppStream.
- `scripts/check-distros.sh` installiert, testet, aktualisiert und entfernt die Pakete aus der signierten Paketquelle in wegwerfbaren Docker-Containern, einem je Distribution. Die Ergebnisse stehen in [`docs/distro-check.md`](docs/distro-check.md). Wie die Pakete gebaut und signiert werden, steht in [`docs/release.md`](docs/release.md).

```sh
python3 -m pytest -q
```

### Architektur

```text
/proc  /sys  intel_gpu_top  nvidia-smi
   |
   v
sysfs.py  system.py  sensors.py  gpu.py  gpu_tools.py  procs.py  classify.py
   |
   v
sampler.py          rates, histories, JSON snapshot
   |  app.py Worker: threads orbitop-worker (1 s), orbitop-procs (2 s)
   v
shell.py            GTK 4 window, WebKitGTK 6.0 view, orbitop://ui/
   |  window.orbitop.receive(msg)
   v
orbitop/ui/app.js   page, chart.js draws the charts
   |  postMessage: ready, view, layout, terminate, autostart, quit
   v
app.py parse_message
   |-- layout    -> layout.py    -> ~/.config/orbitop/layout.json
   |-- autostart -> autostart.py -> ~/.config/autostart/io.github.zappelmann_sketch.orbitop.desktop
   '-- terminate -> actions.py   -> own process: signal
                                 -> other user: pkexec /usr/lib/orbitop/killhelper
```

## Eigenlast

Gemessen mit `scripts/measure-load.py` auf dem Referenzlaptop (Intel Core i7-7600U, Fenster 1600×1000, Skalierung 1,25), über den ganzen Prozessbaum einschließlich der WebKit-Prozesse und `intel_gpu_top`. Jeder Lauf dauerte 60 s; „nach 1 min“ heißt nach 60 s Aufwärmen, „nach 5 min“ nach fünf Minuten. Während der Läufe blieb das Fenster unberührt: Mausbewegungen über dem Fenster lassen WebKit mehr Bilder zeichnen und erhöhen die Last.

| Lage | CPU, % eines Kerns | PSS |
|---|---|---|
| Fenster ausgeblendet | 2,85 | 133 bis 134 MB |
| Reiter „Übersicht“ | 7,06 bis 7,20 | 189 bis 192 MB |
| Reiter „Prozesse“, Standardspalten | 7,81 bis 7,88 | 190 bis 193 MB |
| Reiter „Prozesse“, alle 15 Spalten, nach 1 min | 8,51 bis 8,80 | 194 bis 198 MB |
| Reiter „Prozesse“, alle 15 Spalten, nach 5 min | 9,00 bis 9,41 | 198 bis 201 MB |

orbitops eigene Grenzen: höchstens 3 % eines Kerns bei ausgeblendetem Fenster, höchstens 9 % bei sichtbarem Fenster und PSS unter 275 MB. Mit den Standardspalten bleibt orbitop darin. Mit allen Spalten liegt die Last nach 5 Minuten bei 9,0 bis 9,4 %, knapp über 9 %. Alle Spalten sind nur auf Wunsch eingeblendet, deshalb ist das eine hingenommene Überschreitung. Etwa 1 % eines Kerns entfällt in jeder Lage auf `intel_gpu_top`.

## Lizenz

GPL-3.0-or-later, siehe `LICENSE`. Copyright © 2026 zappelmann-sketch.

Die beigelegten Schriften Orbitron und Oxanium stehen unter der SIL Open Font License 1.1; die Lizenztexte liegen in `orbitop/ui/fonts/`.
