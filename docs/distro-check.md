# Distribution check

The packages of orbitop from the signed package source, installed, tested, updated and removed for real in disposable
Docker containers with [`scripts/check-distros.sh`](../scripts/check-distros.sh). Only the distributions whose result
is exactly `pass` are supported; `pass (expected refusal)` means that the package manager refused orbitop as intended.

`scripts/release.sh` (docs/release.md, "Release") runs the check on every release and writes the part between the
two markers below from its output; a release commits it before the tag. Both trees carry the same key, and the
containers trust whatever key that is; the run checks that both carry the same one and prints it as
`KEY <fingerprint>`, which `release.sh` compares with `ORBITOP_KEY`.

<!-- matrix:start: scripts/release.sh writes this part from the output of scripts/check-distros.sh -->
- Run: `scripts/release.sh 0.2.0 --dry-run` on 2026-11-19, `KEY BEB38C09E2CB0A5254FA037BE38C7E649D290C9C`, the key of `ORBITOP_KEY`; a dry run may sign with a throwaway key instead of the archive key.
- `SITE`: orbitop `0.2.0-1`, `orbitop-apt-source` and `orbitop-release` `2026.11.18`. `SITE2`: the check build (Debian `0.2.0-1+check1`, RPM `0.2.0-1.check1`, Arch `0.2.0-1.1`; plan K6).

| Distribution | Image | Digest | Packages | Tests | Result |
|---|---|---|---|---|---|
| Debian 13 | `debian:trixie` | `debian@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6` | `orbitop 0.2.0-1` → `0.2.0-1+check1`: Python 3.13.5, PyGObject 3.50.0, GTK 4.18.6, WebKitGTK 2.54.0 | 974 passed, 138 skipped | pass |
| Ubuntu 24.04 | `ubuntu:24.04` | `ubuntu@sha256:73b999393d07f2bf65a40373778a44dc9a6d54ad7718d29247d8ff9413c4d6a8` | `orbitop 0.2.0-1` → `0.2.0-1+check1`: Python 3.12.3, PyGObject 3.48.2, GTK 4.14.5, WebKitGTK 2.52.6 | 974 passed, 138 skipped | pass |
| Ubuntu 26.04 | `ubuntu:26.04` | `ubuntu@sha256:d66b366dac61b575bee2aef07e9c26e8070096fbe84a3d4d3eb0da069b5d76db` | `orbitop 0.2.0-1` → `0.2.0-1+check1`: Python 3.14.4, PyGObject 3.56.2, GTK 4.22.4, WebKitGTK 2.52.6 | 975 passed, 137 skipped | pass |
| Fedora 45 | `fedora:latest` | `fedora@sha256:a7d72ba2745b100a3351087472e5ee7b2450af7cf331e7673007e3817612839c` | `orbitop 0.2.0-1` → `0.2.0-1.check1`: Python 3.15.2, PyGObject 3.58.1, GTK 4.24.1, WebKitGTK 2.54.2 | 992 passed, 120 skipped | pass |
| openSUSE Tumbleweed | `opensuse/tumbleweed` | `opensuse/tumbleweed@sha256:5675226bebb80ead08e486d0391d7580105697d1a9dacd9f72e5f191ed99be0d` | `orbitop 0.2.0-1` → `0.2.0-1.check1`: Python 3.13.18, PyGObject 3.58.1, GTK 4.24.1, WebKitGTK 2.54.2 | 992 passed, 120 skipped | pass |
| Arch Linux | `archlinux:latest` | `archlinux@sha256:d4594bb2300cba11f41c2f27923eb56f63d9988909c402f9c95517d1e362c899` | `orbitop 0.2.0-1` → `0.2.0-1.1`: Python 3.14.10, PyGObject 3.58.1, GTK 4.24.1, WebKitGTK 2.54.2 | 992 passed, 120 skipped | pass |
| Debian 12 | `debian:bookworm` | `debian@sha256:268fb24c39bca92d326dd83ea3abebe4a3f7751c804ffef23bb6d857dd343ff8` | `orbitop 0.2.0-1` refused | – | pass (expected refusal): step `install`, "orbitop : Depends: python3 (>= 3.12) but 3.11.2-1+b1 is to be installed" |
| Ubuntu 22.04 | `ubuntu:22.04` | `ubuntu@sha256:9abcaffc92a5279fff3a6a41635c0800ea33e528425fb389658806476e7defde` | `orbitop 0.2.0-1` refused | – | pass (expected refusal): step `install`, "orbitop : Depends: python3 (>= 3.12) but 3.10.6-1~22.04.1 is to be installed" |
<!-- matrix:end -->

How the check runs:

- Each image runs once as
  `docker run --rm -v <copy>:/src:ro -v SITE:/site:ro -v SITE2:/site2:ro <digest> bash /src/scripts/matrix/inside.sh`,
  from the digest that `docker image inspect` reported after the pull (the one in the table), not from the tag:
  no `--privileged`, no added capabilities, nothing writable from the host. `<copy>` is `git archive HEAD`, removed
  afterwards. The containers reach the distribution mirrors over the network. Unlike the builds, the matrix does not
  drop `SETFCAP`: rpm sets file capabilities while it installs (with `--cap-drop SETFCAP`, Fedora's `gstreamer1` failed
  with `cpio: cap_set_file failed - Operation not permitted`), and no output of the container reaches the host.
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
  11. `tamper`: a copy of `SITE` with one changed byte, set up again like in step 2; the index refresh must fail with
      its reason. apt, twice: `Packages.gz` (also at its by-hash paths) gives "Hash Sum mismatch", which tests the
      hashes in `InRelease`; the last digit of the seconds in the signed `Date:` of `InRelease` (the format stays
      valid) gives "is not signed", which tests the signature itself. Fedora and openSUSE: a digit of `<revision>` in
      `repomd.xml`, dnf "Bad PGP signature" (with `--setopt=skip_if_unavailable=False`, notes), zypper "Signature
      verification failed for repomd.xml". Arch: `orbitop.db`, pacman "invalid or corrupted database (PGP signature)".
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
- **Not covered:** the window itself (no display in the containers), the kill helper through `pkexec`, the upgrade
  of a distribution release (Ubuntu disables third-party sources then), and the package source over HTTPS from Pages
  itself (Task 10).
