# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# pacman (Arch Linux) for scripts/matrix/inside.sh, which sources it after lib.sh. The source is set up by hand as in
# the README: the key with pacman-key, the section [orbitop] at the end of pacman.conf (pacman takes a package from
# the first repository that has it).
# shellcheck shell=bash disable=SC2034,SC2154  # NOISE is read by lib.sh, PAGES and STATE come from it

NOISE='^(warning|error):'
CONF=/etc/pacman.conf

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

install_pkg() { net pacman -Syu orbitop --noconfirm; }

tools() { net pacman -S --needed --noconfirm python-pytest shellcheck desktop-file-utils appstream; }

installed() { pacman -Q orbitop | awk '{ print $2 }'; }
offered() { pacman -Qp "$1"/arch/x86_64/orbitop-*-any.pkg.tar.zst | awk '{ print $2 }'; }

update_from() { point "$CONF" "file://$1/" && net pacman -Syu --noconfirm; }

files_of() { pacman -Qlq orbitop; }
owned() { pacman -Qo -- "$1" > /dev/null 2>&1; }
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
