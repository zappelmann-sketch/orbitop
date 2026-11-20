# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Die Fälle der Freigabe in der Container-Matrix (scripts/matrix/counters.sh, Schritt counters in inside.sh): die
Liste je Format, eine Zeile COUNTERS je Fall, ein Fehler macht den Lauf rot. Ohne Docker: die Funktionen laufen wie in
step, mit Stellvertretern (tests/matrix_helpers.py)."""
import os
import re

import pytest

from orbitop import counterhelper
from tests.matrix_helpers import FILES, MATRIX, call

COUNTERS = MATRIX / "counters.sh"
# Security-Dokument 0.3.0: B2.4 Fälle 1–6, B2.8 Fälle 1–7, B2.2 und B2.3 (Dateiliste), B2.9; in der Reihenfolge des
# Laufs, denn jeder Fall beginnt mit dem Stand des vorigen (zuletzt die falsche nächste Version des Eigentümers). RPM
# dazu B2.4 Fall 8 (pkexec_provider, nach der ersten Installation) und Fall 7 (rpm_verify, nach on mit Fähigkeit).
COMMON = ["orbitop_install_manual_cap", "file_list", "reinstall_owner_off", "on_off", "reinstall_owner_on",
          "owner_remove", "owner_first_install_on", "rev2_upgrade_on", "remove_on", "remove_broken_helper", "purge",
          "manual_rule_untouched", "upgrade_from_020", "joint_upgrade"]
RPM_CASES = [*COMMON[:1], "pkexec_provider", *COMMON[1:5], "rpm_verify", *COMMON[5:]]
CASES = {"apt.sh": COMMON, "dnf.sh": RPM_CASES, "zypper.sh": RPM_CASES, "pacman.sh": COMMON}
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


@pytest.mark.parametrize("manager", sorted(CASES))
def test_every_case_and_format_function_exists(tmp_path, manager):
    names = [f"case_{c}" for c in CASES[manager]] + FORMAT
    ok, out = call(tmp_path, " && ".join(f"declare -F {n} > /dev/null" for n in names) + " && "
                   + '[ ${#JOINT[@]} -gt 0 ] && for w in "${JOINT[@]}"; do declare -F "$w"; done', *FILES[manager],
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


def test_a_format_without_cases_fails(tmp_path):  # jedes Format hat Fälle; eine leere Liste wäre eine stille Lücke
    ok, out = call(tmp_path, "set -u; COUNTER_CASES=(); counters", "apt.sh", "counters.sh")
    assert not ok and [ln for ln in out.splitlines() if ln.startswith("COUNTERS ")] == ["COUNTERS none"], out


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


def test_package_scripts_report_a_failed_helper_in_the_words_of_the_matrix(tmp_path):
    """NOT_APPLIED trifft die Texte von postinst und prerm und, für RPM und Arch, deren Scriptlets selbst nichts
    melden, jede Meldung des Helfers und die der Shell, wenn er nicht starten kann."""
    for line in ("orbitop: counter release not applied", "orbitop: counter release not revoked",
                 *(f"counterhelper: {text}" for text in counterhelper._MESSAGES.values()),
                 ">>> /var/tmp/rpm-tmp.Ab12: line 1: /usr/lib/orbitop/counterhelper: Permission denied"):
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


# Jede Prüfung der Fälle kann scheitern (Review Task 3, Minor 3): sonst bestünde ein Fall leer. Stellvertreter sind
# Shell-Funktionen nach dem Laden von counters.sh; MARKER und TOOL zeigen in tmp_path.
CAP = "0100000200000000000000004000000000000000"


@pytest.mark.parametrize("value,has,no", [(CAP, True, False), ("none", False, True),
                                          ("0100000200000000000000000000000000000000", False, False), (None, False, False)],
                         ids=["perfmon", "none", "other", "error"])
def test_has_cap_and_no_cap(tmp_path, value, has, no):
    stub = "cap() { return 1; };" if value is None else f"cap() {{ echo {value}; }};"
    for check, want in (("has_cap", has), ("no_cap", no)):
        assert call(tmp_path, f"{stub} {check}", "apt.sh", "counters.sh")[0] is want, check


def test_cap_reads_the_file_and_fails_without_it(tmp_path):
    tool = tmp_path / "intel_gpu_top"
    tool.write_bytes(b"\x7fELF")
    ok, out = call(tmp_path, f'TOOL={tool}; [ "$(cap)" = none ]', "apt.sh", "counters.sh")
    assert ok, out
    assert not call(tmp_path, f"TOOL={tmp_path}/missing; cap", "apt.sh", "counters.sh")[0]


def marker_tree(tmp_path, kind):
    etc = tmp_path / "etc-orbitop"
    etc.mkdir()
    marker = etc / "counters-released"
    if kind == "file":
        marker.touch()
    elif kind == "symlink":
        (etc / "elsewhere").touch()
        marker.symlink_to(etc / "elsewhere")
    elif kind == "directory":
        marker.mkdir()
    return marker


@pytest.mark.parametrize("kind,stat,on,off", [
    ("file", "0 0 644 0", True, False), ("file", "1000 1000 644 0", False, False), ("file", "0 0 600 0", False, False),
    ("file", "0 0 644 3", False, False), ("symlink", "0 0 644 0", False, False), ("directory", "0 0 644 0", False, False),
    ("missing", "0 0 644 0", False, True)], ids=["ok", "owner", "mode", "size", "symlink", "directory", "missing"])
def test_marker_on_and_off(tmp_path, kind, stat, on, off):  # stat liefert uid gid Modus Größe, als wäre root Eigentümer
    marker = marker_tree(tmp_path, kind)
    for check, want in (("marker_on", on), ("marker_off", off)):
        ok, out = call(tmp_path, f'MARKER={marker}; stat() {{ echo "{stat}"; }}; {check}', "apt.sh", "counters.sh")
        assert ok is want, (check, out)


@pytest.mark.skipif(os.geteuid() == 0, reason="root öffnet jeden Ordner")
@pytest.mark.parametrize("mode,stat,passed", [(0o000, "0 0 711", True), (0o755, "0 0 711", False),
                                              (0o000, "0 0 755", False), (0o000, "1000 1000 711", False)],
                         ids=["closed", "openable", "readable-mode", "owner"])
def test_closed_needs_root_0711_and_no_access_for_others(tmp_path, mode, stat, passed):
    """runuser läuft hier als derselbe Benutzer: ein Ordner mit 000 ist dann so zu wie 0711 für nobody."""
    marker = marker_tree(tmp_path, "missing")
    marker.parent.chmod(mode)
    try:
        ok, out = call(tmp_path, f'MARKER={marker}; stat() {{ echo "{stat}"; }}; runuser() {{ shift 3; "$@"; }}; closed',
                       "apt.sh", "counters.sh")
    finally:
        marker.parent.chmod(0o755)
    assert ok is passed, out


@pytest.mark.parametrize("kind", ["symlink", "missing"])
def test_closed_refuses_a_link_or_no_directory(tmp_path, kind):
    target = tmp_path / "real"
    target.mkdir()
    etc = tmp_path / "etc-orbitop"
    if kind == "symlink":
        etc.symlink_to(target)
    command = f'MARKER={etc}/counters-released; stat() {{ echo "0 0 711"; }}; runuser() {{ return 0; }}; closed'
    assert not call(tmp_path, command, "apt.sh", "counters.sh")[0]


@pytest.mark.parametrize("pattern,log,passed", [("^Processing triggers for orbitop ", "Processing triggers for orbitop "
                                                 "(0.2.0-1) ...", True),
                                                ("^Processing triggers for orbitop ", "Setting up orbitop", False),
                                                ("", "Setting up orbitop", True)], ids=["ran", "not-run", "no-pattern"])
def test_triggered(tmp_path, pattern, log, passed):  # ohne Muster (Format ohne solche Zeile) gilt der Fall weiter
    ok, out = call(tmp_path, f"scripted echo '{log}'; TRIGGERED='{pattern}'; triggered", "apt.sh", "counters.sh")
    assert ok is passed, out


@pytest.mark.parametrize("rc,want,passed", [(0, 0, True), (3, 0, False), (0, 3, False), (3, 3, True)])
def test_helper_compares_the_exit_code(tmp_path, rc, want, passed):
    stub = tmp_path / "counterhelper"
    stub.write_text(f"#!/bin/sh\nexit {rc}\n")
    stub.chmod(0o755)
    ok, out = call(tmp_path, f"HELPER={stub}; helper on {want}", "apt.sh", "counters.sh")
    assert ok is passed and f"counterhelper on: exit {rc}" in out, out


@pytest.mark.parametrize("prerm,passed", [("orbitop: counter release not revoked", True),
                                          ("Removing orbitop (0.2.0-1) ...", False)], ids=["helper-failed", "silent"])
def test_remove_broken_helper_needs_the_report_of_prerm(tmp_path, prerm, passed):
    """Review Task 3, Minor 1: ohne die Zeile von prerm scheitert der Fall von selbst, auch wenn Fähigkeit und
    Merkdatei stimmen (etwa wenn prerm den Helfer nie riefe)."""
    stubs = (f"helper() {{ :; }}; has_cap() {{ :; }}; marker_off() {{ :; }}; set_cap() {{ :; }}; chmod() {{ :; }};"
             f" remove_pkg() {{ echo '{prerm}'; }}; purge_pkg() {{ :; }}; MARKER={tmp_path}/gone/counters-released;")
    ok, out = call(tmp_path, f"{stubs} case_remove_broken_helper", "apt.sh", "counters.sh")
    assert ok is passed, out


@pytest.mark.parametrize("after,passed", [("none", True), (CAP, False)], ids=["taken", "kept"])
def test_reinstall_owner_off_needs_the_reinstall_to_take_a_capability_set_by_hand(tmp_path, after, passed):
    """openSUSE behält bei einer Neuinstallation eine unveränderte Datei (%_minimize_writes), nimmt ihr aber die
    Fähigkeit: dieser Fall belegt das je Format, reinstall_owner_on baut darauf."""
    stubs = (f"helper() {{ :; }}; marker_off() {{ :; }}; triggered() {{ :; }}; cap() {{ echo {after}; }};"
             f" set_cap() {{ echo \"SET $1\" >> {tmp_path}/log; }};"
             f" reinstall_owner() {{ echo REINSTALL >> {tmp_path}/log; }};")
    ok, out = call(tmp_path, f"{stubs} case_reinstall_owner_off", "apt.sh", "counters.sh")
    assert ok is passed, out
    assert (tmp_path / "log").read_text().splitlines() == [f"SET {CAP}", "REINSTALL"]


@pytest.mark.parametrize("changed,passed", [(True, True), (False, False)], ids=["touched", "untouched"])
def test_reinstall_owner_on_needs_the_file_touched(tmp_path, changed, passed):
    stubs = ("helper() { :; }; has_cap() { :; }; marker_on() { :; }; triggered() { :; }; reinstall_owner() { :; };"
             f" stamp() {{ echo x >> {tmp_path}/n; echo \"1 $(({int(changed)} * $(wc -l < {tmp_path}/n)))\"; }};")
    assert call(tmp_path, f"{stubs} case_reinstall_owner_on", "apt.sh", "counters.sh")[0] is passed
