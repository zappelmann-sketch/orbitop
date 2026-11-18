# orbitop

[Deutsch](README.de.md)

A system monitor for Linux that shows what the machine is doing under load, and why.

## What orbitop is for

orbitop shows CPU, GPU, memory, power, temperatures, fans, network and storage as live charts over the last 5 minutes. Its process list tells you which process causes the load and whether that process is working, waiting, busy without any sign of life, or stuck in the kernel. If a process hangs, you can terminate it from the list, always after a confirmation.

orbitop is a GTK 4 window with a WebKitGTK 6.0 view, written in Python with the standard library and PyGObject only. It runs on any hardware: a sensor that is missing is listed as "not available" instead of causing an error. The interface is in English and German and follows the system language.

**Status:** version 0.1.0. orbitop runs from the unpacked release archive or from a checkout of this repository. There is no `.deb`, `.rpm`, AUR or Flatpak package and no update channel yet.

## Features

### Overview tab

- One tile each for CPU, every GPU, memory, power, temperatures, fans, network and storage, with a chart of the last 5 minutes at one value per second. The CPU tile adds a small chart per thread.
- A strip at the top names the three processes with the highest CPU load and the one with the most RAM. A click on it opens the process tab.
- Sensors the machine does not have are listed at the bottom under "Not available".

### Process tab

- Columns PID, Process, User, CPU, Last 60 s, RAM, I/O and State. The `top` columns PR, NI, VIRT, SHR, S, %MEM and TIME+ are available too and hidden by default.
- A right-click on a column header opens the column menu: show or hide columns, move a column left or right, restore the defaults. On the keyboard, the Menu key or Shift+F10 on a header opens the same menu.
- Drag a header to move the column, drag its right edge to change the width (Alt+Left and Alt+Right on the keyboard). If the columns are wider than the list, the list scrolls sideways.
- A divider between the list and the details can be dragged, or moved with the arrow keys.
- Column order, hidden columns, widths and the divider position are saved in `~/.config/orbitop/layout.json` (under `$XDG_CONFIG_HOME` if that is set) and survive a restart.
- Search in names and arguments, filters "All", "Mine only" and "Flagged" (every state except working and waiting). A click on a header sorts by that column.
- The details of the selected process show its command line, its CPU history over 5 minutes, RAM, read and write rate, threads, context switches, parent process and start time.

### Process states are a hint, not a verdict

The process tab classifies each process: working, waiting, constant load, stopped, zombie, stuck in kernel. This is a heuristic from `/proc`, and orbitop says so. "Constant load, no I/O" means at least 90 % of one core for two minutes, at most one voluntary context switch per second and no I/O bytes; from the outside this looks the same as a long computation. "Stuck in kernel" means state D for more than 10 s without progress (no CPU time and no I/O in between). Even "Kill now" only takes effect once the kernel releases such a process.

### Terminating processes

- "Terminate" sends SIGTERM and checks 5 s later whether the process still runs. If it does, "Kill now" (SIGKILL) is highlighted. Both ask for confirmation first.
- Right before the signal, orbitop checks PID and start time again, so a reused PID never hits a different process.
- Your own processes get the signal directly. Processes of other users are terminated only through `pkexec` and the root-owned helper that `setup-privileges.sh` installs. PID 1 and kernel threads cannot be terminated.

Closing the window only hides it. orbitop keeps reading the process list in the background, so the states are already known when you open the window again. Ctrl+Q or "Quit orbitop" in the About dialog ends it.

## Screenshots

![Overview tab](docs/screenshot-overview.png)

![Process tab](docs/screenshot-procs.png)

Both screenshots show demo data from `tests/ui/demo.html`, not a live system. Process names, command lines and users are anonymized; hardware names (CPU, interfaces, disks, sensors) come from the reference laptop. The demo page shows the German interface.

## Tech stack

### Language and libraries

- Python 3.12 or newer, standard library only, plus PyGObject for GTK 4 and WebKitGTK 6.0. No psutil: orbitop reads `/proc` and `/sys` itself.
- The interface is HTML, CSS and plain JavaScript in `orbitop/ui/`, without frameworks. `chart.js` draws the charts on a canvas.
- Fonts Orbitron and Oxanium are bundled. All visible texts come from `orbitop/locale/en.json` and `orbitop/locale/de.json`.

### Interface

- A GTK 4 window holds a single WebKitGTK 6.0 view. The page loads from orbitop's own URI scheme `orbitop://ui/`, never from `file://`. The scheme handler serves only regular files of known types below `orbitop/ui/`.
- Content Security Policy: `default-src 'none'`, scripts, styles and fonts only from the page itself, `connect-src 'none'`. The page has no network access.
- The view uses an ephemeral network session and writes nothing to disk. It navigates only to orbitop's own pages; new windows and downloads are refused.
- While the window is visible, Python sends one JSON snapshot per second to `window.orbitop.receive`. Python sends base units; the page formats them with `Intl.NumberFormat`.

### Data sources

- `/proc`: `stat`, `meminfo`, `cpuinfo`, `diskstats`, `net/dev`, `mounts`, and per process `stat`, `status`, `statm`, `io` and `cmdline`.
- `/sys`: CPU frequencies, block devices, network interfaces, thermal zones, batteries, `devfreq` and the DRM cards (GPU load, clock, video memory).
- hwmon (`/sys/class/hwmon`): temperatures, fans and power readings.
- powercap (`/sys/class/powercap/intel-rapl:*`): CPU package power from the RAPL energy counters, if they are readable.
- DRM fdinfo (`/proc/<pid>/fdinfo`): GPU use of your own processes.
- `intel_gpu_top` (optional): Intel GPU load of all processes and the package power.
- `nvidia-smi` (optional): load, memory, temperature, power and clock of NVIDIA GPUs.

### Threads and timing

- `orbitop-worker`: reads the system values every 1 s and builds the snapshot.
- `orbitop-procs`: reads the process list every 2 s, also while the window is hidden. Reading `/proc/<pid>/cmdline` can block (for example on a hung FUSE or NFS mount); then only the process list waits, the tiles keep running.
- Tools: `intel_gpu_top` and `nvidia-smi` run as long-lived child processes, each read by its own thread. `intel_gpu_top` reports every 2 s, `nvidia-smi` every 1 s.
- Slow hwmon chips (`dell_smm`, where every read is a BIOS call) are read at most every 5 s.
- `/proc/<pid>/status` (owner, context switches) is read every 10 s per process. The selected process and processes at 90 % of one core or more are read on every process tick.
- The GTK main thread only runs the window and the view; the worker hands over the finished JSON through `GLib.idle_add`.

### Security model

- The page talks to Python only through `parse_message` in `orbitop/app.py`. It accepts the messages `ready`, `view`, `layout`, `terminate` and `quit`, checks every value for type and range, drops unknown keys and limits the size to 4096 characters. Anything else is ignored.
- Process names, command lines and users reach the page only as text (`textContent`), never as HTML.
- orbitop opens no port and makes no network connections.
- Terminating a process of another user runs `pkexec /usr/bin/python3 -I /usr/local/libexec/orbitop/killhelper.py`. Before that, orbitop checks with `lstat` that the helper is a regular file and not a symlink, and that it and every directory up to `/` belong to root and are not writable by group or others. If not, it shows a hint and asks for no password.
- The helper opens a pidfd before it checks PID and start time, so the signal reaches exactly the checked process. It refuses PID 1 and kernel threads.
- `intel_gpu_top` and `nvidia-smi` are started with argument lists, never through a shell, and only from the fixed path `/usr/local/bin:/usr/bin:/bin`.

### Tests

- pytest. Every reader takes a `root` argument, so the tests run against fake `/proc` and `/sys` trees in `tests/fixtures/roots/`: `intel-laptop` (captured on the reference laptop), `amd-desktop`, `arm-board` and `vm`.
- `tests/ui/check.html` tests the page in headless Chrome at two window sizes. Without Chrome or Chromium these tests skip themselves.
- The suite also runs ShellCheck, `desktop-file-validate` and `appstreamcli`, so it needs pytest, ShellCheck, desktop-file-utils and AppStream.
- `scripts/check-distros.sh` runs the setup and the test suite in disposable Docker containers, one per distribution. The results are in [`docs/distro-check.md`](docs/distro-check.md).

```sh
python3 -m pytest -q
```

### Architecture

```text
/proc  /sys  intel_gpu_top  nvidia-smi
   |
   v
sysfs.py  system.py  sensors.py  gpu.py  gpu_tools.py  procs.py  classify.py
   |
   v
sampler.py          rates, histories, JSON snapshot
   |  app.py Worker: threads orbitop-worker (1 s), orbitop-procs (2 s)
   v
shell.py            GTK 4 window, WebKitGTK 6.0 view, orbitop://ui/
   |  window.orbitop.receive(msg)
   v
orbitop/ui/app.js   page, chart.js draws the charts
   |  postMessage: ready, view, layout, terminate, quit
   v
app.py parse_message
   |-- layout    -> layout.py  -> ~/.config/orbitop/layout.json
   '-- terminate -> actions.py -> own process: signal
                               -> other user: pkexec killhelper.py
```

## Requirements

- Linux with Python 3.12 or newer
- PyGObject, GTK 4 and WebKitGTK 6.0, each with its GObject introspection typelib (`Gtk-4.0`, `WebKit-6.0`)
- Optional: `intel_gpu_top` from the Intel GPU tools, for the Intel GPU load of all processes and the package power (with `--allow-perfmon`, see [Privileges and risks](#privileges-and-risks))
- Optional: `nvidia-smi` for NVIDIA GPUs. It comes with the proprietary driver, for example in `nvidia-utils-<version>`.

At start, orbitop checks the Python version, PyGObject, GTK 4 and WebKitGTK 6.0. If something is missing, it names the package of your distribution and the command to install it; on an unknown distribution it uses the Debian names.

### Supported distributions

<!-- supported:start -->
| Checked distribution | Derived from it, not tested |
|---|---|
| Ubuntu 24.04 | Linux Mint 22, Pop!_OS 24.04 |
| Debian 13 | |
| Fedora 45 | |
| Arch Linux | Manjaro, EndeavourOS |
| openSUSE Tumbleweed | |
<!-- supported:end -->

Checked on 2026-11-18 with `scripts/check-distros.sh` in disposable Docker containers: setup, import of GTK 4 and WebKitGTK 6.0, test suite, dry run. The containers have no display, so the window itself, the helper through `pkexec` and the `--allow-*` options were not part of the check. Details are in [`docs/distro-check.md`](docs/distro-check.md).

Not supported: Debian 12 (Python 3.11) and Ubuntu 22.04 (Python 3.10). Both ship WebKitGTK 6.0 and the setup runs, but orbitop needs Python 3.12 or newer and refuses to start.

### Package names

| Distribution | Package manager | Runtime packages | Intel GPU tools |
|---|---|---|---|
| Debian, Ubuntu | `apt-get` | `python3-gi` `gir1.2-gtk-4.0` `gir1.2-webkit-6.0` | `intel-gpu-tools` |
| Fedora | `dnf` | `python3-gobject` `gtk4` `webkitgtk6.0` | `igt-gpu-tools` |
| Arch Linux | `pacman` | `python-gobject` `gtk4` `webkitgtk-6.0` | `intel-gpu-tools` |
| openSUSE | `zypper` | `python3-gobject` `typelib-1_0-Gtk-4_0` `typelib-1_0-WebKit-6_0` `python3-gobject-Gdk` | `igt-gpu-tools` |

`setup-privileges.sh` installs these packages with the package manager it finds. It adds the Intel GPU tools only if the machine has an Intel GPU (driver `i915` or `xe`).

## Installation

### Get orbitop

From the release:

```sh
mkdir -p ~/.local/opt
cd ~/.local/opt
curl -LO https://github.com/zappelmann-sketch/orbitop/releases/download/v0.1.0/orbitop-0.1.0.tar.gz
curl -LO https://github.com/zappelmann-sketch/orbitop/releases/download/v0.1.0/SHA256SUMS
sha256sum -c SHA256SUMS
tar -xzf orbitop-0.1.0.tar.gz
cd orbitop-0.1.0
```

`sha256sum -c` must print `orbitop-0.1.0.tar.gz: OK`. Unpack orbitop in a permanent place such as `~/.local/opt`: `install-user.sh` writes the path of this directory into the launcher and the autostart entry, so do not move or delete the directory afterwards.

Or with git:

```sh
git clone https://github.com/zappelmann-sketch/orbitop.git
cd orbitop
```

Then run the commands for your distribution in that directory. To see first what the setup would do, run `bash scripts/setup-privileges.sh --dry-run`; it needs no root and changes nothing.

### Ubuntu and Debian

```sh
sudo apt-get update
sudo bash scripts/setup-privileges.sh
bash scripts/install-user.sh
```

### Fedora and openSUSE

```sh
sudo bash scripts/setup-privileges.sh
bash scripts/install-user.sh
```

`dnf` and `zypper` refresh their package index on their own.

### Arch Linux

```sh
sudo pacman -Syu
sudo bash scripts/setup-privileges.sh
bash scripts/install-user.sh
```

Derived distributions such as Linux Mint, Pop!_OS, Manjaro or EndeavourOS use the commands of their base.

### Other distributions

If `setup-privileges.sh` finds none of `apt-get`, `dnf`, `pacman` and `zypper`, it says "No supported package manager found" and installs no packages. Install these yourself with the package manager of your distribution:

- Python 3.12 or newer
- PyGObject
- GTK 4 with its typelib `Gtk-4.0`
- WebKitGTK 6.0 with its typelib `WebKit-6.0`
- optional: `intel_gpu_top` (Intel GPU tools) and `nvidia-smi`

Then run `sudo bash scripts/setup-privileges.sh` and `bash scripts/install-user.sh` as above. The setup script still installs the root-owned helper. orbitop has not been tested on such a distribution.

### Start

Start orbitop from the application menu or with `bin/orbitop`. From the next login on, the autostart entry starts it hidden (`--hidden`); starting it again from the menu shows the window.

## Privileges and risks

- `scripts/setup-privileges.sh` (with `sudo`) installs the runtime packages of your distribution, and the Intel GPU tools if an Intel GPU (`i915` or `xe`) is present. On every machine it copies `orbitop/killhelper.py` root-owned to `/usr/local/libexec/orbitop/killhelper.py`; terminating processes of other users needs this copy. After an update of `orbitop/killhelper.py` (for example after `git pull` or a new release), run the script again. Only with `--allow-perfmon` does it give `intel_gpu_top` the file capability `cap_perfmon`, so it runs without root (see the risks below). An upgrade of the Intel GPU tools package removes the capability; run the script with `--allow-perfmon` again afterwards. `--dry-run` only prints the commands, changes nothing and needs no root.
- `scripts/install-user.sh` (as your normal user, never root) writes only under `$HOME`: the launcher in `~/.local/share/applications`, the icon, and an autostart entry in `~/.config/autostart` that starts orbitop hidden at login.

Risks:

- **Root helper `/usr/local/libexec/orbitop/killhelper.py`:** `pkexec` starts it as root once you enter the admin password. The copy in the orbitop directory never runs as root, because any of your processes could change it. Before every call, orbitop checks that the helper is a regular file and not a symlink, and that it and every directory up to `/` belong to root and are not writable by group or others. Otherwise it asks for no password and shows a hint to run the setup script. Undo with `sudo rm -r /usr/local/libexec/orbitop`; processes of other users can then no longer be terminated.
- **`--allow-perfmon` (optional, off by default):** sets `cap_perfmon` on `/usr/bin/intel_gpu_top`. Every local account can then run that program with GPU counters and the RAPL package power (CVE-2020-8694). Without the option, orbitop shows only the Intel graphics usage of your own processes. Undo with `sudo setcap -r /usr/bin/intel_gpu_top`.
- **`--allow-rapl` (optional, off by default):** makes the RAPL energy counters readable for all local users (and all Flatpak apps) through a udev rule. The kernel restricts them to root because they enable power side-channel attacks (Platypus, CVE-2020-8694). Without the option, the package power comes from `intel_gpu_top` if it has `cap_perfmon`. Undo with `sudo rm /etc/udev/rules.d/70-orbitop-rapl.rules` and a reboot.

## Uninstall

Quit orbitop first (Ctrl+Q). Then, in the orbitop directory:

```sh
bash scripts/install-user.sh --uninstall
sudo rm -r /usr/local/libexec/orbitop
rm -r ~/.config/orbitop
```

The first line removes the launcher, the icon and the autostart entry. The second removes the root helper, the third the saved column layout. After that you can delete the orbitop directory. If you used `--allow-perfmon` or `--allow-rapl`, undo them as described under [Privileges and risks](#privileges-and-risks).

The packages that `setup-privileges.sh` installed stay installed, because other programs may need them. Remove them with your package manager if you no longer need them.

## Resource use

Measured with `scripts/measure-load.py` on the reference laptop (Intel Core i7-7600U, window 1600×1000, scaling 1.25), over the whole process tree including the WebKit processes and `intel_gpu_top`. Each run took 60 s; "after 1 min" means after 60 s of warm-up, "after 5 min" after five minutes. The window was not touched during the runs: mouse movement over the window makes WebKit draw more frames and raises the load.

| Situation | CPU, % of one core | PSS |
|---|---|---|
| Window hidden | 2.85 | 133 to 134 MB |
| Overview tab | 7.06 to 7.20 | 189 to 192 MB |
| Process tab, default columns | 7.81 to 7.88 | 190 to 193 MB |
| Process tab, all 15 columns, after 1 min | 8.51 to 8.80 | 194 to 198 MB |
| Process tab, all 15 columns, after 5 min | 9.00 to 9.41 | 198 to 201 MB |

orbitop's own limits are at most 3 % of one core with the window hidden, at most 9 % with the window visible, and PSS under 275 MB. With the default columns, orbitop stays within them. With all columns shown, the load after 5 minutes is 9.0 to 9.4 %, slightly above 9 %. All columns are only shown on request, so this is an accepted exceedance. About 1 % of one core in every case is `intel_gpu_top`.

## License

GPL-3.0-or-later, see `LICENSE`. Copyright © 2026 zappelmann-sketch.

The bundled fonts Orbitron and Oxanium are licensed under the SIL Open Font License 1.1; the license texts are in `orbitop/ui/fonts/`.
