"""SSH with explicit physical-trust host key pinning, never TOFU."""
from __future__ import annotations
import base64
import hashlib
import json
import re
import shlex
import paramiko

OPS = {"inspect", "identity", "install", "status", "logs", "health", "services", "configure", "update", "reboot"}


def fingerprint(key) -> str:
    return "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")


def validate_fingerprint(value: str) -> str:
    if not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", value):
        raise ValueError("Expected an OpenSSH SHA256 host fingerprint from the USB provisioning record or physical console")
    return value


class PinnedPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, expected):
        self.expected = validate_fingerprint(expected)

    def missing_host_key(self, client, hostname, key):
        actual = fingerprint(key)
        if actual != self.expected:
            raise paramiko.SSHException(f"Host identity mismatch for {hostname}: expected {self.expected}, received {actual}")


class Remote:
    def __init__(self, host, port=22, key_path=None, host_fingerprint=None, username="ulsim", timeout=20):
        if not host or any(c.isspace() for c in host):
            raise ValueError("Invalid SSH hostname")
        if not 1 <= int(port) <= 65535:
            raise ValueError("Invalid SSH port")
        self.host, self.port, self.key_path = host, int(port), str(key_path)
        self.host_fingerprint = validate_fingerprint(host_fingerprint or "")
        self.username, self.timeout = username, timeout

    def client(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(PinnedPolicy(self.host_fingerprint))
        try:
            key = paramiko.PKey.from_path(self.key_path)
            client.connect(self.host, port=self.port, username=self.username,
                           pkey=key, allow_agent=False, look_for_keys=False,
                           timeout=self.timeout, auth_timeout=self.timeout, banner_timeout=self.timeout)
        except Exception:
            client.close()
            raise
        return client

    def run(self, command: str, input_data: str | None = None, timeout=1800) -> str:
        with self.client() as client:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            if input_data:
                stdin.write(input_data)
                stdin.flush()
            stdin.channel.shutdown_write()
            # Drain both streams concurrently; package installers can fill stderr buffers.
            import time
            channel = stdout.channel
            chunks, errors = [], []
            deadline = time.monotonic() + timeout
            while True:
                while channel.recv_ready():
                    chunks.append(channel.recv(65536))
                while channel.recv_stderr_ready():
                    errors.append(channel.recv_stderr(65536))
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Remote command timed out; use status/logs before retrying")
                time.sleep(.02)
            code = channel.recv_exit_status()
            out = b"".join(chunks).decode("utf-8", errors="replace")
            if code:
                try:
                    message = json.loads(out).get("error", "Remote operation failed")
                except (ValueError, AttributeError):
                    message = b"".join(errors).decode("utf-8",errors="replace")[-2000:]
                raise RuntimeError(f"Remote command failed ({code}): {message}")
            return out

    def rpc(self, op: str, payload: dict | None = None) -> dict:
        if op not in OPS:
            raise ValueError("Unknown target operation")
        output = self.run(f"sudo -n /usr/bin/python3 -I -m ulsim.target {shlex.quote(op)}", json.dumps(payload or {}))
        try:
            result = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Target returned invalid JSON") from exc
        if not isinstance(result, dict) or result.get("error"):
            raise RuntimeError(result.get("error", "Invalid target response") if isinstance(result, dict) else "Invalid target response")
        return result

    def available(self) -> bool:
        try:
            self.rpc("identity")
            return True
        except (OSError, paramiko.SSHException, RuntimeError):
            return False
