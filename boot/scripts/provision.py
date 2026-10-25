#!/usr/bin/python3
"""Read physical FAT provisioning media. Never print Wi-Fi or private key material."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from urllib.parse import urlsplit


def run(*args: str, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs)


def safe_file(directory: Path, name: str, limit: int = 65536) -> Path | None:
    file = directory / name
    if not file.exists():
        return None
    if file.is_symlink() or not file.is_file() or file.stat().st_size > limit:
        raise ValueError(f"Invalid provisioning file: {name}")
    return file


def validate_public_keys(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 2 or fields[0] not in ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256"):
            raise ValueError("Only plain SSH public keys are accepted in authorized_keys")
        blob = base64.b64decode(fields[1], validate=True)
        if len(blob) < 32:
            raise ValueError("Invalid SSH public key")
        lines.append(" ".join(fields[:2]))
    if not lines:
        raise ValueError("authorized_keys is empty")
    return "\n".join(lines) + "\n"


def install_wifi(data: dict) -> None:
    ssid, password = data.get("ssid"), data.get("password")
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32:
        raise ValueError("Wi-Fi SSID must contain 1–32 bytes")
    if not isinstance(password, str) or not (8 <= len(password) <= 63 or
            re.fullmatch(r"[0-9a-fA-F]{64}", password)):
        raise ValueError("Wi-Fi password must be a WPA2 passphrase or 64 hex digits")
    if any(ord(c) < 32 for c in ssid + password):
        raise ValueError("Wi-Fi credentials cannot contain control characters")
    def escape(value):
        return value.replace("\\", "\\\\").replace(";", "\\;").replace(" ", "\\s")
    directory = Path("/etc/NetworkManager/system-connections")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "ulsim-wifi.nmconnection"
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(f"[connection]\nid=ulsim-wifi\nuuid={uuid.uuid4()}\ntype=wifi\nautoconnect=true\n"
                    f"[wifi]\nmode=infrastructure\nssid={escape(ssid)}\n"
                    f"[wifi-security]\nkey-mgmt=wpa-psk\npsk={escape(password)}\n"
                    "[ipv4]\nmethod=auto\n[ipv6]\nmethod=auto\n")
    run("nmcli", "connection", "reload")
    # Auto-connect retries even when firmware loads after this service.



def install_network(config: Path) -> None:
    """Opt-in enterprise egress trust physically provisioned by the owner.

    No network trust is downloaded or inferred. Public images contain neither
    an enterprise CA nor proxy endpoints. URL credentials are deliberately
    unsupported so they cannot appear in process arguments or diagnostics.
    """
    proxy = safe_file(config, "proxy.json", 4096)
    certificate = safe_file(config, "trusted-ca.crt", 65536)
    values = {}
    if proxy:
        data = json.loads(proxy.read_text())
        if not isinstance(data, dict) or not data or set(data) - {"http_proxy", "https_proxy"}:
            raise ValueError("proxy.json accepts only http_proxy and https_proxy")
        for name, value in data.items():
            if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
                raise ValueError("Proxy URL cannot contain whitespace or control characters")
            parsed = urlsplit(value)
            if (parsed.scheme != "http" or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None or parsed.query or parsed.fragment
                    or parsed.path not in ("", "/") or not parsed.port
                    or any(c in value for c in '\"\\')):
                raise ValueError("Proxy must be a credential-free http://host:port URL")
            values[name] = value.rstrip("/")
    if certificate:
        # openssl validates the supplied certificate before it joins system trust.
        run("openssl", "x509", "-in", str(certificate), "-noout", "-checkend", "0")
        destination = Path("/usr/local/share/ca-certificates/ulsim-network.crt")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(certificate, destination)
        destination.chmod(0o644)
        run("update-ca-certificates")
    if values:
        stored = Path("/etc/ulsim/proxy.json")
        stored.write_text(json.dumps(values))
        stored.chmod(0o600)
        apt = Path("/etc/apt/apt.conf.d/80ulsim-proxy")
        apt.write_text("".join(f'Acquire::{name.removesuffix("_proxy")}::Proxy "{value}";\n'
                               for name, value in values.items()))
        apt.chmod(0o600)
        # Detached systemd installation workers inherit the manager environment.
        run("systemctl", "set-environment", *(f"{name}={value}" for name, value in values.items()))
        os.environ.update(values)


def firewall() -> None:
    rules = """table inet ulsim_live {
 chain input {
  type filter hook input priority 0; policy drop;
  iifname "lo" accept
  ct state established,related accept
  ip protocol icmp accept
  meta l4proto ipv6-icmp accept
  udp sport 67 udp dport 68 accept
  udp sport 547 udp dport 546 accept
  udp dport 5353 accept
  ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16 } tcp dport 22 accept
  ip6 saddr { fc00::/7, fe80::/10 } tcp dport 22 accept
 }
}
"""
    present = subprocess.run(["nft", "list", "table", "inet", "ulsim_live"], capture_output=True)
    if present.returncode == 0:
        run("nft", "delete", "table", "inet", "ulsim_live")
    run("nft", "-f", "-", input=rules)


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run provisioning as root")
    state = Path("/etc/ulsim")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = Path("/run/ulsim-config")
    config.mkdir(mode=0o700, exist_ok=True)
    candidates = subprocess.run(["blkid", "-t", "LABEL=ULSIMCFG", "-o", "device"],
                                text=True, capture_output=True).stdout.splitlines()
    if len(candidates) > 1:
        raise SystemExit("Multiple ULSIMCFG volumes found; connect only the intended provisioning USB")
    mounted = False
    writable = False
    try:
        if candidates:
            attempt = subprocess.run(["mount", "-o", "rw,nodev,nosuid,noexec", candidates[0], str(config)],
                                     capture_output=True)
            writable = attempt.returncode == 0
            if not writable:
                run("mount", "-o", "ro,nodev,nosuid,noexec", candidates[0], str(config))
            mounted = True
        identity_file = safe_file(config, "device-id", 128)
        identity = identity_file.read_text().strip() if identity_file else uuid.uuid4().hex
        if not re.fullmatch(r"[a-zA-Z0-9-]{8,64}", identity):
            raise ValueError("Invalid device-id")
        (state / "device-id").write_text(identity + "\n")
        if writable and not identity_file:
            (config / "device-id").write_text(identity + "\n")
        hostname = "ulsim-" + identity[:8].lower()
        run("hostnamectl", "set-hostname", hostname)
        Path("/etc/hosts").write_text(f"127.0.0.1 localhost\n127.0.1.1 {hostname}\n::1 localhost\n")
        keys = safe_file(config, "authorized_keys")
        if keys:
            destination = Path("/home/ulsim/.ssh/authorized_keys")
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            destination.write_text(validate_public_keys(keys.read_text()))
            destination.chmod(0o600)
            shutil.chown(destination.parent, "ulsim", "ulsim")
            shutil.chown(destination, "ulsim", "ulsim")
        private = safe_file(config, "ssh_host_ed25519_key")
        public = safe_file(config, "ssh_host_ed25519_key.pub")
        hostkey = Path("/etc/ssh/ssh_host_ed25519_key")
        if private:
            if not public:
                raise ValueError("Host private key requires matching public key")
            shutil.copyfile(private, hostkey)
            hostkey.chmod(0o600)
            derived = run("ssh-keygen", "-y", "-f", str(hostkey)).stdout.strip()
            expected = " ".join(public.read_text().strip().split()[:2])
            if not derived.startswith("ssh-ed25519 ") or derived != expected:
                hostkey.unlink()
                raise ValueError("Provisioned host key pair does not match")
            hostkey.with_suffix(".pub").write_text(derived + "\n")
        elif not hostkey.exists():
            run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(hostkey))
        install_network(config)
        wifi = safe_file(config, "wifi.json")
        if wifi:
            install_wifi(json.loads(wifi.read_text()))
        # Consumption is deliberate: these secrets must not remain on removable media.
        if writable:
            for secret in (private, wifi):
                if secret:
                    secret.unlink()
            os.sync()
        fingerprint = run("ssh-keygen", "-lf", str(hostkey.with_suffix(".pub"))).stdout.strip()
        print(f"ULSIM device {identity}\nHostname {hostname}.local\nSSH host identity: {fingerprint}")
        if not keys:
            print("SSH remains disabled: provision an authorized_keys file on a FAT volume labelled ULSIMCFG and reboot.")
            return
        firewall()
        service = Path("/etc/avahi/services/ulsim.service")
        service.parent.mkdir(exist_ok=True, parents=True)
        service.write_text('<?xml version="1.0" standalone="no"?>\n<!DOCTYPE service-group SYSTEM "avahi-service.dtd">\n'
                           f'<service-group><name replace-wildcards="yes">%h</name><service><type>_ulsim._tcp</type>'
                           f'<port>22</port><txt-record>device_id={identity}</txt-record>'
                           '<txt-record>mode=live</txt-record></service></service-group>\n')
        # ssh.service normally creates RuntimeDirectory; validate before queuing it.
        Path("/run/sshd").mkdir(mode=0o755, exist_ok=True)
        run("sshd", "-t")
        run("systemctl", "--no-block", "start", "ssh.service")
        print("SSH key access enabled for user ulsim. No disk is modified until an approved installation.")
        run("systemctl", "--no-block", "restart", "avahi-daemon.service")
    finally:
        if mounted:
            run("umount", str(config))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # subprocess stderr can contain secrets; expose type and fixed context only.
        if isinstance(exc, subprocess.CalledProcessError):
            raise SystemExit(f"Provisioning command {exc.cmd[0]} failed; inspect the system journal")
        raise SystemExit(str(exc))
