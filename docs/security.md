# Security model

Physical possession of the configuration USB establishes trust. The controller generates a unique device host key and retains its SHA256 fingerprint. The target consumes that key and authorized controller public key. Pairing verifies the pinned key before SSH authentication and compares the provisioned device ID. mDNS and manually entered IPs locate devices but never authorize them. Public images contain no shared private host keys, machine IDs, passwords or controller credentials.

The controller private key remains on Windows; the server host private key is transferred only on physically trusted removable media and then copied into the installed OS. Private material and optional Wi-Fi credentials are deleted from writable configuration media after consumption. Flash deletion is not guaranteed secure erasure. Keep the USB private, do not reuse its identity for other targets, and prepare it again after a live reboot.

OpenSSH disables password, keyboard-interactive and root logins. The locked `ulsim` administrator has passwordless sudo only for the root-owned target module invoked with Python isolated mode. Isolated mode prevents Python imports from user-controlled working directories. The target accepts a small validated operation set, passes arguments without shell interpolation, and transports requests over authenticated SSH. This user is trusted to administer the machine and approve destructive installation.

Plans bind disk path, capacity, serial/WWN, device identity, boot mode and all configuration to a SHA256 digest. Both controller and target validate it. The target rereads hardware immediately before disk writes, checks active-medium ancestry independently, requires unmounted whole disks, and serializes installers with filesystem locks. Approval is one complete-plan decision, not a blanket authorization to erase any disk.

A default-deny incoming firewall permits SSH and selected service ports only from RFC1918, IPv4 link-local, IPv6 ULA/link-local sources. This default may need explicit adjustment for home networks using global IPv6 addresses. Outgoing connections and established replies are allowed. ULSIM never forwards router ports or exposes a public management API automatically.

Debian archive signatures, package checksums and HTTPS certificates are verified. AdGuard uses a pinned official release hash. The image builder runs privileged in a disposable container and requires a trusted Linux host; never run it with untrusted repository code. VM tests create new qcow2 disks only and bind forwarded ports to loopback. CI uploads logs/results, not ephemeral private keys.

Known scope: no Secure Boot signing, disk encryption, automatic key rotation, 32-bit image, full-disk backup or hardware attestation. A compromised local controller or physically modified config USB can administer the target. Protect the Windows account and its inventory backups.
