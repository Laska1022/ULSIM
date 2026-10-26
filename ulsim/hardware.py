"""Read Linux hardware without modifying devices; unknown values remain explicit."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
from typing import Any

LIVE_MOUNTS = ("/run/live/medium", "/lib/live/mount/medium", "/cdrom")


def _run(args: list[str], *, timeout: int = 8) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        # smartctl uses status bits for health findings and still returns useful JSON.
        if result.returncode and args[0] != "smartctl":
            return None
        return result.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _json(args: list[str], *, timeout: int = 8) -> Any:
    value = _run(args, timeout=timeout)
    if value is None:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip() or None
    except (OSError, UnicodeError):
        return None


def disk_identity(path: str, serial: str | None = None, wwn: str | None = None) -> dict[str, str | None]:
    """Read a stable whole-disk identity using lsblk and the kernel's MMC data.

    Some eMMC/SD drivers expose no udev ID_SERIAL, so lsblk's SERIAL is empty.
    The kernel's read-only device attributes identify the same card without
    opening it. CID is a card identifier, not a WWN; its fallback is labelled
    in the serial field rather than masquerading as a World Wide Name.
    Call this helper again immediately before writes to detect a changed card.
    """
    identity = {"serial": serial.strip() if serial and serial.strip() else None,
                "wwn": wwn.strip() if wwn and wwn.strip() else None}
    match = re.fullmatch(r"/dev/(mmcblk\d+)", path)
    if identity["serial"] is not None or match is None:
        return identity
    device = f"/sys/class/block/{match[1]}/device"
    kernel_serial = _read(f"{device}/serial")
    if kernel_serial and re.fullmatch(r"0[xX][0-9a-fA-F]{8}", kernel_serial) and int(kernel_serial, 16):
        identity["serial"] = f"0x{int(kernel_serial, 16):08x}"
        return identity
    cid = _read(f"{device}/cid")
    if cid and re.fullmatch(r"[0-9a-fA-F]{32}", cid) and int(cid, 16):
        identity["serial"] = "mmc-cid:" + cid.lower()
    return identity


def parse_meminfo(text: str) -> dict[str, int | None]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"(\w+):\s+(\d+)\s+kB", line.strip())
        if match:
            values[match[1]] = int(match[2]) * 1024
    return {"total_bytes": values.get("MemTotal"), "available_bytes": values.get("MemAvailable"),
            "swap_total_bytes": values.get("SwapTotal"), "swap_free_bytes": values.get("SwapFree")}


def parse_cpuinfo(text: str) -> dict[str, Any]:
    blocks = []
    for block in text.strip().split("\n\n"):
        values = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                values[key.strip()] = value.strip()
        if values:
            blocks.append(values)
    first = blocks[0] if blocks else {}
    flags = sorted(set(first.get("flags", first.get("Features", "")).split()))
    cores = {(b["physical id"], b["core id"]) for b in blocks if "physical id" in b and "core id" in b}
    return {"model": first.get("model name"), "manufacturer": first.get("vendor_id"),
            "architecture": platform.machine(), "cores": len(cores) or None,
            "threads": len(blocks) or None, "flags": flags,
            "virtualization": "vmx" if "vmx" in flags else "svm" if "svm" in flags else None}


def _flatten(nodes: list[dict[str, Any]], parent: str | None = None):
    for node in nodes:
        item = dict(node)
        item["path"] = item.get("path") or "/dev/" + item["name"]
        item["_parent"] = parent or ("/dev/" + item["pkname"] if item.get("pkname") and not item["pkname"].startswith("/") else item.get("pkname"))
        yield item
        yield from _flatten(node.get("children", []), item["path"])


def _mounts(node: dict[str, Any]) -> list[str]:
    value = node.get("mountpoints", node.get("mountpoint"))
    if isinstance(value, str):
        return [value] if value else []
    return [item for item in (value or []) if item]


def parse_storage(lsblk: dict[str, Any], live_sources: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Resolve every ancestor, including device mapper and multi-parent trees.

    `identified` is true only if *every* live source resolves to physical disks.
    It never infers the installer from TRAN=usb: USB is a valid destination too.
    """
    nodes = list(_flatten(lsblk.get("blockdevices", [])))
    by_path: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        by_path.setdefault(node["path"], []).append(node)
    def ancestors(path: str, seen: set[str] | None = None) -> set[str]:
        seen = set() if seen is None else set(seen)
        if path in seen:
            return set()
        seen.add(path)
        found = set()
        for node in by_path.get(path, []):
            if node.get("type") in ("disk", "rom"):
                found.add(node["path"])
            elif node.get("_parent"):
                found.update(ancestors(node["_parent"], seen))
        return found
    source_ancestors = [ancestors(source.split("[", 1)[0]) for source in live_sources]
    live_disks = set().union(*source_ancestors) if source_ancestors else set()
    identified = bool(live_sources) and all(source_ancestors)
    result = []
    for path, entries in by_path.items():
        node = entries[0]
        if node.get("type") != "disk":
            continue
        descendants = [n for n in nodes if path in ancestors(n["path"]) and n["path"] != path]
        mountpoints = sorted({m for n in [node, *descendants] for m in _mounts(n)})
        transport = node.get("tran")
        medium = ("eMMC/SD" if re.fullmatch(r"/dev/mmcblk\d+", path) else "USB" if transport == "usb"
                  else "HDD" if node.get("rota") in (True, 1, "1") else "SSD" if node.get("rota") in (False, 0, "0") else None)
        result.append({"path": path, "size_bytes": int(node.get("size") or 0), "model": node.get("model"),
                       **disk_identity(path, node.get("serial"), node.get("wwn")),
                       "transport": transport, "medium": medium, "removable": bool(node.get("rm")),
                       "read_only": bool(node.get("ro")), "installer": path in live_disks,
                       "mounted": bool(mountpoints), "mountpoints": mountpoints,
                       "partitions": [{"path": n["path"], "type": n.get("type"), "size_bytes": int(n.get("size") or 0),
                                       "filesystem": n.get("fstype"), "label": n.get("label"), "uuid": n.get("uuid"),
                                       "mountpoints": _mounts(n)} for n in descendants],
                       "existing_os": None, "health": None})
    return result, {"identified": identified, "sources": live_sources, "disk_paths": sorted(live_disks)}


def validate_destination(report: dict[str, Any], disk: dict[str, Any]) -> dict[str, Any]:
    """Fail closed: require live-media identity and fresh destination identity."""
    media = report.get("installer_media", {})
    if not media.get("identified") or not media.get("disk_paths"):
        raise ValueError("Cannot identify the active installer medium; refusing disk writes")
    matches = [d for d in report.get("disks", []) if d.get("path") == disk.get("path")]
    if len(matches) != 1:
        raise ValueError("Approved destination disk is missing or ambiguous")
    current = matches[0]
    if current.get("installer") or current["path"] in media["disk_paths"]:
        raise ValueError("The destination is the active installer medium")
    if current.get("mounted") or current.get("read_only"):
        raise ValueError("Destination has mounted filesystems/swap or is read-only")
    for field in ("size_bytes", "serial", "wwn"):
        if (current.get(field) or None) != (disk.get(field) or None):
            raise ValueError(f"Destination {field} changed since approval")
    if not disk.get("serial") and not disk.get("wwn"):
        raise ValueError("Destination requires a stable serial number or WWN")
    identities = [(k, disk.get(k)) for k in ("serial", "wwn") if disk.get(k)]
    for key, value in identities:
        if sum(1 for d in report.get("disks", []) if d.get(key) == value) != 1:
            raise ValueError(f"Destination {key} is duplicated; identity is ambiguous")
    return current


def collect() -> dict[str, Any]:
    unknowns = []
    cpu = parse_cpuinfo(_read("/proc/cpuinfo") or "")
    memory = parse_meminfo(_read("/proc/meminfo") or "")
    storage = _json(["lsblk", "--json", "--bytes", "--output", "NAME,KNAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,RM,ROTA,RO,PKNAME,FSTYPE,LABEL,UUID,MOUNTPOINTS"])
    live_sources = []
    for mount in LIVE_MOUNTS:
        mounted = _json(["findmnt", "--json", "--mountpoint", mount, "--output", "SOURCE,TARGET"])
        for item in (mounted or {}).get("filesystems", []):
            if item.get("target") == mount and item.get("source"):
                live_sources.append(os.path.realpath(item["source"]))
    disks, installer_media = parse_storage(storage or {}, list(dict.fromkeys(live_sources)))
    if storage is None:
        unknowns.append("storage: lsblk unavailable or failed")
    if not installer_media["identified"]:
        unknowns.append("active installer medium ancestry unknown; installation is disabled")
    for disk in disks:
        smart = _json(["smartctl", "--json", "--all", disk["path"]], timeout=4)
        if smart:
            disk["health"] = {"passed": smart.get("smart_status", {}).get("passed"),
                              "temperature_c": smart.get("temperature", {}).get("current"),
                              "power_on_hours": smart.get("power_on_time", {}).get("hours")}
        else:
            unknowns.append(f"{disk['path']}: drive health unavailable")
    addresses = _json(["ip", "-json", "address", "show"]) or []
    network = []
    for item in addresses:
        name = item.get("ifname", "")
        if name == "lo":
            continue
        sysnet = Path("/sys/class/net") / name
        driver = sysnet / "device/driver"
        try:
            driver_name = driver.resolve(strict=True).name
        except OSError:
            driver_name = None
        speed = _read(str(sysnet / "speed"))
        network.append({"interface": name, "mac": item.get("address"), "state": item.get("operstate"),
                        "kind": "wifi" if (sysnet / "wireless").exists() else "ethernet",
                        "driver": driver_name, "speed_mbps": int(speed) if speed and speed.isdigit() else None,
                        "addresses": [{"address": a.get("local"), "prefix_length": a.get("prefixlen"),
                                       "family": a.get("family")} for a in item.get("addr_info", [])]})
    firmware = {"manufacturer": _read("/sys/class/dmi/id/board_vendor"), "model": _read("/sys/class/dmi/id/board_name"),
                "version": _read("/sys/class/dmi/id/bios_version"), "vendor": _read("/sys/class/dmi/id/bios_vendor"),
                "date": _read("/sys/class/dmi/id/bios_date")}
    sensors = _json(["sensors", "--json"])
    pci = _run(["lspci", "-nnk"])
    usb = _run(["lsusb"])
    for key, value in {"sensors": sensors, "PCI controllers and graphics": pci, "USB controllers": usb}.items():
        if value is None:
            unknowns.append(f"{key}: unavailable")
    unknowns.append("graphics hardware decoding capabilities: not probed")
    return {"schema_version": 1, "device_id": _read("/etc/ulsim/device-id"), "hostname": socket.gethostname(),
            "architecture": platform.machine(), "boot_mode": "uefi" if Path("/sys/firmware/efi").exists() else "bios",
            "cpu": cpu, "memory": memory, "disks": disks, "installer_media": installer_media, "network": network,
            "firmware": firmware, "sensors": sensors, "pci": pci, "usb": usb, "unknowns": unknowns}
