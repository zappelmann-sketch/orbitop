# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Gemeinsames der counterhelper-Tests: TreeOS, die OS-Schicht des Helfers unter einem Testbaum, und der Baum selbst.

Echt sind Dateien, O_NOFOLLOW, O_EXCL, dir_fd, fchmod, flock und glob. Gefälscht sind nur root (euid und uid 0 für
jede Datei, außer OWNERS sagt anderes), der User-Namespace, security.capability (als root schriebe das CAP_SETFCAP)
und die Uhr. Kein Aufruf erreicht die echten /etc, /usr oder /sys."""
import errno
import fcntl
import glob
import os
import shutil

from orbitop import counterhelper
from tests.roots import ROOTS

INIT_MAP = "         0          0 4294967295\n"  # so formatiert der Kernel /proc/self/uid_map
WRITES = ("create", "unlink", "setxattr", "removexattr", "fchmod")
ZONES = ("intel-rapl:0", "intel-rapl:0:0", "intel-rapl:1")


class TreeOS:
    """Gleiche Namen wie counterhelper.RealOS. log hält jeden ändernden Aufruf und jedes fsync in Reihenfolge, als
    (Aufruf, logischer Pfad[, Wert]); fail: Aufruf oder (Aufruf, Pfad) -> errno, den der Aufruf dann wirft.
    at hält je open, stat und unlink (Aufruf, Name wie übergeben, logischer Pfad des dir_fd oder None)."""

    def __init__(self, root, euid=0, uid_map=INIT_MAP):
        self.root, self.euid, self.map = str(root), euid, uid_map
        self.owners, self.xattrs, self.fail = {}, {}, {}
        self.log, self.opens, self.sleeps, self.at = [], [], [], []
        self.paths = {}  # fd -> logischer Pfad
        self.mask, self.now = None, 0.0

    def writes(self):
        return [e for e in self.log if e[0] in WRITES]

    def _check(self, call, path):
        err = self.fail.get((call, path), self.fail.get(call))
        if err is not None:
            raise OSError(err, os.strerror(err), path)

    def _owned(self, st, path):
        fields = list(st[:10])
        fields[4] = self.owners.get(path, 0)
        return os.stat_result(fields)

    def _at(self, call, name, dir_fd):
        """Logischer Pfad; ohne dir_fd liegt name immer unter dem Testbaum, nie im echten /etc."""
        self.at.append((call, name, None if dir_fd is None else self.paths[dir_fd]))
        if dir_fd is None:
            return name, self.root + name
        return f"{self.paths[dir_fd]}/{name}", name

    def geteuid(self):
        return self.euid

    def umask(self, mask):
        self.mask = mask
        return 0o022

    def uid_map(self):
        self._check("uid_map", "/proc/self/uid_map")
        return self.map

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        logical, real = self._at("open", path, dir_fd)
        self._check("open", logical)
        self.opens.append((logical, flags))
        fd = os.open(real, flags, mode, dir_fd=dir_fd)
        self.paths[fd] = logical
        if flags & os.O_CREAT:
            self.log.append(("create", logical, mode))
        return fd

    def close(self, fd):
        path = self.paths.pop(fd)
        os.close(fd)
        self._check("close", path)

    def fstat(self, fd):
        self._check("fstat", self.paths[fd])
        return self._owned(os.fstat(fd), self.paths[fd])

    def lstat(self, path):
        self._check("lstat", path)
        return self._owned(os.lstat(self.root + path), path)

    def stat(self, name, *, dir_fd=None, follow_symlinks=True):
        logical, real = self._at("stat", name, dir_fd)
        self._check("stat", logical)
        return self._owned(os.stat(real, dir_fd=dir_fd, follow_symlinks=follow_symlinks), logical)

    def fsync(self, fd):
        self._check("fsync", self.paths[fd])
        os.fsync(fd)
        self.log.append(("fsync", self.paths[fd]))

    def unlink(self, name, *, dir_fd=None):
        logical, real = self._at("unlink", name, dir_fd)
        self._check("unlink", logical)
        os.unlink(real, dir_fd=dir_fd)
        self.log.append(("unlink", logical))

    def setxattr(self, fd, name, value):
        self._check("setxattr", self.paths[fd])
        self.xattrs.setdefault(self.paths[fd], {})[name] = value
        self.log.append(("setxattr", self.paths[fd], value))

    def removexattr(self, fd, name):
        path = self.paths[fd]
        self._check("removexattr", path)
        if name not in self.xattrs.get(path, {}):
            raise OSError(errno.ENODATA, os.strerror(errno.ENODATA), path)
        del self.xattrs[path][name]
        self.log.append(("removexattr", path))

    def fchmod(self, fd, mode):
        self._check("fchmod", self.paths[fd])
        os.fchmod(fd, mode)
        self.log.append(("fchmod", self.paths[fd], mode))

    def flock(self, fd, op):
        self._check("flock", self.paths[fd])
        fcntl.flock(fd, op)

    def glob(self, pattern):
        self._check("glob", pattern)
        return [p[len(self.root):] for p in glob.glob(glob.escape(self.root) + pattern)]

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make_tree(root, zones=ZONES, powercap=None):
    """Ein Rechner wie nach der Installation: /etc/orbitop leer und 0711 wie aus dem Paket, /usr/bin/intel_gpu_top
    (0755), energy_uj der zones mit 0400 wie im Kernel; powercap: stattdessen eine Kopie des powercap-Ordners eines
    Baums aus tests/fixtures."""
    for d in ("etc/orbitop", "usr/bin"):
        os.makedirs(root / d)
    (root / "usr/bin/intel_gpu_top").write_bytes(b"\x7fELF\x02\x01\x01\x00")
    cap = root / "sys/class/powercap"
    if powercap:  # die Bäume wurden ohne root aufgenommen, ohne energy_uj (0400): wie im Kernel ergänzt
        shutil.copytree(os.path.join(ROOTS, powercap, "sys/class/powercap"), cap)
        zones = os.listdir(cap)
    for z in zones:
        os.makedirs(cap / z, exist_ok=True)
        (cap / z / "energy_uj").write_text("1\n")
    for dirpath, dirs, files in os.walk(root):  # ohne Rücksicht auf die umask des Testlaufs
        for d in dirs:
            os.chmod(os.path.join(dirpath, d), 0o755)
        for f in files:
            os.chmod(os.path.join(dirpath, f), {"energy_uj": 0o400, "intel_gpu_top": 0o755}.get(f, 0o444))
    os.chmod(root / "etc/orbitop", 0o711)
    return TreeOS(root)


def modes(root):
    """Modus je energy_uj unter /sys/class/powercap, nach Zone."""
    cap = root / "sys/class/powercap"
    return {z: os.stat(cap / z / "energy_uj").st_mode & 0o7777 for z in sorted(os.listdir(cap))
            if os.path.exists(cap / z / "energy_uj")}


def marker(root):
    return root / counterhelper.MARKER.lstrip("/")
