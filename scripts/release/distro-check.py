#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Writes the results of the container matrix into docs/distro-check.md (scripts/release.sh, step 3).

Usage: python3 -I distro-check.py DOC VERSION KEYRING-VERSION [--dry-run] < OUTPUT
OUTPUT is what scripts/check-distros.sh printed: "IMAGE <image>" before the log of each container, then the lines KEY
and RESULT. Only the part of DOC between START and END is replaced; every image must have passed."""
import re
import sys
from datetime import datetime, timezone

START = "<!-- matrix:start: scripts/release.sh writes this part from the output of scripts/check-distros.sh -->"
END = "<!-- matrix:end -->"
NAMES = {"debian": "Debian", "ubuntu": "Ubuntu", "fedora": "Fedora", "opensuse/tumbleweed": "openSUSE Tumbleweed",
         "archlinux": "Arch Linux"}
ROLLING = {"opensuse/tumbleweed", "archlinux"}  # their VERSION_ID is a snapshot, not part of the name
HEAD = ["| Distribution | Image | Digest | Packages | Tests | Result |", "|---|---|---|---|---|---|"]


def field(pattern: str, text: str, where: str):
    """The groups of the last line of TEXT that matches PATTERN; stops if there is none."""
    found = re.findall(pattern, text, re.M)
    if not found:
        sys.exit(f"distro-check.py: {where}: no line {pattern!r} in the output of check-distros.sh")
    return found[-1]


def row(image: str, digest: str, step: str, log: str, version: str) -> list[str]:
    """One line of the table; step "install" is the expected refusal of check-distros.sh."""
    family = image.split(":")[0]
    name = NAMES.get(family) or field(r'^PRETTY_NAME="?([^"\n]*)"?$', log, image)
    if family in NAMES and family not in ROLLING:
        name += " " + field(r'^VERSION_ID="?([^"\n]*)"?$', log, image)
    cells = [name, f"`{image}`", f"`{digest}`"]
    if step == "install":
        refusal = field(r"^\s*(orbitop : Depends: python3 \(>= 3\.12\).*?)\s*$", log, image)
        return [*cells, f"`orbitop {version}-1` refused", "–",
                f'pass (expected refusal): step `install`, "{refusal}"']
    before, _, after = field(r"^VERSION before (\S+), offered (\S+), after (\S+)$", log, image)
    python, gi, gtk, webkit = field(r"^VERSIONS python (\S+) pygobject (\S+) gtk (\S+) webkitgtk (\S+)$", log, image)
    tests = field(r"^(\d+ passed[^\n]*?) in [\d.]+s", log, image)
    return [*cells, f"`orbitop {before}` → `{after}`: Python {python}, PyGObject {gi}, GTK {gtk}, WebKitGTK {webkit}",
            tests, "pass"]


def block(output: str, version: str, keyring: str, dry: bool) -> str:
    parts = re.split(r"^IMAGE (\S+)\n", output, flags=re.M)[1:]  # [image, its log, image, its log, …]
    logs = dict(zip(parts[::2], parts[1::2]))
    results = re.findall(r"^RESULT (\S+) (\S+) (\S+) (\S+)$", output, re.M)
    if not results or set(logs) != {r[0] for r in results} or any(r[2] != "pass" for r in results):
        sys.exit("distro-check.py: the output of check-distros.sh lacks an image, or an image did not pass")
    key = field(r"^KEY ([0-9A-F]{40})$", output, "KEY")
    day = datetime.now(timezone.utc).date().isoformat()
    signer = ("the key of `ORBITOP_KEY`; a dry run may sign with a throwaway key instead of the archive key" if dry
              else "the archive key, whose fingerprint is in the README")
    rows = [row(image, digest, step, logs[image], version) for image, digest, _, step in results]
    return "\n".join([
        START,
        f"- Run: `scripts/release.sh {version}{' --dry-run' if dry else ''}` on {day}, `KEY {key}`, {signer}.",
        f"- `SITE`: orbitop `{version}-1`, `orbitop-apt-source` and `orbitop-release` `{keyring}`. `SITE2`: the check"
        f" build (Debian `{version}-1+check1`, RPM `{version}-1.check1`, Arch `{version}-1.1`; plan K6).",
        "", *HEAD, *("| " + " | ".join(r) + " |" for r in rows), END])


def main() -> None:
    doc, version, keyring, *dry = sys.argv[1:]
    if dry not in ([], ["--dry-run"]):
        sys.exit(__doc__)
    with open(doc, encoding="utf-8") as f:
        text = f.read()
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        sys.exit(f"distro-check.py: {doc} needs the markers {START} and {END}, once each")
    head, rest = text.split(START)
    new = head + block(sys.stdin.read(), version, keyring, bool(dry)) + rest.split(END)[1]
    with open(doc, "w", encoding="utf-8") as f:
        f.write(new)


if __name__ == "__main__":
    main()
