# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/build-packages.sh mit einem Stellvertreter für docker: Was erreicht den Container, was nie."""
import os
import shutil
import subprocess

import pytest

from orbitop import __version__
from tests.packaging_common import ROOT
from tests.site_stub import GETCAP, kill_agent

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
    kill_agent(home)


def build(tmp_path, *args, plant=""):
    """Lauf mit docker-Stellvertreter: schreibt die Argumente nach docker.log und stdin nach stdin.bin, dazu je Format
    ein Paket und einen Lint-Bericht wie die Container; PLANT legt etwas Fremdes in /out, wie es ein Container als root
    könnte, "cross" und "lint" erst im zweiten Container (Fedora)."""
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "docker").write_text(f"""#!/bin/sh
printf '%s\\n' "$@" >> {tmp_path}/docker.log
for a; do case $a in *:/out) out=${{a%:/out}} ;; esac; done
for a; do [ "$a" = bash ] && break; image=$a; done
case $image in
    debian:*) fmt=deb lint=orbitop_9.9.9-1_all ;; fedora:*) fmt=rpm-fedora lint=rpm-fedora ;;
    opensuse/*) fmt=rpm-opensuse lint=rpm-opensuse ;; *) fmt=arch lint=arch-orbitop ;;
esac
mkdir -p "$out/$fmt" "$out/lint" && echo "$image" > "$out/$fmt/package-$fmt" && echo ok > "$out/lint/$lint.txt"
cat >> {tmp_path}/stdin.bin
case $PLANT:$fmt in
    symlink:deb) ln -s {tmp_path}/victim.txt "$out/deb/orbitop_9.9.9-1_all.deb" ;;
    fifo:deb) mkfifo "$out/deb/fifo" ;;
    setuid:deb) touch "$out/deb/x" && chmod 4755 "$out/deb/x" ;;
    cap:deb) touch "$out/deb/capfile" ;;
    cross:rpm-fedora) mkdir "$out/deb" && echo evil > "$out/deb/package-deb" ;;
    lint:rpm-fedora) echo evil > "$out/lint/orbitop_9.9.9-1_all.txt" ;;
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
    outs = set()
    for args in runs:
        assert args[:6] == ["--rm", "-i", "--cap-drop", "MKNOD", "--cap-drop", "SETFCAP"], args
        mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
        assert [m.rsplit(":", 1)[-1] for m in mounts] == ["ro", "/out"]
        outs.add(mounts[1].rsplit(":", 1)[0])
        assert not [a for a in args if a in ("--privileged", "--cap-add", "--network=host")]
        fmt, *versions = images.pop(args[args.index("bash") - 1])
        assert args[args.index("bash") + 1:] == [f"/src/packaging/{fmt}/build-inside.sh", *versions]
    # Jeder Container bekommt nur den schon geprüften Schlüssel, binär wie im Paket
    assert (tmp_path / "stdin.bin").read_bytes() == keys["binary"].read_bytes() * 4
    # Audit F2: jeder Container schreibt in einen eigenen, frischen Ordner, nie in DIR; DIR bekommt das Ergebnis danach
    out = tmp_path / "out"
    assert len(outs) == 4 and not {str(out), *map(str, out.rglob("*"))} & outs, outs
    assert sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()) == [
        "arch/package-arch", "deb/package-deb", "lint/arch-orbitop.txt", "lint/orbitop_9.9.9-1_all.txt",
        "lint/rpm-fedora.txt", "lint/rpm-opensuse.txt", "rpm-fedora/package-rpm-fedora",
        "rpm-opensuse/package-rpm-opensuse"]


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="baut aus git archive HEAD")
@pytest.mark.parametrize("plant", ["cross", "lint"])
def test_build_refuses_writes_into_another_format(tmp_path, keys, plant):
    """Audit F2: Der Fedora-Container schreibt ein Paket unter deb/ oder überschreibt den Lint-Bericht des Debian-Baus.
    Das Skript hält an, und was der Debian-Container in DIR gelegt hat, bleibt, wie es war."""
    r, calls = build(tmp_path, "--out", str(tmp_path / "out"), "--pubkey", str(keys["one"]), plant=plant)
    assert r.returncode == 1 and "refusing the output of fedora:latest" in r.stderr, r.stderr
    assert calls.count("run") == 2  # Abbruch gleich nach dem Fedora-Container
    out = tmp_path / "out"
    assert (out / "deb" / "package-deb").read_text() == "debian:trixie\n"
    assert (out / "lint" / "orbitop_9.9.9-1_all.txt").read_text() == "ok\n"
    assert not (out / "rpm-fedora").exists()


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="baut aus git archive HEAD")
@pytest.mark.parametrize("plant", ["symlink", "fifo", "setuid", "cap"])
def test_build_refuses_odd_container_output(tmp_path, keys, plant):  # build-site.sh liest DIR später als Eingabe
    (tmp_path / "victim.txt").write_text("unchanged\n")
    r, calls = build(tmp_path, "--out", str(tmp_path / "out"), "--pubkey", str(keys["one"]), plant=plant)
    assert r.returncode == 1 and "refusing" in r.stderr, r.stderr
    assert calls.count("run") == 1  # Abbruch gleich nach dem ersten Container
    assert (tmp_path / "victim.txt").read_text() == "unchanged\n"


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="baut aus git archive HEAD")
@pytest.mark.parametrize("args,versions", [
    (["--revision", "2"], [f"{__version__}-2", __version__, "2", __version__, "2", __version__, "2"]),
    (["--revision", "2", "--suffix", "check1"],
     [f"{__version__}-2+check1", __version__, "2.check1", __version__, "2.check1", __version__, "2.1"])],
    ids=["revision", "with-suffix"])
def test_build_takes_a_revision(tmp_path, keys, args, versions):  # orbitop N+1 der Matrix: derselbe Stand, Revision 2
    r, calls = build(tmp_path, "--out", str(tmp_path / "out"), "--pubkey", str(keys["one"]), *args)
    assert r.returncode == 0, r.stderr
    starts = [i for i, a in enumerate(calls) if a == "run"]
    runs = [calls[i + 1:j] for i, j in zip(starts, [*starts[1:], len(calls)])]
    assert [v for args in runs for v in args[args.index("bash") + 2:]] == versions


@pytest.mark.parametrize("revision", ["0", "02", "a", "2.1", "-1", ""])
def test_build_refuses_a_bad_revision(tmp_path, keys, revision):
    r, calls = build(tmp_path, "--out", str(tmp_path / "out"), "--pubkey", str(keys["one"]), "--revision", revision)
    assert r.returncode != 0 and calls == [], r.stderr
