# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Helfer der Tests von scripts/matrix (tests/test_matrix_lib.py, tests/test_matrix_retry.py): call führt Funktionen
von lib.sh und den Dateien der Paketverwaltungen aus wie step in inside.sh, ohne set -e, mit Stellvertretern für rpm
und rpmkeys."""
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
