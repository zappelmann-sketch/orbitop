# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Arch-Paket: PKGBUILD, orbitop.install und ein Testbau mit build-inside.sh."""
import os
import shutil
import subprocess
import tarfile

import pytest

from orbitop import __version__, app
from tests.packaging_common import PKG, ROOT
from tests.site_stub import kill_agent, make_keys

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


# Die Werkzeuge von archlinux:latest, die build-inside.sh aufruft, für den Testbau in bwrap: pacman und useradd tun
# nichts, runuser startet den Befehl nach "--", bsdtar liest wie GNU tar, makepkg baut wie makepkg(8) aus den Quellen
# des PKGBUILD mit package() das Paket. shortcut: das Paket ist ein unkomprimiertes tar ohne .PKGINFO; es dient nur
# dem Blick auf seine Dateien.
STUBS = {
    "pacman": "exit 0", "useradd": "exit 0", "namcap": "exit 0", "bsdtar": 'exec tar "$@"',
    "python": 'exec python3 "$@"', "runuser": 'while [ "$1" != -- ]; do shift; done; shift; exec "$@"',
    "makepkg": """[ "$1" != --geninteg ] || exit 0
set -euo pipefail
source ./PKGBUILD
srcdir=$PWD/src pkgdir=$PWD/pkg
mkdir "$srcdir" "$pkgdir"
for s in "${source[@]}"; do case $s in *.tar) tar -C "$srcdir" -xf "$s" ;; *) cp -- "$s" "$srcdir/" ;; esac; done
(cd "$srcdir" && package)
tar -C "$pkgdir" -cf "$pkgname-$pkgver-$pkgrel-any.pkg.tar.zst" etc usr""",
}


def sandbox(tmp):
    """bwrap statt docker run: root in einem eigenen User-Namespace, /.dockerenv, die Quellen schreibgeschützt unter
    /src, beschreibbar nur /out und ein leeres /tmp, ohne Netz und ohne das Home-Verzeichnis."""
    (tmp / "dockerenv").touch()
    (tmp / "passwd").write_text("root:x:0:0::/tmp:/bin/bash\nbuilder:x:0:0::/tmp:/bin/bash\n")  # chown -R builder
    (tmp / "out").mkdir()
    (tmp / "stubs").mkdir()
    for name, body in STUBS.items():
        (tmp / "stubs" / name).write_text(f"#!/bin/bash\n{body}\n")
        (tmp / "stubs" / name).chmod(0o755)
    src = [a for d in ("bin", "data", "orbitop", "packaging") for a in ("--ro-bind", str(ROOT / d), f"/src/{d}")]
    return ["bwrap", "--unshare-all", "--die-with-parent", "--uid", "0", "--gid", "0", "--ro-bind", "/usr", "/usr",
            *[a for d in ("bin", "lib", "lib64", "sbin") for a in ("--symlink", f"usr/{d}", f"/{d}")],
            "--ro-bind", "/etc", "/etc", "--ro-bind", str(tmp / "passwd"), "/etc/passwd", "--proc", "/proc",
            "--dev", "/dev", "--tmpfs", "/tmp", "--ro-bind", str(tmp / "dockerenv"), "/.dockerenv", *src,
            "--bind", str(tmp / "out"), "/out", "--ro-bind", str(tmp / "stubs"), "/stubs", "--clearenv",
            "--setenv", "PATH", "/stubs:/usr/bin:/bin", "--setenv", "HOME", "/tmp", "--setenv", "OWNER", "0:0"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Das Paket, das build-inside.sh mit einem Wegwerfschlüssel baut, und der Fingerabdruck des Schlüssels."""
    if not shutil.which("bwrap") or subprocess.run(["bwrap", "--unshare-user", "--ro-bind", "/", "/", "true"],
                                                   capture_output=True).returncode:
        pytest.skip("bwrap fehlt oder darf keinen User-Namespace anlegen")
    tmp = tmp_path_factory.mktemp("arch")
    key = make_keys(tmp / "gnupg")
    kill_agent(key["home"])  # gebraucht wird nur der öffentliche Schlüssel
    r = subprocess.run([*sandbox(tmp), "bash", "/src/packaging/arch/build-inside.sh", __version__, "1"],
                       input=key["pub"].read_bytes(), capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode()
    with tarfile.open(tmp / "out" / "arch" / f"orbitop-{__version__}-1-any.pkg.tar.zst") as pkg:
        files = {m.name: pkg.extractfile(m).read() for m in pkg.getmembers() if m.isfile()}
    return files, key


def test_build_script_writes_owner_trust_3():  # ohne bwrap, also auch in den Matrix-Containern (Audit M3)
    script = (ARCH / "build-inside.sh").read_text(encoding="utf-8")
    assert """printf '%s:3:\\n' "$fpr" > "$work/orbitop-trusted"\n""" in script
    assert script.count("orbitop-trusted") == 1


def test_trusted_file_never_trusts_the_key_as_introducer(built):  # Owner-Trust 3: "never", nie 4 (marginal) oder höher
    files, key = built
    assert files["usr/share/pacman/keyrings/orbitop-trusted"] == f"{key['fpr']}:3:\n".encode()
    assert files["usr/share/pacman/keyrings/orbitop.gpg"] == key["pub"].read_bytes()
    assert files["usr/lib/orbitop/killhelper"] == (ROOT / "orbitop" / "killhelper.py").read_bytes()


def test_package_ships_the_counter_hook(built):  # B2.4: pacman liest Hooks aus /usr/share/libalpm/hooks
    files, _ = built
    hook = files["usr/share/libalpm/hooks/orbitop-counters.hook"]
    assert hook == (ARCH / "orbitop-counters.hook").read_bytes()
