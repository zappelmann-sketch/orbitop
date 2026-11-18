# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from orbitop import app

ROOT = Path(__file__).resolve().parent.parent
TREES = ROOT / "tests" / "fixtures" / "roots"


RULE = ('ACTION=="add", SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", '
        'RUN+="/usr/bin/chmod 0444 /sys%p/energy_uj"')
SCRIPT = str(ROOT / "scripts" / "setup-privileges.sh")


INSTALL = {"apt-get": "apt-get install -y", "dnf": "dnf install -y", "pacman": "pacman -S --needed --noconfirm",
           "zypper": "zypper --non-interactive install"}
INTEL_TOOL = {"apt-get": "intel-gpu-tools", "dnf": "igt-gpu-tools", "pacman": "intel-gpu-tools",
              "zypper": "igt-gpu-tools"}


def dry_run(tree, *args, manager="apt-get"):
    env = {**os.environ, "ORBITOP_SYSROOT": str(TREES / tree), "ORBITOP_PKG_MANAGER": manager}
    r = subprocess.run(["bash", SCRIPT, "--dry-run", *args],
                       env=env, capture_output=True, text=True, check=True)
    return r.stdout


def test_intel_plans_webkit_igt_without_setcap_by_default():  # F-2: cap_perfmon nur auf Wunsch
    out = dry_run("intel-laptop")
    assert "WOULD: apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 intel-gpu-tools" in out
    assert "setcap" not in out and "cap_perfmon" not in out
    assert "rapl" not in out.lower().replace("--allow-rapl", "")


def test_intel_allow_perfmon_warns_then_sets_capability():
    out = dry_run("intel-laptop", "--allow-perfmon")
    warning = ("WARNING: cap_perfmon lets every local account run /usr/bin/intel_gpu_top with GPU and package power "
               "counters (RAPL, CVE-2020-8694).")
    assert out.index(warning) < out.index("WOULD: setcap cap_perfmon=ep /usr/bin/intel_gpu_top")


def test_allow_perfmon_without_intel_gpu_does_nothing():
    out = dry_run("amd-desktop", "--allow-perfmon")
    assert "setcap" not in out and "nothing to do for --allow-perfmon" in out


def test_usage_names_every_option():
    r = subprocess.run(["bash", SCRIPT, "--bogus"], capture_output=True, text=True)
    assert "[--dry-run] [--allow-rapl] [--allow-perfmon]" in r.stderr
    assert "[--dry-run] [--allow-rapl] [--allow-perfmon]" in Path(SCRIPT).read_text().splitlines()[4]


def test_amd_default_no_rapl_rule():
    out = dry_run("amd-desktop")
    assert "intel-gpu-tools" not in out and "70-orbitop-rapl.rules" not in out


def test_amd_allow_rapl_plans_udev_rule_with_warning():
    out = dry_run("amd-desktop", "--allow-rapl")
    assert "/etc/udev/rules.d/70-orbitop-rapl.rules" in out and "CVE-2020-8694" in out
    assert out.index("CVE-2020-8694") < out.index("70-orbitop-rapl.rules")
    assert RULE in out.splitlines()
    assert "WOULD: udevadm control --reload" in out
    assert "WOULD: udevadm trigger --subsystem-match=powercap --action=add" in out


def test_arm_plans_only_webkit():
    out = dry_run("arm-board")
    assert "gir1.2-webkit-6.0" in out and "setcap" not in out and "rapl" not in out.lower()


def test_vm_plans_only_webkit():
    out = dry_run("vm")
    assert "gir1.2-webkit-6.0" in out and "setcap" not in out and "rapl" not in out.lower()


HELPER_LINES = ["WOULD: install -d -o root -g root -m 0755 /usr/local/libexec/orbitop",
                f"WOULD: install -o root -g root -m 0755 {ROOT}/orbitop/killhelper.py "
                "/usr/local/libexec/orbitop/killhelper.py"]


@pytest.mark.parametrize("manager", list(INSTALL))
def test_installs_runtime_packages_per_manager(manager):  # hält die Listen gleich mit app.PACKAGES
    line = f"WOULD: {INSTALL[manager]} {' '.join(app.PACKAGES[manager])}"
    assert line in dry_run("vm", manager=manager).splitlines()
    assert f"{line} {INTEL_TOOL[manager]}" in dry_run("intel-laptop", manager=manager).splitlines()


@pytest.mark.parametrize("manager", ["none", "rm -rf /"])
def test_unknown_manager_names_packages_and_still_installs_helper(manager):
    lines = dry_run("vm", manager=manager).splitlines()
    assert any("No supported package manager" in ln and "python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0" in ln
               and "README" in ln for ln in lines)
    assert lines[lines.index(HELPER_LINES[0]):][:2] == HELPER_LINES
    assert not any(ln.startswith(("WOULD: apt-get", "WOULD: dnf", "WOULD: pacman", "WOULD: zypper")) for ln in lines)


FIXED_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"  # PATH im Skript
FALLBACK = [m for m in INSTALL if shutil.which(m, path=FIXED_PATH)][:1]  # der erste installierte


def detected(tmp_path, text, where="etc"):
    """(Hinweis, Installzeilen) eines Probelaufs mit diesem os-release: Der Hinweis nennt den Paketmanager der
    Distribution, wenn er hier fehlt; die Installzeile den, der installieren würde."""
    (tmp_path / where).mkdir(parents=True)
    (tmp_path / where / "os-release").write_text(text)
    env = {k: v for k, v in os.environ.items() if k != "ORBITOP_PKG_MANAGER"}
    out = subprocess.run(["bash", SCRIPT, "--dry-run"], env={**env, "ORBITOP_SYSROOT": str(tmp_path)},
                         capture_output=True, text=True, check=True).stdout
    hint = re.search(r"^os-release names (\S+), but it is not installed", out, re.M)
    return (hint[1] if hint else None), [m for m, cmd in INSTALL.items() if f"WOULD: {cmd} " in out]


@pytest.mark.parametrize("text,where", [
    ("NAME=Ubuntu\nID=ubuntu\nID_LIKE=debian\n", "etc"),
    ("ID=debian\n", "etc"),
    ('ID="fedora"\n', "etc"),
    ("ID=arch\n", "usr/lib"),  # ohne /etc/os-release
    ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n', "etc"),
    ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', "etc"),
    ("ID=endeavouros\nID_LIKE=arch", "etc"),  # letzte Zeile ohne Zeilenende
    ("ID=rocky\nID_LIKE='rhel centos fedora'\n", "etc"),
    ('ID=sles\nID_LIKE="suse"\n', "etc"),
    ("ID_LIKE=debian\nID=arch\n", "etc"),  # ID vor ID_LIKE, egal in welcher Zeile
])
def test_manager_from_os_release_equals_app(tmp_path, text, where):  # Triage 8: dieselbe Zuordnung wie die App
    got = detected(tmp_path, text, where)
    want = app.package_manager(str(tmp_path))
    if shutil.which(want, path=FIXED_PATH):
        assert got == (None, [want])
    else:  # per command -v bestätigt: fehlt er, nennt ihn der Hinweis, und der erste gefundene installiert
        assert got == (want, FALLBACK)


@pytest.mark.parametrize("text", ["ID=nixos\n", "", "ID=*\nID_LIKE=*\n"])
def test_without_known_os_release_first_installed_manager(tmp_path, text):  # Rückfall wie vorher
    assert detected(tmp_path, text) == (None, FALLBACK)


@pytest.mark.parametrize("tree", ["intel-laptop", "amd-desktop", "arm-board", "vm"])
def test_installs_root_owned_helper_on_every_tree(tree):  # F-1: pkexec startet nur diese Kopie
    lines = dry_run(tree).splitlines()
    i = lines.index(HELPER_LINES[0])
    assert lines[i:i + 2] == HELPER_LINES
    assert any("run this script again" in ln and "killhelper.py" in ln for ln in lines)


def test_refuses_symlinked_helper_source(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "orbitop").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts")
    (tmp_path / "orbitop" / "killhelper.py").symlink_to(ROOT / "orbitop" / "killhelper.py")
    r = subprocess.run(["bash", str(tmp_path / "scripts" / "setup-privileges.sh"), "--dry-run"],
                       env={**os.environ, "ORBITOP_SYSROOT": str(TREES / "vm")}, capture_output=True, text=True)
    assert r.returncode == 1 and "refusing" in r.stderr and "WOULD:" not in r.stdout  # vor jeder Aktion


def test_refuses_without_root_and_without_dry_run():
    if os.geteuid() == 0:
        pytest.skip("running as root")
    r = subprocess.run(["bash", SCRIPT], capture_output=True, text=True)
    assert r.returncode != 0 and "root" in r.stderr


@pytest.mark.parametrize("args", [["--bogus"], [""], ["--dry-run", ""], ["--dry-run", "extra"]])
def test_bad_arguments_exit_2_without_actions(args):
    r = subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True)
    assert r.returncode == 2 and "WOULD:" not in r.stdout


def test_shellcheck_clean():
    assert subprocess.run(["shellcheck", str(ROOT / "scripts/setup-privileges.sh"),
                           str(ROOT / "scripts/capture-fixture.sh")]).returncode == 0


def test_capture_mount_filter_keeps_only_plain_mounts():
    lines = [
        "nas.local:/volume1 /data/nas nfs4 rw,relatime 0 0",
        "192.168.1.5:/export /srv/x nfs rw 0 0",
        "//host/share /srv/s cifs rw 0 0",
        "user@host:/path /srv/ssh fuse.sshfs rw 0 0",
        "/dev/loop3 /opt/app squashfs ro 0 0",
        "/dev/sdb1 /media/someone/stick vfat rw 0 0",
        "/dev/nvme0n1p2 / ext4 rw,relatime 0 0",
    ]
    r = subprocess.run(["bash", str(ROOT / "scripts" / "capture-fixture.sh"), "--filter-mounts"],
                       input="\n".join(lines) + "\n", capture_output=True, text=True, check=True)
    assert r.stdout == lines[-1] + "\n"
