"""Deterministic recommendations and tamper-evident destructive-install plans."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import struct
from typing import Any

from .hardware import validate_destination

GIB = 1024 ** 3
MIB = 1024 ** 2
PROFILE_NAMES = {"dns", "fileserver", "vpn", "web", "media"}
DISK_PATH = re.compile(r"/dev/(?:sd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme\d+n\d+|mmcblk\d+)\Z")
PLAN_FIELDS = {"version", "plan_id", "device_id", "hostname", "distro", "suite", "architecture", "disk", "boot_mode", "partition_table", "profiles", "profile_config", "admin_user", "authorized_key"}

# Minimum service RAM (MiB), disk (GiB), threads, and operational caveats.
_CATALOG = [
    ("adguard-home", "AdGuard Home", "networking", 128, 1, 1, "dns", "DNS filtering; review router DNS settings separately."),
    ("pi-hole", "Pi-hole", "networking", 512, 2, 1, None, "DNS filtering; alternative to AdGuard Home, not co-installed on port 53."),
    ("unbound", "Unbound", "networking", 128, 1, 1, None, "Recursive DNS; firewall must restrict DNS to trusted clients."),
    ("wireguard", "WireGuard", "networking", 64, 1, 1, "vpn", "Encrypted VPN; bandwidth depends on CPU. Router forwarding is manual."),
    ("tailscale", "Tailscale", "networking", 128, 1, 1, None, "Mesh VPN requires account authentication."),
    ("network-monitoring", "Network monitoring", "networking", 256, 2, 1, None, "Prefer low-frequency lightweight checks and bounded retention."),
    ("dns-cache", "DNS caching", "networking", 64, 1, 1, None, "Useful on weak processors; resolve port conflicts with filtering services."),
    ("ntp", "NTP time service", "networking", 32, 1, 1, None, "Chrony works well on low-power hardware."),
    ("samba", "Samba file server", "files", 256, 2, 1, "fileserver", "Use authenticated shares; capacity and network speed determine usefulness."),
    ("sftp", "SFTP", "files", 64, 1, 1, None, "Already available through installed OpenSSH; key authentication required."),
    ("nfs", "NFS", "files", 128, 2, 1, None, "Restrict exports to trusted LAN clients."),
    ("syncthing", "Syncthing", "files", 512, 4, 1, None, "Large file indexes increase memory requirements."),
    ("backup", "Backup storage", "files", 256, 8, 1, None, "Use a separate appropriately sized data drive and test restore operations."),
    ("jellyfin", "Jellyfin", "media", 1024, 8, 2, None, "Direct play may work; video transcoding is not assumed available."),
    ("dlna", "ReadyMedia DLNA", "media", 128, 2, 1, "media", "Direct streaming only; clients must support the source media format."),
    ("music", "Music server", "media", 256, 4, 1, None, "Direct streaming is preferable to real-time transcoding."),
    ("http-media", "HTTP media hosting", "media", 64, 2, 1, "web", "Serve static files without transcoding; configure access control if needed."),
    ("mosquitto", "Mosquitto MQTT", "automation", 64, 1, 1, None, "Require client authentication before allowing network connections."),
    ("node-red", "Node-RED", "automation", 512, 4, 1, None, "Memory use grows with installed nodes and flows."),
    ("home-assistant", "Home Assistant", "automation", 2048, 16, 2, None, "Reserve resources for integrations; 4 GiB RAM is preferable."),
    ("nginx", "Nginx", "web", 64, 1, 1, "web", "Static websites are suitable for low-power CPUs."),
    ("caddy", "Caddy", "web", 128, 1, 1, None, "Public certificate issuance needs separately configured reachability."),
    ("static-site", "Static website", "web", 64, 1, 1, "web", "A lightweight first workload; no dynamic runtime required."),
    ("python-web", "Python web application", "web", 256, 2, 1, None, "Use a production process manager and limit worker count."),
    ("database", "Small database", "web", 512, 4, 1, None, "Small SQLite/PostgreSQL workloads; write-heavy use wears eMMC."),
    ("light-game", "Lightweight dedicated game server", "gaming", 512, 4, 2, None, "Check the game's Linux architecture, CPU and player-count requirements."),
    ("minecraft", "Minecraft Java server", "gaming", 4096, 12, 4, None, "Requires strong per-core performance; unsuitable for most old Atom CPUs."),
]


def canonical_plan_id(plan: dict[str, Any]) -> str:
    document = {key: value for key, value in plan.items() if key != "plan_id"}
    try:
        data = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("Plan must contain finite JSON data") from exc
    return hashlib.sha256(data).hexdigest()


def normalize_authorized_key(key: str) -> str:
    """Accept a bare OpenSSH key, never authorized_keys options or newlines."""
    if not isinstance(key, str) or "\n" in key.strip() or "\r" in key.strip():
        raise ValueError("Expected one SSH public key")
    parts = key.strip().split()
    if len(parts) < 2 or parts[0] not in {"ssh-ed25519", "ssh-rsa"}:
        raise ValueError("Use a bare ED25519 or RSA SSH public key without key options")
    try:
        blob = base64.b64decode(parts[1], validate=True)
        fields = []
        while blob:
            if len(blob) < 4:
                raise ValueError
            length = struct.unpack(">I", blob[:4])[0]
            if length > len(blob) - 4:
                raise ValueError
            fields.append(blob[4:4 + length])
            blob = blob[4 + length:]
        if fields[0].decode("ascii") != parts[0]:
            raise ValueError
        if parts[0] == "ssh-ed25519" and (len(fields) != 2 or len(fields[1]) != 32):
            raise ValueError
        if parts[0] == "ssh-rsa" and (len(fields) != 3 or int.from_bytes(fields[2], "big").bit_length() < 2048 or int.from_bytes(fields[1], "big") < 3):
            raise ValueError
    except (ValueError, IndexError, UnicodeError, struct.error) as exc:
        raise ValueError("Invalid SSH public key (RSA keys must be at least 2048 bits)") from exc
    return " ".join(parts[:2])


def _contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return any(any(word in str(key).lower() for word in ("password", "private_key", "secret", "token")) or _contains_secret(item) for key, item in value.items())
    return isinstance(value, list) and any(_contains_secret(item) for item in value)


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        raise ValueError("Plan contains missing or unsupported fields")
    if type(plan["version"]) is not int or plan["version"] != 1:
        raise ValueError("Unsupported plan version")
    if (plan["distro"], plan["suite"], plan["architecture"]) != ("debian", "trixie", "amd64"):
        raise ValueError("Only Debian trixie amd64 installation is supported")
    for key, regex in (("hostname", r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"), ("device_id", r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")):
        if not isinstance(plan[key], str) or re.fullmatch(regex, plan[key]) is None:
            raise ValueError(f"Invalid {key}")
    if plan["admin_user"] != "ulsim":
        raise ValueError("Administrative account must be ulsim")
    if plan["boot_mode"] not in ("bios", "uefi") or plan["partition_table"] not in ("gpt", "mbr"):
        raise ValueError("Invalid boot mode or partition table")
    if plan["boot_mode"] == "uefi" and plan["partition_table"] != "gpt":
        raise ValueError("UEFI requires GPT partitioning")
    disk = plan["disk"]
    if not isinstance(disk, dict) or set(disk) != {"path", "size_bytes", "serial", "wwn"}:
        raise ValueError("Invalid disk identity")
    if not isinstance(disk["path"], str) or DISK_PATH.fullmatch(disk["path"]) is None:
        raise ValueError("Destination must be a supported whole-disk Linux device")
    if type(disk["size_bytes"]) is not int or disk["size_bytes"] < 4 * GIB:
        raise ValueError("Destination must have at least 4 GiB")
    if plan["partition_table"] == "mbr" and disk["size_bytes"] > 2 * 1024 * GIB:
        raise ValueError("Use GPT for disks larger than 2 TiB")
    for key in ("serial", "wwn"):
        value = disk[key]
        if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError(f"Invalid disk {key}")
    if not disk["serial"] and not disk["wwn"]:
        raise ValueError("Destination needs a stable serial number or WWN")
    names = plan["profiles"]
    if not isinstance(names, list) or any(not isinstance(n, str) or n not in PROFILE_NAMES for n in names) or len(set(names)) != len(names):
        raise ValueError("Invalid or duplicate application profile")
    if not isinstance(plan["profile_config"], dict) or _contains_secret(plan["profile_config"]):
        raise ValueError("Profile configuration must be an object without secrets; provide credentials during deployment")
    from .profiles import validate_config
    validate_config(names, plan["profile_config"], require_secrets=False)
    if normalize_authorized_key(plan["authorized_key"]) != plan["authorized_key"]:
        raise ValueError("Plan SSH key must be normalized")
    if not isinstance(plan["plan_id"], str) or not re.fullmatch(r"[0-9a-f]{64}", plan["plan_id"]) or canonical_plan_id(plan) != plan["plan_id"]:
        raise ValueError("Plan checksum does not match its contents; regenerate and approve the plan")
    return plan


def create_plan(report: dict[str, Any], disk_path: str, hostname: str, profiles: list[str], authorized_key: str,
                partition_table: str = "gpt", profile_config: dict[str, Any] | None = None) -> dict[str, Any]:
    if report.get("architecture") not in ("x86_64", "amd64"):
        raise ValueError("The installation image and installer support x86-64 only")
    matches = [d for d in report.get("disks", []) if d.get("path") == disk_path]
    if len(matches) != 1:
        raise ValueError("Select exactly one disk shown by hardware inspection")
    disk = {key: matches[0].get(key) for key in ("path", "size_bytes", "serial", "wwn")}
    validate_destination(report, disk)
    config = {} if profile_config is None else profile_config
    if not isinstance(config, dict) or _contains_secret(config):
        raise ValueError("Never store application credentials in an installation plan")
    from .profiles import validate_config
    config = validate_config(profiles, config, require_secrets=False)
    plan = {"version": 1, "device_id": report.get("device_id"), "hostname": hostname, "distro": "debian", "suite": "trixie",
            "architecture": "amd64", "disk": disk, "boot_mode": report.get("boot_mode"), "partition_table": partition_table,
            "profiles": sorted(profiles), "profile_config": config, "admin_user": "ulsim", "authorized_key": normalize_authorized_key(authorized_key)}
    plan["plan_id"] = canonical_plan_id(plan)
    return validate_plan(plan)


def partition_layout(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Human/JSON preview; boundaries correspond to installer partitioning."""
    validate_plan(plan)
    if plan["boot_mode"] == "uefi":
        return [{"number": 1, "purpose": "EFI system", "filesystem": "fat32", "size_mib": 512},
                {"number": 2, "purpose": "Linux root", "filesystem": "ext4", "size_mib": "remaining"}]
    if plan["partition_table"] == "gpt":
        return [{"number": 1, "purpose": "BIOS boot", "filesystem": None, "size_mib": 2},
                {"number": 2, "purpose": "Linux root", "filesystem": "ext4", "size_mib": "remaining"}]
    return [{"number": 1, "purpose": "Linux root (bootable)", "filesystem": "ext4", "size_mib": "remaining"}]


def recommend(report: dict[str, Any]) -> dict[str, Any]:
    ram = report.get("memory", {}).get("total_bytes")
    threads = report.get("cpu", {}).get("threads")
    disks = [d for d in report.get("disks", []) if not d.get("installer")]
    capacity = max((d.get("size_bytes", 0) for d in disks), default=None)
    x64 = report.get("architecture") in ("x86_64", "amd64")
    model = str(report.get("cpu", {}).get("model") or "").lower()
    weak_cpu = any(name in model for name in ("atom", "celeron", "pentium"))
    workloads = []
    for key, name, category, memory, disk, cores, profile, note in _CATALOG:
        reasons = []
        if ram is None or threads is None or capacity is None:
            suitability = "unknown"
            reasons.append("Hardware information is incomplete")
        else:
            # Reserve 256 MiB for OS/SSH and 4 GiB for the base system.
            if ram < (memory + 256) * MIB:
                reasons.append(f"Needs about {memory + 256} MiB including base OS")
            if capacity < (disk + 4) * GIB:
                reasons.append(f"Needs about {disk + 4} GiB including base OS, before application data")
            if threads < cores:
                reasons.append(f"At least {cores} CPU threads recommended")
            if key == "minecraft" and weak_cpu:
                reasons.append("Detected low-power CPU is unsuitable for this workload")
            suitability = "not_recommended" if reasons else "suitable"
        workloads.append({"id": key, "name": name, "category": category, "suitability": suitability,
                          "ram_mib": memory, "disk_gib": disk, "cpu_threads": cores,
                          "installation_profile": profile, "reasons": reasons, "notes": note})
    return {"distributions": [
        {"name": "Debian Minimal", "release": "13 (trixie)", "installation_supported": x64,
         "recommendation": "preferred" if x64 else "unsupported architecture", "reason": "Maintained native packages, broad hardware support, and the supported automated installation path."},
        {"name": "Alpine Linux", "release": "current supported stable", "installation_supported": False,
         "recommendation": "consider for experienced administrators", "reason": "Low memory footprint; musl and application compatibility require review. Automated installation is not implemented."},
        {"name": "Ubuntu Server", "release": "24.04 LTS", "installation_supported": False,
         "recommendation": "alternative" if ram and ram >= 2 * GIB else "not preferred on this memory budget",
         "reason": "Broad software support; typically a larger base installation. Automated installation is not implemented."}],
        "workloads": workloads, "budget": {"ram_bytes": ram, "largest_data_disk_bytes": capacity, "cpu_threads": threads,
        "reserved_os_ram_mib": 256}, "warnings": ["Each workload is assessed separately; sum RAM requirements before combining services.",
        "Hardware decoding was not verified; do not assume video transcoding will work.",
        "Data capacity, backup strategy, and expected user count require user input."]}
