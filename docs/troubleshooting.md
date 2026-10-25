# Troubleshooting

- **No device discovered:** use the console IP with `pair --host`; allow Python's mDNS UDP 5353 on Windows Private networks. Disable router client/AP isolation or connect both devices to the same Ethernet LAN. Discovery does not scan subnets.
- **No SSH:** verify one FAT configuration volume labelled `ULSIMCFG`, valid `authorized_keys`, and successful provisioning on the console. The unconfigured image intentionally leaves SSH disabled. Missing Wi-Fi firmware may require Ethernet.
- **Host mismatch:** check the physical target and controller provisioning record. A new live session may generate a different host key if the consumed configuration was not recreated. Never use automatic trust acceptance.
- **Disk cannot be selected:** check unique serial/WWN, mounted partitions/swap, read-only flags and live-medium ancestry in `inspect`. ULSIM intentionally refuses uncertain disks. Some cheap USB adapters do not expose reliable identities.
- **Installation stalled/failed:** inspect `status` and `logs`; ensure Debian mirror HTTPS access, valid clock, sufficient memory and disk capacity. Preserve logs before reboot because live logs reside in RAM. No “success” is reported from a PID or an open port.
- **Reboot returns to live USB:** choose installed disk in firmware or remove installer USB after `ready`. Use `install --resume --wait` after correcting boot order.
- **Services fail:** use `services --verify`, inspect free space and network with `health`. Samba needs a prompted password on first configure; data paths need readable/writable permissions and verified external mounts.
- **Build failure:** preserve build.log, check trusted CA/proxy configuration and signed repository access. Never disable package signatures or TLS verification. A download checksum mismatch needs investigation, not a changed expected checksum.

Logs can contain machine names, IPs, hardware serials and paths. Review before posting them publicly. They should never contain Wi-Fi passwords, SSH private keys, Samba passwords or WireGuard private keys.
