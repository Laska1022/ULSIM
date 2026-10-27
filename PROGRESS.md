# Implementation and validation

Status: clean-image BIOS/GPT and UEFI/GPT installation, all five profiles, and separate profile reboot/persistence checks passed. Final release gates are in progress; no public image release has been published. Read [AI_HANDOFF.md](AI_HANDOFF.md) to continue from this checkpoint.

## Implemented

Native Windows/Linux Python controller, SQLite inventory and resumable orchestration, mDNS discovery/manual pairing, physically provisioned unique SSH identities, Wi-Fi configuration, real Linux hardware inspection, workload recommendations, exact approved plans, detached Debian 13 installer, BIOS GPT/MBR and UEFI GPT partitioning, installed identity transfer, and five native service profiles. Documentation, Windows setup, Docker image builds, and GitHub test/release workflows are included.

## Measured results

- The real Debian hybrid image builds successfully with signed package metadata and TLS verification. Structural and extracted-root audits check boot entries, automatic boot configuration, exact included source, privileged file ownership, and absence of shared private keys or cloud-specific trust/network configuration.
- Real QEMU BIOS/GPT and UEFI/GPT installations passed: live boot, DHCP, pinned SSH pairing, disk identity/protection, plan approval enforcement, debootstrap/kernel/GRUB installation, USB removal, independent installed-disk boot, preserved trust, and Nginx HTTP through the firewall.
- The clean image at source revision `600b82a` also passed automatic `install --wait` through reconnect, profile deployment, verification, and journal completion in both boot modes.
- Extended BIOS testing found an AdGuard archive extraction error and a missing service data directory. Both are fixed. The clean image at revision `956be8f` passed build, extracted-source/security audits, checksum validation, BIOS/GPT installation (`bios-05`), and UEFI/GPT installation (`uefi-05`). BIOS additionally passed all five native profiles. Exact image hashes and final results are committed in `docs/validation`.
- `profile-persistence-03` passed reconfiguration without resetting the Samba credential or WireGuard identity, a real RPC reboot with a changed kernel boot ID, pinned reconnection, all five profiles, and external HTTP. This separate development-overlay test is not relabelled as clean-image acceptance.
- Earlier GitHub Windows jobs failed because a controller test imported the Linux-only installer. Controller preview coverage remains cross-platform; the Linux renderer cross-check now resides with Linux installer tests. [GitHub run 40360242011](https://github.com/Laska1022/ULSIM/actions/runs/40360242011) passed all four Windows/Linux Python 3.11/3.13 jobs at revision `503f1dc`. The local complete suite passes 154 tests.
- [GitHub run 40412694400](https://github.com/Laska1022/ULSIM/actions/runs/40412694400) passed the Windows/Linux matrix and the actual Windows PowerShell installer, isolated installed-package import, and installed CLI checks at revision `a78289d`.
- Release publication requires Windows/Linux tests, BIOS/GPT, BIOS/MBR and UEFI/GPT installation acceptance, and all five profiles plus reconfiguration/reboot checks on BIOS/GPT. JUnit reports and failure summaries are retained.

Evidence, including the historical extended-profile failure, is in [docs/validation](docs/validation/README.md). Tests against a development-modified VM are recorded separately from clean-image acceptance.

## Remaining validation

Two tests were started at this checkpoint: `ulsim-accept-bios-mbr-01` checks BIOS/MBR with 1024 MiB RAM; `ulsim-accept-bios-06` checks a clean BIOS/GPT installation plus all-profile reconfiguration/reboot using the updated runner. Inspect their current state before rerunning anything. Their exact directories, commands, and image provenance are in [AI_HANDOFF.md](AI_HANDOFF.md).

After those checks, verify the actual GitHub image/three-VM workflow and publish release assets only after all release gates pass. Real Wi-Fi adapters, physical disks, legacy firmware variations, VPN client handshakes, and media playback are not established by hosted-runner and VM/service checks.

## Supported scope

Debian 13 amd64 installation is supported; Alpine and Ubuntu are recommendations only. Secure Boot and i386 are unsupported. External data disks are never silently formatted or mounted; existing external mounts require explicit preparation. WireGuard initially provides access to the server itself; router forwarding and gateway routing require separate configuration. See [profiles](docs/profiles.md) for exact functional checks and limitations.

## Cloud environment

The development environment has a working Python virtual environment, Docker builder, and QEMU TCG runner. Reusable setup/start instructions and `api.github.com`/`adguardteam.github.io` network additions are saved as an environment draft. Saving a draft does not apply it or publish a snapshot. Git reads/pushes work through platform authentication; GitHub API requests remain blocked by the current proxy policy, while public GitHub web summaries are readable. No additional token was requested.
