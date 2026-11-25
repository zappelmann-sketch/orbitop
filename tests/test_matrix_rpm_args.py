# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""E2 (#10): die Aufrufe von rpm, rpmbuild, dnf und zypper in scripts/matrix/{rpm,dnf,zypper}.sh setzen -- nach den
Optionen und vor feste Paketnamen und Pfade. Ausgenommen sind die Befehle der README, die die Matrix wörtlich
ausführt (tests/test_readme.py, STEPS und RPM_KEYS): dort stünde -- vor -y oder zwischen den Wörtern des Befehls. Ohne
Docker: Stellvertreter schreiben jeden Aufruf als Zeile nach STATE/argv; rpm geht danach an den Stellvertreter auf
PATH (tests/matrix_helpers.py)."""
import pytest

from tests.matrix_helpers import FILES, call, rpm_site

RECORD = ('rpm() { echo "rpm $*" >> "$STATE/argv"; command rpm "$@"; };'
          ' rpmbuild() { echo "rpmbuild $*" >> "$STATE/argv"; }; dnf() { echo "dnf $*" >> "$STATE/argv"; };'
          ' zypper() { echo "zypper $*" >> "$STATE/argv"; };'
          ' net() { "$@"; }; quiet() { "$@"; }; point() { :; }; drop_key() { :; }; leftovers() { :; };')
KEYRING = "rpm_key() { :; }; release_package() { :; };"
OWNER = 'TOOL=<tmp>/tool; elf() { :; }; rpm() { echo "rpm $*" >> "$STATE/argv"; echo "(none)|2.5|1.1|x86_64|(none)"; };'
Z = "zypper --non-interactive"
RPMBUILD = ("rpmbuild -bb --target x86_64 --define _topdir <state>/owner-1 --define debug_package %{nil} --define"
            " __spec_install_post %{nil} --define _build_id_links none -- <state>/owner-1/SPECS/owner.spec")
CALLS = [
    ("dnf.sh", "", "installed", ["rpm -q --qf %{VERSION}-%{RELEASE} -- orbitop"]),
    ("dnf.sh", "", "offered <root>",
     ["rpm -qp --qf %{VERSION}-%{RELEASE} -- <root>/rpm/fedora/orbitop-0.2.0-1.noarch.rpm"]),
    ("dnf.sh", "", "pkg_files", ["rpm -ql -- orbitop"]),
    ("dnf.sh", "", "purge_pkg orbitop",
     ["rpm -q -- orbitop", "dnf remove -y --setopt=clean_requirements_on_remove=False -- orbitop"]),
    ("dnf.sh", "", "install_file /x.rpm",
     ["rpm -q -- orbitop", "rpm -U --replacepkgs --oldpackage --nosignature -- /x.rpm"]),
    ("dnf.sh", "", "rpm_pair /a.rpm /b.rpm", ["rpm -U --nosignature -- /a.rpm /b.rpm"]),
    ("dnf.sh", "", "case_pkexec_provider", ["rpm -q --whatprovides --qf %{NAME}\\n -- /usr/bin/pkexec"]),
    ("dnf.sh", "", "rpm_key <root>", ["rpm --import -- <root>/orbitop-archive-keyring.asc",
                                      "rpm -K -- <root>/rpm/fedora/orbitop-0.2.0-1.noarch.rpm"
                                      " <root>/rpm/fedora/orbitop-release-2026.11.18-1.noarch.rpm"]),
    ("dnf.sh", OWNER, "fake_owner 1",
     ["rpm -q --qf %{EPOCH}|%{VERSION}|%{RELEASE}|%{ARCH}|%{VENDOR}\\n -- igt-gpu-tools", RPMBUILD]),
    ("dnf.sh", "", "get_pkg igt-gpu-tools", ["dnf install -y -- igt-gpu-tools"]),
    ("dnf.sh", "", "reget_pkg igt-gpu-tools", ["dnf reinstall -y -- igt-gpu-tools"]),
    ("dnf.sh", "", "remove_pkg orbitop", ["dnf remove -y --setopt=clean_requirements_on_remove=False -- orbitop"]),
    ("dnf.sh", "", "install_new /x.rpm", ["dnf install -y -- /x.rpm"]),
    ("dnf.sh", "", "dnf_pair /a.rpm /b.rpm", ["dnf upgrade -y -- /a.rpm /b.rpm"]),
    ("dnf.sh", "", "tools", ["dnf install -y -- python3-pytest ShellCheck desktop-file-utils appstream util-linux"]),
    ("dnf.sh", KEYRING, "keyring <root>",
     ["dnf install ./orbitop-release-fedora.rpm -y", "rpm -V -- orbitop-release"]),
    ("dnf.sh", "", "install_pkg", ["dnf install orbitop -y"]),
    ("dnf.sh", "", "remove",
     ["rpm -ql -- orbitop orbitop-release", "dnf remove orbitop -y", "dnf makecache --refresh"]),
    ("dnf.sh", "ls() { :; }; rm() { :; };", "purge",  # nichts unter /var/cache auf dem Rechner der Tests
     ["rpm -V --nomtime -- orbitop-release", "dnf remove orbitop-release -y", "dnf makecache --refresh"]),
    ("zypper.sh", "", "get_pkg intel-gpu-tools", [f"{Z} install -- intel-gpu-tools"]),
    ("zypper.sh", "", "reget_pkg intel-gpu-tools", [f"{Z} install --force -- intel-gpu-tools"]),
    ("zypper.sh", "", "remove_pkg orbitop", [f"{Z} remove -- orbitop"]),
    ("zypper.sh", "", "install_new /x.rpm", [f"{Z} --no-gpg-checks install --allow-unsigned-rpm -- /x.rpm"]),
    ("zypper.sh", "", "zypper_pair <tmp>/a.rpm <tmp>/b.rpm",
     [f"{Z} addrepo --no-gpgcheck --type plaindir -- <state>/joint joint",
      f"{Z} update --repo joint -- orbitop intel-gpu-tools", f"{Z} removerepo -- joint"]),
    ("zypper.sh", "", "tools", [f"{Z} install -- python3-pytest ShellCheck desktop-file-utils AppStream"]),
    ("zypper.sh", KEYRING, "keyring <root>",
     [f"{Z} install -- findutils", f"{Z} install ./orbitop-release-opensuse.rpm", "rpm -V -- orbitop-release"]),
    ("zypper.sh", "", "install_pkg", [f"{Z} install orbitop", "zypper lr -- orbitop"]),
    ("zypper.sh", "", "remove", ["rpm -ql -- orbitop orbitop-release", f"{Z} remove orbitop",
                                 f"{Z} refresh --force -- orbitop"]),
    ("zypper.sh", "", "purge", ["rpm -V --nomtime -- orbitop-release", f"{Z} remove orbitop-release", f"{Z} refresh"]),
    ("zypper.sh", "", "refresh_index", [f"{Z} refresh -- orbitop"]),
]


@pytest.mark.parametrize("manager,stubs,command,want", CALLS, ids=[f"{c[0][:-3]}-{c[2].split()[0]}" for c in CALLS])
def test_fixed_values_follow_a_double_dash(tmp_path, manager, stubs, command, want):
    root = rpm_site(tmp_path)
    for name in ("tool", "a.rpm", "b.rpm"):
        (tmp_path / name).write_bytes(b"x")
    places = {"<root>": str(root), "<state>": str(tmp_path / "state"), "<tmp>": str(tmp_path)}

    def fill(text):
        for key, value in places.items():
            text = text.replace(key, value)
        return text

    call(tmp_path, fill(f"{RECORD} {stubs} {command}"), *FILES[manager], env={"RPMK": "digests signatures OK"})
    argv = tmp_path / "state" / "argv"
    assert (argv.read_text().splitlines() if argv.exists() else []) == [fill(w) for w in want]
