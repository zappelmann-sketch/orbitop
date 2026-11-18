# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Debian-Pakete orbitop und orbitop-apt-source: Steuerdaten, Conffiles, Pinning, Köpfe, keine persönlichen Daten."""
import hashlib
import re
from urllib.parse import urlsplit

from orbitop import app
from tests.packaging_common import APT_SOURCE, METAINFO, NOREPLY, PKG, ROOT, deb822, load_changelog

# einzeilige Datendateien, die kein Kommentarformat kennen
NO_HEADER = {PKG / "debian" / "source" / "format", APT_SOURCE / "debian" / "source" / "format",
             PKG / "keyring.version"}
# Eingaben von orbitop-apt-source außer dem Schlüssel, je packaging/keyring.version. Ändert sich eine, steigt die
# Version, und hier kommt ein Eintrag dazu; sonst gäbe es zwei verschiedene Pakete mit derselben Version.
# Nur vor der ersten Veröffentlichung (Task 10) darf ein Eintrag ersetzt werden.
APT_SOURCE_INPUTS = {"2026.11.18": "243b6c11a0579276dacb2c21f061be8683894c8d4c37e028ce24141fe24f391b"}
KEYRING = "/etc/apt/keyrings/orbitop-archive-keyring.pgp"


def package(name):
    return next(p for p in deb822(PKG / "debian" / "control") if p.get("Package") == name)


def relations(field):
    return [r.strip() for r in field.split(",") if r.strip()]


def test_debian_depends_match_app_packages():
    main = package("orbitop")
    depends = relations(main["Depends"])
    assert "python3 (>= 3.12)" in depends
    assert set(app.PACKAGES["apt-get"]) <= set(depends)
    assert "pkexec" in depends
    assert relations(main["Suggests"]) == ["intel-gpu-tools"]
    assert main["Architecture"] == "all"
    assert [p.get("Package") for p in deb822(PKG / "debian" / "control")[1:]] == ["orbitop"]


def test_main_package_never_pulls_the_apt_source():  # K3: die Quelle kommt nur auf ausdrücklichen Wunsch
    main = package("orbitop")
    pulled = [r for f in ("Depends", "Pre-Depends", "Recommends") for r in relations(main.get(f, ""))]
    assert not [r for r in pulled if r.startswith("orbitop")]


def test_description_matches_metainfo():
    meta = METAINFO.read_text(encoding="utf-8")
    summary = re.search(r"<summary>(.*?)</summary>", meta).group(1)
    first = re.sub(r"\s+", " ", re.search(r"<p>(.*?)</p>", meta, re.S).group(1))
    synopsis, _, long = package("orbitop")["Description"].partition("\n")
    assert (synopsis, long.replace("\n", " ")) == (summary, first)


def test_no_debian_changelog_in_repo():  # entsteht beim Bauen, aus der metainfo bzw. aus keyring.version
    assert not (PKG / "debian" / "changelog").exists() and not (APT_SOURCE / "debian" / "changelog").exists()


def test_apt_source_package():  # eigenes Quellpaket: lintian erlaubt sources.list.d nur in Paketen *-apt-source
    source, pkg = deb822(APT_SOURCE / "debian" / "control")
    assert (source["Source"], pkg["Package"], pkg["Architecture"]) == ("orbitop-apt-source",) * 2 + ("all",)
    assert relations(pkg["Depends"]) == ["${misc:Depends}"]
    assert source["Maintainer"] == deb822(PKG / "debian" / "control")[0]["Maintainer"]


def test_apt_source_installs_only_conffiles_under_etc_apt():  # remove behält alle drei, purge entfernt alle drei
    rules = (APT_SOURCE / "debian" / "rules").read_text()
    assert sorted(re.findall(r"debian/orbitop-apt-source/(\S+)", rules)) == [
        "etc/apt/keyrings/orbitop-archive-keyring.pgp", "etc/apt/preferences.d/orbitop.pref",
        "etc/apt/sources.list.d/orbitop.sources"]


def test_apt_source_sources_file():  # ohne "Architectures": apt nimmt "all" aus dem Release (docs/release.md)
    (src,) = deb822(APT_SOURCE / "orbitop.sources")
    assert src == {"Types": "deb", "URIs": "https://zappelmann-sketch.github.io/orbitop/apt", "Suites": "stable",
                   "Components": "main", "Signed-By": KEYRING}
    assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\n", (PKG / "keyring.version").read_text())


def test_apt_source_pins_its_origin_to_100():  # UseThirdParty: nie über Pakete der Distribution, Updates bleiben
    (pref,) = deb822(APT_SOURCE / "orbitop.pref")
    assert {k: v for k, v in pref.items() if k != "Explanation"} == {
        "Package": "*", "Pin": "origin zappelmann-sketch.github.io", "Pin-Priority": "100"}
    (src,) = deb822(APT_SOURCE / "orbitop.sources")
    assert pref["Pin"].split()[1] == urlsplit(src["URIs"]).hostname


def test_only_lintian_override_is_the_preferences_file():  # Ruling: genau diese eine Ausnahme, sonst keine
    overrides = sorted(PKG.rglob("*lintian-overrides"))
    assert overrides == [APT_SOURCE / "debian" / "orbitop-apt-source.lintian-overrides"]
    lines = [ln for ln in overrides[0].read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert lines == ["package-installs-apt-preferences [etc/apt/preferences.d/orbitop.pref]"]


def apt_source_inputs():
    version = (PKG / "keyring.version").read_text().strip()
    h = hashlib.sha256(load_changelog().apt_source(version).encode())
    for p in sorted(p for p in APT_SOURCE.rglob("*") if p.is_file()):
        h.update(b"\0" + str(p.relative_to(PKG)).encode() + b"\0" + p.read_bytes())
    return version, h.hexdigest()


def test_apt_source_inputs_pinned():  # gleiche Version, gleiche Bytes
    version, digest = apt_source_inputs()
    assert APT_SOURCE_INPUTS.get(version) == digest


def header_files():
    return [p for p in [*PKG.rglob("*"), ROOT / "scripts" / "build-packages.sh", ROOT / "scripts" / "build-site.sh"]
            if p.is_file() and p not in NO_HEADER and "__pycache__" not in p.parts]


def test_spdx_headers():
    files = header_files()
    assert {PKG / "debian" / n for n in ("control", "rules", "copyright", "build-inside.sh")} <= set(files)
    assert {APT_SOURCE / n for n in ("orbitop.sources", "orbitop.pref", "debian/rules")} <= set(files)
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
