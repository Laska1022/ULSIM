import base64
import io
import os
import socket
import struct
import subprocess
import tarfile

import pytest

from ulsim import profiles


def _adguard_archive(path, entries):
    with tarfile.open(path, 'w:gz') as archive:
        for name, kind in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            if kind == tarfile.REGTYPE:
                member.size = len(b'AdGuard executable')
                archive.addfile(member, io.BytesIO(b'AdGuard executable'))
            else:
                member.linkname = '/etc/passwd'
                archive.addfile(member)


@pytest.mark.parametrize('name', ['AdGuardHome/AdGuardHome', './AdGuardHome/AdGuardHome'])
def test_adguard_extracts_upstream_executable_only(tmp_path, name):
    archive, binary = tmp_path / 'release.tar.gz', tmp_path / 'installed' / 'AdGuardHome'
    _adguard_archive(archive, [(name, tarfile.REGTYPE), ('../escape', tarfile.REGTYPE)])
    profiles._extract_adguard_binary(archive, binary)
    assert binary.read_bytes() == b'AdGuard executable'
    assert list(binary.parent.iterdir()) == [binary]
    assert not (tmp_path / 'escape').exists()
    if os.name != 'nt':
        assert binary.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize('entries', [
    [('AdGuardHome/AdGuardHome', tarfile.SYMTYPE)],
    [('./AdGuardHome/AdGuardHome', tarfile.LNKTYPE)],
    [('AdGuardHome/AdGuardHome', tarfile.DIRTYPE)],
    [('AdGuardHome/AdGuardHome', tarfile.REGTYPE), ('./AdGuardHome/AdGuardHome', tarfile.REGTYPE)],
    [('AdGuardHome/AdGuardHome', tarfile.REGTYPE), ('AdGuardHome/AdGuardHome', tarfile.REGTYPE)],
    [('other/AdGuardHome', tarfile.REGTYPE)],
])
def test_adguard_rejects_unsafe_or_ambiguous_executable(tmp_path, entries):
    archive, binary = tmp_path / 'release.tar.gz', tmp_path / 'AdGuardHome'
    binary.write_bytes(b'previous executable')
    _adguard_archive(archive, entries)
    with pytest.raises(RuntimeError, match='AdGuard Home'):
        profiles._extract_adguard_binary(archive, binary)
    assert binary.read_bytes() == b'previous executable'


def test_defaults_and_storage_validation():
    config = profiles.validate_config(['fileserver', 'vpn', 'dns', 'media', 'web'])
    assert config['fileserver']['path'] == '/srv/ulsim/share'
    assert config['vpn']['address'] == '10.77.0.1/24'
    for path in ('/etc', '/etc/ssh', '/srv/../etc/ssh', '/srv/data\nadmin users = root', '/srv'):
        with pytest.raises(ValueError):
            profiles.validate_config(['fileserver'], {'fileserver': {'path': path}})


def test_unknown_keys_and_bad_password_rejected():
    for config in ({'web': {'command': 'bad'}}, {'bad': {}}, {'web': 'x'}):
        with pytest.raises(ValueError):
            profiles.validate_config(['web'], config)
    for password in ('short', 'a' * 15 + '\n', 42):
        with pytest.raises(ValueError):
            profiles.validate_config(['fileserver'], {'fileserver': {'password': password}})


def test_wireguard_routes_are_restricted_to_unique_vpn_hosts():
    key = base64.b64encode(b'k' * 32).decode()
    config = {'vpn': {'peers': [{'public_key': key, 'allowed_ips': ['10.77.0.2/32']}]}}
    assert profiles.validate_config(['vpn'], config)['vpn']['peers'][0]['allowed_ips'] == ['10.77.0.2/32']
    for route in ('0.0.0.0/0', '192.168.1.1/32', '10.77.0.1/32', '10.77.0.0/24'):
        config['vpn']['peers'][0]['allowed_ips'] = [route]
        with pytest.raises(ValueError):
            profiles.validate_config(['vpn'], config)


def test_firewall_checks_before_apply_and_limits_services_to_lan(monkeypatch):
    calls, writes = [], {}
    monkeypatch.setattr(profiles, '_run', lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(profiles, '_write', lambda path, text, *args: writes.update({path: text}))
    profiles.firewall({'web': {}, 'dns': {}, 'vpn': {'listen_port': 51820}})
    assert calls[0][:2] == ['nft', '-c']
    assert calls[1][:2] == ['nft', '-f']
    rules = writes['/etc/nftables.conf']
    assert 'policy drop' in rules
    assert 'ip saddr { 10.0.0.0/8' in rules
    assert 'tcp dport { 22, 53, 80 } accept' in rules
    assert '0.0.0.0/0' not in rules


def test_failed_verification_does_not_record_success(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, 'STATE', tmp_path / 'profiles.json')
    monkeypatch.setattr(profiles.os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setattr(profiles, '_run', lambda *a, **kw: None)
    monkeypatch.setattr(profiles, '_web', lambda config: None)
    monkeypatch.setattr(profiles, 'firewall', lambda config: None)
    monkeypatch.setattr(profiles, 'verify', lambda names: {'ok': False, 'profiles': {'web': {'ok': False}}})
    with pytest.raises(RuntimeError, match='verification failed'):
        profiles.configure(['web'])
    assert not profiles.STATE.exists()


def test_samba_password_never_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, 'STATE', tmp_path / 'profiles.json')
    monkeypatch.setattr(profiles.os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setattr(profiles, '_run', lambda *a, **kw: None)
    monkeypatch.setattr(profiles, '_fileserver', lambda config: None)
    monkeypatch.setattr(profiles, 'firewall', lambda config: None)
    monkeypatch.setattr(profiles, 'verify', lambda names: {'ok': True, 'profiles': {'fileserver': {'ok': True}}})
    profiles.configure(['fileserver'], {'fileserver': {'password': 'correct horse battery staple'}})
    assert 'password' not in profiles.STATE.read_text()
    assert 'correct horse' not in profiles.STATE.read_text()


def test_dns_probe_requires_matching_id_and_nxdomain(monkeypatch):
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def settimeout(self, value): pass
        def sendto(self, packet, address): self.packet = packet
        def recvfrom(self, size): return self.packet[:2] + struct.pack('!H', 0x8183) + b'\0' * 8, ('127.0.0.1', 53)
    monkeypatch.setattr(socket, 'socket', lambda *args: Socket())
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,*args): return b'{"reason":"FilteredBlackList"}'
    monkeypatch.setattr(profiles.urllib.request, 'urlopen', lambda *a,**kw: Response())
    assert profiles._dns_check()


def test_process_error_does_not_echo_secret(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 1, '', 'SECRET'))
    with pytest.raises(RuntimeError) as error:
        profiles._run(['smbpasswd'], data='SECRET')
    assert 'SECRET' not in str(error.value)
