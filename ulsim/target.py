"""Small authenticated SSH RPC entry point for live and installed targets.

No server listens in this module. OpenSSH authenticates the controller and sudo
runs this root-owned package using Python isolated mode (-I).
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import time

CONFIG = Path('/etc/ulsim')
MAX_REQUEST = 1024 * 1024
OPERATIONS = {'identity', 'inspect', 'install', 'status', 'logs', 'health', 'services', 'configure', 'update', 'reboot'}


def identity():
    os_release = {}
    try:
        for line in Path('/etc/os-release').read_text().splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                os_release[key] = value.strip('"')
    except OSError:
        pass
    marker = CONFIG / 'installed.json'
    installed = json.loads(marker.read_text()) if marker.exists() else {}
    if not installed and (CONFIG / 'installed').exists():
        installed = {'plan_id': (CONFIG / 'installed').read_text().strip()}
    device_file = CONFIG / 'device-id'
    device_id = device_file.read_text().strip() if device_file.exists() else None
    return {'device_id': device_id, 'hostname': socket.gethostname(),
            'installed': bool(installed), 'mode': 'installed' if installed else 'live', 'plan_id': installed.get('plan_id'),
            'architecture': platform.machine(),
            'os': {'id': os_release.get('ID'), 'version_id': os_release.get('VERSION_ID'),
                   'pretty_name': os_release.get('PRETTY_NAME')},
            'os_id': os_release.get('ID'), 'os_version': os_release.get('VERSION_ID')}


def health():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            memory[key] = int(value.split()[0]) * 1024
    usage = shutil.disk_usage('/')
    return {'identity': identity(), 'memory': memory,
            'disk': {'path': '/', 'total_bytes': usage.total, 'used_bytes': usage.used, 'free_bytes': usage.free},
            'load_average': list(os.getloadavg()),
            'uptime_seconds': float(Path('/proc/uptime').read_text().split()[0]),
            'timestamp': time.time()}


def _keys(payload, allowed):
    if not isinstance(payload, dict) or set(payload) - set(allowed):
        raise ValueError('Unexpected request fields')


def dispatch(operation, payload):
    if operation not in OPERATIONS:
        raise ValueError('Unknown target operation')
    if not isinstance(payload, dict):
        raise ValueError('Request must be a JSON object')
    if operation in {'install', 'configure', 'update', 'reboot'} and os.geteuid() != 0:
        raise PermissionError('This operation requires root')
    if operation == 'identity':
        _keys(payload, [])
        return identity()
    if operation == 'inspect':
        _keys(payload, [])
        from .hardware import collect
        return collect()
    if operation == 'install':
        _keys(payload, ['plan', 'approval'])
        from .installer import start_install
        return start_install(payload['plan'], payload['approval'])
    if operation in {'status', 'logs'}:
        _keys(payload, [])
        from . import installer
        return getattr(installer, operation)()
    if operation == 'health':
        _keys(payload, [])
        return health()
    if operation == 'services':
        _keys(payload, ['profiles', 'verify'])
        from .profiles import status, verify
        return verify(payload.get('profiles') or []) if payload.get('verify') else status(payload.get('profiles'))
    if operation == 'configure':
        _keys(payload, ['profiles', 'config'])
        if not identity()['installed']:
            raise ValueError('Application deployment is allowed only after booting installed Debian')
        from .profiles import configure
        return configure(payload['profiles'], payload.get('config'))
    if operation == 'update':
        _keys(payload, [])
        if not identity()['installed']:
            raise ValueError('Updates are allowed only on the installed server')
        from .profiles import _run
        _run(['apt-get', 'update'])
        _run(['apt-get', '-y', 'upgrade'], timeout=3600)
        return {'ok': True, 'reboot_required': Path('/var/run/reboot-required').exists()}
    if operation == 'reboot':
        _keys(payload, [])
        # Delay long enough for SSH to deliver the acknowledgement, detached.
        subprocess.run(['systemd-run', '--quiet', '--unit=ulsim-reboot', '--on-active=3s',
                        '/usr/bin/systemctl', 'reboot'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return {'ok': True, 'stage': 'rebooting'}
    raise ValueError('Unknown target operation')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) != 1 or argv[0] not in OPERATIONS:
            raise ValueError('Usage: python3 -I -m ulsim.target ' + '|'.join(sorted(OPERATIONS)))
        raw = sys.stdin.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError('Request exceeds 1 MiB')
        payload = json.loads(raw) if raw.strip() else {}
        # Any helper diagnostics go to stderr, keeping stdout exactly one JSON document.
        with contextlib.redirect_stdout(sys.stderr):
            response = dispatch(argv[0], payload)
        print(json.dumps(response, sort_keys=True))
        return 0
    except Exception as error:
        # Validation errors intentionally contain descriptions, never request bodies.
        print(json.dumps({'error': str(error), 'type': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
