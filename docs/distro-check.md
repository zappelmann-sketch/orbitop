# Distribution check

The packages of orbitop from the signed package source, installed, tested, updated and removed for real in disposable
Docker containers with [`scripts/check-distros.sh`](../scripts/check-distros.sh). Only the distributions whose result
is exactly `pass` are supported; `pass (expected refusal)` means that the package manager refused orbitop as intended.

`scripts/release.sh` (docs/release.md, "Release") runs the check on every release and writes the part between the
two markers below from its output; a release commits it before the tag. Both trees carry the same key, and the
containers trust whatever key that is; the run checks that both carry the same one and prints it as
`KEY <fingerprint>`, which `release.sh` compares with `ORBITOP_KEY`.

<!-- matrix:start: scripts/release.sh writes this part from the output of scripts/check-distros.sh -->
- Run: `scripts/release.sh 0.2.0` on 2026-11-19, `KEY B6F10E7E76A63D9D569DE0674B5D133F71445C01`, the archive key, whose fingerprint is in the README.
- `SITE`: orbitop `0.2.0-1`, `orbitop-apt-source` and `orbitop-release` `2026.11.18`. `SITE2`: the check build (Debian `0.2.0-1+check1`, RPM `0.2.0-1.check1`, Arch `0.2.0-1.1`; plan K6).

| Distribution | Image | Digest | Packages | Tests | Result |
|---|---|---|---|---|---|
| Debian 13 | `debian:trixie` | `debian@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6` | `orbitop 0.2.0-1` → `0.2.0-1+check1`: Python 3.13.5, PyGObject 3.50.0, GTK 4.18.6, WebKitGTK 2.54.0 | 974 passed, 138 skipped | pass |
| Ubuntu 24.04 | `ubuntu:24.04` | `ubuntu@sha256:73b999393d07f2bf65a40373778a44dc9a6d54ad7718d29247d8ff9413c4d6a8` | `orbitop 0.2.0-1` → `0.2.0-1+check1`: Python 3.12.3, PyGObject 3.48.2, GTK 4.14.5, WebKitGTK 2.52.6 | 974 passed, 138 skipped | pass |
| Ubuntu 26.04 | `ubuntu:26.04` | `ubuntu@sha256:d66b366dac61b575bee2aef07e9c26e8070096fbe84a3d4d3eb0da069b5d76db` | `orbitop 0.2.0-1` → `0.2.0-1+check1`: Python 3.14.4, PyGObject 3.56.2, GTK 4.22.4, WebKitGTK 2.52.6 | 975 passed, 137 skipped | pass |
| Fedora 45 | `fedora:latest` | `fedora@sha256:a7d72ba2745b100a3351087472e5ee7b2450af7cf331e7673007e3817612839c` | `orbitop 0.2.0-1` → `0.2.0-1.check1`: Python 3.15.2, PyGObject 3.58.1, GTK 4.24.1, WebKitGTK 2.54.2 | 992 passed, 120 skipped | pass |
| openSUSE Tumbleweed | `opensuse/tumbleweed` | `opensuse/tumbleweed@sha256:873ddd8d2a548bbd38c9d8485bd710ab6d17d013cacb38a252005f634b3ab187` | `orbitop 0.2.0-1` → `0.2.0-1.check1`: Python 3.13.18, PyGObject 3.58.1, GTK 4.24.1, WebKitGTK 2.54.2 | 992 passed, 120 skipped | pass |
| Arch Linux | `archlinux:latest` | `archlinux@sha256:d4594bb2300cba11f41c2f27923eb56f63d9988909c402f9c95517d1e362c899` | `orbitop 0.2.0-1` → `0.2.0-1.1`: Python 3.14.10, PyGObject 3.58.1, GTK 4.24.1, WebKitGTK 2.54.2 | 992 passed, 120 skipped | pass |
| Debian 12 | `debian:bookworm` | `debian@sha256:268fb24c39bca92d326dd83ea3abebe4a3f7751c804ffef23bb6d857dd343ff8` | `orbitop 0.2.0-1` refused | – | pass (expected refusal): step `install`, "orbitop : Depends: python3 (>= 3.12) but 3.11.2-1+b1 is to be installed" |
| Ubuntu 22.04 | `ubuntu:22.04` | `ubuntu@sha256:9abcaffc92a5279fff3a6a41635c0800ea33e528425fb389658806476e7defde` | `orbitop 0.2.0-1` refused | – | pass (expected refusal): step `install`, "orbitop : Depends: python3 (>= 3.12) but 3.10.6-1~22.04.1 is to be installed" |
<!-- matrix:end -->

How the check runs:

- Before the images, `check-distros.sh` builds the packages that the step `counters` updates from and to, with
  `scripts/build-packages.sh` and the key of the sites, their logs on stderr: the commit `ORBITOP_REV` once more as
  revision 2 (`--revision 2`, orbitop N+1), and 0.2.0 from the files of the tag `refs/tags/v0.2.0` (`ORBITOP_REV` set
  to its commit, so the containers run the tag's own build scripts), never from the published source: the run depends
  neither on the state of Pages nor on the archive key. Without `ORBITOP_REV`, the script takes HEAD once and passes
  it on, so `/src` and revision 2 are the same commit. The tag cannot change, so its build runs with
  `--lint report`: lint findings of a newer lintian, rpmlint or namcap are reported, not fatal; any other failure
  (the build, a cmp or mode guard) stops the run, as every finding of revision 1 and 2 does.
- Each image runs once as
  `docker run --rm -v <copy>:/src:ro -v SITE:/site:ro -v SITE2:/site2:ro -v <rev2>:/rev2:ro -v <v020>:/v020:ro <digest> bash /src/scripts/matrix/inside.sh`,
  from the digest that `docker image inspect` reported after the pull (the one in the table), not from the tag:
  no `--privileged`, no added capabilities, nothing writable from the host. `<copy>` is `git archive` of the commit
  `ORBITOP_REV` (HEAD without it), removed afterwards. The containers reach the distribution mirrors over the network.
  Unlike the builds, the matrix does not drop `SETFCAP`: rpm sets file capabilities while it installs (with
  `--cap-drop SETFCAP`, Fedora's `gstreamer1` failed with `cpio: cap_set_file failed - Operation not permitted`), and
  no output of the container reaches the host.
- The steps run the commands of the README. Only the installed copies of the source definitions under `/etc` point to
  `file:///site/` (later `/site2/`) instead of `https://zappelmann-sketch.github.io/orbitop/`; the packages keep the
  Pages address (`tests/test_check_distros.py`). `point` writes these copies always from the file the package
  installed, and refuses to overwrite one that is no longer what it wrote last, so any change by the package manager
  stops the step. The commands of each package manager are in `scripts/matrix/{apt,dnf,zypper,pacman}.sh`, the shared
  rpm part in `scripts/matrix/rpm.sh`, the helpers in `scripts/matrix/lib.sh` (`tests/test_matrix_lib.py`).
  `check-distros.sh` exits 1 unless every image passed.
  1. `refresh`: the index of the distribution (`apt-get update`, `dnf makecache`, `zypper refresh`, `pacman -Syu`).
  2. `keyring`: apt: `apt install ./orbitop-apt-source.deb`; the source's `Release` has `Architectures: all` and
     `Acquire-By-Hash: yes` and no `Valid-Until`. Fedora and openSUSE: `rpm --import orbitop-archive-keyring.asc`, then
     `rpm -K` must report exactly `digests signatures OK` for every RPM of the source (for an RPM without a signature
     it reports `digests OK` and still exits 0: review of Task 6, Tumbleweed), then
     `dnf install ./orbitop-release-fedora.rpm` or `zypper install ./orbitop-release-opensuse.rpm`, and
     `rpm -V orbitop-release` reports nothing; openSUSE installs `findutils` first, as the README says (the image has
     no `xargs`, which the full uninstall needs). Arch: `pacman-key --init` and `--populate archlinux`,
     `pacman-key --add orbitop-archive-keyring.asc`,
     `pacman-key --lsign-key <fingerprint>`, the section `[orbitop]` with `SigLevel = Required DatabaseRequired` and
     `Server = …/arch/$arch` at the end of `/etc/pacman.conf`.
  3. `install`: `apt update` (no `W:`, `E:` or `N:`) and `apt install orbitop`; `dnf install orbitop`;
     `zypper install orbitop`, and `zypper lr orbitop` shows `GPG Check: (rp) Yes`; `pacman -Syu orbitop`.
     Afterwards `/usr/bin/pkexec`, which starts orbitop's helper, is a file that a package owns; the log names that
     package (`dpkg -S`, `rpm -qf`, `pacman -Qo`). The installed orbitop must accept it with its own check before every
     `pkexec` (`actions.real_pkexec`: a root-owned ELF with the setuid bit in a root-owned directory chain), so a
     distribution whose `pkexec` it refuses fails the matrix instead of silently losing "terminate other users'
     processes". On openSUSE it is the package `pkexec`, which orbitop requires as `/usr/bin/pkexec`, because `polkit`
     there does not pull it in. On Arch,
     `/usr/share/pacman/keyrings/orbitop-trusted` of the installed package is exactly the line `<fingerprint>:3:`
     (owner trust "never", docs/release.md); the log shows it as `TRUSTED …`.
  4. `import`: import GTK 4 and WebKitGTK 6.0 through PyGObject.
  5. `tools`: install pytest, ShellCheck, desktop-file-utils and AppStream.
  6. `pytest`: `python3 -m pytest -q` as an ordinary user on a copy of the repository. The browser tests skip
     themselves (no Chrome in the images), and so do the tests that need a display, git, gpg or the reference machine's
     GPU.
  7. `version`: `/usr/bin/orbitop --version` as that user prints the version of the tree.
  8. `upgrade`: the source switched to `SITE2`, then the regular update (`apt upgrade`, `dnf upgrade`, `zypper dup`,
     `pacman -Syu`); afterwards the check version is installed.
  9. `remove`: apt: `apt remove orbitop`, `apt update`, `apt remove orbitop-apt-source`, `apt update`; each `apt update`
     exits 0 without `W:`, `E:`, `N:` (apt 3: `Warning:`, `Error:`, `Notice:`), and orbitop still has a candidate: the
     conffiles keep the source with its key. Fedora, openSUSE, Arch: remove `orbitop`, then a refresh that fetches the
     index again, without a warning or an error: `dnf makecache --refresh` (`dnf makecache` alone keeps metadata that
     has not expired), `zypper refresh --force orbitop`, `pacman -Syy`.
  10. `purge`: first the check that the source definition is still what `point` wrote last, so the package manager
      did not change it during refresh, update and removal. apt: `apt purge orbitop orbitop-apt-source` (the source
      still points to `SITE2`; with the Pages address apt would no longer know orbitop). Fedora and openSUSE: the
      `.repo` back to the Pages address, `rpm -V --nomtime orbitop-release` reports nothing, `remove orbitop-release`,
      then the README's line that deletes every key named `orbitop archive signing key` from the rpm database
      (`rpmkeys --list | grep -F … | xargs -r -n1 rpmkeys --delete`, afterwards `rpmkeys --list` names none); on
      Fedora also `rm -rf /var/cache/libdnf5/orbitop-*` (notes). Arch: the section back to the Pages address and out
      of `pacman.conf` (byte for byte the file from before), the README's line that selects the keys with exactly the
      user ID `orbitop archive signing key` in pacman's keyring and deletes them with `pacman-key --delete`
      (`pacman-key --list-keys '=orbitop archive signing key'` then reports "No public key"), `pacman -Sc`. These
      lines select by user ID, so the run needs a key with exactly that user ID, a throwaway one in a dry run.
      Afterwards no path from the file lists of the packages is left, except directories that another package owns;
      `/etc/orbitop` does not exist; the index refresh (`dnf makecache --refresh`, `pacman -Syy`) is clean; and no index
      of the source is left (apt lists, `/var/cache/zypp/*/orbitop`, `/var/lib/pacman/sync/orbitop.*`).
  11. `counters`: the cases of the counter release (security document 0.3.0, the container matrix of B2.1, B2.2,
      B2.3, B2.4, B2.8 and B2.9), from the state the purge left: no source of orbitop configured; its dependencies
      stay installed, so orbitop comes only from files, of `SITE` (revision 1), `/rev2` and `/v020`. One line `COUNTERS <case> ok|FAIL`
      per case; one `FAIL` fails the step, and with it the image, and so does a format without cases (`COUNTERS
      none`). The cases are the same for every format (`scripts/matrix/counters.sh`, `tests/test_matrix_counters.py`);
      the file of the package manager gives their list, the owner of `/usr/bin/intel_gpu_top`, the commands and the
      cases of its own (`tests/test_matrix_counters_formats.py`). They run as root without polkit and check the
      capability (`security.capability` must be the 20 bytes of `cap_perfmon=ep`,
      `0100000200000000000000004000000000000000`), the marker `/etc/orbitop/counters-released` (empty, root 0644) and
      the exit codes of `counterhelper`. Docker masks the RAPL zones (`/sys/devices/virtual/powercap`), so the helper
      finds none and exits 0 for that part; the read bits are left to the unit tests and the hardware test. apt, in this
      order (the owner is `intel-gpu-tools`, on Ubuntu 26.04 `igt-gpu-tools`, and `dpkg -S` must name it; orbitop goes
      in with `dpkg -i`, which also takes the same or a lower version, where apt keeps what is installed):
      - `orbitop_install_manual_cap` (B2.4, 5): the Intel tools from the mirrors, a capability set by hand, then the
        first installation of orbitop: no marker, and the capability stays.
      - `file_list` (B2.2, B2.3): `dpkg -L orbitop` names `/etc/orbitop` and no file in it, the udev rule only as
        `/usr/lib/udev/rules.d/70-orbitop-counters.rules` and nothing below `/etc/udev`; `/etc/orbitop` is empty, root
        0711, and `nobody` cannot open it.
      - `reinstall_owner_off` (B2.4, 1): `apt-get install --reinstall` of the owner runs orbitop's trigger
        ("Processing triggers for orbitop") and releases nothing; a capability set by hand before is gone afterwards,
        which shows that a reinstall takes it in this format.
      - `on_off` (B2.1, B2.2): `counterhelper on` exits 0 and sets the capability and the marker; `nobody` cannot open
        `/etc/orbitop` (`EACCES`); `off` exits 0 and takes both back.
      - `reinstall_owner_on` (B2.4, 2): after `on`, the reinstalled `intel_gpu_top` (a new inode, or a new change
        time) has the capability.
      - `owner_remove` (B2.4, 3): removing the owner runs the trigger, no package script reports a failed helper, and
        `counterhelper sync` exits 0.
      - `owner_first_install_on` (B2.4, 4): after `on`, the first installation of the owner brings the capability.
      - `rev2_upgrade_on` (B2.8, 4): with `on`, the update to revision 2 keeps the marker and the capability.
      - `remove_on` (B2.8, 1 and 2): with `on`, `apt-get remove orbitop` takes the marker and the capability back;
        orbitop and the owner installed again release nothing.
      - `remove_broken_helper` (B2.8, 6; M-3): with `on` and `chmod -x` on the helper, the removal succeeds (prerm
        prints "orbitop: counter release not revoked") and the marker goes. The capability stays, as the case expects,
        and the log says so ("M-3: the capability stays …"); after the purge there is no `/etc/orbitop`.
      - `purge` (B2.8, 7): with `on`, `apt-get purge orbitop` leaves no `/etc/orbitop`, no marker and no capability.
      - `manual_rule_untouched` (B2.9): the rule of the README of 0.2.0, `/etc/udev/rules.d/70-orbitop-rapl.rules`,
        stays byte for byte through install, `on`, `off`, removal and purge.
      - `upgrade_from_020` (B2.8, 3): 0.2.0, then the update to revision 1: no marker, no capability, and the installed
        orbitop accepts `pkexec` (`real_pkexec` as in step 3, only after the update: 0.2.0 has no
        `actions.real_pkexec`); a capability set by hand before 0.2.0 stays.
      - `joint_upgrade` (B2.4, 6; B2.8, 5; I-1): with `on`, orbitop from revision 1 to 2 and the owner to a new version
        in one transaction: `apt-get install` of both files, then `dpkg -i` in both orders. The new version of the owner
        is a package built in the container with the owner's name and `<version>+fake<N>`, whose `intel_gpu_top` is a
        copy of the installed program. Afterwards the new file (a new inode) has the capability.

      RPM (Fedora, openSUSE), the same cases with these differences (`scripts/matrix/rpm.sh`, `dnf.sh`, `zypper.sh`):
      the owner is `igt-gpu-tools` on Fedora and `intel-gpu-tools` on openSUSE (`rpm -qf` must name it), from the
      mirrors with `dnf install`/`reinstall` or `zypper install`/`install --force`, removed with `dnf remove` (without
      the dependencies) or `zypper remove`. orbitop goes in with `rpm -U --replacepkgs --oldpackage --nosignature`,
      the first time with `dnf install` or `zypper --no-gpg-checks install --allow-unsigned-rpm`, which bring the
      dependencies (rpm 6 on Fedora refuses unsigned packages, and the key of `SITE` left the rpm database in step 10;
      the signatures are the business of steps 2, 3 and 12). RPM has no purge: `purge` is the removal, so it also
      covers B2.8, 1 (no `/etc/orbitop` right after it). `%filetriggerin` runs only when the file comes, so
      `owner_remove` expects no trigger; dnf5 and zypper name a scriptlet only when it prints something, and `sync`
      without a marker prints nothing, so no case looks for a trigger line there. `remove_broken_helper` expects the
      shell's own line from `%preun` (`… /usr/lib/orbitop/counterhelper: Permission denied`). Two cases of RPM only:
      - `pkexec_provider` (B2.4, 8; E5), after the first installation: `rpm -q --whatprovides /usr/bin/pkexec` names
        exactly `polkit` (Fedora) or `pkexec` (openSUSE), not `run0-wrappers`; the log line `PKEXEC <name>`.
      - `rpm_verify` (B2.4, 7), after `reinstall_owner_on`: `rpm -V` of the owner exits 1 and reports exactly
        `........P    /usr/bin/intel_gpu_top`, the capability; the log line `RPM-V …` goes into the report.

      `joint_upgrade` there: `rpm -U` of both files, then `dnf upgrade` of both, or `zypper up --repo joint` from a
      plaindir repository of both files without signatures (zypper up takes no files), removed afterwards. The new
      owner is `<release>.fake<N>` with the installed epoch, version, architecture and vendor (zypper keeps the vendor),
      built with `rpmbuild` (`rpm-build` from the mirrors), its `intel_gpu_top` the installed program plus one byte at
      the end. openSUSE's rpm keeps an unchanged file on an update or reinstall (`%_minimize_writes 1`) and only sets
      its metadata anew, which takes the capability too (probe on 2026-11-20): hence the changed program here, and the
      change time in `reinstall_owner_on`.

      Arch, the same cases (`scripts/matrix/pacman.sh`): the owner `intel-gpu-tools` with `pacman -S` (`pacman -Qqo`
      must name it), removed with `pacman -R`; orbitop with `pacman -U` of a copy, since pacman checks a `.sig` next
      to the file and the key left pacman's keyring in step 10. pacman has no purge: `purge` is the removal. The hook
      shows as "(n/m) Applying the orbitop counter release, if turned on..."; it has no `Remove`, so `owner_remove`
      expects none. `remove_broken_helper` expects the shell's line from `pre_remove`. `joint_upgrade`: `pacman -U` of
      both files; the new owner is packed by hand (`.PKGINFO` and the file, `<pkgver>.fake<N>`, newer for `vercmp`).
  12. `tamper`: a copy of `SITE` with one changed byte, set up again like in step 2; the index refresh must fail with
      its reason. apt, twice: `Packages.gz` (also at its by-hash paths) gives "Hash Sum mismatch", which tests the
      hashes in `InRelease`; the last digit of the seconds in the signed `Date:` of `InRelease` (the format stays
      valid) gives "is not signed", which tests the signature itself. Fedora and openSUSE: a digit of `<revision>` in
      `repomd.xml`, dnf "Bad PGP signature" (with `--setopt=skip_if_unavailable=False`, notes), zypper "Signature
      verification failed for repomd.xml". Arch: `orbitop.db`, pacman "invalid or corrupted database (PGP signature)".
- Network hiccups of the mirrors (`scripts/matrix/lib.sh`, `tests/test_matrix_retry.py`): each command that fetches
  from the mirrors runs under `net`, in the steps `refresh`, `install`, `tools` and `upgrade`, on Fedora and openSUSE
  also `keyring`. A run that exits with a status other than 0, printed a hiccup and left the installed packages as
  they were runs again after 10 s, up to three runs; only the last one counts, and the log shows each repetition with
  a line `RETRY`. The packages are compared by a hash of a non-empty list from
  `dpkg-query -W -f '${db:Status-Abbrev} ${binary:Package} ${Version}\n'` (with the status, so that a removal that
  keeps the conffiles counts as a change), `rpm -qa | sort` or `pacman -Q`, before and after the run; if they changed,
  or if there is no such list, the log shows `NO RETRY` and the run counts at once. `net` judges only the exit status
  and the hiccup. The index refreshes that must be clean (`quiet`: apt in `install` and `upgrade`, every package
  manager in `remove` and `purge`) also count a line that matches `NOISE` as a failed run; without `NOISE` they fail.
  Each run first removes the copy of the previous run's output in `STATE` (if it cannot, the run fails without
  starting), then writes its output live into the log and into a new copy, which `net` and `quiet` search as text,
  with each NUL byte and each carriage return read as a line break; if the new copy cannot be written or read, or
  grep fails, the run fails and is not repeated. Any other failure counts at once: the expected refusal on
  `debian:bookworm` and
  `ubuntu:22.04` stays one run, and the `tamper` step runs its refresh once. A `NOISE` line of an earlier run stays in
  the log, but the verdict comes from the last run: the sources are read-only, so a signature check gives the same
  result in every run. A hiccup is one of the messages the images print (read from the strings of librepo, libzypp,
  libalpm, libcurl, libapt-pkg and libc in the images, 2026-11-20): `Curl error` 6, 7, 28, 35, 52 or 56 (dnf with
  parentheses, zypper without), zypper's `Timeout exceeded when accessing`, the texts of libcurl after pacman's
  `failed retrieving file` (`Could not resolve host`, `Could not connect to server`, before libcurl 8
  `Couldn't connect to server`, `Operation timed out`, `Operation too slow`, `Empty reply from server`,
  `Connection timed out after`, `Resolving timed out after`, `Connection timeout after`,
  `Failed to resolve '…' with timeout after`, from libcurl 8.18 `Failed to resolve host '…' with timeout after`), apt's
  `Temporary failure resolving`, `Could not resolve '…'`, `Could not connect to` and `Connection timed out`, and the
  system's `Connection reset by peer` and `Temporary failure in name resolution`. Not a hiccup: `Curl error 60` (a
  certificate) and `Failed to connect to`, which systemd prints in the scripts of packages. Cause: on 2026-11-19
  `mirrors.fedoraproject.org` reset the connection ("Curl error (56)") in `remove` or `purge` of three runs, although
  dnf then loaded the index from another mirror and exited 0.
- `debian:bookworm` and `ubuntu:22.04` pass only as an expected refusal: exactly the step `install` fails, with apt's
  `orbitop : Depends: python3 (>= 3.12)`. The run ends there.
- In the table, `Packages` is the version of orbitop that the `install` step installed and the one the `upgrade` step
  updated it to, followed by the versions the `import` step reported; `Tests` is the summary of the `pytest` step.

## Notes

From the run of 2026-11-18 (orbitop 0.1.0, throwaway key) unless a note names another date.

- **apt pinning:** a `file://` source has no origin, so the pin of `orbitop-apt-source`
  (`Pin: origin zappelmann-sketch.github.io`) does not apply to it: `apt-cache policy orbitop` shows
  `500 file:/site/apt stable/main all Packages`. The `upgrade` step therefore serves `SITE2` inside the container at
  `http://zappelmann-sketch.github.io/orbitop/` (the host name on 127.0.0.1 in the container's `/etc/hosts`,
  `python3 -m http.server`), so that the pin applies as with Pages: `apt-cache policy orbitop` shows
  `100 http://zappelmann-sketch.github.io/orbitop/apt stable/main all Packages`, and `apt upgrade` still installs the
  check version. Installed and new version both have priority 100, and of the same priority apt takes the higher
  version (apt_preferences(5)). The server's log shows that apt fetched the index as
  `dists/stable/main/binary-all/by-hash/SHA512/<sha512>`. Afterwards the source points to `file:///site2/` again.
- **by-hash and the tamper step:** with a changed `Packages.gz` alone, `apt-get update` exits 0 (probe): apt fetches
  the index by its hash from `by-hash/SHA512/`, whose copy was intact. The step therefore changes the by-hash copies as
  well, as a server that delivers a changed index would. That case checks only the chain of hashes: the audit of Task 6
  found that a source with `Trusted: yes` refuses it too, but accepts an `InRelease` with a changed `Date:` (only a
  warning, exit 0). The second case, the changed `Date:`, is the one that shows that apt checks the signature.
- **Ubuntu 26.04:** `ubuntu:26.04` was Ubuntu 26.04.1 LTS. **Ubuntu 24.04:** Ubuntu 24.04.5 LTS. **Debian 13:**
  `debian:trixie` was Debian 13; its apt 3 writes `Error:` where older apt writes `E:`.
- **Fedora:** `fedora:latest` was Fedora 45 (`VERSION_ID=45`). The first installation as in the README, `rpm --import`
  of the key from the site before `dnf install ./orbitop-release-fedora.rpm`:
  - Installing the local `orbitop-release` prints "Warning: skipped OpenPGP checks for 1 package from repository:
    @commandline" (dnf5 checks no local packages); there is no warning about an unknown key.
  - On the first use of the source, dnf still asks once: "Importing OpenPGP key 0xE652BA57: … From:
    file:///etc/pki/rpm-gpg/RPM-GPG-KEY-orbitop", answered here by `-y`. dnf5 keeps the keys for `repo_gpgcheck`
    for each repository in `/var/cache/libdnf5/orbitop-<hash>/pubring/<key id>.pub`. Without `rpm --import` first it
    asks twice, for the metadata and then for the packages (probe). The run asked three times, because `SITE`, `SITE2`
    and the tampered copy are three addresses with a cache each; with Pages there is one.
  - After `dnf remove orbitop orbitop-release` and `rpmkeys --delete`, the copy in the pubring stays, also after
    `dnf clean all` (probe). The full uninstall on Fedora therefore also removes `/var/cache/libdnf5/orbitop-*`.
  - dnf5 skips a source whose `repomd.xml` has a bad signature and still exits 0 (`skip_if_unavailable=True`, the
    Fedora default; docs/release.md). The `tamper` step runs `dnf makecache -y --setopt=skip_if_unavailable=False` and
    also requires the text "Bad PGP signature".
  - The image lacks `runuser`, so the `tools` step also installs `util-linux` there.
- **openSUSE Tumbleweed:** `docker pull` brought a new image during the run, snapshot `VERSION_ID="20261117"`; it has
  no `awk`, `find` or `cmp`.
  - Without `rpm --import` first, `zypper install ./orbitop-release-opensuse.rpm` aborts: "Signature verification
    failed [4-Signatures public key is not available]" (probe). With it, zypper asks nothing; `zypper refresh` only
    reports "Looking for gpg keys in repository orbitop". This is the way for the README, on Fedora too.
  - `zypper lr orbitop` shows `GPG Check: (rp) Yes`: metadata and packages are checked. zypper did not rewrite the
    `.repo` (`type=rpm-md`): `point` found it unchanged after refresh, install, `zypper dup` and removal of orbitop, and
    after the address is put back `rpm -V --nomtime orbitop-release` reports nothing.
  - After `zypper remove orbitop-release`, `rpmkeys --delete` and `zypper refresh`, no cache of the source is left
    (`/var/cache/zypp/*/orbitop`).
  - zypper parses `repomd.xml` before it checks the signature: a byte changed in the middle of the file gave
    "Parse error: repomd.xml[14] Opening and ending tag mismatch" instead of a signature error. The `tamper` step
    therefore changes a digit of `<revision>`, which keeps the XML well-formed.
  - Not checked: that `pkg_gpgcheck=1` refuses an unsigned or a foreign-signed package. That needs a third tree whose
    signed metadata lists such a package, and no secret key goes into a container.
- **Arch Linux:** the image was built on 2026-11-08 (`VERSION_ID=20261108.0.623074`); `pacman -Syu` brought it up to
  date first. It has no local master key, so `pacman-key --init` comes first (docs/release.md). On install,
  `orbitop.install` ran `pacman-key --populate orbitop` ("Appending keys from orbitop.gpg"). After the section is
  removed, `orbitop.db` and `orbitop.db.sig` stay in `/var/lib/pacman/sync/` until `pacman -Sc` ("removing unused sync
  repositories"); the uninstall of the README needs it. The image has no `cmp`.
- **Debian 12 and Ubuntu 22.04 are not supported.** apt refuses to install orbitop because their package `python3` is
  older than 3.12 (Debian 12: `3.11.2-1+b1`, Ubuntu 22.04: `3.10.6-1~22.04.1`), with the message in the table and
  "E: Unable to correct problems, you have held broken packages."
  `orbitop-apt-source` itself installs there.
- **Counter release** (step `counters`), probe on 2026-11-20 in `debian:trixie` with repacked packages: without the
  trigger and the maintainer scripts of 0.3.0, 8 of the 14 cases fail (`reinstall_owner_off` and `owner_remove`: no
  trigger runs; `reinstall_owner_on`, `owner_first_install_on`, `remove_on`, `remove_broken_helper`, `purge`,
  `joint_upgrade`); with `sync` only on `triggered`, only `joint_upgrade` fails, already with
  `apt-get install` of both files: dpkg calls orbitop's postinst only with `configure` there (I-1); with `off` also on
  `upgrade`, `rev2_upgrade_on` and `joint_upgrade` fail. RPM and Arch, probe on 2026-11-20 with the packages of the
  commit before their scriptlets and hook (as revision 1 and 2): Fedora and openSUSE fail 6 of 16 cases
  (`reinstall_owner_on`, `owner_first_install_on`, `remove_on`, `remove_broken_helper`, `purge`, `joint_upgrade`),
  Arch 7 of 14 (the same and `reinstall_owner_off`, which sees no hook line); with revision 2 without `%posttrans`,
  `joint_upgrade` fails on Fedora already with `rpm -U` of both files: no file trigger runs there (I-1). Not covered in
  the containers: the RAPL read bits and the udev rule at boot (Docker masks the zones and runs no udev); they belong
  to the hardware test.
- **Not covered:** the window itself (no display in the containers), the kill helper through `pkexec`, the upgrade
  of a distribution release (Ubuntu disables third-party sources then), and the package source over HTTPS from Pages
  itself (plan 2026-11-18, Task 10).
