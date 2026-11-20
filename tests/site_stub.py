# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsames der Tests von scripts/build-site.sh: Wegwerfschlüssel und ein docker-Stellvertreter."""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.apt_tree import make_deb
from tests.packaging_common import ROOT

SCRIPT = ROOT / "scripts" / "build-site.sh"
PACKAGES = ["deb/orbitop_0.2.0-1_all.deb", "deb/orbitop-apt-source_2026.11.18_all.deb",
            "rpm-fedora/orbitop-0.2.0-1.noarch.rpm", "rpm-fedora/orbitop-release-2026.11.18-1.noarch.rpm",
            "rpm-opensuse/orbitop-0.2.0-1.noarch.rpm", "rpm-opensuse/orbitop-release-2026.11.18-1.noarch.rpm",
            "arch/orbitop-0.2.0-1-any.pkg.tar.zst", "lint/orbitop_0.2.0-1_all.txt"]
# build-site.sh nimmt Vorlage und Container-Skripte aus git archive HEAD
needs_git = pytest.mark.skipif(not (ROOT / ".git").exists(), reason="baut aus git archive HEAD")
RPMS = ROOT / "tests" / "fixtures" / "rpm"  # echte Paare aus build-packages.sh und build-site.sh (test_rpm_same.py)
# createrepo_c schreibt neben repomd.xml je Index eine Datei <sha256>-<Name>.xml.zst
REPODATA = [f"repodata/{hashlib.sha256(t.encode() + b'\n').hexdigest()}-{t}.xml.zst"
            for t in ("primary", "filelists", "other")]
LEAK = "ORBITOP-LEAK"  # steht in der gpg.conf des Wegwerf-GNUPGHOME und darf nie in die Seite gelangen
# Der Stellvertreter legt nur an, was die Container-Schritte schreiben; PLANT legt dabei etwas Fremdes in /out.
DOCKER = """#!/bin/sh
printf '%s\\n' "$@" ---- >> "$LOG_DIR/docker.log"
[ "$1" = build ] && { cat > /dev/null; exit 0; }
for a; do case $a in *:/out) out=${a%:/out} ;; /src/packaging/site/*) step=${a##*/} ;; esac; done
cat >> "$LOG_DIR/stdin.bin"
case $step in
    apt-inside.sh) python3 -I "$APT_TREE" index "$out" stable main $([ "$PLANT" = apt-forged ] && echo forge) ;;
    rpm-inside.sh)  # "signiert": das unsignierte Paar der Familie wird zum signierten
        for r in "$out"/*.rpm; do
            for f in fedora opensuse; do ! cmp -s "$r" "$RPMS/$f-unsigned.rpm" || cp "$RPMS/$f-signed.rpm" "$r"; done
        done
        mkdir -p "$out/repodata" && echo '<repomd/>' > "$out/repodata/repomd.xml"
        for t in primary filelists other; do
            echo "$t" > "$out/repodata/$(echo "$t" | sha256sum | cut -c1-64)-$t.xml.zst"
        done ;;
    arch-inside.sh) echo db > "$out/orbitop.db" && echo files > "$out/orbitop.files" ;;
esac
case $step:$PLANT in
    apt-inside.sh:symlink) ln -s "$VICTIM" "$out/dists/stable/InRelease" ;;
    apt-inside.sh:fifo) mkfifo "$out/dists/stable/Release.gpg" ;;
    apt-inside.sh:cap) touch "$out/dists/stable/capfile" ;;
    apt-inside.sh:apt-extra) echo x > "$out/dists/stable/notes.txt" ;;
    apt-inside.sh:changed-apt) printf x >> "$out/pool/main/o/orbitop/orbitop_0.2.0-1_all.deb" ;;
    arch-inside.sh:setgid) chmod 2755 "$out/orbitop.db" ;;
    arch-inside.sh:changed-arch) printf x >> "$out/orbitop-0.2.0-1-any.pkg.tar.zst" ;;
    arch-inside.sh:extra) echo evil > "$out/evil-1-1-any.pkg.tar.zst" ;;
    rpm-inside.sh:rpm-extra) echo x > "$out/repodata/primary.sqlite.zst" ;;
    rpm-inside.sh:rpm-missing) rm "$out/orbitop-0.2.0-1.noarch.rpm" ;;
    rpm-inside.sh:rpm-changed) cp "$RPMS/opensuse-signed.rpm" "$out/orbitop-0.2.0-1.noarch.rpm" ;;
esac
"""
# getcap -r -- DIR wie das echte, das ohne Rechte keine Datei mit Capability sieht: "capfile" trägt eine.
GETCAP = """#!/bin/sh
for a; do d=$a; done
find "$d" -name capfile -printf '%p cap_setuid=ep\\n'
"""


def gpg(home, *args):
    return subprocess.run(["gpg", "--homedir", str(home), "--batch", *args], check=True, capture_output=True).stdout


def make_keys(home, uids=("Test Signing <test@example.com>",)):
    """Wegwerfschlüssel ohne Passphrase; pub.pgp neben home ist der erste, export-minimal. Danach eine gpg.conf,
    deren Optionen build-site.sh nie lesen darf."""
    if not all(shutil.which(t) for t in ("gpg", "gpgv", "gpg-connect-agent")):
        pytest.skip("gpg fehlt")
    home.mkdir(mode=0o700)
    for uid in uids:
        gpg(home, "--passphrase", "", "--quick-gen-key", uid, "ed25519", "sign", "1y")
    fprs = [ln.split(":")[9] for ln in gpg(home, "--with-colons", "--list-keys").decode().splitlines()
            if ln.startswith("fpr:")]
    (home.parent / "pub.pgp").write_bytes(gpg(home, "--export", "--export-options", "export-minimal", fprs[0]))
    (home / "gpg.conf").write_text(f"comment {LEAK}\nsig-notation leak@example.com={LEAK}\narmor\n")
    return {"home": home, "fprs": fprs, "fpr": fprs[0], "pub": home.parent / "pub.pgp"}


def kill_agent(home):
    """Am Ende jedes Tests mit einem GNUPGHOME: dessen Agent stoppt, und dessen Socket-Ordner unter
    /run/user/<uid>/gnupg (den gpgconf --kill anlegt, falls er fehlt) verschwindet (Wächter: tests/conftest.py)."""
    for what in (["--kill", "all"], ["--remove-socketdir"]) if shutil.which("gpgconf") else ():
        subprocess.run(["gpgconf", "--homedir", str(home), *what], capture_output=True)


def run(tmp_path, key, *, packages=PACKAGES, fpr=None, socket=None, env=(), stubs=()):
    """build-site.sh mit Stellvertretern für docker und getcap (und STUBS: Name -> Skript); Pakete, die schon da
    sind (auch als Symlink), bleiben. Gibt das Ergebnis und die docker-Aufrufe zurück, je Aufruf seine Argumente."""
    pkgs = tmp_path / "pkgs"
    for name in packages:
        (pkgs / name).parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(pkgs / name):
            continue
        if name.endswith(".deb"):  # echte, kleine debs: build-site.sh prüft den apt-Index gegen sie
            make_deb(pkgs / name, *Path(name).name.split("_")[:2])
        elif name.endswith(".rpm"):  # echte RPMs: build-site.sh vergleicht sie nach rpmsign mit diesen
            shutil.copy(RPMS / f"{name.split('/')[0].removeprefix('rpm-')}-unsigned.rpm", pkgs / name)
        else:
            (pkgs / name).write_bytes(name.encode())
    fake = tmp_path / "bin"
    fake.mkdir()
    for name, text in {"docker": DOCKER, "getcap": GETCAP, **dict(stubs)}.items():
        (fake / name).write_text(text)
    if socket:  # gpgconf meldet einen anderen Ort des extra-socket
        (fake / "gpgconf").write_text(f"""#!/bin/sh
[ "$1 $2" = "--list-dirs agent-extra-socket" ] && {{ echo {socket}; exit 0; }}
exec {shutil.which("gpgconf")} "$@"
""")
    for f in fake.iterdir():
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "GNUPGHOME": str(key["home"]),
           "ORBITOP_KEY": key["fpr"] if fpr is None else fpr, "LOG_DIR": str(tmp_path),
           "APT_TREE": str(ROOT / "tests" / "apt_tree.py"), "RPMS": str(RPMS), **dict(env)}
    r = subprocess.run(["bash", str(SCRIPT), "--packages", str(pkgs), "--out", str(tmp_path / "site")],
                       capture_output=True, text=True, env=env, timeout=120)
    log = tmp_path / "docker.log"
    calls, cur = [], []
    for line in log.read_text().splitlines() if log.exists() else []:
        if line == "----":
            calls, cur = [*calls, cur], []
        else:
            cur.append(line)
    return r, calls
