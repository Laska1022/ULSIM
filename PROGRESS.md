# Implementation and validation

Status: complete Debian installation workflow implemented; final service and release validation in progress. A public verified release has not yet been published.

## Implemented

Native Windows/Linux Python controller, SQLite inventory and resumable orchestration, mDNS discovery/manual pairing, physically provisioned unique SSH identities, Wi-Fi configuration, real Linux hardware inspection, workload recommendations, exact approved plans, detached Debian 13 installer, BIOS GPT/MBR and UEFI GPT partitioning, installed identity transfer, and five native service profiles. Documentation, Windows setup, Docker image builds, and GitHub test/release workflows are included.

## Measured results

- The real Debian hybrid image builds successfully with signed package metadata and TLS verification. Structural and extracted-root audits check boot entries, automatic boot configuration, exact included source, privileged file ownership, and absence of shared private keys or cloud-specific trust/network configuration.
- Real QEMU BIOS/GPT and UEFI/GPT installations passed: live boot, DHCP, pinned SSH pairing, disk identity/protection, plan approval enforcement, debootstrap/kernel/GRUB installation, USB removal, independent installed-disk boot, preserved trust, and Nginx HTTP through the firewall.
- The clean image at source revision `600b82a` also passed automatic `install --wait` through reconnect, profile deployment, verification, and journal completion in both boot modes.
- Extended BIOS testing found an AdGuard archive extraction error after all baseline checks passed. The checksum-verified upstream release uses `./AdGuardHome/AdGuardHome`. The corrected extractor accepts the two exact supported names, rejects ambiguous/nonregular members, and never extracts archive-controlled paths. Real-archive extraction and regression tests pass. VM revalidation found a subsequent DNS service startup error that is being diagnosed; Samba, WireGuard, Nginx, and MiniDLNA started successfully.
- Earlier GitHub Windows jobs failed because a controller test imported the Linux-only installer. Controller preview coverage remains cross-platform; the Linux renderer cross-check now resides with Linux installer tests. All 130 non-installer tests pass with the Linux-only module unavailable; a fresh native Windows run is still required.
- Release publication now requires Windows/Linux tests, BIOS/UEFI installation acceptance, and all five profiles on BIOS. JUnit reports and failure summaries are retained.

Evidence, including the historical extended-profile failure, is in [docs/validation](docs/validation/README.md). Tests against a development-modified VM are recorded separately from clean-image acceptance.

## Remaining validation

Resolve DNS startup, complete all-profile verification, rebuild the image with corrected profiles, rerun required clean-image acceptance, confirm Windows CI, and publish release assets only after the release gates pass. Physical Windows PowerShell setup, real Wi-Fi adapters, physical disks, legacy firmware variations, VPN client handshakes, and media playback are not established by VM/service checks.

## Supported scope

Debian 13 amd64 installation is supported; Alpine and Ubuntu are recommendations only. Secure Boot and i386 are unsupported. External data disks are never silently formatted or mounted; existing external mounts require explicit preparation. WireGuard initially provides access to the server itself; router forwarding and gateway routing require separate configuration. See [profiles](docs/profiles.md) for exact functional checks and limitations.

## Cloud environment

The development environment has a working Python virtual environment, Docker builder, and QEMU TCG runner. Reusable setup/start instructions and `api.github.com`/`adguardteam.github.io` network additions are saved as an environment draft. Saving a draft does not apply it or publish a snapshot. Git reads/pushes work through platform authentication; GitHub API requests remain blocked by the current proxy policy, while public GitHub web summaries are readable. No additional token was requested.
