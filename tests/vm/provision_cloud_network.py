#!/usr/bin/env python3
"""Prepare private VM-only enterprise network configuration from this process.

This opt-in utility never changes the public boot image. It refuses authenticated
proxy URLs, writes only to a new private directory, and never prints endpoints
or CA material. Use the output with run.py --provision-network DIRECTORY.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
from urllib.parse import urlsplit, urlunsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ca-file", type=Path,
                        help="Explicit enterprise root certificate; defaults to CODEX_PROXY_CERT if set")
    args = parser.parse_args()
    proxies = {}
    for name in ("http_proxy", "https_proxy"):
        value = os.environ.get(name) or os.environ.get(name.upper())
        if not value:
            continue
        parsed = urlsplit(value)
        if (parsed.scheme != "http" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path not in ("", "/")
                or parsed.fragment or parsed.query or not parsed.port):
            parser.error("Expected credential-free HTTP proxy endpoints")
        # The cloud Docker DNS server may not know the platform's proxy alias.
        # An explicit IP keeps QEMU's guest independent of that local alias.
        address = socket.gethostbyname(parsed.hostname)
        ipaddress.ip_address(address)
        proxies[name] = urlunsplit(("http", f"{address}:{parsed.port}", "", "", ""))
    if not proxies:
        parser.error("No HTTP proxy is configured in the current environment")
    certificate = args.ca_file
    if certificate is None and os.environ.get("CODEX_PROXY_CERT"):
        certificate = Path(os.environ["CODEX_PROXY_CERT"])
    if certificate and (not certificate.is_file() or certificate.stat().st_size > 65536):
        parser.error("Enterprise root certificate is missing or too large")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    proxy_file = args.output / "proxy.json"
    proxy_file.write_text(json.dumps(proxies))
    proxy_file.chmod(0o600)
    if certificate:
        shutil.copyfile(certificate, args.output / "trusted-ca.crt")
        (args.output / "trusted-ca.crt").chmod(0o600)
    print("Private VM network provisioning created; keep this directory out of source control and build artifacts.")


if __name__ == "__main__":
    main()
