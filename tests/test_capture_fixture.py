# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""scripts/capture-fixture.sh, das den Testbaum intel-laptop aufnimmt."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "capture-fixture.sh"


def test_shellcheck_clean():
    assert subprocess.run(["shellcheck", str(SCRIPT)]).returncode == 0


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
    r = subprocess.run(["bash", str(SCRIPT), "--filter-mounts"],
                       input="\n".join(lines) + "\n", capture_output=True, text=True, check=True)
    assert r.stdout == lines[-1] + "\n"
