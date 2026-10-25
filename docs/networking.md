# Networking

Ethernet DHCP is the first-install default. Live networking uses NetworkManager with automatic wired profiles; installed Debian uses systemd-networkd for Ethernet, or NetworkManager when a Wi-Fi profile was provisioned. Supported repository firmware is included for common adapters. Hardware requiring separate vendor downloads may need Ethernet or additional verified firmware.

Wi-Fi credentials are provisioned physically from Windows on FAT `ULSIMCFG` using an interactive password prompt. Only WPA2/WPA3 personal passphrases are currently supported. They are copied to a root-only NetworkManager keyfile and consumed from writable USB. Hidden SSIDs, enterprise EAP and captive portals are not automated.

Discovery uses `_ulsim._tcp.local.` on UDP 5353. It supports multiple distinct device IDs and hostnames. A controller can always pair using an explicit IP/SSH port. The target and controller must be able to reach one another; isolated guest Wi-Fi, VLANs and firewalls may block discovery or SSH. Neither public IP nor router forwarding is required.

Required download destinations include `deb.debian.org`, `security.debian.org`, `github.com`, `release-assets.githubusercontent.com`, and `adguardteam.github.io` for the DNS profile. Controller package installation uses PyPI. Public installation normally uses standard system certificate authorities. TLS verification and Debian signature verification remain mandatory.

For managed networks and cloud VM tests, an optional physically trusted configuration volume can also contain `proxy.json` and `trusted-ca.crt`. The proxy schema and test runner options are documented in tests/vm/README.md. This explicitly extends target trust; use only an administrator-approved CA. No corporate/cloud CA or proxy is embedded in the public image. Proxy URLs with credentials are refused. A proxy does not provide local LAN discovery; it only serves supported outbound downloads.
