# Universal Linux Server Installer & Manager

ULSIM lets a Windows 11 computer inspect an old x86-64 PC, approve a disk installation, install Debian 13 minimal over SSH, and manage its server applications. Codex CLI can operate the deterministic `ulsim` CLI using your existing ChatGPT login. No WSL or additional AI API key is required.

**Validation status:** implementation and tests are under active integration. See [PROGRESS.md](PROGRESS.md) for measured results. Do not treat an untested build as a verified release. The GitHub release workflow requires successful BIOS and UEFI installation tests before publishing.

The system has a Debian live USB, a Python Windows controller, and a target-side installer. Booting the USB never formats a disk. Installation requires the hash of a reviewed plan, rechecks disk serial/WWN and capacity on the target, and refuses the active installer medium. SSH uses a unique host key pinned through a physically provisioned USB; password and root SSH logins are disabled.

Implemented targets and profiles:

- Debian 13 amd64: BIOS with GPT or MBR; UEFI with GPT; ext4 root; DHCP; locked administrative account; SSH; firewall; automatic security updates; zram.
- AdGuard Home DNS filtering, authenticated Samba, WireGuard server access, Nginx, and MiniDLNA.
- Recommendations for Debian, Alpine, Ubuntu and lightweight workloads. Alpine/Ubuntu installation and 32-bit images are not implemented.

## Start on Windows

1. Download a **verified** release's `ulsim-live-amd64.img.xz`, `SHA256SUMS.txt`, and source archive. Check the SHA-256 value with `Get-FileHash`. No verified image is available until the image/VM build succeeds.
2. Use balenaEtcher to write the compressed image, or extract `.img` with 7-Zip and use Rufus in DD mode. This erases the selected USB. See [USB preparation](docs/create-usb.md).
3. Extract the source archive, open PowerShell in its directory, and run `powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1`.
4. Prepare a **second small FAT32 USB**, labelled `ULSIMCFG`, using Windows Disk Management. This separate volume avoids relying on Windows mounting the Linux live image. Run `ulsim configure-usb --volume E:\` (replace `E:` with that configuration USB). Save the printed record path. Add `--ssid "Network"` to prompt securely for Wi-Fi.
5. Attach both USBs to the target and boot the installer. Connect Ethernet for the simplest setup. Disable Secure Boot for this initial image.
6. Discover and pair using the physical trust record:

```powershell
ulsim discover --json
ulsim pair --host 192.168.1.120 --record "$env:LOCALAPPDATA\ulsim\provisioned\DEVICE_ID.json" --name oldpc
ulsim inspect --device oldpc --json
ulsim recommend --device oldpc --json
ulsim plan --device oldpc --disk /dev/sda --hostname homeserver --profile web --output plan.json
Get-Content plan.json
ulsim install --plan plan.json --approve EXACT_PLAN_ID_FROM_REVIEWED_FILE --wait
ulsim health --device oldpc
ulsim services --device oldpc --verify
```

Use the actual IP, record path, destination path and plan hash. Remove the installer USB or adjust boot order after installation reaches `ready` so the next boot uses the installed disk. The private configuration material is consumed on first live boot; prepare it again before booting a new live session.

For conversational management, run your authenticated `codex` CLI from this directory; [AGENTS.md](AGENTS.md) explains safe operations. Start with “Find my old computer and suggest useful server workloads.”

## Development and delivery

```sh
python -m pip install -e '.[test]'
python -m pytest
bash boot/build/docker-build.sh
python tests/vm/run.py --image dist/ulsim-live-amd64.img --firmware bios --work-dir dist/vm-bios
python tests/vm/run.py --image dist/ulsim-live-amd64.img --firmware uefi --work-dir dist/vm-uefi
```

The image builder needs Linux Docker with privileged containers; ordinary Windows controller use does not. [Development](docs/development.md), [installation and recovery](docs/installation.md), [security](docs/security.md), [profiles](docs/profiles.md), and [troubleshooting](docs/troubleshooting.md) describe the details. MIT licensed.
