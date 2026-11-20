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
# the macro _udevrulesdir for the udev rule in the file list
BuildRequires:  systemd-rpm-macros
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

# The counter release (security document 0.3.0, B2.4 and B2.8). No scriptlet ever turns it on, and none fails
# because of the helper. "sync" changes nothing without the marker /etc/orbitop/counters-released, which only the
# helper creates after the admin password.
%preun
# Only on the final removal ($1 = 0), never on an upgrade: an update keeps the release.
if [ "$1" -eq 0 ]; then /usr/lib/orbitop/counterhelper off || :; fi

%postun
# The backup for a helper that could not run (M-3): the marker goes anyway, durably, and the empty directory too.
if [ "$1" -eq 0 ]; then rm -f /etc/orbitop/counters-released; rmdir /etc/orbitop 2>/dev/null || :; sync -f /etc 2>/dev/null || :; fi

%posttrans
# Also when orbitop and the Intel tools come in one transaction, where no file trigger reaches orbitop (I-1, E4).
/usr/lib/orbitop/counterhelper sync || :

%filetriggerin -- /usr/bin/intel_gpu_top
# Each new copy of the file loses the capability. A transaction file trigger on a path never fires (R4.4).
/usr/lib/orbitop/counterhelper sync || :

%files
%license LICENSE
%{_bindir}/orbitop
%{_datadir}/orbitop/
%dir %{_prefix}/lib/orbitop
%{_prefix}/lib/orbitop/killhelper
%{_prefix}/lib/orbitop/counterhelper
%dir %attr(0711,root,root) %{_sysconfdir}/orbitop
%{_udevrulesdir}/70-orbitop-counters.rules
%{_datadir}/polkit-1/actions/io.github.zappelmann-sketch.orbitop.policy
%{_datadir}/applications/io.github.zappelmann_sketch.orbitop.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.zappelmann_sketch.orbitop.svg
%{_datadir}/metainfo/io.github.zappelmann_sketch.orbitop.metainfo.xml

%changelog
