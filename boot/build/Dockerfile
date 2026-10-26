FROM debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get -o APT::Update::Error-Mode=any update && apt-get install -y --no-install-recommends \
    live-build debootstrap debian-archive-keyring ca-certificates \
    dctrl-tools apt-utils debconf cpio fdisk parted zsync bzip2 wget \
    squashfs-tools xorriso isolinux syslinux-common syslinux-utils grub-pc-bin grub-efi-amd64-bin grub-efi-ia32-bin \
    mtools dosfstools xz-utils file python3 librsvg2-bin fonts-dejavu-core isomd5sum && rm -rf /var/lib/apt/lists/*
WORKDIR /build
ENTRYPOINT ["/bin/bash", "/src/boot/build/build.sh"]
