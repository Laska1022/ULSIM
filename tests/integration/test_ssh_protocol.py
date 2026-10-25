"""Real loopback SSH transport tests. These do not simulate OS installation."""
import json
import socket
import threading
from contextlib import contextmanager

import paramiko
import pytest

from ulsim.ssh import Remote, fingerprint


class TestServer(paramiko.ServerInterface):
    __test__ = False

    def __init__(self, permitted_key):
        self.permitted_key = permitted_key
        self.command = None
        self.event = threading.Event()

    def check_auth_publickey(self, username, key):
        return (paramiko.AUTH_SUCCESSFUL if username == "ulsim" and key == self.permitted_key
                else paramiko.AUTH_FAILED)

    def get_allowed_auths(self, username):
        return "publickey"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        self.command = command.decode()
        self.event.set()
        return True


@contextmanager
def ssh_server(tmp_path, response=None, exit_code=0):
    host_key = paramiko.RSAKey.generate(2048)
    permitted_key = paramiko.RSAKey.generate(2048)
    key_file = tmp_path / "id_rsa"
    permitted_key.write_private_key_file(str(key_file))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    server = TestServer(permitted_key)
    captured = {}

    def serve():
        try:
            connection, _ = listener.accept()
            with paramiko.Transport(connection) as transport:
                transport.add_server_key(host_key)
                transport.start_server(server=server)
                channel = transport.accept(5)
                if channel is None or not server.event.wait(5):
                    return
                incoming = []
                while True:
                    part = channel.recv(65536)
                    if not part:
                        break
                    incoming.append(part)
                captured["request"] = b"".join(incoming).decode()
                captured["command"] = server.command
                channel.sendall(json.dumps(response or {"device_id": "integration-target"}).encode())
                channel.send_exit_status(exit_code)
                channel.shutdown_write()
                # Client is responsible for closing after draining output.
                while transport.is_active():
                    if channel.closed:
                        break
                    threading.Event().wait(.02)
        except (EOFError, OSError, paramiko.SSHException):
            pass  # Expected on host-key or authentication rejection.
        finally:
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    remote = Remote("127.0.0.1", listener.getsockname()[1], str(key_file), fingerprint(host_key), timeout=3)
    try:
        yield remote, captured
    finally:
        listener.close()
        thread.join(timeout=6)


def test_authenticated_rpc_roundtrip(tmp_path):
    with ssh_server(tmp_path) as (remote, captured):
        result = remote.rpc("identity", {"sample": "roundtrip"})
        assert result == {"device_id": "integration-target"}
    assert captured["command"] == "sudo -n /usr/bin/python3 -I -m ulsim.target identity"
    assert json.loads(captured["request"]) == {"sample": "roundtrip"}


def test_host_identity_mismatch_rejected(tmp_path):
    with ssh_server(tmp_path) as (remote, captured):
        remote.host_fingerprint = "SHA256:" + "A" * 43
        with pytest.raises(paramiko.SSHException, match="identity mismatch"):
            remote.rpc("identity")
    assert "command" not in captured


def test_untrusted_client_key_rejected(tmp_path):
    with ssh_server(tmp_path) as (remote, captured):
        bad_key = tmp_path / "untrusted_key"
        paramiko.RSAKey.generate(2048).write_private_key_file(str(bad_key))
        remote.key_path = str(bad_key)
        with pytest.raises(paramiko.AuthenticationException):
            remote.rpc("identity")
    assert "command" not in captured


def test_target_failure_is_not_success(tmp_path):
    with ssh_server(tmp_path, {"error": "invalid plan approval"}, exit_code=2) as (remote, _):
        with pytest.raises(RuntimeError, match="invalid plan approval"):
            remote.rpc("install", {"approval": "invalid"})
