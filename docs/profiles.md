# Native server profiles

All five profiles run natively without Docker on the server. Install via an approved plan or `ulsim services --device NAME --profile web --configure`; inspect with `ulsim services --device NAME --verify`. They need installed Debian, package access, and working networking. A profile is recorded only after functional verification.

| Profile | Software and verification | Configuration |
| --- | --- | --- |
| `dns` | Pinned, SHA256-verified AdGuard Home; DNS query checks a test blocking rule | `upstream_dns`: one to four DNS IP addresses |
| `fileserver` | Samba SMB2+; authenticated private share, service check and initial credential login | `path`, existing `username` (default `ulsim`); password entered interactively, minimum 12 characters |
| `vpn` | WireGuard; checks interface and public key | `address`, `listen_port`, peers with public keys and unique VPN `/32` addresses |
| `web` | Nginx; HTTP response contains ULSIM test site | No extra fields |
| `media` | MiniDLNA; service and HTTP status check | `path`; direct streaming only, no transcoding |

Example `profiles.json` for `--config`:

```json
{
  "fileserver": {"path": "/srv/ulsim/share", "username": "ulsim"},
  "media": {"path": "/srv/ulsim/media"},
  "vpn": {"address": "10.77.0.1/24", "listen_port": 51820, "peers": []}
}
```

Select only the profiles included in that file. Data paths must be explicit subdirectories of `/srv`, `/mnt`, or `/media`; path traversal and symlinks are refused. Media files must be readable by MiniDLNA. New Samba shares are accessible only to the selected existing user; guest access is disabled. Do not put passwords in configuration files for AI use. Credentials are sent through authenticated SSH stdin and omitted from saved profile state.

WireGuard creates its private key on the server, mode 0600. `services` returns its public key, listen port and handshake timestamps. Add client public keys and unique addresses using the VPN config, then configure each client with its own private key, the server public key, and endpoint. The initial profile gives access to the server's VPN address. LAN routing, internet exit routing, NAT, public firewall rules and router forwarding are deliberately not enabled automatically. They need explicit network configuration. A residential router with no forwarding permits LAN-only use; remote access requires separate networking choices.

AdGuard's administrative HTTP UI is bound to loopback; use SSH tunnelling if administering it manually. Point selected clients or router DHCP DNS at the server only after testing. Upstream filter downloads require `adguardteam.github.io` plus GitHub release asset access; DNS resolution itself uses configured UDP/TCP upstream servers. A successful blocking probe proves the service and configured local rule, not that every public filter list downloaded.

All service ports are restricted to private/local source networks by nftables. ULSIM owns the managed firewall file. Review existing custom firewall rules before using it on a server managed by other tooling. Service removal, TLS certificate management, backup retention and arbitrary application deployment are outside version 0.1.
