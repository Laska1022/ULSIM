#!/usr/bin/env python3
"""Build with optional inherited proxies and a temporary, explicit build CA mount."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


def main() -> int:
    source = Path(__file__).resolve().parents[2]
    output = Path(os.environ.get("ULSIM_OUTPUT_DIR", source / "dist")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    docker_config = Path(environment.get("DOCKER_CONFIG", Path.home() / ".docker"))
    # In restricted cloud environments the normal Docker config directory is readonly.
    if not docker_config.exists() and not os.access(docker_config.parent, os.W_OK):
        environment["DOCKER_CONFIG"] = tempfile.mkdtemp(prefix="ulsim-docker-")
    build = ["docker", "build", "-t", "ulsim-image-builder", "-f", str(source / "boot/build/Dockerfile")]
    run = ["docker", "run", "--rm", "--privileged"]
    hosts = set()
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        if not environment.get(name):
            continue
        # Values remain in the process environment, not command arguments or logs.
        build += ["--build-arg", name]
        run += ["--env", name]
        if name.lower() == "no_proxy":
            continue
        proxy = urlsplit(environment[name])
        if not proxy.hostname:
            raise ValueError(f"{name} has no proxy hostname")
        if proxy.hostname not in hosts:
            address = socket.gethostbyname(proxy.hostname)
            mapping = proxy.hostname + ":" + address
            build += ["--add-host", mapping]
            run += ["--add-host", mapping]
            hosts.add(proxy.hostname)
    build += [str(source / "boot/build")]
    subprocess.run(build, env=environment, check=True)
    run += ["--mount", f"type=bind,source={source},target=/src,readonly",
            "--mount", f"type=bind,source={output},target=/out",
            "--mount", "type=volume,source=ulsim-live-build,target=/build"]
    trust = environment.get("ULSIM_BUILD_CA_DIR")
    if trust:
        directory = Path(trust).resolve(strict=True)
        if not directory.is_dir() or not list(directory.glob("*.crt")):
            raise ValueError("ULSIM_BUILD_CA_DIR must contain the explicitly trusted build CA .crt files")
        run += ["--mount", f"type=bind,source={directory},target=/build-ca,readonly",
                "--env", "ULSIM_BUILD_CA_DIR=/build-ca"]
    run += ["ulsim-image-builder"]
    return subprocess.run(run, env=environment).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Image build failed: {type(exc).__name__}; inspect the build output.", file=sys.stderr)
        raise SystemExit(1)
