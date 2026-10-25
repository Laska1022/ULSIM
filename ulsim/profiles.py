"""Native Debian service deployments. Secrets travel over SSH stdin only."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import struct
import subprocess
import tarfile
import tempfile
import time
import urllib.request

STATE = Path('/var/lib/ulsim/profiles.json')
SERVICES = {'dns': 'ulsim-adguard', 'fileserver': 'smbd', 'vpn': 'wg-quick@wg0', 'web': 'nginx', 'media': 'minidlna'}
PACKAGES = {'dns': ['ca-certificates'], 'fileserver': ['samba', 'smbclient'], 'vpn': ['wireguard-tools'], 'web': ['nginx'], 'media': ['minidlna']}
ADGUARD_VERSION = 'v0.107.79'
# From upstream HTTPS release checksums.txt, also published as GitHub asset digest.
ADGUARD_SHA256 = 'c48f4a43000665484c5ec28177de11a004759b620dae8f77b2aabefc9ef3687f'
PRIVATE4 = '{ 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16 }'
PRIVATE6 = '{ fc00::/7, fe80::/10 }'


def _run(args, *, data=None, check=True, timeout=900):
    result = subprocess.run(args, input=data, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout,
                            env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive', 'LC_ALL': 'C'})
    if check and result.returncode:
        # Never include stdin or arbitrary stderr: tools can echo supplied secrets.
        raise RuntimeError(f'{Path(args[0]).name} failed (exit {result.returncode})')
    return result


def _write(path, content, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.ulsim-', dir=path.parent)
    try:
        os.chmod(temporary, mode)
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _path(value):
    if not isinstance(value, str) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', value):
        raise ValueError('Storage path must be an absolute path without whitespace or special characters')
    path = PurePosixPath(value)
    if '..' in path.parts or path == PurePosixPath('/'):
        raise ValueError('Unsafe storage path')
    # Only explicit data roots; never expose system configuration or private keys.
    if path.parts[1] not in ('srv', 'mnt', 'media'):
        raise ValueError('Storage path must be below /srv, /mnt or /media')
    if len(path.parts) < 3:
        raise ValueError('Choose a subdirectory of the storage root')
    return str(path)


def validate_config(names, config=None, require_secrets=False):
    if not isinstance(names, list) or len(set(names)) != len(names) or any(n not in SERVICES for n in names):
        raise ValueError('Unknown or duplicate service profile')
    if config is None:
        config = {}
    if not isinstance(config, dict) or set(config) - set(names):
        raise ValueError('Configuration contains an unselected profile')
    result = {}
    allowed = {'dns': {'upstream_dns'}, 'fileserver': {'path', 'username', 'password'},
               'vpn': {'address', 'listen_port', 'peers'}, 'web': set(), 'media': {'path'}}
    for name in names:
        value = config.get(name, {})
        if not isinstance(value, dict) or set(value) - allowed[name]:
            raise ValueError(f'Unknown configuration field for {name}')
        value = dict(value)
        if name == 'dns':
            upstream = value.get('upstream_dns', ['1.1.1.1', '9.9.9.9'])
            if not isinstance(upstream, list) or not 1 <= len(upstream) <= 4:
                raise ValueError('Provide one to four upstream DNS addresses')
            value['upstream_dns'] = [str(ipaddress.ip_address(x)) for x in upstream]
        elif name == 'fileserver':
            value['path'] = _path(value.get('path', '/srv/ulsim/share'))
            value['username'] = value.get('username', 'ulsim')
            if not isinstance(value['username'], str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', value['username']):
                raise ValueError('Invalid Samba username')
            if 'password' in value and (not isinstance(value['password'], str) or len(value['password']) < 12 or '\n' in value['password'] or '\r' in value['password'] or '\x00' in value['password']):
                raise ValueError('Samba password requires at least 12 characters and no control line breaks')
            if require_secrets and not value.get('password'):
                raise ValueError('First Samba deployment needs a password via encrypted configure stdin')
        elif name == 'media':
            value['path'] = _path(value.get('path', '/srv/ulsim/media'))
        elif name == 'vpn':
            interface = ipaddress.ip_interface(value.get('address', '10.77.0.1/24'))
            if interface.version != 4 or not interface.ip.is_private or interface.ip.is_loopback or interface.network.prefixlen < 16:
                raise ValueError('WireGuard address must be a private IPv4 subnet of /16 or smaller')
            value['address'] = str(interface)
            port = value.get('listen_port', 51820)
            if type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError('WireGuard listen_port must be 1024..65535')
            value['listen_port'] = port
            peers = value.get('peers', [])
            if not isinstance(peers, list) or len(peers) > 128:
                raise ValueError('WireGuard peers must be a list of up to 128 peers')
            seen = set()
            clean = []
            for peer in peers:
                if not isinstance(peer, dict) or set(peer) != {'public_key', 'allowed_ips'}:
                    raise ValueError('Each peer needs public_key and allowed_ips')
                try:
                    key = base64.b64decode(peer['public_key'], validate=True)
                except (ValueError, TypeError):
                    raise ValueError('Invalid WireGuard public key') from None
                if len(key) != 32 or peer['public_key'] in seen:
                    raise ValueError('Invalid or duplicate WireGuard peer key')
                seen.add(peer['public_key'])
                if not isinstance(peer['allowed_ips'], list) or len(peer['allowed_ips']) != 1:
                    raise ValueError('Each peer requires one unique VPN host address')
                network = ipaddress.ip_network(peer['allowed_ips'][0], strict=True)
                if network.version != 4 or network.prefixlen != 32 or not network.subnet_of(interface.network) or network.network_address == interface.ip:
                    raise ValueError('Peer address must be a /32 inside the WireGuard subnet')
                if str(network) in seen:
                    raise ValueError('Duplicate WireGuard peer address')
                seen.add(str(network))
                clean.append({'public_key': peer['public_key'], 'allowed_ips': [str(network)]})
            value['peers'] = clean
        result[name] = value
    return result


def _saved():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {}


def firewall(config):
    """Install a complete atomic nftables ruleset; LAN services never open globally."""
    tcp, udp = {22}, {5353}
    if 'dns' in config:
        tcp.add(53); udp.add(53)
    if 'fileserver' in config:
        tcp.update((139, 445)); udp.update((137, 138))
    if 'web' in config:
        tcp.add(80)
    if 'media' in config:
        tcp.add(8200); udp.add(1900)
    if 'vpn' in config:
        udp.add(config['vpn']['listen_port'])
    lines = ['#!/usr/sbin/nft -f', 'flush ruleset', 'table inet ulsim {',
             ' chain input { type filter hook input priority 0; policy drop;',
             '  iifname "lo" accept', '  ct state established,related accept',
             '  ct state invalid drop', '  ip protocol icmp accept', '  meta l4proto ipv6-icmp accept',
             '  udp sport 67 udp dport 68 accept', '  udp sport 547 udp dport 546 accept']
    for family, ranges in [('ip', PRIVATE4), ('ip6', PRIVATE6)]:
        for protocol, ports in [('tcp', tcp), ('udp', udp)]:
            portset = '{ ' + ', '.join(map(str, sorted(ports))) + ' }'
            lines.append(f'  {family} saddr {ranges} {protocol} dport {portset} accept')
    lines.extend([' }', ' chain forward { type filter hook forward priority 0; policy drop; }',
                  ' chain output { type filter hook output priority 0; policy accept; }', '}', ''])
    text = '\n'.join(lines)
    fd, temporary = tempfile.mkstemp(prefix='ulsim-nft-', suffix='.conf')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        _run(['nft', '-c', '-f', temporary])
        _run(['nft', '-f', temporary])
        _write('/etc/nftables.conf', text)
        _run(['systemctl', 'enable', 'nftables'])
    finally:
        os.unlink(temporary)


def _dns(config):
    directory = Path('/opt/ulsim-adguard')
    binary = directory / 'AdGuardHome'
    stamp = directory / 'version'
    if not binary.exists() or not stamp.exists() or stamp.read_text().strip() != ADGUARD_VERSION:
        url = f'https://github.com/AdguardTeam/AdGuardHome/releases/download/{ADGUARD_VERSION}/AdGuardHome_linux_amd64.tar.gz'
        with tempfile.TemporaryDirectory(prefix='ulsim-adguard-') as temporary:
            archive = Path(temporary) / 'adguard.tar.gz'
            digest = hashlib.sha256()
            with urllib.request.urlopen(url, timeout=60) as response, archive.open('wb') as output:
                for block in iter(lambda: response.read(1024 * 1024), b''):
                    output.write(block); digest.update(block)
            if digest.hexdigest() != ADGUARD_SHA256:
                raise RuntimeError('AdGuard Home release checksum mismatch')
            with tarfile.open(archive, 'r:gz') as tar:
                member = tar.getmember('AdGuardHome/AdGuardHome')
                if not member.isfile():
                    raise RuntimeError('AdGuard Home executable is not a regular file')
                directory.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, (directory / 'AdGuardHome.new').open('wb') as output:
                    shutil.copyfileobj(source, output)
                os.chmod(directory / 'AdGuardHome.new', 0o755)
                os.replace(directory / 'AdGuardHome.new', binary)
            _write(stamp, ADGUARD_VERSION + '\n')
    settings = {'http': {'address': '127.0.0.1:3000'}, 'users': [],
                'dns': {'bind_hosts': ['0.0.0.0'], 'port': 53,
                        'upstream_dns': config['upstream_dns'], 'bootstrap_dns': config['upstream_dns'],
                        'allowed_clients': ['127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16'],
                        'cache_size': 4194304},
                'filtering': {'protection_enabled': True, 'filtering_enabled': True, 'blocking_mode': 'nxdomain'},
                'filters': [{'enabled': True, 'url': 'https://adguardteam.github.io/HostlistsRegistry/assets/filter_1.txt', 'name': 'AdGuard DNS filter', 'id': 1}],
                'user_rules': ['||ulsim-block-test.invalid^'], 'schema_version': 29}
    _run(['systemctl', 'stop', SERVICES['dns']], check=False)
    _write('/etc/ulsim/AdGuardHome.yaml', json.dumps(settings, indent=2), 0o600)
    _write('/etc/systemd/system/ulsim-adguard.service', '''[Unit]
Description=ULSIM AdGuard Home DNS filtering
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=/opt/ulsim-adguard/AdGuardHome --no-check-update -c /etc/ulsim/AdGuardHome.yaml -w /var/lib/ulsim/adguard
Restart=on-failure
NoNewPrivileges=true
ProtectHome=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
''')


def _fileserver(config):
    user = config['username']
    _run(['id', user])  # Do not silently create privileged or password accounts.
    path = Path(config['path'])
    if path.is_symlink() or path.resolve() != path:
        raise ValueError('Share path cannot contain symlinks')
    path.mkdir(parents=True, exist_ok=True)
    _run(['chown', f'{user}:{user}', str(path)])
    os.chmod(path, 0o770)
    existing = _run(['pdbedit', '-L', '-u', user], check=False)
    if not config.get('password') and (existing.returncode or not existing.stdout.strip()):
        raise ValueError('Initial Samba deployment requires a password via configure stdin')
    _write('/etc/samba/smb.conf', f'''[global]
workgroup = WORKGROUP
server role = standalone server
security = user
map to guest = Never
server min protocol = SMB2
smb encrypt = desired
hosts allow = 127. 10. 172.16.0.0/12 192.168. 169.254.
hosts deny = ALL
[share]
path = {path}
valid users = {user}
read only = no
guest ok = no
create mask = 0660
directory mask = 0770
''')
    _run(['testparm', '-s'])
    if config.get('password'):
        _run(['smbpasswd', '-a', '-s', user], data=config['password'] + '\n' + config['password'] + '\n')


def _vpn(config):
    directory = Path('/etc/wireguard')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    keypath = directory / 'ulsim.key'
    if not keypath.exists():
        _write(keypath, _run(['wg', 'genkey']).stdout, 0o600)
    private = keypath.read_text().strip()
    lines = ['[Interface]', f'Address = {config["address"]}', f'ListenPort = {config["listen_port"]}', f'PrivateKey = {private}']
    for peer in config['peers']:
        lines += ['', '[Peer]', f'PublicKey = {peer["public_key"]}', 'AllowedIPs = ' + ', '.join(peer['allowed_ips'])]
    _write(directory / 'wg0.conf', '\n'.join(lines) + '\n', 0o600)


def _web(config):
    _write('/var/www/ulsim/index.html', '<!doctype html><html lang="en"><meta charset="utf-8"><title>ULSIM server</title><h1>ULSIM server is running</h1></html>\n')
    _write('/etc/nginx/sites-available/ulsim', '''server {
 listen 80 default_server;
 listen [::]:80 default_server;
 server_name _;
 root /var/www/ulsim;
 index index.html;
 server_tokens off;
 location / { try_files $uri $uri/ =404; }
}
''')
    default = Path('/etc/nginx/sites-enabled/default')
    if default.is_symlink():
        default.unlink()
    enabled = Path('/etc/nginx/sites-enabled/ulsim')
    if not enabled.exists():
        enabled.symlink_to('/etc/nginx/sites-available/ulsim')
    _run(['nginx', '-t'])


def _media(config):
    path = Path(config['path'])
    if path.is_symlink() or path.resolve() != path:
        raise ValueError('Media path cannot contain symlinks')
    path.mkdir(parents=True, exist_ok=True)
    _run(['chown', 'ulsim:ulsim', str(path)])
    os.chmod(path, 0o755)
    _write('/etc/minidlna.conf', f'''user=minidlna
media_dir={path}
friendly_name=ULSIM Media
port=8200
db_dir=/var/cache/minidlna
log_dir=/var/log/minidlna
inotify=yes
notify_interval=900
''')


def configure(names, config=None):
    if os.geteuid() != 0:
        raise PermissionError('Service configuration requires root')
    settings = validate_config(names, config)
    previous = _saved()
    packages = sorted({p for name in names for p in PACKAGES[name]} | {'nftables'})
    if names:
        _run(['apt-get', 'update'])
        _run(['apt-get', 'install', '-y', '--no-install-recommends', *packages], timeout=1800)
    for name in names:
        globals()['_' + name](settings[name])
    _run(['systemctl', 'daemon-reload'])
    for name in names:
        _run(['systemctl', 'enable', SERVICES[name]])
        _run(['systemctl', 'restart', SERVICES[name]])
    clean = {name: {k: v for k, v in value.items() if k != 'password'} for name, value in settings.items()}
    combined = {**previous, **clean}
    firewall(combined)
    checks = verify(names)
    if not checks['ok']:
        raise RuntimeError('Application verification failed: ' + ', '.join(k for k, v in checks['profiles'].items() if not v['ok']))
    # Exercise actual SMB credential login without argv, output, or retained credentials.
    if 'fileserver' in settings and settings['fileserver'].get('password'):
        value = settings['fileserver']
        fd, credential_file = tempfile.mkstemp(prefix='ulsim-smb-')
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(f'username = {value["username"]}\npassword = {value["password"]}\n')
            _run(['smbclient', '//127.0.0.1/share', '-A', credential_file, '-c', 'ls'])
        finally:
            os.unlink(credential_file)
    _write(STATE, json.dumps(combined, indent=2) + '\n', 0o600)
    return {'ok': True, 'profiles': checks['profiles']}


def _dns_check():
    txid = secrets.randbits(16)
    question = b''.join(bytes([len(s)]) + s.encode() for s in 'ulsim-block-test.invalid'.split('.')) + b'\0\0\1\0\1'
    packet = struct.pack('!HHHHHH', txid, 0x0100, 1, 0, 0, 0) + question
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.sendto(packet, ('127.0.0.1', 53))
        reply, _ = sock.recvfrom(4096)
    if len(reply) < 12:
        return False
    identifier, flags = struct.unpack('!HH', reply[:4])
    return identifier == txid and flags & 0x8000 != 0 and flags & 15 == 3


def _functional(name):
    if name == 'web':
        with urllib.request.urlopen('http://127.0.0.1/', timeout=5) as response:
            return response.status == 200 and b'ULSIM server is running' in response.read(65536)
    if name == 'dns':
        return _dns_check()
    if name == 'fileserver':
        return _run(['testparm', '-s'], check=False).returncode == 0 and _run(['smbcontrol', 'smbd', 'ping'], check=False).returncode == 0
    if name == 'vpn':
        result = _run(['wg', 'show', 'wg0', 'public-key'], check=False)
        return result.returncode == 0 and len(base64.b64decode(result.stdout.strip(), validate=True)) == 32
    if name == 'media':
        with urllib.request.urlopen('http://127.0.0.1:8200/', timeout=5) as response:
            return response.status == 200 and b'MiniDLNA' in response.read(65536)
    return False


def verify(names):
    if any(name not in SERVICES for name in names):
        raise ValueError('Unknown service profile')
    checks = {}
    for name in names:
        active = _run(['systemctl', 'is-active', SERVICES[name]], check=False).returncode == 0
        good = False
        for attempt in range(5):
            try:
                good = active and _functional(name)
            except (OSError, ValueError, RuntimeError):
                good = False
            if good or not active:
                break
            time.sleep(1)
        checks[name] = {'service': SERVICES[name], 'active': active, 'functional': good, 'ok': bool(active and good)}
    return {'ok': all(check['ok'] for check in checks.values()), 'profiles': checks}


def status(names=None):
    config = _saved()
    names = list(config) if names is None else names
    result = verify(names)
    if 'vpn' in config:
        result['vpn'] = {'address': config['vpn']['address'], 'listen_port': config['vpn']['listen_port'],
                         'public_key': _run(['wg', 'show', 'wg0', 'public-key'], check=False).stdout.strip(),
                         'peers': _run(['wg', 'show', 'wg0', 'latest-handshakes'], check=False).stdout.strip(),
                         'note': 'Server access only. Router forwarding, routing and peer keys require explicit configuration.'}
    return result
