FROM --platform=linux/riscv64 registry.opensuse.org/opensuse/bci/python:latest

ENV LANG=C.UTF-8

# Avoid running zypper inside qemu-riscv64. It can stall in repository
# metadata/GPG handling on x86_64 hosts, so this image bootstraps the small
# RPM toolchain needed by the artifact smoke cases directly from the official
# openSUSE RISC-V ports repository.
RUN set -eux; \
    mkdir -p /tmp/evident-rpms; \
    cd /tmp/evident-rpms; \
    base="http://download.opensuse.org/ports/riscv/tumbleweed/repo/oss"; \
    for rpm_url in \
      "$base/riscv64/librpmbuild10-4.20.1-7.1.riscv64.rpm" \
      "$base/riscv64/rpm-build-4.20.1-7.1.riscv64.rpm" \
      "$base/riscv64/debugedit-5.1-1.2.riscv64.rpm" \
      "$base/riscv64/libdw1-0.194-1.1.riscv64.rpm" \
      "$base/riscv64/libelf1-0.194-1.1.riscv64.rpm" \
      "$base/riscv64/libgomp1-gcc15-15.2.1+git10776-3.1.riscv64.rpm" \
      "$base/riscv64/libmagic1-5.47-4.1.riscv64.rpm" \
      "$base/riscv64/libarchive13-3.8.7-1.1.riscv64.rpm" \
      "$base/riscv64/liblz1-1.16-1.1.riscv64.rpm" \
      "$base/riscv64/liblz4-1-1.10.0-2.2.riscv64.rpm" \
      "$base/riscv64/file-5.47-4.1.riscv64.rpm" \
      "$base/riscv64/patch-2.8-2.2.riscv64.rpm" \
      "$base/riscv64/fdupes-2.4.0-1.2.riscv64.rpm" \
      "$base/riscv64/libpython3_13-1_0-3.13.13-5.1.riscv64.rpm" \
      "$base/riscv64/python313-base-3.13.13-5.1.riscv64.rpm" \
      "$base/riscv64/python313-3.13.13-5.1.riscv64.rpm" \
      "$base/riscv64/python313-devel-3.13.13-5.1.riscv64.rpm" \
      "$base/noarch/python-rpm-macros-20260317.5e02b19-1.2.noarch.rpm" \
      "$base/noarch/python-rpm-generators-20260317.5e02b19-1.2.noarch.rpm" \
      "$base/noarch/systemd-rpm-macros-26-1.2.noarch.rpm" \
      "$base/noarch/python313-pip-26.1.2-1.1.noarch.rpm" \
      "$base/noarch/python313-setuptools-80.9.0-3.1.noarch.rpm" \
      "$base/noarch/python313-wheel-0.46.3-2.4.noarch.rpm" \
      "$base/noarch/python313-packaging-26.2-1.1.noarch.rpm" \
      "$base/noarch/python313-pytest-9.0.3-1.1.noarch.rpm" \
      "$base/noarch/python313-pluggy-1.6.0-2.4.noarch.rpm" \
      "$base/noarch/python313-iniconfig-2.3.0-1.3.noarch.rpm" \
      "$base/noarch/python313-Pygments-2.20.0-2.1.noarch.rpm"; do \
      curl -fsSLO "$rpm_url"; \
    done; \
    rpm -Uvh --nodeps ./*.rpm; \
    rpmbuild --version; \
    python3.13 --version; \
    rm -rf /tmp/evident-rpms
