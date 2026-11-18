# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import importlib.util
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from orbitop import __version__, app

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
APP = "io.github.zappelmann_sketch.orbitop"
METAINFO = ROOT / "data" / f"{APP}.metainfo.xml"
NOREPLY = "235797375+zappelmann-sketch@users.noreply.github.com"
SHARE = "/usr/share/orbitop/"
# einzeilige Datendateien, die kein Kommentarformat kennen
NO_HEADER = {PKG / "debian" / "source" / "format", PKG / "keyring.version"}


def load_changelog():  # über den Pfad: "packaging" ist auch der Name einer PyPI-Bibliothek, die pytest lädt
    spec = importlib.util.spec_from_file_location("orbitop_changelog", PKG / "changelog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def deb822(path):
    """Absätze einer deb822-Datei als dicts (ohne Kommentare, Folgezeilen angehängt)."""
    paras, cur, key = [], {}, None
    for line in path.read_text(encoding="utf-8").splitlines() + [""]:
        if line.startswith("#"):
            continue
        if not line.strip():
            if cur:
                paras.append(cur)
            cur, key = {}, None
        elif line[0] in " \t":
            cur[key] += "\n" + line.strip()
        else:
            key, _, value = line.partition(":")
            cur[key] = value.strip()
    return paras


def package(name):
    return next(p for p in deb822(PKG / "debian" / "control") if p.get("Package") == name)


def relations(field):
    return [r.strip() for r in field.split(",") if r.strip()]


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    dest = tmp_path_factory.mktemp("destdir")
    # umask 077: Die Rechte im Baum dürfen nicht von der umask des Aufrufers abhängen
    subprocess.run(["bash", str(PKG / "install-tree.sh"), str(dest)], check=True, umask=0o077)
    return dest


def listing(dest):
    return sorted("/" + str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_symlink() or not p.is_dir())


def test_install_tree_file_list(tree):
    code = sorted(SHARE + str(p.relative_to(ROOT)) for p in (ROOT / "orbitop").rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts)
    assert listing(tree) == sorted([
        "/usr/bin/orbitop",
        "/usr/lib/orbitop/killhelper",
        f"/usr/share/applications/{APP}.desktop",
        f"/usr/share/icons/hicolor/scalable/apps/{APP}.svg",
        f"/usr/share/metainfo/{APP}.metainfo.xml",
        "/usr/share/orbitop/autostart.desktop",
        "/usr/share/orbitop/bin/orbitop",
        "/usr/share/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy",
        *code])
    assert SHARE + "orbitop/ui/fonts/Orbitron.ttf" in code and SHARE + "orbitop/locale/de.json" in code
    assert not [p for p in listing(tree) if p.startswith("/usr/local") or "__pycache__" in p or "/tests/" in p]


def test_modes_independent_of_umask(tree):
    executables = {"/usr/lib/orbitop/killhelper", SHARE + "bin/orbitop", SHARE + "orbitop/killhelper.py"}
    for p in tree.rglob("*"):
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            continue
        name = "/" + str(p.relative_to(tree))
        want = 0o755 if stat.S_ISDIR(st.st_mode) or name in executables else 0o644
        assert stat.S_IMODE(st.st_mode) == want, name


def test_helper_copy_identical_and_executable(tree):
    helper = tree / "usr/lib/orbitop/killhelper"
    assert helper.read_bytes() == (ROOT / "orbitop" / "killhelper.py").read_bytes()
    assert stat.S_IMODE(os.lstat(helper).st_mode) == 0o755
    assert helper.read_text().startswith("#!/usr/bin/python3 -I\n")  # pkexec startet ihn direkt (K1)


def test_data_files_identical(tree):  # Starter, Vorlage und polkit-Datei unverändert aus data/ und bin/
    for src, dst in (("bin/orbitop", SHARE + "bin/orbitop"), ("data/autostart.desktop", SHARE + "autostart.desktop"),
                     ("data/io.github.zappelmann-sketch.orbitop.policy",
                      "/usr/share/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy")):
        assert (tree / dst.lstrip("/")).read_bytes() == (ROOT / src).read_bytes(), src


def test_symlink_target_relative(tree):
    link = tree / "usr/bin/orbitop"
    assert os.readlink(link) == "../share/orbitop/bin/orbitop"
    assert link.resolve() == tree / "usr/share/orbitop/bin/orbitop"


def test_installed_starter_runs_from_its_tree(tree):  # K2: realpath im Starter findet /usr/share/orbitop
    r = subprocess.run([sys.executable, "-I", "-B", str(tree / "usr/bin/orbitop"), "--version"],
                       capture_output=True, text=True, cwd=tree)
    assert (r.returncode, r.stdout) == (0, f"orbitop {__version__}\n"), r.stderr


def test_install_tree_refuses_root_and_missing_destdir(tmp_path):
    for args in ([], [""], ["/"], ["//"], ["/usr/.."], [str(tmp_path), "extra"]):
        r = subprocess.run(["bash", str(PKG / "install-tree.sh"), *args], capture_output=True, text=True)
        assert r.returncode == 2, args


def test_debian_depends_match_app_packages():
    main = package("orbitop")
    depends = relations(main["Depends"])
    assert "python3 (>= 3.12)" in depends
    assert set(app.PACKAGES["apt-get"]) <= set(depends)
    assert "pkexec" in depends
    assert not [d for d in depends if "keyring" in d]  # K3: das Hauptpaket hängt nie vom Keyring-Paket ab
    assert relations(main["Suggests"]) == ["intel-gpu-tools"]
    assert main["Architecture"] == package("orbitop-archive-keyring")["Architecture"] == "all"


def test_description_matches_metainfo():
    meta = METAINFO.read_text(encoding="utf-8")
    summary = re.search(r"<summary>(.*?)</summary>", meta).group(1)
    first = re.sub(r"\s+", " ", re.search(r"<p>(.*?)</p>", meta, re.S).group(1))
    synopsis, _, long = package("orbitop")["Description"].partition("\n")
    assert (synopsis, long.replace("\n", " ")) == (summary, first)


def test_keyring_sources_file():  # ohne "Architectures": apt nimmt "all" aus dem Release (Probe in docs/release.md)
    (src,) = deb822(PKG / "keyring" / "orbitop.sources")
    assert src == {"Types": "deb", "URIs": "https://zappelmann-sketch.github.io/orbitop/apt", "Suites": "stable",
                   "Components": "main", "Signed-By": "/usr/share/keyrings/orbitop-archive-keyring.pgp"}
    assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\n", (PKG / "keyring.version").read_text())


def test_no_debian_changelog_in_repo():  # entsteht beim Bauen aus der metainfo
    assert not (PKG / "debian" / "changelog").exists()


PUBLIC = "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nAAAA\n-----END PGP PUBLIC KEY BLOCK-----\n"
SECRET = "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nAAAA\n-----END PGP PRIVATE KEY BLOCK-----\n"


def build(tmp_path, *args):
    """build-packages.sh mit einem Stellvertreter für docker, der seine Argumente aufschreibt."""
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "docker").write_text(f"""#!/bin/sh
printf '%s\\n' "$@" >> {tmp_path}/docker.log
for a; do case $a in *:/out) mkdir -p "${{a%:/out}}/deb" ;; esac; done
cat > /dev/null
""")
    (fake / "docker").chmod(0o755)
    r = subprocess.run(["bash", str(ROOT / "scripts" / "build-packages.sh"), *args], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"})
    log = tmp_path / "docker.log"
    return r, log.read_text().splitlines() if log.exists() else []


def test_build_refuses_secret_key_and_old_output(tmp_path):  # ein geheimer Schlüssel erreicht nie einen Container
    for name, text in (("secret.asc", SECRET), ("mixed.asc", PUBLIC + SECRET), ("binary.pgp", "\x99\x01")):
        (tmp_path / name).write_text(text)
        r, calls = build(tmp_path, "--out", str(tmp_path / "out"), "--pubkey", str(tmp_path / name))
        assert (r.returncode, calls) == (1, []), name
    (tmp_path / "key.asc").write_text(PUBLIC)
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "orbitop_0.0.9-1_all.deb").write_text("")
    for args in (["--out", str(tmp_path / "old")], ["--suffix", "Check-1", "--out", str(tmp_path / "o2")]):
        r, calls = build(tmp_path, *args, "--pubkey", str(tmp_path / "key.asc"))
        assert r.returncode != 0 and calls == [], args


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="baut aus git archive HEAD")
def test_build_runs_one_disposable_container(tmp_path):
    (tmp_path / "key.asc").write_text(PUBLIC)
    r, calls = build(tmp_path, "--out", str(tmp_path / "out"), "--pubkey", str(tmp_path / "key.asc"),
                     "--suffix", "check1")
    assert r.returncode == 0, r.stderr
    assert calls[:3] == ["run", "--rm", "-i"] and calls.count("run") == 1
    mounts = [calls[i + 1] for i, a in enumerate(calls) if a == "-v"]
    assert [m.rsplit(":", 1)[-1] for m in mounts] == ["ro", "/out"]
    assert not [a for a in calls if a in ("--privileged", "--cap-add", "--network=host")]
    assert calls[-3:] == ["/src/scripts/build-packages.sh", "--inside-deb", f"{__version__}-1+check1"]


def header_files():
    return [p for p in [*PKG.rglob("*"), ROOT / "scripts" / "build-packages.sh"]
            if p.is_file() and p not in NO_HEADER and "__pycache__" not in p.parts]


def test_spdx_headers():
    files = header_files()
    assert {PKG / "debian" / n for n in ("control", "rules", "copyright")} <= set(files)
    for p in files:
        head = "\n".join(p.read_text(encoding="utf-8").splitlines()[:4])
        assert "SPDX-License-Identifier: GPL-3.0-or-later" in head, p
        assert "Copyright © 2026 zappelmann-sketch" in head, p


def test_no_personal_data():
    home = re.compile(r"(/home/(?!u\b)[^/\s\"']+|/Users/|/tmp/claude)")
    mail = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    for p in [*header_files(), ROOT / "docs" / "release.md"]:
        text = p.read_text(encoding="utf-8")
        assert not home.findall(text), p
        assert not [m for m in mail.findall(text) if m != NOREPLY and not m.endswith("@example.com")], p


META = """<component><releases>
  <release version="0.2.0" date="2026-12-01"><description><p>Packages for Debian.</p>
    <p xml:lang="de">Pakete für Debian.</p></description></release>
  <release version="0.1.0" date="2026-11-18"/>
</releases></component>"""


def test_changelog_from_metainfo():
    changelog = load_changelog()
    trailer = f" -- zappelmann-sketch <{NOREPLY}>"
    assert changelog.debian(META, "0.2.0-1") == (
        "orbitop (0.2.0-1) stable; urgency=medium\n\n  * Packages for Debian.\n\n"
        f"{trailer}  Tue, 01 Dec 2026 00:00:00 +0000\n\n"
        "orbitop (0.1.0-1) stable; urgency=medium\n\n  * Release 0.1.0.\n\n"
        f"{trailer}  Wed, 18 Nov 2026 00:00:00 +0000\n")
    assert changelog.rpm(META) == (
        f"* Tue Dec 01 2026 zappelmann-sketch <{NOREPLY}> - 0.2.0-1\n- Packages for Debian.\n\n"
        f"* Wed Nov 18 2026 zappelmann-sketch <{NOREPLY}> - 0.1.0-1\n- Release 0.1.0.\n")


def test_changelog_top_entry_carries_build_version():  # K6: Prüfbau mit Suffix
    assert load_changelog().debian(META, "0.2.0-1+check1").startswith("orbitop (0.2.0-1+check1) stable;")


def test_changelog_refuses_version_without_release():  # __version__ neuer als die metainfo: Bau bricht ab
    with pytest.raises(ValueError):
        load_changelog().debian(META, "0.3.0-1")


def test_changelog_of_real_metainfo_matches_version():
    text = load_changelog().debian(METAINFO.read_text(encoding="utf-8"), f"{__version__}-1")
    assert text.startswith(f"orbitop ({__version__}-1) stable; urgency=medium\n")
