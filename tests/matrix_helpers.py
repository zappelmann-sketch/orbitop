# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Helfer der Tests von scripts/matrix (tests/test_matrix_lib.py, tests/test_matrix_retry.py,
tests/test_matrix_capture.py): call führt Funktionen von lib.sh und den Dateien der Paketverwaltungen aus wie step in
inside.sh, ohne set -e, mit Stellvertretern für rpm und rpmkeys; runs dazu mit dem Ersatz-Paketmanager pm."""
import os
import subprocess

from tests.packaging_common import ROOT

MATRIX = ROOT / "scripts" / "matrix"
PAGES = "https://zappelmann-sketch.github.io/orbitop/"
# rpm --import legt einen Schlüssel in keys ab, rpm -K meldet für jede Datei $RPMK; rpmkeys liest und löscht dort.
RPM = """#!/bin/sh
case $1 in
    --import) [ -n "$KNOWN" ] || echo "e652ba57-6afe03a5: orbitop archive signing key public key" >> "$STATE/keys" ;;
    -K) shift; for f; do echo "$f: $RPMK"; done ;;
esac
"""
RPMKEYS = """#!/bin/sh
case $1 in
    --list) [ -z "$LIST_FAILS" ] || exit 1; cat "$STATE/keys" ;;
    --delete) [ -n "$KEEP" ] || grep -v "^$2:" "$STATE/keys" > "$STATE/keys.new"; mv "$STATE/keys.new" "$STATE/keys" ;;
esac
"""


def call(tmp_path, command, *files, env=()):
    """COMMAND nach lib.sh und FILES aus scripts/matrix, mit STATE in tmp_path und rpm/rpmkeys-Stellvertretern;
    gibt (bestanden, Ausgabe) zurück."""
    state, fake = tmp_path / "state", tmp_path / "stubs"
    for d in (state, fake):
        d.mkdir(exist_ok=True)
    (state / "keys").touch()
    for name, text in {"rpm": RPM, "rpmkeys": RPMKEYS}.items():
        (fake / name).write_text(text)
        (fake / name).chmod(0o755)
    sourced = " ".join(f". {MATRIX / f};" for f in ("lib.sh", *files))
    r = subprocess.run(["bash", "-c", f"{sourced} if {command}; then echo PASSED; else echo FAILED; fi"],
                       capture_output=True, text=True, timeout=30,
                       env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "STATE": str(state), **dict(env)})
    assert r.stdout.splitlines()[-1] in {"PASSED", "FAILED"}, r.stderr
    return r.stdout.splitlines()[-1] == "PASSED", r.stdout


def rpm_site(tmp_path):
    """Eine Paketquelle mit den beiden RPMs je Familie und dem Schlüssel."""
    root = tmp_path / "site"
    for family in ("fedora", "opensuse"):
        (root / "rpm" / family).mkdir(parents=True)
        for name in ("orbitop-0.2.0-1.noarch.rpm", "orbitop-release-2026.11.18-1.noarch.rpm"):
            (root / "rpm" / family / name).write_bytes(b"rpm")
    (root / "orbitop-archive-keyring.asc").write_text("key\n")
    return root


# Ersatz-Paketmanager pm: Lauf N gibt STATE/out.N aus, hängt STATE/installs.N an die Paketliste STATE/packages (eine
# geänderte Paketdatenbank) und endet mit STATE/rc.N (fehlen sie: nichts, 0); jeder Lauf hängt eine Zeile an
# STATE/calls. packages liest die Paketliste; sleep schreibt seine Dauer nach STATE/slept, statt zu warten.
PM = ('pm() { echo >> "$STATE/calls"; local n; n=$(wc -l < "$STATE/calls"); cat "$STATE/out.$n" 2> /dev/null;'
      ' cat "$STATE/installs.$n" >> "$STATE/packages" 2> /dev/null;'
      ' return "$(cat "$STATE/rc.$n" 2> /dev/null || echo 0)"; }; packages() { cat "$STATE/packages"; };'
      ' sleep() { echo "$1" >> "$STATE/slept"; };')
# Die Quelldefinitionen liegen in STATE statt unter /etc; serve und kill in apts update_from tun nichts.
SOURCES = ('SOURCE=$STATE/orbitop.sources REPO=$STATE/orbitop.repo CONF=$STATE/pacman.conf;'
           ' serve() { :; }; kill() { :; };')
POLICY = " 100 http://zappelmann-sketch.github.io/orbitop/apt stable/main all Packages"  # wie über serve
AS_PM = {"apt.sh": f'apt() {{ pm "$@"; }}; apt-get() {{ pm "$@"; }}; apt-cache() {{ echo "{POLICY}"; }};',
         "dnf.sh": 'dnf() { pm "$@"; };', "zypper.sh": 'zypper() { pm "$@"; };', "pacman.sh": 'pacman() { pm "$@"; };'}


def runs(tmp_path, command, *outputs, files=("dnf.sh",)):
    """COMMAND nach lib.sh und FILES mit pm (auch als Programme von FILES), dessen Lauf N outputs[N-1] = (Ausgabe, rc[,
    neue Pakete]) liefert; gibt (bestanden, Ausgabe, Zahl der Läufe von pm, Pausen) zurück."""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    for name, line in {"packages": "bash 5.3", "orbitop.sources": f"URIs: {PAGES}apt",
                       "orbitop.repo": f"baseurl={PAGES}rpm/fedora", "pacman.conf": f"Server = {PAGES}arch/$arch",
                       "http.log": "GET /orbitop/apt/dists/stable/main/binary-all/by-hash/SHA512/0 HTTP/1.1"}.items():
        (state / name).write_text(line + "\n")
    for n, (text, rc, *installed) in enumerate(outputs, 1):
        (state / f"out.{n}").write_text(text + "\n")
        (state / f"rc.{n}").write_text(f"{rc}\n")
        if installed:
            (state / f"installs.{n}").write_text(installed[0] + "\n")
    stand_ins = " ".join(AS_PM[f] for f in files if f in AS_PM)
    ok, out = call(tmp_path, f"{PM} {SOURCES} {stand_ins} {command}", *files, env={"RPMK": "digests signatures OK"})
    calls = (state / "calls").read_text().count("\n") if (state / "calls").exists() else 0
    slept = (state / "slept").read_text().split() if (state / "slept").exists() else []
    return ok, out, calls, slept
