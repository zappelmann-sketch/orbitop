# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# pacman (Arch Linux) for scripts/matrix/inside.sh, which sources it and provides point, quiet, flip, leftovers and
# PAGES. The source is set up by hand as in the README: the key with pacman-key, the section [orbitop] at the end
# of pacman.conf (pacman takes a package from the first repository that has it).
# shellcheck shell=bash disable=SC2034,SC2154  # inside.sh reads NOISE and TAMPERED, and it sets PAGES

NOISE='^(warning|error):'
TAMPERED='invalid or corrupted database (PGP signature)'
CONF=/etc/pacman.conf

refresh() { pacman -Syu --noconfirm; }  # Arch supports only full upgrades

# keyring ROOT: the image has no local master key, so pacman-key --init first (docs/release.md); the fingerprint is
# the one the README shows.
keyring() {
    local fpr
    [ -f /tmp/pacman.conf ] || cp -- "$CONF" /tmp/pacman.conf || return 1  # as it was, for purge
    fpr=$(gpg --with-colons --show-keys "$1/orbitop-archive-keyring.asc" | awk -F: '$1 == "fpr" { print $10; exit }') &&
        echo "$fpr" > /tmp/fpr && pacman-key --init && pacman-key --populate archlinux &&
        pacman-key --add "$1/orbitop-archive-keyring.asc" && pacman-key --lsign-key "$fpr" &&
        printf '%s\n' '[orbitop]' 'SigLevel = Required DatabaseRequired' "Server = ${PAGES}arch/\$arch" >> "$CONF" &&
        point "$CONF" "file://$1/"
}

install() { pacman -Syu orbitop --noconfirm; }

tools() { pacman -S --needed --noconfirm python-pytest shellcheck desktop-file-utils appstream; }

installed() { pacman -Q orbitop | awk '{ print $2 }'; }
offered() { pacman -Qp "$1"/arch/x86_64/orbitop-*-any.pkg.tar.zst | awk '{ print $2 }'; }

update_from() { point "$CONF" "file://$1/" && pacman -Syu --noconfirm; }

files_of() { pacman -Qlq orbitop; }
owned() { pacman -Qo -- "$1" > /dev/null 2>&1; }

remove() { files_of > /tmp/files && pacman -R orbitop --noconfirm && quiet pacman -Sy; }

# pacman has no purge: the section leaves pacman.conf, the key the keyring, and pacman -Sc drops the database of
# the source (README).
purge() {
    local fpr
    fpr=$(cat /tmp/fpr) && sed -i '/^\[orbitop\]$/,$d' "$CONF" &&
        [ "$(sha256sum < /tmp/pacman.conf)" = "$(sha256sum < "$CONF")" ] &&  # the image has no cmp
        pacman-key --delete "$fpr" && ! pacman-key --list-keys "$fpr" && ls /var/lib/pacman/sync &&
        pacman -Sc --noconfirm && leftovers /tmp/files && quiet pacman -Sy && ! ls /var/lib/pacman/sync/orbitop.*
}

tamper_index() { flip "$1/arch/x86_64/orbitop.db"; }

refresh_index() { pacman -Sy; }
