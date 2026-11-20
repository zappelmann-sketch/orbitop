# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Paket-Skripte der Freigabe zum Ausführen in Tests (test_packaging_{debian,rpm,arch}_counters.py,
test_matrix_counters_formats.py): je Format der Text des Skripts, gestartet wie von seiner Paketverwaltung, auf einer
Kopie in tmp_path. Darin ist der Helfer ein Stellvertreter, /etc/orbitop ein Ordner in tmp_path, und sync ist ein
Stellvertreter auf PATH. dpkg startet die Skripte direkt (#!/bin/sh), rpm schreibt ein Scriptlet in eine Datei und
startet sie mit /bin/sh, pacman lädt .install mit /bin/sh -c ". DATEI; FUNKTION VERSION". Auf Fedora, openSUSE und
Arch ist /bin/sh bash, daher laufen RPM und Arch hier mit bash; auf Debian und Ubuntu ist es dash, hier sh."""
import os
import re
import subprocess

from tests.packaging_common import PKG

HELPER = "/usr/lib/orbitop/counterhelper"
SPEC = PKG / "rpm" / "orbitop.spec"
INSTALL = PKG / "arch" / "orbitop.install"
# Die Abschnitte einer Spec; die Scriptlets darunter enden am nächsten Abschnitt (rpm-scriptlets(7)).
SCRIPTLETS = {"pre", "post", "preun", "postun", "pretrans", "posttrans", "preuntrans", "postuntrans",
              "verifyscript", "triggerprein", "triggerin", "triggerun", "triggerpostun", "filetriggerin",
              "filetriggerun", "filetriggerpostun", "transfiletriggerin", "transfiletriggerun",
              "transfiletriggerpostun"}
SECTIONS = SCRIPTLETS | {"prep", "build", "install", "check", "files", "changelog", "description", "package"}


def deb_script(name):
    return (PKG / "debian" / f"orbitop.{name}").read_text(encoding="utf-8")


def rpm_scriptlets(code_only=True):
    """{Kopfzeile: Zeilen} jedes Scriptlets der Spec; mit CODE_ONLY ohne Leer- und Kommentarzeilen."""
    found, current = {}, None
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"%(\w+)", line)
        if m and m[1] in SECTIONS:
            current = line if m[1] in SCRIPTLETS else None
            if current is not None:
                found[current] = []
        elif current is not None:
            found[current].append(line)
    return {head: [ln for ln in body if not code_only or (ln.strip() and not ln.lstrip().startswith("#"))]
            for head, body in found.items()}


def recorded(tmp_path, name):
    """Die Zeilen, die ein Stellvertreter nach tmp_path/NAME schrieb (calls, syncs)."""
    path = tmp_path / name
    return path.read_text().splitlines() if path.exists() else []


def run(tmp_path, name, text, argv, rc=0, helper=0o755, sync_rc=0):
    """TEXT als tmp_path/NAME, gestartet als ARGV(Pfad). Der Helfer schreibt seine Wörter nach calls und endet mit RC;
    HELPER ist sein Modus (0o644: nicht ausführbar wie nach chmod -x, None: er fehlt). sync schreibt seine Argumente
    und ob die Merkdatei dann noch da ist nach syncs und endet mit SYNC_RC. Gibt (Ergebnis, Wörter, /etc/orbitop) zurück."""
    etc, stub, bin_ = tmp_path / "etc" / "orbitop", tmp_path / "counterhelper", tmp_path / "bin"
    etc.mkdir(parents=True, exist_ok=True)
    bin_.mkdir(exist_ok=True)
    stub.unlink(missing_ok=True)
    if helper is not None:
        stub.write_text(f'#!/bin/sh\necho "$*" >> {tmp_path}/calls\nexit {rc}\n')
        stub.chmod(helper)
    (bin_ / "sync").write_text(f'#!/bin/sh\nleft=no && [ ! -e {etc}/counters-released ] || left=yes\n'
                               f'echo "$* marker-left=$left" >> {tmp_path}/syncs\nexit {sync_rc}\n')
    (bin_ / "sync").chmod(0o755)
    (tmp_path / name).write_text(text.replace(HELPER, str(stub)).replace("/etc/orbitop", str(etc)))
    r = subprocess.run(argv(str(tmp_path / name)), capture_output=True, text=True, timeout=30,
                       env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"})
    return r, " ".join(recorded(tmp_path, "calls")).split(), etc


def run_deb(tmp_path, name, arg, **kw):
    """orbitop.NAME ARG, wie dpkg es startet."""
    return run(tmp_path, name, deb_script(name), lambda path: ["sh", path, arg], **kw)


def run_rpm(tmp_path, head, arg, **kw):
    """Das Scriptlet HEAD der Spec mit $1 = ARG (die Zahl der Pakete danach), wie rpm es startet."""
    body = "\n".join(rpm_scriptlets(code_only=False)[head]) + "\n"
    return run(tmp_path, "scriptlet", body, lambda path: ["bash", path, arg], **kw)


def run_arch(tmp_path, function, **kw):
    """FUNCTION aus orbitop.install, wie pacman sie startet."""
    text = INSTALL.read_text(encoding="utf-8")
    return run(tmp_path, ".INSTALL", text, lambda path: ["bash", "-c", f'. "$1"; {function} 0.2.0-1', "sh", path],
               **kw)
