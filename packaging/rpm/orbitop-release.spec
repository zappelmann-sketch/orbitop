# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Package source and signing key in a package of their own (plan K3, Fedora Third Party Repository Policy).
# packaging/rpm/build-inside.sh defines keyring_version and appends %changelog, both only from
# packaging/keyring.version: the same version gives the same bytes, whatever orbitop is built alongside.
# Removing the package removes both files.
Name:           orbitop-release
Version:        %{keyring_version}
Release:        1
Summary:        OpenPGP key and package source of the orbitop repository
License:        GPL-3.0-or-later
URL:            https://github.com/zappelmann-sketch/orbitop
Source0:        RPM-GPG-KEY-orbitop
Source1:        orbitop-fedora.repo
Source2:        orbitop-opensuse.repo
Source3:        LICENSE
BuildArch:      noarch
%if 0%{?suse_version}
%global reposdir %{_sysconfdir}/zypp/repos.d
%global repofile %{SOURCE2}
%else
%global reposdir %{_sysconfdir}/yum.repos.d
%global repofile %{SOURCE1}
%endif

%description
Installs the signing key of the orbitop package repository and the
repository definition that uses it, so that new versions of orbitop
arrive with the regular system update.

%prep
%setup -q -c -T
cp -p %{SOURCE3} .

%build
# Only data files: nothing to build.

%install
install -D -m 0644 %{SOURCE0} %{buildroot}%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-orbitop
install -D -m 0644 %{repofile} %{buildroot}%{reposdir}/orbitop.repo

%files
%license LICENSE
%dir %{_sysconfdir}/pki/rpm-gpg
%{_sysconfdir}/pki/rpm-gpg/RPM-GPG-KEY-orbitop
%config(noreplace) %{reposdir}/orbitop.repo

%changelog
