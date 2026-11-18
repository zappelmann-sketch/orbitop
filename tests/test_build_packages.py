# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/build-packages.sh mit einem Stellvertreter für docker: Was erreicht den Container, was nie."""
import os
import shutil
import subprocess

import pytest

from orbitop import __version__
from tests.packaging_common import ROOT
from tests.site_stub import GETCAP

PUBLIC = "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nAAAA\n-----END PGP PUBLIC KEY BLOCK-----\n"
SECRET = "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nAAAA\n-----END PGP PRIVATE KEY BLOCK-----\n"


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    """Wegwerfschlüssel in einem eigenen GNUPGHOME: einer, zwei in einer Datei, ein geheimer als PUBLIC getarnt."""
    if not shutil.which("gpg"):
        pytest.skip("gpg fehlt")
    d = tmp_path_factory.mktemp("keys")
    home = d / "gnupg"
    home.mkdir(mode=0o700)

    def gpg(*args):
        return subprocess.run(["gpg", "--homedir", str(home), "--batch", *args], check=True,
                              capture_output=True).stdout

    for uid in ("Test Signing <test@example.com>", "Test Signing Two <test@example.com>"):
        gpg("--passphrase", "", "--quick-gen-key", uid, "ed25519", "sign", "1y")
    fprs = [ln.split(":")[9] for ln in gpg("--with-colons", "--list-keys").decode().splitlines()
            if ln.startswith("fpr:")]
    files = {"one": gpg("--armor", "--export", fprs[0]), "two": gpg("--armor", "--export", *fprs),
             "mislabelled": gpg("--armor", "--pinentry-mode", "loopback", "--passphrase", "",
                                "--export-secret-keys", fprs[0]).replace(b"PRIVATE KEY BLOCK", b"PUBLIC KEY BLOCK"),
             "binary": gpg("--export", fprs[0])}
    for name, data in files.items():
        (d / f"{name}.asc").write_bytes(data)
    yield {name: d / f"{name}.asc" for name in files}
    subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "all"], capture_output=True)


def build(tmp_path, *args, plant=""):
    """Lauf mit docker-Stellvertreter: schreibt die Argumente nach docker.log und stdin nach stdin.bin; PLANT legt
    etwas Fremdes in /out, wie es ein Container als root könnte."""
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "docker").write_text(f"""#!/bin/sh
printf '%s\\n' "$@" >> {tmp_path}/docker.log
for a; do case $a in *:/out) out=${{a%:/out}} && mkdir -p "$out/deb" ;; esac; done
cat >> {tmp_path}/stdin.bin
case $PLANT in
    symlink) ln -s {tmp_path}/victim.txt "$out/deb/orbitop_9.9.9-1_all.deb" ;;
    fifo) mkfifo "$out/deb/fifo" ;;
    setuid) touch "$out/deb/x" && chmod 4755 "$out/deb/x" ;;
    cap) touch "$out/deb/capfile" ;;
esac
""")
    (fake / "getcap").write_text(GETCAP)
    for f in fake.iterdir():
        f.chmod(0o755)
    r = subprocess.run(["bash", str(ROOT / "scripts" / "build-packages.sh"), *args], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "PLANT": plant})
    log = tmp_path / "docker.log"
    return r, log.read_text().splitlines() if log.exists() else []


def test_build_refuses_bad_keys_before_docker(tmp_path, keys):  # nur genau ein öffentlicher Schlüssel kommt hinein
    (tmp_path / "secret.asc").write_text(SECRET)
    (tmp_path / "mixed.asc").write_text(PUBLIC + SECRET)
    (tmp_path / "garbage.asc").write_text(PUBLIC)
    for key in (tmp_path / "secret.asc", tmp_path / "mixed.asc", tmp_path / "garbage.asc", keys["two"],
                keys["mislabelled"], keys["binary"]):
        r, calls = build(tmp_path, "--out", str(tmp_path / "out"), "--pubkey", str(key))
        assert (r.returncode, calls) == (1, []), (key.name, r.stderr)
        assert "--pubkey" in r.stderr, key.name


def test_build_refuses_old_output_and_bad_suffix(tmp_path, keys):
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "orbitop_0.0.9-1_all.deb").write_text("")
    for args in (["--out", str(tmp_path / "old")], ["--suffix", "Check-1", "--out", str(tmp_path / "o2")]):
        r, calls = build(tmp_path, *args, "--pubkey", str(keys["one"]))
        assert r.returncode != 0 and calls == [], args


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="baut aus git archive HEAD")
def test_build_runs_disposable_containers(tmp_path, keys):
    r, calls = build(tmp_path, "--out", str(tmp_path / "out"), "--pubkey", str(keys["one"]), "--suffix", "check1")
    assert r.returncode == 0, r.stderr
    starts = [i for i, a in enumerate(calls) if a == "run"]  # je Container ein Aufruf "docker run …"
    runs = [calls[i + 1:j] for i, j in zip(starts, [*starts[1:], len(calls)])]
    assert starts[:1] == [0]
    images = {"debian:trixie": ("debian", f"{__version__}-1+check1"),
              "fedora:latest": ("rpm", __version__, "1.check1"),
              "opensuse/tumbleweed": ("rpm", __version__, "1.check1"),
              "archlinux:latest": ("arch", __version__, "1.1")}  # K6: Prüfbau mit Suffix je Format
    assert len(runs) == len(images)
    for args in runs:
        assert args[:6] == ["--rm", "-i", "--cap-drop", "MKNOD", "--cap-drop", "SETFCAP"], args
        mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
        assert [m.rsplit(":", 1)[-1] for m in mounts] == ["ro", "/out"]
        assert not [a for a in args if a in ("--privileged", "--cap-add", "--network=host")]
        fmt, *versions = images.pop(args[args.index("bash") - 1])
        assert args[args.index("bash") + 1:] == [f"/src/packaging/{fmt}/build-inside.sh", *versions]
    # Jeder Container bekommt nur den schon geprüften Schlüssel, binär wie im Paket
    assert (tmp_path / "stdin.bin").read_bytes() == keys["binary"].read_bytes() * 4


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="baut aus git archive HEAD")
@pytest.mark.parametrize("plant", ["symlink", "fifo", "setuid", "cap"])
def test_build_refuses_odd_container_output(tmp_path, keys, plant):  # build-site.sh liest DIR später als Eingabe
    (tmp_path / "victim.txt").write_text("unchanged\n")
    r, calls = build(tmp_path, "--out", str(tmp_path / "out"), "--pubkey", str(keys["one"]), plant=plant)
    assert r.returncode == 1 and "refusing" in r.stderr, r.stderr
    assert calls.count("run") == 1  # Abbruch gleich nach dem ersten Container
    assert (tmp_path / "victim.txt").read_text() == "unchanged\n"
