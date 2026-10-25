# Plan, install and recover

Use `ulsim inspect --device NAME --json` and choose the entire target disk from the actual report. A writable disk with unique serial or WWN is required. Devices whose bridges hide identity are refused. The currently mounted live medium, mounted storage, swap devices and read-only devices are refused. No additional disk is formatted.

`ulsim plan --device NAME --disk /dev/sda --hostname homeserver --profile web --output plan.json` creates a Debian 13 amd64 plan. Add repeated profiles and optionally `--config profiles.json`. Review disk identity, capacity, boot mode, partition table, filesystem and application settings. `plan_id` is SHA256 of canonical content; every change invalidates it. The hash acknowledges a plan and is not an authentication secret.

BIOS GPT uses a BIOS boot partition and ext4 root. UEFI GPT uses a 512 MiB FAT32 EFI partition and ext4 root. `--partition-table mbr` supports BIOS disks below 2 TiB. The kernel, GRUB, DHCP, SSH, firewall, firmware, zram and unattended security updates are installed from signed Debian repositories. Internet access is required. Low RAM and slow flash can make installation lengthy; downloads fail safely before initial partitioning when possible, but failures after erasure can leave an incomplete OS.

After explicit approval run:

```powershell
ulsim install --plan plan.json --approve THE_EXACT_PLAN_ID --wait
```

`--wait` follows the detached target installation, requests reboot, retries the pinned address/mDNS identity, verifies the installed plan and Debian, configures the selected applications and verifies services. For Samba, run interactively so its password can be supplied over SSH stdin. Passwords are never stored in the plan or inventory. Without `--wait`, installation is queued; later use `ulsim install --plan plan.json --resume --wait`.

The target retains the same unique SSH host key and device ID in the installed system. It receives the controller authorized key and a locked `ulsim` account. Root and password SSH are disabled. Startup no longer depends on either USB. When status reaches `ready`, select the internal disk or remove the installer USB before reboot. A USB-first BIOS can otherwise enter live mode again; the controller will not report that as installed success.

## Recovery

- `ulsim status --device NAME --json` and `ulsim logs --device NAME --json` give target state and diagnostics. Controller journal is SQLite in the local state directory.
- Interrupted controller, completed target install: use `install --resume --wait`. It never repeats partitioning. If reboot left the target unreachable, correct boot order/networking and retry resume.
- IP changed: mDNS candidates must match the device ID and pass pinned SSH. Manual `pair --host NEW_IP --record SAME_RECORD` refreshes the address without changing trust.
- Host fingerprint mismatch: stop. Verify physical identity and whether the configuration USB was reprovisioned. Never remove verification to get past this error.
- Partial installation or bootloader failure: preserve logs, boot a freshly provisioned live USB, diagnose and create a new reviewed plan. A previously failed journal is never silently re-erased.
- Application failure after Debian boot: inspect `services` and retry the explicitly selected configuration. Resume will recheck the installed identity and run idempotent configuration.

External data drives are not automatically formatted, repartitioned or mounted. Before using `/mnt/data/share`, explicitly configure and verify the intended persistent mount on the server; otherwise a directory on the root disk would be used. Version 0.1 does not automate separate data-disk mounting.
