# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Fälle der Freigabe in der Container-Matrix (scripts/matrix/counters.sh, Schritt counters in inside.sh): die
Liste je Format, eine Zeile COUNTERS je Fall, ein Fehler macht den Lauf rot. Ohne Docker: die Funktionen laufen wie in
step, mit Stellvertretern (tests/matrix_helpers.py)."""
import re

import pytest

from orbitop import counterhelper
from tests.matrix_helpers import MATRIX, call

COUNTERS = MATRIX / "counters.sh"
# Security-Dokument 0.3.0: B2.4 Fälle 1–6, B2.8 Fälle 1–7, B2.2 und B2.3 (Dateiliste), B2.9; in der Reihenfolge des
# Laufs, denn jeder Fall beginnt mit dem Stand des vorigen (zuletzt die falsche nächste Version des Eigentümers).
CASES = {"apt.sh": ["orbitop_install_manual_cap", "file_list", "reinstall_owner_off", "on_off", "reinstall_owner_on",
                    "owner_remove", "owner_first_install_on", "rev2_upgrade_on", "remove_on", "remove_broken_helper",
                    "purge", "manual_rule_untouched", "upgrade_from_020", "joint_upgrade"],
         "dnf.sh": [], "zypper.sh": [], "pacman.sh": []}  # ihre Auslöser und Fälle kommen mit den RPM- und Arch-Skripten
FILES = {"apt.sh": ("apt.sh",), "dnf.sh": ("rpm.sh", "dnf.sh"), "zypper.sh": ("rpm.sh", "zypper.sh"),
         "pacman.sh": ("pacman.sh",)}
# Was counters.sh vom Format braucht.
FORMAT = ["install_owner", "reinstall_owner", "remove_owner", "fake_owner", "install_file", "orbitop_file",
          "pkg_files", "remove_pkg", "purge_pkg", "installed", "owned"]


def cases(tmp_path, manager):
    ok, out = call(tmp_path, 'set -u; for c in "${COUNTER_CASES[@]}"; do echo "CASE $c"; done', *FILES[manager], "counters.sh")
    assert ok, out
    return [ln.split()[1] for ln in out.splitlines() if ln.startswith("CASE ")]


@pytest.mark.parametrize("manager", sorted(CASES))
def test_case_list_per_format(tmp_path, manager):
    assert cases(tmp_path, manager) == CASES[manager]


@pytest.mark.parametrize("manager", sorted(m for m, c in CASES.items() if c))
def test_every_case_and_format_function_exists(tmp_path, manager):
    names = [f"case_{c}" for c in CASES[manager]] + FORMAT
    ok, out = call(tmp_path, " && ".join(f"declare -F {n} > /dev/null" for n in names) + " && "
                   + '[ ${#JOINT[@]} -gt 0 ] && for w in "${JOINT[@]}"; do declare -F "$w"; done', manager,
                   "counters.sh")
    assert ok, out


def test_joint_upgrade_ways_of_apt(tmp_path):  # B2.4 Fall 6: apt-get install beider Dateien, dpkg -i in beiden Reihenfolgen
    ok, out = call(tmp_path, 'printf "WAY %s\\n" "${JOINT[@]}"; declare -f install_pair dpkg_pair dpkg_pair_reversed',
                   "apt.sh", "counters.sh")
    assert ok and re.findall(r"^WAY (\S+)", out, re.M) == ["install_pair", "dpkg_pair", "dpkg_pair_reversed"], out
    assert 'apt-get install -y "$1" "$2"' in out and 'dpkg -i "$1" "$2"' in out and 'dpkg -i "$2" "$1"' in out


@pytest.mark.parametrize("results,passed", [([0, 0, 0], True), ([0, 1, 0], False), ([1, 1, 1], False)])
def test_one_failed_case_fails_the_step_and_all_run(tmp_path, results, passed):
    """counters läuft jeden Fall, schreibt je Fall COUNTERS <fall> ok|FAIL und scheitert, sobald einer scheiterte;
    step in inside.sh macht daraus STEP counters fail und check-distros.sh daraus RESULT … fail counters."""
    stubs = " ".join(f"case_c{i}() {{ echo running c{i}; return {rc}; }};" for i, rc in enumerate(results))
    ok, out = call(tmp_path, f"{stubs} COUNTER_CASES=(c0 c1 c2); counters", "apt.sh", "counters.sh")
    assert ok is passed, out
    lines = [ln for ln in out.splitlines() if ln.startswith("COUNTERS ")]
    assert lines == [f"COUNTERS c{i} {'FAIL' if rc else 'ok'}" for i, rc in enumerate(results)]
    assert out.count("running c") == 3


@pytest.mark.parametrize("manager", sorted(m for m, c in CASES.items() if not c))
def test_a_format_without_cases_says_so_and_passes(tmp_path, manager):  # set -u wie in inside.sh
    ok, out = call(tmp_path, "set -u; counters", *FILES[manager], "counters.sh")
    assert ok and [ln for ln in out.splitlines() if ln.startswith("COUNTERS ")] == ["COUNTERS none"], out


def test_inside_runs_the_cases_as_a_step_before_tamper():
    inside = (MATRIX / "inside.sh").read_text()
    steps = re.findall(r"^step (\S+) ", inside, re.M)
    assert steps[-3:] == ["purge", "counters", "tamper"]
    assert ". /src/scripts/matrix/counters.sh" in inside


def test_values_match_the_helper():  # dieselben Werte wie orbitop/counterhelper.py, B2.1 wörtlich für CAP
    text = COUNTERS.read_text()
    assert f"\nMARKER={counterhelper.MARKER} " in text and f"\nTOOL={counterhelper.TOOL}\n" in text
    assert "\nCAP=0100000200000000000000004000000000000000 " in text
    assert counterhelper.CAP.hex() == "0100000200000000000000004000000000000000"
    assert "\nHELPER=/usr/lib/orbitop/counterhelper\n" in text


def test_manual_rule_is_the_one_of_the_readme_of_0_2_0():  # B2.9
    text = COUNTERS.read_text()
    assert "MANUAL_RULE=/etc/udev/rules.d/70-orbitop-rapl.rules" in text
    assert ("""MANUAL_LINE='ACTION=="add", SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", """
            """RUN+="/usr/bin/chmod 0444 /sys%p/energy_uj"'""") in text


def test_package_scripts_report_a_failed_helper_in_the_words_of_the_matrix(tmp_path):  # NOT_APPLIED trifft beide Texte
    for line in ("orbitop: counter release not applied", "orbitop: counter release not revoked"):
        ok, out = call(tmp_path, f'grep -qE -- "$NOT_APPLIED" <<< "{line}"', "apt.sh", "counters.sh")
        assert ok, out


@pytest.mark.parametrize("text,rc,passed", [("Setting up orbitop (0.2.0-1) ...", 0, True),
                                            ("orbitop: counter release not applied", 0, False),
                                            ("dpkg: error processing package orbitop", 1, False)])
def test_scripted_needs_success_and_no_report_of_a_failed_helper(tmp_path, text, rc, passed):
    ok, out = call(tmp_path, f'scripted sh -c \'echo "{text}"; exit {rc}\'', "apt.sh", "counters.sh")
    assert ok is passed, out


@pytest.mark.parametrize("name,files,passed", [
    ("rev1", ["site/apt/pool/main/o/orbitop/orbitop_0.2.0-1_all.deb"], True),
    ("rev2", ["rev2/deb/orbitop_0.2.0-2_all.deb", "rev2/deb/orbitop-apt-source_2026.11.18_all.deb"], True),
    ("v020", ["v020/deb/orbitop_0.2.0-1_all.deb"], True),
    ("rev2", [], False), ("rev2", ["rev2/deb/orbitop_0.2.0-2_all.deb", "rev2/deb/orbitop_0.2.0-3_all.deb"], False),
    ("rev3", ["rev2/deb/orbitop_0.2.0-2_all.deb"], False)], ids=["rev1", "rev2", "v020", "none", "two", "unknown"])
def test_orbitop_file_names_exactly_one_package(tmp_path, name, files, passed):
    for f in files:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).touch()
    ok, out = call(tmp_path, f'SITE={tmp_path}/site REV2={tmp_path}/rev2 V020={tmp_path}/v020; orbitop_file {name}', "apt.sh", "counters.sh")
    assert ok is passed, out
    if passed:
        assert out.splitlines()[-2] == str(tmp_path / files[0])
