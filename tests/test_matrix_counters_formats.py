# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Werte und Befehle je Format für die Fälle der Freigabe (scripts/matrix/{apt,rpm,dnf,zypper,pacman}.sh): was
ein Entfern-Skript bei defektem Helfer meldet, die Wege des gemeinsamen Upgrades, die Auslöser im Log, die Dateien von
orbitop und die RPM-Fälle aus B2.4 (Fall 7 und 8). Ohne Docker, mit Stellvertretern (tests/matrix_helpers.py)."""
import re

import pytest

from tests.matrix_helpers import FILES, call
from tests.packaging_common import PKG
from tests.scriptlets import HELPER, run_arch, run_deb, run_rpm

REMOVE = {"apt.sh": lambda tmp, **kw: run_deb(tmp, "prerm", "remove", **kw),
          "dnf.sh": lambda tmp, **kw: run_rpm(tmp, "%preun", "0", **kw),
          "zypper.sh": lambda tmp, **kw: run_rpm(tmp, "%preun", "0", **kw),
          "pacman.sh": lambda tmp, **kw: run_arch(tmp, "pre_remove", **kw)}


def sourced(tmp_path, manager, command):
    return call(tmp_path, command, *FILES[manager], "counters.sh")


@pytest.mark.parametrize("manager", sorted(FILES))
def test_revoke_failed_is_what_the_remove_script_prints_when_off_cannot_run(tmp_path, manager):
    """Controller nach dem Review von Task 3: REVOKE_FAILED ist nie leer (matching "" träfe jede Zeile, und
    remove_broken_helper bestünde leer) und trifft, was das echte Entfern-Skript des Formats mit einem Helfer ohne
    x-Bit (chmod -x) meldet: deb die Zeile von prerm, RPM und Arch die Meldung der Shell (bash: "DATEI: line N:"
    davor), nie eine leere oder fremde Zeile."""
    r, _, _ = REMOVE[manager](tmp_path, helper=0o644)
    (tmp_path / "op.out").write_text(r.stdout + r.stderr.replace(str(tmp_path / "counterhelper"), HELPER))
    (tmp_path / "other.out").write_text("\nRemoving orbitop (0.2.0-1) ...\n")
    ok, out = sourced(tmp_path, manager, f'[ -n "$REVOKE_FAILED" ] && matching "$REVOKE_FAILED" {tmp_path}/op.out && '
                                         f'! matching "$REVOKE_FAILED" {tmp_path}/other.out')
    assert r.returncode == 0 and ok, (r.stderr, out)


@pytest.mark.parametrize("manager,ways,commands", [
    ("dnf.sh", ["rpm_pair", "dnf_pair"], ['rpm -U --nosignature "$1" "$2"', 'dnf upgrade -y "$1" "$2"']),
    ("zypper.sh", ["rpm_pair", "zypper_pair"], ['rpm -U --nosignature "$1" "$2"',
                                                'update --repo joint orbitop "$OWNER"']),
    ("pacman.sh", ["pacman_pair"], ['pacman -U --noconfirm -- "$1" "$2"'])])
def test_joint_upgrade_ways(tmp_path, manager, ways, commands):
    """B2.4 Fall 6: rpm -U beider Pakete und dnf upgrade bzw. zypper up, unter Arch pacman -U beider Pakete."""
    ok, out = sourced(tmp_path, manager, f'printf "WAY %s\\n" "${{JOINT[@]}}"; declare -f {" ".join(ways)}')
    assert ok and re.findall(r"^WAY (\S+)", out, re.M) == ways, out
    assert all(c in out for c in commands), out


def hook_description():
    lines = (PKG / "arch" / "orbitop-counters.hook").read_text(encoding="utf-8").splitlines()
    return next(ln.split(" = ", 1)[1] for ln in lines if ln.startswith("Description = "))


@pytest.mark.parametrize("manager,line,passed", [
    ("pacman.sh", f"(2/3) {hook_description()}", True), ("pacman.sh", "(1/1) Arming ConditionNeedsUpdate...", False),
    ("dnf.sh", "[3/4] Reinstalling igt-gpu-tools-0:2.6-3.fc45.x86_64", True),
    ("zypper.sh", "(1/1) Installing: intel-gpu-tools-2.5-1.2.x86_64 [done]", True)],
    ids=["pacman", "pacman-other", "dnf-logs-none", "zypper-logs-none"])
def test_triggered_sees_the_line_of_the_format(tmp_path, manager, line, passed):
    """pacman nennt den Hook mit seiner Description. dnf5 und zypper melden ein Scriptlet nur, wenn es etwas ausgibt,
    und sync schweigt ohne Fehler: dort gibt es kein Muster (Probe 2026-11-20)."""
    ok, out = sourced(tmp_path, manager, f"scripted echo '{line}' && triggered")
    assert ok is passed, out


@pytest.mark.parametrize("manager,passed", [("apt.sh", False), ("dnf.sh", True), ("zypper.sh", True),
                                            ("pacman.sh", True)])
def test_owner_remove_needs_a_trigger_only_where_one_fires(tmp_path, manager, passed):
    """B2.4 Fall 3: dpkg löst auch beim Entfernen des Eigentümers aus; %filetriggerin und der Hook (ohne Remove) nur,
    wenn die Datei kommt. Ohne Zeile des Auslösers scheitert der Fall nur unter deb."""
    stubs = (f"helper() {{ :; }}; marker_on() {{ :; }}; remove_owner() {{ echo 'removed the owner'; }};"
             f" TOOL={tmp_path}/missing;")
    assert sourced(tmp_path, manager, f"{stubs} case_owner_remove")[0] is passed


@pytest.mark.parametrize("output,rc,passed", [("........P    /usr/bin/intel_gpu_top", 1, True), ("", 0, False),
                                              ("........P    /usr/bin/intel_gpu_top\nS.5....T.    /usr/bin/gputop", 1,
                                               False), ("........P    /usr/bin/intel_gpu_top", 0, False)],
                         ids=["capability", "clean", "more", "exit-0"])
@pytest.mark.parametrize("manager", ["dnf.sh", "zypper.sh"])
def test_rpm_verify_reports_only_the_capability(tmp_path, manager, output, rc, passed):  # B2.4 Fall 7
    stubs = f"helper() {{ :; }}; has_cap() {{ :; }}; rpm() {{ printf '%s\\n' '{output}'; return {rc}; }};"
    ok, out = sourced(tmp_path, manager, f"{stubs} case_rpm_verify")
    assert ok is passed and "RPM-V " in out, out


@pytest.mark.parametrize("manager,names,passed", [("dnf.sh", "polkit", True), ("zypper.sh", "pkexec", True),
                                                  ("zypper.sh", "run0-wrappers", False), ("dnf.sh", "pkexec", False),
                                                  ("zypper.sh", "pkexec\nrun0-wrappers", False)],
                         ids=["fedora", "opensuse", "run0", "other", "both"])
def test_pkexec_comes_from_polkit(tmp_path, manager, names, passed):  # B2.4 Fall 8, E5
    ok, out = sourced(tmp_path, manager, f"rpm() {{ printf '%s\\n' '{names}'; }}; case_pkexec_provider")
    assert ok is passed, out


@pytest.mark.parametrize("manager,name,files,passed", [
    ("dnf.sh", "rev1", ["site/rpm/fedora/orbitop-0.2.0-1.noarch.rpm",
                        "site/rpm/fedora/orbitop-release-2026.11.18-1.noarch.rpm"], True),
    ("zypper.sh", "rev2", ["rev2/rpm-opensuse/orbitop-0.2.0-2.noarch.rpm",
                           "rev2/rpm-fedora/orbitop-0.2.0-3.noarch.rpm"], True),
    ("dnf.sh", "v020", ["v020/rpm-fedora/orbitop-0.2.0-1.noarch.rpm"], True),
    ("dnf.sh", "rev2", ["rev2/rpm-opensuse/orbitop-0.2.0-2.noarch.rpm"], False),
    ("pacman.sh", "rev1", ["site/arch/x86_64/orbitop-0.2.0-1-any.pkg.tar.zst",
                           "site/arch/x86_64/orbitop-0.2.0-1-any.pkg.tar.zst.sig"], True),
    ("pacman.sh", "rev2", ["rev2/arch/orbitop-0.2.0-2-any.pkg.tar.zst"], True),
    ("pacman.sh", "v020", ["v020/arch/orbitop-0.2.0-1-any.pkg.tar.zst", "v020/arch/orbitop-0.2.0-2-any.pkg.tar.zst"],
     False)], ids=["fedora-rev1", "opensuse-rev2", "fedora-v020", "fedora-none", "arch-rev1", "arch-rev2", "arch-two"])
def test_orbitop_file_of_rpm_and_arch(tmp_path, manager, name, files, passed):
    for f in files:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).touch()
    ok, out = sourced(tmp_path, manager, f"SITE={tmp_path}/site REV2={tmp_path}/rev2 V020={tmp_path}/v020; "
                                         f"orbitop_file {name}")
    assert ok is passed, out
    if passed:
        assert out.splitlines()[-2] == str(tmp_path / files[0])


@pytest.mark.parametrize("installed,want", [(0, "RPM -U --replacepkgs --oldpackage --nosignature /x.rpm"),
                                            (1, "NEW /x.rpm")], ids=["installed", "first"])
@pytest.mark.parametrize("manager", ["dnf.sh", "zypper.sh"])
def test_rpm_install_file_brings_dependencies_the_first_time(tmp_path, manager, installed, want):
    """rpm -U nimmt auch dieselbe und eine niedrigere Version; das erste Mal holt die Paketverwaltung die
    Abhängigkeiten, die dnf remove im Schritt remove mitnahm."""
    stubs = (f'rpm() {{ [ "$1" = -q ] && return {installed}; echo "RPM $*"; }};'
             ' install_new() { echo "NEW $*"; };')
    ok, out = sourced(tmp_path, manager, f"{stubs} install_file /x.rpm")
    assert ok and want in out.splitlines(), out


@pytest.mark.parametrize("installed,removed", [(0, True), (1, False)], ids=["installed", "gone"])
@pytest.mark.parametrize("manager", ["dnf.sh", "zypper.sh", "pacman.sh"])
def test_purge_is_the_removal_or_nothing(tmp_path, manager, installed, removed):  # RPM und pacman kennen kein Purge
    stubs = (f'rpm() {{ return {installed}; }}; pacman() {{ return {installed}; }};'
             ' remove_pkg() { echo "REMOVE $*"; };')
    ok, out = sourced(tmp_path, manager, f"{stubs} purge_pkg orbitop")
    assert ok and ("REMOVE orbitop" in out.splitlines()) is removed, out


def test_pacman_installs_a_copy_without_the_signature_next_to_it(tmp_path):
    """pacman -U prüft eine .sig neben der Datei (Probe 2026-11-20), und purge nahm den Schlüssel aus pacmans
    Schlüsselbund: orbitop kommt aus einer Kopie in STATE."""
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "orbitop-0.2.0-1-any.pkg.tar.zst").write_text("pkg")
    (tmp_path / "site" / "orbitop-0.2.0-1-any.pkg.tar.zst.sig").write_text("sig")
    ok, out = sourced(tmp_path, "pacman.sh", 'pacman() { echo "PACMAN $*"; };'
                                             f" install_file {tmp_path}/site/orbitop-0.2.0-1-any.pkg.tar.zst")
    state = tmp_path / "state"
    assert ok and f"PACMAN -U --noconfirm -- {state}/orbitop-0.2.0-1-any.pkg.tar.zst" in out.splitlines(), out
    assert not (state / "orbitop-0.2.0-1-any.pkg.tar.zst.sig").exists()
