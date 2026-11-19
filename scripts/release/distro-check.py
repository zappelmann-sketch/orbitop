#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""Writes the results of the container matrix into docs/distro-check.md (scripts/release.sh, step 3).

Usage: python3 -I distro-check.py DOC VERSION KEYRING-VERSION [--dry-run] < OUTPUT
OUTPUT is what scripts/check-distros.sh printed: "IMAGE <image>" before the log of each container, then the lines KEY
and RESULT. Only the part of DOC between START and END is replaced; every image must have passed. The containers
write the logs, so every line taken over must match its pattern in full, with values of a small character set."""
import re
import sys
from datetime import datetime, timezone

START = "<!-- matrix:start: scripts/release.sh writes this part from the output of scripts/check-distros.sh -->"
END = "<!-- matrix:end -->"
NAMES = {"debian": "Debian", "ubuntu": "Ubuntu", "fedora": "Fedora", "opensuse/tumbleweed": "openSUSE Tumbleweed",
         "archlinux": "Arch Linux"}
ROLLING = {"opensuse/tumbleweed", "archlinux"}  # their VERSION_ID is a snapshot, not part of the name
HEAD = ["| Distribution | Image | Digest | Packages | Tests | Result |", "|---|---|---|---|---|---|"]
SAFE = r"[0-9A-Za-z.+~:_-]+"  # versions, VERSION_ID
IMAGE = r"[a-z0-9][a-z0-9._/:-]*"  # as check-distros.sh accepts it
DIGEST = r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}"
# The lines taken over: a line that starts like one of them must match it in full.
LINES = {
    "key": (r"KEY ", r"KEY ([0-9A-F]{40})"),
    "result": (r"RESULT ", rf"RESULT ({IMAGE}) ({DIGEST}) pass (-|install)"),
    "version_id": (r"VERSION_ID=", rf'VERSION_ID="?({SAFE})"?'),
    "update": (r"VERSION before ", rf"VERSION before ({SAFE}), offered ({SAFE}), after ({SAFE})"),
    "versions": (r"VERSIONS ", rf"VERSIONS python ({SAFE}) pygobject ({SAFE}) gtk ({SAFE}) webkitgtk ({SAFE})"),
    "tests": (r"\d+ passed", r"(\d+ passed(?:, \d+ \w+)*) in [\d.]+s(?: \(\d+:\d{2}:\d{2}\))?"),  # pytest -q
    "refusal": (r"orbitop : Depends: python3 ",
                rf"orbitop : Depends: python3 \(>= 3\.12\) but ({SAFE}) is to be installed"),
}


def stop(message: str):
    sys.exit(f"distro-check.py: {message}")


def lines(kind: str, text: str, where: str) -> list[tuple[str, ...]]:
    """The groups of every line of TEXT of KIND; stops at a line that starts like KIND but does not match it."""
    head, pattern = LINES[kind]
    found = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(head, line):
            match = re.fullmatch(pattern, line)
            if not match:
                stop(f"{where}: unexpected line {line!r}")
            found.append(match.groups())
    return found


def last(kind: str, text: str, where: str) -> tuple[str, ...]:
    found = lines(kind, text, where)
    if not found:
        stop(f"{where}: no {kind} line in the output of check-distros.sh")
    return found[-1]


def logs(output: str) -> dict[str, str]:
    """The log of each image, by the line "IMAGE <image>" before it; an image may come once."""
    found, image = {}, None
    for line in output.splitlines():
        if line.startswith("IMAGE "):
            image = (re.fullmatch(rf"IMAGE ({IMAGE})", line) or stop(f"unexpected line {line!r}"))[1]
            if image in found:
                stop(f"{image} appears twice")
            found[image] = []
        elif image:
            found[image].append(line)
    return {image: "\n".join(text) for image, text in found.items()}


def row(image: str, digest: str, step: str, log: str, version: str) -> list[str]:
    """One line of the table; step "install" is the expected refusal of check-distros.sh."""
    family = image.split(":")[0]
    if family not in NAMES:
        stop(f"{image}: no distribution name known for it")
    name = NAMES[family] + ("" if family in ROLLING else " " + last("version_id", log, image)[0])
    cells = [name, f"`{image}`", f"`{digest}`"]
    if step == "install":
        (python,) = last("refusal", log, image)
        return [*cells, f"`orbitop {version}-1` refused", "–",
                f'pass (expected refusal): step `install`, "orbitop : Depends: python3 (>= 3.12) but {python} is to'
                ' be installed"']
    before, _, after = last("update", log, image)
    python, gi, gtk, webkit = last("versions", log, image)
    (tests,) = last("tests", log, image)
    return [*cells, f"`orbitop {before}` → `{after}`: Python {python}, PyGObject {gi}, GTK {gtk}, WebKitGTK {webkit}",
            tests, "pass"]


def block(output: str, version: str, keyring: str, dry: bool) -> str:
    by_image = logs(output)
    results = lines("result", output, "RESULT")
    if not results or len({r[0] for r in results}) != len(results) or set(by_image) != {r[0] for r in results}:
        stop("the RESULT lines must name each image of the run once")
    keys = {k for (k,) in lines("key", output, "KEY")}
    if len(keys) != 1:
        stop("the output of check-distros.sh must name exactly one KEY")
    day = datetime.now(timezone.utc).date().isoformat()
    signer = ("the key of `ORBITOP_KEY`; a dry run may sign with a throwaway key instead of the archive key" if dry
              else "the archive key, whose fingerprint is in the README")
    rows = [row(image, digest, step, by_image[image], version) for image, digest, step in results]
    return "\n".join([
        START,
        f"- Run: `scripts/release.sh {version}{' --dry-run' if dry else ''}` on {day}, `KEY {keys.pop()}`, {signer}.",
        f"- `SITE`: orbitop `{version}-1`, `orbitop-apt-source` and `orbitop-release` `{keyring}`. `SITE2`: the check"
        f" build (Debian `{version}-1+check1`, RPM `{version}-1.check1`, Arch `{version}-1.1`; plan K6).",
        "", *HEAD, *("| " + " | ".join(r) + " |" for r in rows), END])


def main() -> None:
    doc, version, keyring, *dry = sys.argv[1:]
    if dry not in ([], ["--dry-run"]) or not re.fullmatch(SAFE, version) or not re.fullmatch(SAFE, keyring):
        sys.exit(__doc__)
    with open(doc, encoding="utf-8") as f:
        text = f.read()
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        stop(f"{doc} needs the markers {START} and {END}, once each")
    head, rest = text.split(START)
    new = head + block(sys.stdin.read(), version, keyring, bool(dry)) + rest.split(END)[1]
    with open(doc, "w", encoding="utf-8") as f:
        f.write(new)


if __name__ == "__main__":
    main()
