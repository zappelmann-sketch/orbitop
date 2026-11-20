# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# pacman (Arch Linux) for scripts/matrix/inside.sh, which sources it after lib.sh. The source is set up by hand as in
# the README: the key with pacman-key, the section [orbitop] at the end of pacman.conf (pacman takes a package from
# the first repository that has it).
# shellcheck shell=bash disable=SC2034,SC2154  # NOISE is read by lib.sh, the values of the counter release by
# counters.sh; PAGES and STATE come from lib.sh, SITE, REV2 and V020 from inside.sh, TOOL from counters.sh

NOISE='^(warning|error):'
CONF=/etc/pacman.conf
TRUSTED=/usr/share/pacman/keyrings/orbitop-trusted

refresh() { net pacman -Syu --noconfirm; }  # Arch supports only full upgrades

# keyring ROOT: the image has no local master key, so pacman-key --init first (docs/release.md). The fingerprint is
# that of the key in ROOT; check-distros.sh prints it (KEY), and release.sh compares it with ORBITOP_KEY.
keyring() {
    local fpr
    [ -f "$STATE/pacman.conf" ] || cp -- "$CONF" "$STATE/pacman.conf" || return 1  # as it was, for purge
    fpr=$(gpg --with-colons --show-keys "$1/orbitop-archive-keyring.asc" | awk -F: '$1 == "fpr" { print $10; exit }') &&
        [[ $fpr =~ ^[0-9A-F]{40}$ ]] && pacman-key --init &&
        pacman-key --populate archlinux && pacman-key --add "$1/orbitop-archive-keyring.asc" &&
        pacman-key --lsign-key "$fpr" &&
        printf '%s\n' '[orbitop]' 'SigLevel = Required DatabaseRequired' "Server = ${PAGES}arch/\$arch" >> "$CONF" &&
        point "$CONF" "file://$1/"
}

# never_introducer: orbitop-trusted of the installed package is exactly the line "<fingerprint>:3:", owner trust 3
# ("never"): the key never helps to validate another key in pacman's keyring (docs/release.md, Arch). Exactly 44
# bytes as well: $(cat) drops a NUL byte, which the pattern alone would let through.
never_introducer() {
    local line
    line=$(cat -- "$TRUSTED") && echo "TRUSTED $line" && [[ $line =~ ^[0-9A-F]{40}:3:$ ]] &&
        [ "$(wc -l < "$TRUSTED")" -eq 1 ] && [ "$(wc -c < "$TRUSTED")" -eq 44 ]
}

install_pkg() { net pacman -Syu orbitop --noconfirm && never_introducer; }

tools() { net pacman -S --needed --noconfirm python-pytest shellcheck desktop-file-utils appstream; }

installed() { pacman -Q orbitop | awk '{ print $2 }'; }
offered() { pacman -Qp "$1"/arch/x86_64/orbitop-*-any.pkg.tar.zst | awk '{ print $2 }'; }

update_from() { point "$CONF" "file://$1/" && net pacman -Syu --noconfirm; }

files_of() { pacman -Qlq orbitop; }
owned() { pacman -Qo -- "$1" 2> /dev/null; }
packages() { pacman -Q; }

# -Syy: pacman -Sy downloads a database only when it changed.
remove() { files_of > "$STATE/files" && pacman -R orbitop --noconfirm && quiet pacman -Syy; }

# drop_keys: the second line of the README's uninstall, without sudo: every primary key with exactly the user ID of
# the archive key leaves pacman's keyring (pacman's homedir is 755 on purpose, hence --no-permission-warning).
drop_keys() {
    gpg --homedir /etc/pacman.d/gnupg --no-options --no-permission-warning --batch --with-colons --list-keys \
        '=orbitop archive signing key' | awk -F: '$1 == "pub" { p = 1; next } p && $1 == "fpr" { print $10 } { p = 0 }' |
        grep -xE '[0-9A-F]{40}' | xargs -r -n1 pacman-key --delete
}

# pacman has no purge: the section leaves pacman.conf (back to the Pages address first: point refuses if pacman
# changed it), the keys the keyring, and pacman -Sc drops the database of the source (README).
purge() {
    local was now
    point "$CONF" "$PAGES" && sed -i '/^\[orbitop\]$/,$d' "$CONF" &&
        was=$(sha256sum < "$STATE/pacman.conf") && now=$(sha256sum < "$CONF") && [ "$was" = "$now" ] &&
        drop_keys && refused 'No public key' pacman-key --list-keys '=orbitop archive signing key' &&
        ls /var/lib/pacman/sync && pacman -Sc --noconfirm && leftovers "$STATE/files" && quiet pacman -Syy &&
        absent '/var/lib/pacman/sync/orbitop.*'
}

tamper_index() { flip "$1/arch/x86_64/orbitop.db"; }

tamper() { tampered db 'invalid or corrupted database (PGP signature)' tamper_index; }

refresh_index() { pacman -Sy; }

# The counter release (scripts/matrix/counters.sh). The owner of intel_gpu_top as in the security document 0.3.0,
# B2.4; pacman names the hook by its Description when it runs (orbitop-counters.hook), which has no Remove.
COUNTER_CASES=(orbitop_install_manual_cap file_list reinstall_owner_off on_off reinstall_owner_on owner_remove
    owner_first_install_on rev2_upgrade_on remove_on remove_broken_helper purge manual_rule_untouched upgrade_from_020
    joint_upgrade)
OWNER=intel-gpu-tools
JOINT=(pacman_pair)  # B2.4, 6: pacman -U of both files
TRIGGERED='^\([0-9]+/[0-9]+\) Applying the orbitop counter release, if turned on\.\.\.$'
REMOVE_TRIGGERED=''
# pre_remove ("off || true", B2.8) prints nothing of its own; pacman loads orbitop.install with /bin/sh (bash), which
# names the script in front ("/tmp/alpm_XXXXXX/.INSTALL: line N: ").
REVOKE_FAILED='/usr/lib/orbitop/counterhelper: Permission denied$'

install_owner() { net pacman -S --noconfirm -- "$OWNER" && [ "$(pacman -Qqo -- "$TOOL")" = "$OWNER" ]; }
reinstall_owner() { net pacman -S --noconfirm -- "$OWNER"; }
remove_owner() { remove_pkg "$OWNER"; }

# fake_owner N: OWNER as the next version, <installed pkgver>.fakeN (newer for vercmp), packed here by hand like
# makepkg (.PKGINFO and the files, owned by root); its intel_gpu_top is a copy of the installed program (an ELF file;
# cp takes no capability along), nothing else, and no dependencies. Prints the file.
fake_owner() {
    local dir=$STATE/owner-$1 was version
    was=$(pacman -Q -- "$OWNER") && was=${was#* } && version=${was%-*}.fake$1-${was##*-} &&
        [ "$(vercmp "$version" "$was")" -gt 0 ] && elf "$TOOL" && rm -rf -- "$dir" && mkdir -p "$dir/usr/bin" &&
        cp -- "$TOOL" "$dir/usr/bin/" &&
        printf '%s\n' "pkgname = $OWNER" "pkgbase = $OWNER" "pkgver = $version" "arch = $(uname -m)" \
            "pkgdesc = the next version of $OWNER, for the matrix" "url = https://example.com/" \
            "builddate = $(date +%s)" "packager = orbitop matrix <matrix@example.com>" \
            "size = $(stat -c %s -- "$TOOL")" > "$dir/.PKGINFO" &&
        bsdtar -C "$dir" --uid 0 --gid 0 --zstd -cf "$dir.pkg.tar.zst" .PKGINFO usr && echo "$dir.pkg.tar.zst"
}

# install_file FILE: pacman -U of a copy, also of the same or a lower version. pacman checks a .sig next to the
# file (probe on 2026-11-20), and the key of SITE left pacman's keyring in the step purge; the signatures are the
# matter of the steps keyring, install and tamper.
install_file() { cp -- "$1" "$STATE/" && pacman -U --noconfirm -- "$STATE/${1##*/}"; }
pacman_pair() { pacman -U --noconfirm -- "$1" "$2"; }  # one transaction for both files
remove_pkg() { pacman -R --noconfirm -- "$1"; }
purge_pkg() { ! pacman -Q -- "$1" > /dev/null 2>&1 || remove_pkg "$1"; }  # pacman has no purge: a removal is final
pkg_files() { pacman -Qlq orbitop; }

# orbitop_file rev1|rev2|v020: orbitop of SITE, or the one check-distros.sh built of the same tree as revision 2
# (REV2) or of the tag v0.2.0 (V020).
orbitop_file() {
    case $1 in
        rev1) only_file "$SITE"/arch/x86_64/orbitop-*-any.pkg.tar.zst ;;
        rev2) only_file "$REV2"/arch/orbitop-*-any.pkg.tar.zst ;;
        v020) only_file "$V020"/arch/orbitop-*-any.pkg.tar.zst ;;
        *) return 1 ;;
    esac
}
