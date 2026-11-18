# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""RPM-Pakete orbitop und orbitop-release (Fedora, openSUSE): Abhängigkeiten, Quellen, Schlüssel, Bytes je Version."""
import configparser
import hashlib
import re

from orbitop import app
from tests.packaging_common import METAINFO, PKG, ROOT, load_changelog

RPM = PKG / "rpm"
KEYRING = PKG / "keyring"
KEY = "/etc/pki/rpm-gpg/RPM-GPG-KEY-orbitop"
PAGES = "https://zappelmann-sketch.github.io/orbitop/rpm/"
# Eingaben von orbitop-release außer dem Schlüssel, je packaging/keyring.version (wie APT_SOURCE_INPUTS in
# test_packaging_debian.py): Ändert sich eine, steigt die Version. Ersetzen nur vor der ersten Veröffentlichung.
RELEASE_INPUTS = {"2026.11.18": "f07e14f0ca69be331538e36c0a694fc2033ab3bcbdd86af796d9b26bed4c202c"}


def tags(spec):
    """(Zweig, Tag, Wert) je Zeile "Tag: Wert"; Zweig ist "suse", "fedora" oder "" außerhalb von %if."""
    out, branch = [], ""
    for line in (RPM / spec).read_text(encoding="utf-8").splitlines():
        if line.strip() == "%if 0%{?suse_version}":
            branch = "suse"
        elif line.strip() == "%else" and branch == "suse":
            branch = "fedora"
        elif line.strip() == "%endif":
            branch = ""
        elif m := re.fullmatch(r"([A-Za-z]+):\s+(.*)", line):
            out.append((branch, m[1], m[2].strip()))
    return out


def values(spec, tag, branch):
    return [v for b, t, v in tags(spec) if t == tag and b in ("", branch)]


def test_rpm_requires_match_app_packages():  # beide Zweige des %if, Namen wie in app.PACKAGES (K4)
    for branch, manager in (("fedora", "dnf"), ("suse", "zypper")):
        assert values("orbitop.spec", "Requires", branch) == ["python3 >= 3.12", *app.PACKAGES[manager], "polkit"]
        assert values("orbitop.spec", "Suggests", branch) == ["igt-gpu-tools"]
        assert values("orbitop.spec", "BuildArch", branch) == ["noarch"]
        assert not [v for v in values("orbitop.spec", "Requires", branch) if v.startswith("orbitop")]  # K3


def test_rpm_version_only_from_build():  # die Upstream-Version steht nur in orbitop/__init__.py
    assert values("orbitop.spec", "Version", "") == ["%{orbitop_version}"]
    assert values("orbitop.spec", "Release", "") == ["%{orbitop_release}"]
    assert values("orbitop-release.spec", "Version", "") == ["%{keyring_version}"]
    assert values("orbitop-release.spec", "Release", "") == ["1"]


def test_specs_end_without_changelog_entries():  # %changelog schreibt build-inside.sh aus metainfo bzw. keyring.version
    for spec in ("orbitop.spec", "orbitop-release.spec"):
        assert (RPM / spec).read_text(encoding="utf-8").endswith("\n%changelog\n"), spec


def test_spec_description_matches_metainfo():
    meta = METAINFO.read_text(encoding="utf-8")
    summary = re.search(r"<summary>(.*?)</summary>", meta).group(1)
    first = re.sub(r"\s+", " ", re.search(r"<p>(.*?)</p>", meta, re.S).group(1))
    spec = (RPM / "orbitop.spec").read_text(encoding="utf-8")
    description = re.search(r"%description\n(.*?)\n\n", spec, re.S).group(1)
    assert (values("orbitop.spec", "Summary", ""), description.replace("\n", " ")) == ([summary], first)


def test_spec_installs_the_common_tree():  # derselbe Baum wie das .deb, dazu nur Byte-Code und %license
    spec = (RPM / "orbitop.spec").read_text(encoding="utf-8")
    assert "bash packaging/install-tree.sh %{buildroot}\n" in spec
    files = spec.split("\n%files\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert files == [
        "%license LICENSE", "%{_bindir}/orbitop", "%{_datadir}/orbitop/", "%{_prefix}/lib/orbitop/",
        "%{_datadir}/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy",
        "%{_datadir}/applications/io.github.zappelmann_sketch.orbitop.desktop",
        "%{_datadir}/icons/hicolor/scalable/apps/io.github.zappelmann_sketch.orbitop.svg",
        "%{_datadir}/metainfo/io.github.zappelmann_sketch.orbitop.metainfo.xml"]


def repo(family):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(KEYRING / f"orbitop-{family}.repo", encoding="utf-8")
    assert parser.sections() == ["orbitop"]
    return dict(parser["orbitop"])


def test_repo_files_have_signature_checks():
    for family in ("fedora", "opensuse"):
        r = repo(family)
        assert (r["gpgcheck"], r["repo_gpgcheck"], r["gpgkey"]) == ("1", "1", "file://" + KEY), family
        assert (r["baseurl"], r["enabled"]) == (PAGES + family, "1"), family
        # über dem Standard 99: dnf und zypper nehmen die kleinere Zahl, Pakete der Distribution gewinnen immer
        assert r["priority"] == "100", family
    assert repo("opensuse")["autorefresh"] == "1"
    assert set(repo("opensuse")) - set(repo("fedora")) == {"autorefresh"}


def test_release_spec_installs_repo_and_key():  # .repo als %config(noreplace), der Schlüssel nie als %config
    spec = (RPM / "orbitop-release.spec").read_text(encoding="utf-8")
    files = spec.split("\n%files\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert files == ["%license LICENSE", "%dir %{_sysconfdir}/pki/rpm-gpg",
                     "%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-orbitop",
                     "%config(noreplace) %{reposdir}/orbitop.repo"]
    assert "%global reposdir %{_sysconfdir}/zypp/repos.d\n" in spec.split("%else", 1)[0]
    assert "%global reposdir %{_sysconfdir}/yum.repos.d\n" in spec.split("%else", 1)[1]


def release_inputs():
    version = (PKG / "keyring.version").read_text().strip()
    h = hashlib.sha256(load_changelog().rpm_release(version).encode())
    for p in [RPM / "orbitop-release.spec", *sorted(KEYRING.glob("*.repo")), ROOT / "LICENSE"]:
        h.update(b"\0" + str(p.relative_to(ROOT)).encode() + b"\0" + p.read_bytes())
    return version, h.hexdigest()


def test_release_inputs_pinned():  # gleiche Version, gleiche Bytes
    version, digest = release_inputs()
    assert RELEASE_INPUTS.get(version) == digest
