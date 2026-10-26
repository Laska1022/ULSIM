# Recorded validation runs

These JSON files preserve measured local QEMU results. They do not establish Windows, physical-hardware, or GitHub Actions success.

- `*-integration.json`: baseline BIOS/GPT and UEFI/GPT installation, independent installed-disk boot, pinned SSH identity, and Nginx passed on the audited integration build.
- `uefi-clean-build.json`: the clean build completed the public `install --wait` workflow and web checks. Additional profiles were not requested.
- `bios-clean-build.json`: the same clean build completed installation, reboot, controller orchestration, and web checks, then failed its extended profile test because the upstream AdGuard executable path begins with `./`. Its `passed: false` records that failure.

Clean-build hashes were calculated from the retained, unchanged image after the test. These historical records must not be relabelled as validation of a later source revision or image.
