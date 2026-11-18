# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
# Tool image for packaging/site/rpm-inside.sh: rpmsign, createrepo_c and gpg, installed here with network and without
# the gpg-agent socket, so that the container that gets the socket installs nothing and runs without network.
# Built by scripts/build-site.sh: docker build -t TAG --build-arg BASE=fedora:latest|opensuse/tumbleweed - < this file
ARG BASE
FROM ${BASE}
RUN if command -v dnf >/dev/null; then \
        dnf -y -q install rpm-sign createrepo_c gnupg2 cpio diffutils gawk && dnf clean all; \
    else \
        zypper -n -q refresh && zypper -n -q install --no-recommends createrepo_c gpg2 cpio diffutils gawk && \
        zypper -n clean -a; \
    fi
