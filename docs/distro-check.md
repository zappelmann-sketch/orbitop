# Distribution check

The setup and the test suite of orbitop, run for real in disposable Docker containers with
[`scripts/check-distros.sh`](../scripts/check-distros.sh). Only the distributions marked `pass` are supported.

- Date: 2026-11-18. The five supported images ran a second time that day, after `setup-privileges.sh` started to pick
  the package manager from os-release: same digests, same versions, all `pass` (openSUSE only on a further run after commit a568c23, see below). Debian 12 and Ubuntu 22.04 are from
  the first run. Ubuntu 26.04 was added later that day and ran once.
- Docker: 29.9.3 (x86_64 host with an Intel GPU)
- Each image runs once as
  `docker run --rm -v <copy>:/src:ro <image> bash /src/scripts/check-distros.sh --inside`:
  no `--privileged`, no added capabilities, no other mounts, and `setup-privileges.sh` without `--allow-*` options.
  `<copy>` is a temporary copy of the files tracked by git (in a release tree: of the whole tree), removed afterwards.
- Steps inside the container:
  1. `refresh`: refresh the package index (`apt-get update`, `pacman -Syu --noconfirm`; dnf and zypper refresh on their own).
  2. `setup`: `bash scripts/setup-privileges.sh` as root, without options.
  3. `import`: import GTK 4 and WebKitGTK 6.0 through PyGObject.
  4. `tools`: install pytest, ShellCheck, desktop-file-utils and AppStream.
  5. `pytest`: `python3 -m pytest -q` as an ordinary user on a copy of the repository.
     The browser tests skip themselves (no Chrome in the images), and so do the tests that need a display or the
     reference machine's GPU.
  6. `dry-run`: `bash scripts/setup-privileges.sh --dry-run` as that user.
  7. `version`: `python3 bin/orbitop --version`.

| Distribution | Image | Digest | Date | Packages | Result |
|---|---|---|---|---|---|
| Ubuntu 26.04 | `ubuntu:26.04` | `ubuntu@sha256:d66b366dac61b575bee2aef07e9c26e8070096fbe84a3d4d3eb0da069b5d76db` | 2026-11-18 | `python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 intel-gpu-tools`: Python 3.14.4, PyGObject 3.56.2, GTK 4.22.4, WebKitGTK 2.52.6 | pass |
| Ubuntu 24.04 | `ubuntu:24.04` | `ubuntu@sha256:73b999393d07f2bf65a40373778a44dc9a6d54ad7718d29247d8ff9413c4d6a8` | 2026-11-18 | `python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 intel-gpu-tools`: Python 3.12.3, PyGObject 3.48.2, GTK 4.14.5, WebKitGTK 2.52.6 | pass |
| Debian 13 | `debian:trixie` | `debian@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6` | 2026-11-18 | `python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 intel-gpu-tools`: Python 3.13.5, PyGObject 3.50.0, GTK 4.18.6, WebKitGTK 2.54.0 | pass |
| Fedora 45 | `fedora:latest` | `fedora@sha256:a7d72ba2745b100a3351087472e5ee7b2450af7cf331e7673007e3817612839c` | 2026-11-18 | `python3-gobject gtk4 webkitgtk6.0 igt-gpu-tools`: Python 3.15.2, PyGObject 3.58.1, GTK 4.24.1, WebKitGTK 2.54.2 | pass |
| Arch Linux | `archlinux:latest` | `archlinux@sha256:d4594bb2300cba11f41c2f27923eb56f63d9988909c402f9c95517d1e362c899` | 2026-11-18 | `python-gobject gtk4 webkitgtk-6.0 intel-gpu-tools`: Python 3.14.10, PyGObject 3.58.1, GTK 4.24.1, WebKitGTK 2.54.2 | pass |
| openSUSE Tumbleweed | `opensuse/tumbleweed` | `opensuse/tumbleweed@sha256:e313db943628a15807fe9f774dc6a388d63e9e35c5b81a399cdf67b8db64b986` | 2026-11-18 | `python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-WebKit-6_0 python3-gobject-Gdk igt-gpu-tools`: Python 3.13.16, PyGObject 3.58.1, GTK 4.24.1, WebKitGTK 2.54.2 | pass |
| Debian 12 | `debian:bookworm` | `debian@sha256:268fb24c39bca92d326dd83ea3abebe4a3f7751c804ffef23bb6d857dd343ff8` | 2026-11-18 | `python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 intel-gpu-tools`: Python 3.11.2, PyGObject 3.42.2, GTK 4.8.3, WebKitGTK 2.50.6 | fail (expected): step `pytest`, "orbitop needs Python 3.12 or newer, found 3.11.2." |
| Ubuntu 22.04 | `ubuntu:22.04` | `ubuntu@sha256:9abcaffc92a5279fff3a6a41635c0800ea33e528425fb389658806476e7defde` | 2026-11-18 | `python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 intel-gpu-tools`: Python 3.10.12, PyGObject 3.42.1, GTK 4.6.9, WebKitGTK 2.50.4 | fail (expected): step `pytest`, "orbitop needs Python 3.12 or newer, found 3.10.12." |

`Packages` is the install line of `setup-privileges.sh` on that distribution, followed by the versions the `import`
step reported.

## Notes

- **Intel tools everywhere:** a container sees the host's `/sys`, so `setup-privileges.sh` found the host's Intel GPU
  and added the Intel GPU tools on every distribution. Every name resolved, and each install ran in one transaction.
  On a machine without an Intel GPU the line ends before the tools.
- **Ubuntu 26.04:** `ubuntu:26.04` was Ubuntu 26.04.1 LTS (`VERSION_ID="26.04"`).
- **Ubuntu 24.04:** GLib 2.80 has a `GLibUnix` namespace without `signal_add`. orbitop falls back to
  `GLib.unix_signal_add` there; this check found the case. A test now calls the fallback for real and passes there
  (GLib 2.80.0).
- **Debian 13:** `debian:trixie` was Debian 13 (`VERSION_ID="13"`).
- **Fedora:** `fedora:latest` was Fedora 45 (`VERSION_ID=45`) with Python 3.15. The image lacks `runuser`, so the
  `tools` step also installs `util-linux` there.
- **Arch Linux:** the image was built on 2026-11-08 (`VERSION_ID=20261108.0.623074`); `pacman -Syu` brought it up to
  date first.
- **openSUSE Tumbleweed:** snapshot `VERSION_ID="20261116"`. zypper resolves `python3-gobject`,
  `python3-gobject-Gdk` and `igt-gpu-tools` as capabilities and installs `python313-gobject`,
  `python313-gobject-Gdk` and `intel-gpu-tools`. The image has no `find`. In the second run a test's Docker stand-in
  still listed files with it and failed there; it uses `tar` now, and the image passed when run once more.
- **Debian 12 and Ubuntu 22.04 are not supported.** Both ship WebKitGTK 6.0, so `setup` and `import` pass, but their
  Python is older than 3.12. orbitop then refuses to start with the message in the table (seven tests of the runtime
  check fail with it, and the app shell tests skip themselves).
- **Not covered:** the window itself (no display in the containers), the kill helper through `pkexec`, and the
  `--allow-rapl` and `--allow-perfmon` options.
