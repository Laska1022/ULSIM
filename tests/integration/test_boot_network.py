"""Physically provisioned enterprise proxy and CA validation; no live system writes."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("boot_provision", Path(__file__).parents[2] / "boot/scripts/provision.py")
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


def setup_paths(monkeypatch, tmp_path):
    root, config = tmp_path / "root", tmp_path / "config"
    root.mkdir()
    config.mkdir()
    for name in ("etc/ulsim", "etc/apt/apt.conf.d"):
        (root / name).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(provision, "Path", lambda name: root / name.lstrip("/"))
    calls = []
    monkeypatch.setattr(provision, "run", lambda *args, **kwargs: calls.append(args))
    return root, config, calls


@pytest.mark.parametrize("value", [
    "http://user:password@proxy:8080", "http://proxy:8080/path", "http://proxy:8080?a=b",
    'http://proxy:8080/\"', "https://proxy:8080", "http://proxy", "http://proxy:8080\n",
    "file:///etc/passwd", "http://proxy:99999", "http://proxy:8080/#fragment",
])
def test_unsafe_proxy_rejected_before_writing(tmp_path, monkeypatch, value):
    root, config, calls = setup_paths(monkeypatch, tmp_path)
    (config / "proxy.json").write_text(json.dumps({"https_proxy": value}))
    with pytest.raises(ValueError):
        provision.install_network(config)
    assert not (root / "etc/ulsim/proxy.json").exists()
    assert not calls


def test_provision_proxy_without_embedding_credentials(tmp_path, monkeypatch):
    root, config, calls = setup_paths(monkeypatch, tmp_path)
    values = {"http_proxy": "http://192.0.2.1:8080", "https_proxy": "http://192.0.2.1:8080"}
    (config / "proxy.json").write_text(json.dumps(values))
    monkeypatch.setattr(provision.os, "environ", {})
    provision.install_network(config)
    stored = root / "etc/ulsim/proxy.json"
    assert json.loads(stored.read_text()) == values
    if os.name != "nt":
        assert stored.stat().st_mode & 0o777 == 0o600
    assert 'Acquire::https::Proxy "http://192.0.2.1:8080";' in (root / "etc/apt/apt.conf.d/80ulsim-proxy").read_text()
    assert calls[0][:2] == ("systemctl", "set-environment")
    assert provision.os.environ == values


def test_no_provisioning_does_not_change_network_trust(tmp_path, monkeypatch):
    root, config, calls = setup_paths(monkeypatch, tmp_path)
    provision.install_network(config)
    assert calls == []
    assert not (root / "etc/ulsim/proxy.json").exists()


def test_real_ssh_keygen_host_key_comments_are_normalized(tmp_path):
    import subprocess
    key = tmp_path / 'unique_host_key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'physical USB identity', '-f', str(key)], check=True)
    derived = subprocess.check_output(['ssh-keygen', '-y', '-f', str(key)], text=True)
    public = key.with_suffix('.pub').read_text()
    assert provision.validate_public_keys(derived) == provision.validate_public_keys(public)
    assert 'physical USB identity' not in provision.validate_public_keys(derived)
