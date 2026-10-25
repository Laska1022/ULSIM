"""Physical USB provisioning with per-device host identity."""
from __future__ import annotations
import json
import os
import subprocess
import uuid
from pathlib import Path
import paramiko
from .ssh import fingerprint


def ensure_key(directory: Path, existing=None) -> Path:
    path = Path(existing).expanduser().resolve() if existing else directory / "controller_ed25519"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)], check=True)
        if os.name != "nt":
            path.chmod(0o600)
    if not Path(str(path) + ".pub").exists():
        public = subprocess.run(["ssh-keygen", "-y", "-f", str(path)], check=True, capture_output=True, text=True).stdout
        Path(str(path) + ".pub").write_text(public)
    return path


def configure_usb(volume: Path, directory: Path, key_path=None, ssid=None, password=None) -> dict:
    """Use an already formatted FAT volume; never format or choose disks for the user."""
    volume = volume.resolve()
    if not volume.is_dir():
        raise ValueError("USB configuration volume must already exist and be labelled ULSIMCFG")
    if ssid is not None and (not 1 <= len(ssid.encode()) <= 32 or not password or not 8 <= len(password) <= 63):
        raise ValueError("Wi-Fi requires a 1–32 byte SSID and an 8–63 character WPA2/WPA3 password")
    reserved = ["authorized_keys", "device-id", "ssh_host_ed25519_key", "ssh_host_ed25519_key.pub", "wifi.json"]
    if any((volume / n).exists() for n in reserved):
        raise ValueError("Configuration files already exist. Preserve or remove the previous provisioning files before preparing this volume")
    key = ensure_key(directory, key_path)
    device_id = uuid.uuid4().hex
    # Generate on controller then physically transfer; never trust a discovered fingerprint.
    host_path = volume / "ssh_host_ed25519_key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(host_path)], check=True)
    host_key = paramiko.Ed25519Key.from_private_key_file(str(host_path))
    record = {"device_id": device_id, "hostname": f"ulsim-{device_id[:6]}", "host_fingerprint": fingerprint(host_key),
              "key_path": str(key.resolve()), "port": 22, "username": "ulsim"}
    (volume / "device-id").write_text(device_id + "\n")
    (volume / "authorized_keys").write_text(Path(str(key) + ".pub").read_text())
    if ssid is not None:
        (volume / "wifi.json").write_text(json.dumps({"ssid": ssid, "password": password}))
    records = directory / "provisioned"
    records.mkdir(parents=True, exist_ok=True, mode=0o700)
    (records / f"{device_id}.json").write_text(json.dumps(record, indent=2))
    return {**record, "record_path": str(records / f"{device_id}.json"),
            "message": "Safely eject ULSIMCFG. It contains this device's private host key and optional Wi-Fi credentials; keep it physically secure."}
