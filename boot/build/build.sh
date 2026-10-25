#!/bin/bash
# Executed in the privileged builder, with source read-only and output separate.
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Image building needs root in the build container.' >&2; exit 1; }
SOURCE_DIR=${ULSIM_SOURCE_DIR:-/src}
OUTPUT_DIR=${ULSIM_OUTPUT_DIR:-/out}
BUILD_DIR=${ULSIM_BUILD_DIR:-/build/live}
test -f "$SOURCE_DIR/ulsim/target.py"
BUILD_CA_DIR=${ULSIM_BUILD_CA_DIR:-}
# /cloud-ca is the optional readonly trust mount used by the cloud build runner.
if [ -z "$BUILD_CA_DIR" ] && [ -d /cloud-ca ]; then BUILD_CA_DIR=/cloud-ca; fi
if [ -n "$BUILD_CA_DIR" ]; then
  test -d "$BUILD_CA_DIR"
  for cert in "$BUILD_CA_DIR"/*.crt; do
    test -f "$cert" || continue
    install -m 644 "$cert" /usr/local/share/ca-certificates/
  done
  update-ca-certificates >/dev/null
fi
mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"
cd "$BUILD_DIR"
# Retain verified package/bootstrap caches while discarding stale stage outputs.
if [ -f config/common ]; then lb clean; fi
lb config --mode debian --distribution trixie --architectures amd64 \
  --binary-images iso-hybrid --bootloaders 'syslinux grub-efi' \
  --archive-areas 'main contrib non-free non-free-firmware' \
  --apt-secure true --apt-recommends false --debian-installer false --cache-stages bootstrap \
  --security true --updates true --firmware-chroot true --firmware-binary true \
  --linux-flavours amd64 --memtest none --iso-volume ULSIM_LIVE \
  --mirror-bootstrap https://deb.debian.org/debian/ \
  --mirror-chroot https://deb.debian.org/debian/ \
  --mirror-binary https://deb.debian.org/debian/ \
  --mirror-chroot-security https://security.debian.org/debian-security/ \
  --mirror-binary-security https://security.debian.org/debian-security/ \
  --bootappend-live 'boot=live components live-config.nocomponents=user-setup,ssh hostname=ulsim locales=en_US.UTF-8 keyboard-layouts=us'
mkdir -p config/package-lists config/includes.chroot/usr/local/lib/python3.13/dist-packages \
  config/includes.chroot/usr/local/sbin config/includes.chroot/etc/systemd/system \
  config/includes.chroot/etc/ssh/sshd_config.d config/hooks/live
cp "$SOURCE_DIR/boot/configuration/packages.list.chroot" config/package-lists/ulsim.list.chroot
rm -rf config/includes.chroot/usr/local/lib/python3.13/dist-packages/ulsim
cp -a "$SOURCE_DIR/ulsim" config/includes.chroot/usr/local/lib/python3.13/dist-packages/
find config/includes.chroot -type d -name __pycache__ -prune -exec rm -rf {} +
install -m 755 "$SOURCE_DIR/boot/scripts/provision.py" config/includes.chroot/usr/local/sbin/ulsim-provision
install -m 644 "$SOURCE_DIR/boot/services/ulsim-provision.service" config/includes.chroot/etc/systemd/system/
install -m 644 "$SOURCE_DIR/boot/configuration/sshd.conf" config/includes.chroot/etc/ssh/sshd_config.d/10-ulsim.conf
install -m 755 "$SOURCE_DIR/boot/configuration/0100-ulsim.hook.chroot" config/hooks/live/
# Separate stages so bootstrap cache restoration cannot discard injected build trust.
lb bootstrap
if [ -n "$BUILD_CA_DIR" ]; then
  mkdir -p chroot/usr/local/share/ca-certificates chroot/etc/ssl/certs
  for cert in "$BUILD_CA_DIR"/*.crt; do
    test -f "$cert" || continue
    install -m 644 "$cert" chroot/usr/local/share/ca-certificates/
  done
  cp /etc/ssl/certs/ca-certificates.crt chroot/etc/ssl/certs/ca-certificates.crt
fi
lb chroot
# The distributed image must trust Debian's normal CA bundle, not the build proxy.
if [ -n "$BUILD_CA_DIR" ]; then
  for cert in "$BUILD_CA_DIR"/*.crt; do
    test -f "$cert" || continue
    rm -f "chroot/usr/local/share/ca-certificates/$(basename "$cert")"
  done
  chroot chroot update-ca-certificates --fresh >/dev/null
fi
if [ -n "$(find chroot/etc/ssh -maxdepth 1 -name 'ssh_host_*_key' -print -quit)" ]; then
  echo 'Refusing to distribute SSH host private keys' >&2; exit 1
fi
lb binary
test -s live-image-amd64.hybrid.iso
python3 "$SOURCE_DIR/boot/build/validate-image.py" live-image-amd64.hybrid.iso
cp live-image-amd64.hybrid.iso "$OUTPUT_DIR/ulsim-live-amd64.img"
cp live-image-amd64.packages "$OUTPUT_DIR/ulsim-live-amd64.packages"
xz -T2 -6 -k -f "$OUTPUT_DIR/ulsim-live-amd64.img"
cd "$OUTPUT_DIR"
sha256sum ulsim-live-amd64.img.xz > SHA256SUMS.txt
printf 'Debian trixie amd64 live-build; BIOS and UEFI hybrid image\n' > BUILD-INFO.txt
date -u '+Built: %Y-%m-%dT%H:%M:%SZ' >> BUILD-INFO.txt
git -C "$SOURCE_DIR" rev-parse HEAD >> BUILD-INFO.txt 2>/dev/null || true
