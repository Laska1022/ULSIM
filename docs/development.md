# Build and validate

Python 3.11+ runs the Windows/Linux controller. Target code runs on Debian 13's Python 3.13 and uses standard-library/Linux utilities. Use the existing checkout in cloud tasks; each task is already isolated.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
python -m build
```

The integration suite runs a real loopback SSH transport for authentication, pinned identity, JSON stdin/stdout and error handling. Safety unit tests exercise actual validation with synthetic hardware data; they do not prove a physical disk installation. Linux-only installer tests are skipped on Windows, where controller/planning/transport tests run.

## Live image

`bash boot/build/docker-build.sh` uses a pinned Debian builder, official live-build, signed Debian repositories, maintained Syslinux/GRUB, a Linux kernel and live SquashFS. It emits a real BIOS/UEFI hybrid ISO under the raw image filename `dist/ulsim-live-amd64.img`, compressed `.img.xz`, SHA256SUMS, package manifest and build information. A structural validator requires BIOS and EFI boot entries and a real live root filesystem. Package updates make builds repeatable by procedure but not bit-for-bit reproducible across dates; the manifest records resolved versions.

Use a Linux Docker engine, approximately 20 GB free space and at least 4 GB RAM. The builder runs privileged in a disposable container with source read-only and a named build-cache volume. Reuse successful download caches. After modifying included source or boot configuration, invalidate the live-build chroot/binary stages before rebuilding; merely rerunning a completed cached stage may retain older code. Never publish cached outputs without verifying included source.

## Acceptance tests

See [tests/vm/README.md](../tests/vm/README.md). Both BIOS and UEFI must pass live boot, DHCP, pinned SSH, inspection, safe plan, actual Debian install, independent installed-disk boot, trust continuity and Nginx HTTP response. The runner uses disposable virtual disks and retains logs. TCG works without `/dev/kvm`, but is slower. Optional BIOS/MBR testing uses `--partition-table mbr`.

## CI and releases

`.github/workflows/test.yml` runs Windows and Linux controller/safety tests. Select **Build and verify live image** in GitHub Actions and **Run workflow** for image+BIOS+UEFI acceptance. Download `ulsim-live-amd64` and VM evidence artifacts from the successful run. A failed or unexecuted workflow is not a validated release.

After all checks pass, push a reviewed `v*` tag to run `.github/workflows/release.yml`; it rebuilds, waits for both VM checks, builds the controller package, and publishes assets using GitHub's workflow token. Source archives are available on the release page. `install-windows.ps1` expects the extracted source tree, not the standalone script alone. Do not tag an unverified revision as a finished product.

Cloud execution cannot establish compatibility with every legacy BIOS, Wi-Fi adapter, Windows installation, or physical disk. Keep measured results and unrun checks explicit in PROGRESS.md and release notes.
