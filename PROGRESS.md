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
