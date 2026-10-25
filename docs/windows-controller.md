# Windows controller reference

Windows 11, Python 3.11+ with the `py` launcher, and Windows OpenSSH Client are required. Run `scripts/install-windows.ps1` from the extracted source distribution. It creates `%LOCALAPPDATA%\ULSIM\venv`, installs the package and dependencies, adds its Scripts directory to the user PATH and checks `ulsim --version`. It does not require administrator privileges, WSL, Visual Studio, or an AI API key. It does not change the machine's execution policy persistently.

`ulsim --help` and each subcommand's `--help` explain options. `--json` belongs after the subcommand. `--state-dir PATH` belongs before it. A unique `--device` ID or friendly name selects a server; it can be omitted when exactly one is paired. Machine-readable errors use `{"error": "..."}` and nonzero exit status.

| Command | Purpose |
| --- | --- |
| `discover` | LAN mDNS announcements; untrusted until pairing |
| `devices`, `servers` | Persistent trusted-device inventory and installed servers |
| `configure-usb`, `configure-wifi` | Physical initial key and network provisioning |
| `pair` | Verify physical fingerprint, authenticate, remember target |
| `connect` | Check pinned SSH and target identity |
| `inspect` | Actual hardware report; `--output` saves JSON |
| `recommend` | Workload and distribution recommendations; accepts `--report` |
| `plan` | Produce complete approved-disk plan and partition preview |
| `install` | Approve exact plan; `--wait` follows reboot; `--resume` continues journal |
| `status`, `logs` | Target installation progress and diagnostics |
| `services` | Status/verification or explicitly selected profile configuration |
| `health` | Memory, uptime, load and root disk usage |
| `update`, `reboot` | Explicit administrative action; `--yes` for authorized automation |

Inventory and controller keys are in `%LOCALAPPDATA%\ulsim` by default. Back up this directory securely. An inventory database alone cannot restore access without its matching private key. Inventory records contain IPs, hardware serials and health data, but no Wi-Fi/Samba passwords or WireGuard private key.

Codex CLI is optional. Start your locally authenticated Codex from the extracted source folder so it can read AGENTS.md. ULSIM's CLI works independently of AI.
