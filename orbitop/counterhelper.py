#!/usr/bin/python3 -IS
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Root-Helfer der Zählerfreigabe: counterhelper on|off|sync (Security-Dokument 0.3.0, B2.1 bis B2.3).

on und off startet pkexec, je über eine eigene polkit-Action (exec.argv1); sync rufen nur die Paket-Skripte, und es
gibt nur frei, was die Merkdatei verlangt. Er nimmt keine Pfade, liest keine Umgebung und startet kein Programm.
Er schreibt nur die Merkdatei, security.capability an TOOL und die Lesebits g+r, o+r an energy_uj der Zonen
intel-rapl:*. Läuft unter python3 -IS: nur Standardbibliothek, nie orbitop.*.
Exit-Codes: 0 alles wie verlangt, 1 unerwartet oder Lock besetzt, 2 Aufruf ungültig oder nicht root, 3 Ort oder
Umgebung unsicher, 4 teilweise (ein Teil scheiterte mit OSError). Nie 126 oder 127: die meldet pkexec selbst."""
import errno
import fcntl
import glob
import os
import stat
import struct
import sys
import time

OK, FAILED, INVALID, UNSAFE, PARTIAL = 0, 1, 2, 3, 4
WORDS = ("on", "off", "sync")
MARKER = "/etc/orbitop/counters-released"  # die Regel für den ganzen Rechner; die udev-Regel prüft sie beim Start
TOOL = "/usr/bin/intel_gpu_top"
RAPL = "/sys/class/powercap/intel-rapl:*/energy_uj"  # genau die Zonen, die sensors.RaplReader liest, ohne MMIO
CAP = struct.pack("<5I", 0x02000001, 0, 0, 1 << (38 - 32), 0)  # cap_perfmon=ep, dieselben Bytes wie setcap (P1)
INIT_USERNS = "0 0 4294967295"
LOCK_WAIT, LOCK_STEP = 10.0, 0.2
_DIR, _NAME = os.path.split(MARKER)
_MESSAGES = {FAILED: "unexpected error, or another counterhelper holds the lock",
             INVALID: "usage: counterhelper on|off|sync, as root",
             UNSAFE: "unsafe place or environment (/etc/orbitop, /usr/bin or a user namespace)",
             PARTIAL: "applied in part: a step failed with an OS error"}


class RealOS:
    """Die Systemaufrufe des Helfers. Die Tests setzen eine Schicht mit denselben Namen ein."""
    geteuid = staticmethod(os.geteuid)
    umask = staticmethod(os.umask)
    open = staticmethod(os.open)
    close = staticmethod(os.close)
    fstat = staticmethod(os.fstat)
    lstat = staticmethod(os.lstat)
    stat = staticmethod(os.stat)
    fsync = staticmethod(os.fsync)
    unlink = staticmethod(os.unlink)
    setxattr = staticmethod(os.setxattr)
    removexattr = staticmethod(os.removexattr)
    fchmod = staticmethod(os.fchmod)
    flock = staticmethod(fcntl.flock)
    glob = staticmethod(glob.glob)
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)

    @staticmethod
    def uid_map() -> str:
        with open("/proc/self/uid_map", encoding="ascii") as f:
            return f.read()


def _safe(st, kind) -> bool:
    return kind(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022


def _chain(path: str, osl) -> bool:
    """Wie actions.trusted: path und jedes Glied darüber bis / gehören root und sind für Gruppe und andere nicht
    beschreibbar; ein Symlink hat 0777 und fällt heraus."""
    try:
        while True:
            st = osl.lstat(path)
            if st.st_uid != 0 or st.st_mode & 0o022:
                return False
            if path == "/":
                return True
            path = os.path.dirname(path)
    except OSError:
        return False


def _init_userns(osl) -> bool:
    try:
        return " ".join(osl.uid_map().split()) == INIT_USERNS
    except OSError:
        return False


def _open_dir(osl):
    """fd von /etc/orbitop, wenn es ein root-eigenes, nicht g/o-beschreibbares Verzeichnis in ebensolcher Kette ist;
    sonst None."""
    try:
        fd = osl.open(_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        if _safe(osl.fstat(fd), stat.S_ISDIR) and _chain(_DIR, osl):
            return fd
    except OSError:
        pass
    osl.close(fd)
    return None


def _lock(fd, osl) -> bool:
    """Exklusives flock am Verzeichnis, alle LOCK_STEP Sekunden versucht, höchstens LOCK_WAIT lang (R1.5, R1.8)."""
    end = osl.monotonic() + LOCK_WAIT
    while True:
        try:
            osl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if osl.monotonic() >= end:
                return False
            osl.sleep(LOCK_STEP)


def _perfmon(on: bool, osl) -> int:
    """cap_perfmon=ep an TOOL setzen oder nehmen, nur am fd und nur nach der Kettenprüfung (R1.2, R4.1, R4.6)."""
    try:
        fd = osl.open(TOOL, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return OK  # nicht installiert: nichts freizugeben
    except OSError:
        return PARTIAL  # ELOOP: ein Symlink an diesem Pfad wird nie behandelt
    try:
        st = osl.fstat(fd)
        if not (_safe(st, stat.S_ISREG) and st.st_nlink == 1 and _chain(os.path.dirname(TOOL), osl)):
            return UNSAFE
        if on:
            osl.setxattr(fd, "security.capability", CAP)
        else:
            try:
                osl.removexattr(fd, "security.capability")
            except OSError as e:
                if e.errno != errno.ENODATA:
                    raise
        return OK
    except OSError:
        return PARTIAL
    finally:
        osl.close(fd)


def _rapl(on: bool, osl) -> int:
    """go+r an energy_uj jeder Zone intel-rapl:*, oder zurück auf die Bits des Besitzers (S_IMODE & 0o600, R3.3)."""
    code = OK
    for path in sorted(osl.glob(RAPL)):
        try:
            fd = osl.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError:
            code = PARTIAL
            continue
        try:
            st = osl.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                code = max(code, UNSAFE)
                continue
            mode = stat.S_IMODE(st.st_mode)
            osl.fchmod(fd, mode | 0o044 if on else mode & 0o600)
        except OSError:
            code = PARTIAL
        finally:
            osl.close(fd)
    return code


def apply(on: bool, osl) -> int:
    """Beide Teile, auch wenn einer scheitert; es zählt der höchste Code."""
    return max(_perfmon(on, osl), _rapl(on, osl))


def _on(dirfd, osl) -> int:
    try:
        fd = osl.open(_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644,
                      dir_fd=dirfd)
    except FileExistsError:
        pass
    else:
        try:
            osl.fsync(fd)
        finally:
            osl.close(fd)
    osl.fsync(dirfd)
    return apply(True, osl)


def _off(dirfd, osl) -> int:
    """Zuerst die Merkdatei, dauerhaft, dann die Wirkungen: sonst setzte ein Auslöser nach einem Absturz neu (R1.4)."""
    code = OK
    try:
        try:
            osl.unlink(_NAME, dir_fd=dirfd)
        except FileNotFoundError:
            pass
        osl.fsync(dirfd)
    except OSError:
        code = PARTIAL  # die Wirkungen fallen trotzdem weg
    return max(code, apply(False, osl))


def _sync(dirfd, osl) -> int:
    """Nur mit Merkdatei (reguläre Datei von root) wird angewendet; sync nimmt nie etwas zurück (E4)."""
    try:
        st = osl.stat(_NAME, dir_fd=dirfd, follow_symlinks=False)
    except FileNotFoundError:
        return OK
    return apply(True, osl) if stat.S_ISREG(st.st_mode) and st.st_uid == 0 else OK


def _run(word: str, osl) -> int:
    if word != "off" and not _init_userns(osl):
        return UNSAFE if word == "on" else OK  # eine Fähigkeit aus einem User-Namespace wirkt auf dem Host nicht
    dirfd = _open_dir(osl)
    if dirfd is None:
        return max(UNSAFE, apply(False, osl)) if word == "off" else UNSAFE
    try:
        if not _lock(dirfd, osl):
            return FAILED
        return {"on": _on, "off": _off, "sync": _sync}[word](dirfd, osl)
    finally:
        osl.close(dirfd)


def main(argv: list[str], osl=RealOS()) -> int:
    if len(argv) != 1 or argv[0] not in WORDS or osl.geteuid() != 0:
        return INVALID
    osl.umask(0o022)
    try:
        return _run(argv[0], osl)
    except OSError:
        return FAILED


if __name__ == "__main__":
    code = main(sys.argv[1:])
    if code:
        print(f"counterhelper: {_MESSAGES[code]}", file=sys.stderr)
    sys.exit(code)
