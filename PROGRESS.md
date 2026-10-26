# Implementation checkpoint

Status: integration in progress; **not a verified complete release**.

Implemented: Python controller CLI and SQLite inventory, mDNS discovery/manual pairing, pinned SSH RPC, physical FAT USB identity/Wi-Fi provisioning, Linux hardware inspection and workload recommendations, canonical approved plans, detached Debian debootstrap installer, BIOS GPT/MBR and UEFI GPT code paths, host identity transfer, persistent orchestration, five native service profiles, Windows installation scripts, Codex instructions, Docker live-build and GitHub release/test workflows.

Measured results on this cloud instance:

- Initial integrated suite: 101 tests passed after correcting a syntax error, inaccurate lsblk fixtures, and SSH private-key error handling. Includes real loopback SSH authentication/host pinning/error tests.
- Debian builder and VM-runner Docker images built.
- Live image build reached verified Debian Release signatures and bootstrap packages. Chroot network configuration is being diagnosed. No final image or complete VM acceptance result yet.
- GitHub Actions, native Windows runtime, BIOS/UEFI acceptance, physical hardware and release publication have not yet been verified.

Current work: finish image build with trusted cloud proxy configuration; keep build-only trust material out of public artifacts; run real disposable BIOS and UEFI install tests; fix any failures; rerun integration regression tests and build controller packages; publish branch when allowed.

Architecture: Debian 13 amd64 live-build hybrid USB; two-drive Windows provisioning (installer + FAT ULSIMCFG); unique physically transferred ED25519 host keys; isolated-Python target RPC; stable disk serial/WWN + exact plan hash required; native Debian profiles; optional Alpine/Ubuntu recommendations only. Secure Boot and i386 are unsupported in this release. No external data disk is silently formatted or mounted.

Known integration findings being fixed: installer ready state must wait for clean unmount; installed identity must match exact approved plan; service verification must return affirmative results. See implementation and tests for final state.

## Integration update

- 143 automated tests passed, including real SSH and mDNS protocols, eMMC identity fallback, resume failure handling, and SSH public-key comment normalization.
- Full saved image build completed and exact SquashFS audit passed; produced a real amd64 BIOS/UEFI image, compressed image, SHA256 and source manifests. This build preceded the automatic-boot configuration correction.
- First real VM boots diagnosed indefinite default boot menus. Added explicit three-second BIOS/UEFI text-mode autoboot configurations. Both modes now enter the Linux kernel and live init in fresh VM runs.
- Fixed privileged target file ownership (root-owned, non-user-writable) and ensured public images contain no shared private host key, machine ID, provisioned network settings, or added cloud trust roots.
- Actual installation/reboot/application VM acceptance still running; no completed-release claim. Rebuild with final boot configuration and validate both boot modes before publication.
- GitHub API access is blocked by cloud proxy (403 on CONNECT); branch push succeeded. Setup/start instructions and api.github.com/adguardteam.github.io additions were saved as an environment draft, not applied or published.

## Verified Debian installation milestone

BIOS/GPT and UEFI/GPT real QEMU tests both passed all six baseline checks: automatic live boot and DHCP, controller CLI pairing, hardware/disk protection, explicit plan approval, actual debootstrap/kernel/GRUB installation, independent installed-disk boot with USB removed and unchanged SSH trust, and Nginx HTTP response. Evidence is in docs/validation. These checks used the audited integration image.

The final clean image build also succeeded at source revision 600b82af4631bcd5a95b2115df130ee1ea83529f. Its compressed checksum verified. Fresh BIOS/UEFI runs against that exact image are exercising the full `install --wait` controller state machine; the BIOS run additionally requests all five profiles. These runs are still in progress.
