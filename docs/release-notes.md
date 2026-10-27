# ULSIM 0.1.0

Install Debian 13 on an x86-64 computer from a live USB, then manage it from Windows PowerShell or Linux. Codex CLI can operate the controller with your existing ChatGPT login; ordinary Windows use requires neither WSL nor a separate AI API key.

- BIOS/GPT, BIOS/MBR, and UEFI/GPT installation with ext4, DHCP, SSH, a LAN firewall, security updates, and zram.
- Physical USB provisioning of unique SSH identities, pinned pairing, disk identity checks, and explicit approval of the complete installation plan.
- Automatic installation, reboot, reconnection, profile deployment, and persistent progress tracking.
- Native AdGuard Home, Samba, WireGuard, Nginx, and MiniDLNA profiles, with functional checks.
- Hardware inspection, workload recommendations, inventory, health, updates, and reboot commands.

Download `ulsim-live-amd64.img.xz`, `SHA256SUMS.txt`, and the source archive. Verify the compressed image checksum before writing it with Etcher or Rufus. Extract the source archive and run `scripts/install-windows.ps1`; the standalone script needs the rest of the source tree. Follow the [Windows and USB instructions](https://github.com/Laska1022/ULSIM#start-on-windows), including preparation of the separate FAT32 `ULSIMCFG` volume.

Publication is gated on Windows/Linux controller tests, the real Windows installer smoke test, BIOS/GPT, BIOS/MBR and UEFI/GPT VM installations, and the five-profile configuration/reboot checks. Build and source manifests accompany the image. VM acceptance uses disposable disks and does not certify every physical computer or Wi-Fi adapter.

Version 0.1 supports Debian installation only; Alpine and Ubuntu are recommendations. Secure Boot and 32-bit x86 are unsupported. External data mounts need explicit preparation. WireGuard initially provides access to the server itself; internet routing and router forwarding require separate configuration. Profile checks cover DNS blocking, authenticated Samba, the WireGuard interface, and HTTP responses; VPN client handshakes and media playback remain separate checks on the intended network.
