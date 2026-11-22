# Security policy

[Deutsch](#sicherheitsrichtlinie)

## Supported versions

Only the newest release gets security fixes. Updates come through the package manager from the signed package source ([README](README.md#installation)), so updating the system is enough. After an Ubuntu release upgrade, turn the source on again ([README](README.md#after-an-ubuntu-release-upgrade)); until then no fixes arrive.

## Reporting a vulnerability

Please report security issues privately: on GitHub, tab **Security**, button **Report a vulnerability**. Do not open a public issue for a vulnerability.

orbitop is a hobby project with one maintainer. You will usually get a first answer within 7 days; there are no guaranteed deadlines. Fixes are published in coordination with you, and you are named in the release notes if you wish.

## Scope

In particular:

- the root helpers `/usr/lib/orbitop/killhelper` and `/usr/lib/orbitop/counterhelper` and their polkit actions;
- the udev rule `70-orbitop-counters.rules` and the package scripts (Debian maintainer scripts and triggers, RPM scriptlets, pacman hook and install script);
- the gate between the page and Python (`parse_message` in `orbitop/messages.py`) and the jobs behind it (terminate, counter release, install button via PackageKit);
- the signed package source, the release files and the signing key.

## Known and documented

These are not new vulnerabilities:

- With the switch "Release counters" turned on, every account and program on the machine can read the GPU and energy counters. This is the side channel of CVE-2020-8694 (Platypus); the switch is off by default, explains the risk and asks for the admin password.
- The remaining risks R1 to R22 in section 5 of the [security document of 0.3.0](docs/superpowers/specs/2026-11-19-orbitop-0.3.0-security-runde.md) (German).

## Signing key

The package source (on Fedora, openSUSE and Arch also every package) and the release files are signed with the archive key `B6F10E7E76A63D9D569DE0674B5D133F71445C01`. How to check it is in the [README, section "Signing key"](README.md#signing-key).

From the next release on, every release tag is signed with the SSH key `SHA256:o79Sk5q32huTQYqEHtXaUKwPg/k3WyDC2byTkiJl1x0` (Ed25519), which `.github/allowed_signers` lists and GitHub shows as "Verified"; in a checkout of `main`, `git -c gpg.ssh.allowedSignersFile=.github/allowed_signers tag -v v<version>` checks a tag. The tags up to `v0.3.0` are not signed.

---

# Sicherheitsrichtlinie

## Unterstützte Versionen

Sicherheitskorrekturen gibt es nur für das neueste Release. Updates kommen über die Paketverwaltung aus der signierten Paketquelle ([README](README.de.md#installation)); ein System-Update genügt. Nach einem Ubuntu-Release-Upgrade schalten Sie die Quelle wieder ein ([README](README.de.md#nach-einem-ubuntu-release-upgrade)); bis dahin kommen keine Korrekturen an.

## Sicherheitslücken melden

Bitte Sicherheitsprobleme vertraulich melden: auf GitHub im Reiter **Security** über **Report a vulnerability**. Für eine Sicherheitslücke bitte kein öffentliches Issue anlegen.

orbitop ist ein Hobbyprojekt mit einem Betreuer. Eine erste Antwort kommt meist innerhalb von 7 Tagen; feste Fristen gibt es nicht. Korrekturen werden mit Ihnen abgestimmt veröffentlicht, und auf Wunsch nennen die Release-Notizen Ihren Namen.

## Umfang

Insbesondere:

- die Root-Helfer `/usr/lib/orbitop/killhelper` und `/usr/lib/orbitop/counterhelper` und ihre polkit-Actions;
- die udev-Regel `70-orbitop-counters.rules` und die Paket-Skripte (Debian-Maintainer-Skripte und Trigger, RPM-Scriptlets, pacman-Hook und Install-Skript);
- die Schleuse zwischen Seite und Python (`parse_message` in `orbitop/messages.py`) und die Aufträge dahinter (Beenden, Freigabe der Zähler, Knopf „Installieren“ über PackageKit);
- die signierte Paketquelle, die Release-Dateien und der Signierschlüssel.

## Bekannt und dokumentiert

Das sind keine neuen Lücken:

- Ist der Schalter „Messzähler freigeben“ an, kann jedes Konto und jedes Programm auf dem Rechner die Grafik- und Energiezähler lesen. Das ist der Seitenkanal aus CVE-2020-8694 (Platypus); der Schalter ist anfangs aus, erklärt das Risiko und fragt nach dem Admin-Passwort.
- Die Restrisiken R1 bis R22 in Abschnitt 5 des [Security-Dokuments von 0.3.0](docs/superpowers/specs/2026-11-19-orbitop-0.3.0-security-runde.md).

## Signierschlüssel

Die Paketquelle (unter Fedora, openSUSE und Arch auch jedes Paket) und die Release-Dateien sind mit dem Archivschlüssel `B6F10E7E76A63D9D569DE0674B5D133F71445C01` signiert. Wie Sie ihn prüfen, steht in der [README, Abschnitt „Signierschlüssel“](README.de.md#signierschlüssel).

Ab dem nächsten Release ist jeder Release-Tag mit dem SSH-Schlüssel `SHA256:o79Sk5q32huTQYqEHtXaUKwPg/k3WyDC2byTkiJl1x0` (Ed25519) signiert, den `.github/allowed_signers` nennt und GitHub als „Verified“ anzeigt; in einem Checkout von `main` prüft `git -c gpg.ssh.allowedSignersFile=.github/allowed_signers tag -v v<version>` einen Tag. Die Tags bis `v0.3.0` sind nicht signiert.
