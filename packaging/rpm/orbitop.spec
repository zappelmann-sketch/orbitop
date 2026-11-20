# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# One recipe for Fedora and openSUSE (branches on suse_version), built by packaging/rpm/build-inside.sh: it defines
# orbitop_version (from orbitop/__init__.py) and orbitop_release and appends %changelog from the metainfo.
Name:           orbitop
Version:        %{orbitop_version}
Release:        %{orbitop_release}
Summary:        System monitor for CPU, memory, GPU, network and processes
License:        GPL-3.0-or-later AND OFL-1.1 AND CC0-1.0
URL:            https://github.com/zappelmann-sketch/orbitop
Source0:        %{name}-%{version}.tar
BuildArch:      noarch
BuildRequires:  /usr/bin/appstream-util
BuildRequires:  /usr/bin/desktop-file-validate
Requires:       python3 >= 3.12
%if 0%{?suse_version}
BuildRequires:  python-rpm-macros
BuildRequires:  python3
Requires:       python3-gobject
Requires:       typelib-1_0-Gtk-4_0
Requires:       typelib-1_0-WebKit-6_0
Requires:       python3-gobject-Gdk
# pkexec is a package of its own here, which polkit does not pull in; on Fedora, polkit ships /usr/bin/pkexec.
Requires:       /usr/bin/pkexec
%else
BuildRequires:  python3-devel
Requires:       python3-gobject
Requires:       gtk4
Requires:       webkitgtk6.0
%endif
Requires:       polkit
Suggests:       igt-gpu-tools

%description
orbitop shows the load of your computer at a glance: processor, memory,
graphics card, network, disks, sensors and the running processes.

%prep
%autosetup

%build
# Pure Python: nothing to build.

%install
bash packaging/install-tree.sh %{buildroot}
# The package carries the byte code (Fedora Python guidelines), so that no untracked cache is written at run time.
%if 0%{?suse_version}
%py3_compile %{buildroot}%{_datadir}/orbitop/orbitop
%else
%py_byte_compile %{python3} %{buildroot}%{_datadir}/orbitop/orbitop/
%endif

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.zappelmann_sketch.orbitop.desktop
appstream-util validate-relax --nonet %{buildroot}%{_datadir}/metainfo/io.github.zappelmann_sketch.orbitop.metainfo.xml

%files
%license LICENSE
%{_bindir}/orbitop
%{_datadir}/orbitop/
%{_prefix}/lib/orbitop/
%{_datadir}/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy
%{_datadir}/applications/io.github.zappelmann_sketch.orbitop.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.zappelmann_sketch.orbitop.svg
%{_datadir}/metainfo/io.github.zappelmann_sketch.orbitop.metainfo.xml

%changelog
