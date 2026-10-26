#!/usr/bin/env python3
"""Audit the exact distributable SquashFS, never just its assembly directory."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    image, source, manifest = map(Path, sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix='ulsim-root-audit-') as temporary:
        root = Path(temporary) / 'root'
        subprocess.run(['unsquashfs', '-no-progress', '-processors', '2', '-d', str(root), str(image),
                        'etc/ssh', 'etc/ulsim', 'etc/machine-id', 'etc/apt', 'etc/systemd/system/ulsim-provision.service',
                        'usr/local/share/ca-certificates', 'usr/local/sbin/ulsim-provision',
                        'usr/local/lib/python3.13/dist-packages/ulsim'], check=True,
                       stdout=subprocess.DEVNULL)
        if list((root / 'etc/ssh').glob('ssh_host_*_key')):
            raise SystemExit('Public image contains an SSH private host key')
        if (root / 'etc/machine-id').read_text().strip():
            raise SystemExit('Public image contains a shared machine ID')
        for relative in ['etc/ulsim/device-id', 'etc/ulsim/proxy.json', 'etc/apt/apt.conf.d/80ulsim-proxy']:
            if (root / relative).exists():
                raise SystemExit('Public image contains provisioned device/network identity')
        if list((root / 'usr/local/share/ca-certificates').glob('*.crt')):
            raise SystemExit('Public image contains build-only additional certificate authorities')
        # live-build must remove its apt proxy configuration before distribution.
        for file in (root / 'etc/apt').rglob('*'):
            if file.is_file() and b'::proxy' in file.read_bytes().lower():
                raise SystemExit('Public image contains an apt proxy setting')
        expected = {f'usr/local/lib/python3.13/dist-packages/ulsim/{file.name}': file
                    for file in (source / 'ulsim').glob('*.py')}
        expected['usr/local/sbin/ulsim-provision'] = source / 'boot/scripts/provision.py'
        expected['etc/systemd/system/ulsim-provision.service'] = source / 'boot/services/ulsim-provision.service'
        expected['etc/ssh/sshd_config.d/10-ulsim.conf'] = source / 'boot/configuration/sshd.conf'
        entries = []
        for relative, original in sorted(expected.items()):
            file = root / relative
            permissions = file.stat()
            if permissions.st_uid != 0 or permissions.st_gid != 0 or permissions.st_mode & 0o022:
                raise SystemExit(f'Privileged target code is not owned securely by root: {relative}')
            actual = file.read_bytes()
            if actual != original.read_bytes():
                raise SystemExit(f'Image source differs from checkout: {relative}; rebuild the image')
            entries.append(f'{hashlib.sha256(actual).hexdigest()}  {relative}')
        package = root / 'usr/local/lib/python3.13/dist-packages/ulsim'
        for directory in [package, *[p for p in package.rglob('*') if p.is_dir()]]:
            permissions = directory.stat()
            if permissions.st_uid != 0 or permissions.st_gid != 0 or permissions.st_mode & 0o022:
                raise SystemExit('Privileged target package directory is writable by non-root')
        manifest.write_text('\n'.join(entries) + '\n')
    print('Audited live root: current sources, no shared host keys, machine ID, additional CAs or proxy settings')


if __name__ == '__main__':
    main()
