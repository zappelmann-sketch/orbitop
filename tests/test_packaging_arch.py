# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Arch-Paket: PKGBUILD und orbitop.install."""
import os
import subprocess

from orbitop import app
from tests.packaging_common import PKG

ARCH = PKG / "arch"


def pkgbuild(*names):
    """Variablen und Arrays des PKGBUILD, so wie makepkg sie mit bash liest (je Name eine Liste)."""
    script = 'source "$1"; shift; for n; do declare -n v=$n; printf "%s\\0" "${v[@]}"; printf "\\1"; done'
    r = subprocess.run(["bash", "-ec", script, "pkgbuild", str(ARCH / "PKGBUILD"), *names],
                       capture_output=True, text=True, check=True, env={"PATH": os.environ["PATH"]})
    return [field.split("\0")[:-1] for field in r.stdout.split("\1")[:-1]]


def test_pkgbuild_depends_match_app_packages():
    depends, optdepends, arch = pkgbuild("depends", "optdepends", "arch")
    # dazu glib2 und hicolor-icon-theme, die namcap als direkte Abhängigkeiten verlangt (sonst E:)
    assert depends == ["python>=3.12", *app.PACKAGES["pacman"], "glib2", "hicolor-icon-theme", "polkit"]
    assert optdepends == ["intel-gpu-tools: Intel GPU load of all processes"]
    assert arch == ["any"]
    assert not [d for d in depends if d.startswith("orbitop")]


def test_pkgbuild_fields():
    name, install, source = pkgbuild("pkgname", "install", "source")
    assert (name, install) == (["orbitop"], ["orbitop.install"])
    assert source == ["orbitop-.tar", "orbitop.gpg", "orbitop-trusted"]  # pkgver setzt erst build-inside.sh


def test_pkgbuild_has_no_version_or_sums():  # Version nur in orbitop/__init__.py, Summen hängt makepkg -g an
    lines = (ARCH / "PKGBUILD").read_text(encoding="utf-8").splitlines()
    assert not [ln for ln in lines if ln.startswith(("pkgver=", "pkgrel=", "sha256sums=", "b2sums="))]


def test_pkgbuild_ships_keyring_and_tree():
    text = (ARCH / "PKGBUILD").read_text(encoding="utf-8")
    assert 'bash packaging/install-tree.sh "$pkgdir"' in text
    assert '"$pkgdir/usr/share/pacman/keyrings"' in text and "startdir" not in text  # PKGBUILD(5): deprecated


def hooks(tmp_path, keyring_ok):
    """post_install und post_upgrade mit einem pacman-key-Stellvertreter; "-l" gelingt nur mit keyring_ok."""
    (tmp_path / "pacman-key").write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/calls\n'
                                         f'[ "$1" != -l ] || exit {0 if keyring_ok else 1}\n')
    (tmp_path / "pacman-key").chmod(0o755)
    out = [subprocess.run(["sh", "-ec", f'. "$1"; {hook} 0.2.0-1', "sh", str(ARCH / "orbitop.install")], check=True,
                          capture_output=True, text=True, env={"PATH": f"{tmp_path}:{os.environ['PATH']}"}).stdout
           for hook in ("post_install", "post_upgrade")]
    return (tmp_path / "calls").read_text().splitlines(), out


def test_install_script_populates_keyring(tmp_path):  # pacman-key(8): --populate liest /usr/share/pacman/keyrings
    calls, _ = hooks(tmp_path, keyring_ok=True)
    assert calls == ["-l", "--populate orbitop"] * 2


def test_install_script_without_keyring_only_hints(tmp_path):  # wie archlinux-keyring: kein Fehler ohne Schlüsselbund
    calls, out = hooks(tmp_path, keyring_ok=False)
    assert calls == ["-l"] * 2
    assert all("pacman-key --init" in o for o in out)


def test_trusted_file_never_trusts_the_key_as_introducer():  # Owner-Trust 3: "never", nie 4 (marginal) oder höher
    script = (ARCH / "build-inside.sh").read_text(encoding="utf-8")
    assert """printf '%s:3:\\n' "$fpr" > "$work/orbitop-trusted"\n""" in script
    assert script.count("orbitop-trusted") == 1
