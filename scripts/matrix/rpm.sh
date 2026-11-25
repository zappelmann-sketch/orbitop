# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# The rpm part of scripts/matrix/dnf.sh and zypper.sh, sourced by scripts/matrix/inside.sh after lib.sh and before
# either of them; they set FAMILY (fedora, opensuse), the directory of their packages below rpm/ in the site, and
# TAMPERED, the reason their index refresh names for a changed repomd.xml.
# shellcheck shell=bash disable=SC2034,SC2154  # counters.sh reads the values of the counter release; FAMILY, TAMPERED
# and those of the counter release come from dnf.sh or zypper.sh, STATE from lib.sh, TOOL from counters.sh

installed() { rpm -q --qf '%{VERSION}-%{RELEASE}' -- orbitop; }
offered() { rpm -qp --qf '%{VERSION}-%{RELEASE}' -- "$1/rpm/$FAMILY"/orbitop-[0-9]*.noarch.rpm; }
files_of() { rpm -ql -- orbitop orbitop-release; }
owned() { rpm -qf -- "$1" 2> /dev/null; }
packages() { rpm -qa | sort; }

# rpm_key ROOT: the key of the site into the rpm database, as the README does before the first package (no
# unknown key then for zypper, and dnf asks only for its copy for the metadata); exactly one key is new there. Then
# every RPM of ROOT must carry a signature that verifies: rpm -K reports "digests OK" with exit 0 for an RPM without
# one.
rpm_key() {
    local before after checked
    before=$(rpmkeys --list) && rpm --import -- "$1/orbitop-archive-keyring.asc" && after=$(rpmkeys --list) || return 1
    [ "$(grep -cvxF -- "$before" <<< "$after")" -eq 1 ] && checked=$(rpm -K -- "$1/rpm/$FAMILY"/*.rpm) || return 1
    printf '%s\n' "$checked"
    ! grep -v -- ': digests signatures OK$' <<< "$checked"
}

# release_package ROOT: orbitop-release of ROOT under the name of the release asset (plan K3), in STATE.
release_package() { cp -- "$1/rpm/$FAMILY"/orbitop-release-*.noarch.rpm "$STATE/orbitop-release-$FAMILY.rpm"; }

# drop_key: the line of the README's full uninstall that deletes every key named like the archive key from the rpm
# database (without sudo); afterwards it lists none.
drop_key() {
    local keys
    rpmkeys --list | grep -F 'orbitop archive signing key' | sed 's/[: ].*//' | xargs -r -n1 rpmkeys --delete &&
        keys=$(rpmkeys --list) && ! grep -F 'orbitop archive signing key' <<< "$keys"
}

# tamper_index ROOT: one digit of <revision> in repomd.xml changed; the XML stays well-formed, so the signature check
# has to refuse it (zypper parses repomd.xml before it checks the signature).
tamper_index() {
    local repomd=$1/rpm/$FAMILY/repodata/repomd.xml at
    at=$(grep -bo '<revision>[0-9]' "$repomd" | cut -d: -f1) && flip "$repomd" $((at + 10))
}

tamper() { tampered repomd "$TAMPERED" tamper_index; }

# The counter release (scripts/matrix/counters.sh): its cases, with those of RPM only, B2.4, 7 and 8 (below). OWNER,
# PKEXEC_PROVIDER, TRIGGERED, JOINT, get_pkg, reget_pkg, remove_pkg and install_new come from dnf.sh or zypper.sh.
COUNTER_CASES=(orbitop_install_manual_cap pkexec_provider file_list reinstall_owner_off on_off reinstall_owner_on
    rpm_verify owner_remove owner_first_install_on rev2_upgrade_on remove_on remove_broken_helper purge
    manual_rule_untouched upgrade_from_020 joint_upgrade)
REMOVE_TRIGGERED=''  # %filetriggerin runs only when the file comes
# %preun ("off || :", B2.8) prints nothing of its own; rpm runs it with /bin/sh, bash on Fedora and openSUSE, which
# names the script in front ("/var/tmp/rpm-tmp.XXXXXX: line N: ").
REVOKE_FAILED='/usr/lib/orbitop/counterhelper: Permission denied$'

install_owner() { net get_pkg "$OWNER" && [ "$(rpm -qf --qf '%{NAME}\n' -- "$TOOL")" = "$OWNER" ]; }
reinstall_owner() { net reget_pkg "$OWNER"; }
remove_owner() { remove_pkg "$OWNER"; }

# fake_owner N: OWNER as the next release, <installed release>.fakeN with the installed epoch, version, architecture
# and vendor (zypper up keeps the vendor), built here with rpmbuild; its intel_gpu_top is a copy of the installed
# program (an ELF file; cp takes no capability along) with one more byte at the end, as a new version brings a changed
# program: rpm on openSUSE keeps an unchanged file (%_minimize_writes). Nothing else, and no dependencies. Prints the
# file.
fake_owner() {
    local dir=$STATE/owner-$1 epoch version release arch vendor
    IFS='|' read -r epoch version release arch vendor < <(rpm -q --qf '%{EPOCH}|%{VERSION}|%{RELEASE}|%{ARCH}|%{VENDOR}\n' \
        -- "$OWNER") && elf "$TOOL" || return 1
    { command -v rpmbuild > /dev/null || net get_pkg rpm-build >&2; } && rm -rf -- "$dir" && mkdir -p "$dir/SPECS" &&
        cp -- "$TOOL" "$dir/intel_gpu_top" && echo >> "$dir/intel_gpu_top" || return 1
    {
        [ "$epoch" = "(none)" ] || echo "Epoch: $epoch"
        [ "$vendor" = "(none)" ] || echo "Vendor: $vendor"
        printf '%s\n' "Name: $OWNER" "Version: $version" "Release: $release.fake$1" "License: MIT" "AutoReqProv: no" \
            "Summary: the next version of $OWNER, for the matrix" "%description" "Only $TOOL, a copy." "%install" \
            "install -D -m 0755 $dir/intel_gpu_top %{buildroot}$TOOL" "%files" "$TOOL"
    } > "$dir/SPECS/owner.spec" &&
        rpmbuild -bb --target "$arch" --define "_topdir $dir" --define 'debug_package %{nil}' \
            --define '__spec_install_post %{nil}' --define '_build_id_links none' -- "$dir/SPECS/owner.spec" >&2 &&
        only_file "$dir/RPMS/$arch/$OWNER-"*.rpm
}

# install_file FILE: rpm -U, which also takes the same or a lower version; the first time the package manager
# (install_new), which brings what dnf remove took along in the step remove. --nosignature: rpm 6 (Fedora) refuses
# the unsigned packages of /rev2 and /v020 and those of SITE, whose key left the rpm database in the step purge; the
# signatures are the matter of the steps keyring, install and tamper.
install_file() {
    if rpm -q -- orbitop > /dev/null; then
        rpm -U --replacepkgs --oldpackage --nosignature -- "$1"
    else
        install_new "$1"
    fi
}
rpm_pair() { rpm -U --nosignature -- "$1" "$2"; }  # one rpm transaction for both files
purge_pkg() { ! rpm -q -- "$1" > /dev/null || remove_pkg "$1"; }  # rpm has no purge: a removal is final
pkg_files() { rpm -ql -- orbitop; }

# orbitop_file rev1|rev2|v020: orbitop of SITE, or the one check-distros.sh built of the same tree as revision 2
# (REV2) or of the tag v0.2.0 (V020), for this family.
orbitop_file() {
    case $1 in
        rev1) only_file "$SITE/rpm/$FAMILY"/orbitop-[0-9]*.noarch.rpm ;;
        rev2) only_file "$REV2/rpm-$FAMILY"/orbitop-[0-9]*.noarch.rpm ;;
        v020) only_file "$V020/rpm-$FAMILY"/orbitop-[0-9]*.noarch.rpm ;;
        *) return 1 ;;
    esac
}

# B2.4, 7: after on, rpm -V of the owner reports the capability on intel_gpu_top as a changed attribute P (the
# exception the stage-2 spec allows), and nothing else; the line goes into the log for the report.
case_rpm_verify() {
    local out rc=0
    helper on 0 && has_cap || return 1
    out=$(rpm -V -- "$OWNER") || rc=$?
    printf 'RPM-V %s\n' "$out"
    [ "$rc" -eq 1 ] && [[ $out =~ ^\.{8}P\ +/usr/bin/intel_gpu_top$ ]]
}

# B2.4, 8 and E5: /usr/bin/pkexec comes from polkit's package (PKEXEC_PROVIDER), not from run0-wrappers.
case_pkexec_provider() {
    local names
    names=$(rpm -q --whatprovides --qf '%{NAME}\n' -- /usr/bin/pkexec) && echo "PKEXEC $names" &&
        [ "$names" = "$PKEXEC_PROVIDER" ]
}
