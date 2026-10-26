"""Debian installer executed only on a physically provisioned ULSIM live target.

Destructive work runs in a detached systemd unit. No disk operation occurs while
collecting a report, constructing a plan, or starting the live environment.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

STATE_DIR = Path('/var/lib/ulsim')
JOB_DIR = STATE_DIR / 'jobs'
KEYRING = '/usr/share/keyrings/debian-archive-keyring.gpg'
MIRROR = 'https://deb.debian.org/debian'
MOUNT_DIR = Path('/mnt')
CACHE_DIR = Path('/var/cache/ulsim/debootstrap')
ACTIVE = {'queued', 'preparing', 'installing', 'bootloader', 'configuring'}
LIVE_MOUNTS = ('/run/live/medium', '/lib/live/mount/medium', '/cdrom')


def run(args, *, input=None, capture=False, check=True):
    """No command interpolation: every process receives a concrete argv."""
    return subprocess.run([str(a) for a in args], input=input, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,
                          check=check, env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive',
                                           'LC_ALL': 'C.UTF-8'})


def atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        os.chmod(f.name, 0o600)
        json.dump(data, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(f.name, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {} if default is None else default


def set_state(job, stage, **fields):
    path = JOB_DIR / job / 'state.json'
    previous = read_json(path)
    data = {**previous, 'job_id': job, 'stage': stage, 'updated_at': time.time(), **fields}
    atomic_json(path, data)
    atomic_json(STATE_DIR / 'status.json', data)
    print(json.dumps({'stage': stage, 'job_id': job}), flush=True)
    return data


def status():
    return read_json(STATE_DIR / 'status.json', {'stage': 'idle'})


def logs():
    current = status()
    job = current.get('job_id')
    if not job or not re.fullmatch(r'[0-9a-f]{32}', job):
        return {'stage': current.get('stage'), 'lines': []}
    path = JOB_DIR / job / 'install.log'
    if not path.exists():
        return {'job_id': job, 'lines': []}
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 65536))
        content = stream.read().decode('utf-8', errors='replace')
    return {'job_id': job, 'lines': content.splitlines()[-300:]}


def _flatten(nodes):
    for node in nodes:
        yield node
        yield from _flatten(node.get('children', []))


def _ancestry(source):
    # findmnt may suffix btrfs subvolume with [...]. It is not a device suffix.
    source = source.split('[', 1)[0]
    if not source.startswith('/dev/'):
        raise ValueError('Live medium source is not an identifiable block device')
    result = run(['lsblk', '--inverse', '--json', '--paths', '--output', 'PATH,TYPE', source], capture=True)
    nodes = list(_flatten(json.loads(result.stdout)['blockdevices']))
    return {os.path.realpath(n['path']) for n in nodes if n['type'] == 'disk'}


def protected_disks():
    """Resolve physical parent disks of the mounted installer, failing closed."""
    protected = set()
    for mount in LIVE_MOUNTS:
        result = run(['findmnt', '--noheadings', '--raw', '--output', 'SOURCE',
                      '--mountpoint', mount], capture=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            for source in result.stdout.splitlines():
                protected.update(_ancestry(source.strip()))
    if not protected:
        raise ValueError('Cannot identify active installer medium; refusing disk writes')
    return protected


def validate_live_disk(plan, report):
    from .hardware import validate_destination, disk_identity
    validate_destination(report, plan['disk'])
    if report.get('device_id') != plan['device_id']:
        raise ValueError('Approved device identity does not match this target')
    if report.get('boot_mode') != plan['boot_mode']:
        raise ValueError('Target boot mode changed since planning')
    disk = plan['disk']
    path = disk['path']
    if not re.fullmatch(r'/dev/(sd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme\d+n\d+|mmcblk\d+)', path):
        raise ValueError('Destination must be a supported whole block device')
    if os.path.realpath(path) in protected_disks():
        raise ValueError('Destination is the active installer USB')
    result = run(['lsblk', '--json', '--bytes', '--paths', '--output',
                  'PATH,TYPE,SIZE,SERIAL,WWN,RO,MOUNTPOINTS', path], capture=True)
    tree = json.loads(result.stdout)['blockdevices']
    if len(tree) != 1 or tree[0]['type'] != 'disk':
        raise ValueError('Destination must be one whole disk')
    actual = tree[0]
    actual.update(disk_identity(path, actual.get('serial'), actual.get('wwn')))
    if int(actual['size']) != disk['size_bytes']:
        raise ValueError('Destination size changed since approval')
    if not disk.get('serial') and not disk.get('wwn'):
        raise ValueError('Destination needs a stable serial or WWN')
    for name in ('serial', 'wwn'):
        if (actual.get(name) or '').strip() != (disk.get(name) or '').strip():
            raise ValueError(f'Destination {name} changed since approval')
    for node in _flatten(tree):
        if node.get('ro') or any(node.get('mountpoints') or []):
            raise ValueError('Destination or one of its partitions is read-only or mounted')
    if not stat.S_ISBLK(os.stat(path).st_mode):
        raise ValueError('Destination is not a block device')
    return actual


def partition_path(disk, number):
    return f'{disk}{"p" if disk[-1].isdigit() else ""}{number}'


def partition_layout(plan):
    """Return an sfdisk script and exact root/EFI partition numbers."""
    if plan['boot_mode'] == 'uefi':
        if plan['partition_table'] != 'gpt':
            raise ValueError('UEFI installation requires GPT')
        return ('label: gpt\nunit: sectors\n\n'
                'size=512M,type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B\n'
                'type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n', 2, 1)
    if plan['partition_table'] == 'gpt':
        return ('label: gpt\nunit: sectors\n\n'
                'size=2M,type=21686148-6449-6E6F-744E-656564454649\n'
                'type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n', 2, None)
    return ('label: dos\nunit: sectors\n\ntype=83,bootable\n', 1, None)


def write(root, name, data, mode=0o644):
    path = root / name.lstrip('/')
    root = root.resolve()
    if not path.parent.resolve().is_relative_to(root):
        raise ValueError('Configuration path escapes the installed root')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Chroot absolute symlinks refer to its future root, not the live host.
    # Replace the final link (not its target), especially /etc/resolv.conf.
    if path.is_symlink():
        path.unlink()
    path.write_text(data)
    path.chmod(mode)


def chroot(root, args, **kwargs):
    return run(['chroot', root, *args], **kwargs)


def _base_firewall():
    return '''#!/usr/sbin/nft -f
flush ruleset
table inet ulsim {
 chain input {
  type filter hook input priority 0; policy drop;
  iifname "lo" accept
  ct state established,related accept
  ct state invalid drop
  ip protocol icmp accept
  ip6 nexthdr ipv6-icmp accept
  udp sport 67 udp dport 68 accept
  udp sport 547 udp dport 546 accept
  ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16 } tcp dport 22 accept
  ip6 saddr { fc00::/7, fe80::/10 } tcp dport 22 accept
  ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16 } udp dport 5353 accept
  ip6 saddr { fc00::/7, fe80::/10 } udp dport 5353 accept
 }
 chain forward { type filter hook forward priority 0; policy drop; }
 chain output { type filter hook output priority 0; policy accept; }
}
'''


def configure_system(root, plan, report):
    hostname = plan['hostname']
    write(root, '/etc/hostname', hostname + '\n')
    write(root, '/etc/hosts', f'127.0.0.1 localhost\n127.0.1.1 {hostname}\n::1 localhost ip6-localhost\n')
    write(root, '/etc/apt/sources.list',
          'deb https://deb.debian.org/debian trixie main contrib non-free-firmware\n'
          'deb https://deb.debian.org/debian trixie-updates main contrib non-free-firmware\n'
          'deb https://security.debian.org/debian-security trixie-security main contrib non-free-firmware\n')
    write(root, '/etc/systemd/network/20-wired.network',
          '[Match]\nName=en* eth*\nType=ether\n\n[Network]\nDHCP=yes\nIPv6AcceptRA=yes\n\n[DHCPv4]\nUseDNS=yes\n')
    # Copy live Wi-Fi profiles only if present; NetworkManager keyfiles are
    # private and use the same native format on the installed system.
    connections = Path('/etc/NetworkManager/system-connections')
    wifi = connections.exists() and any(connections.glob('*.nmconnection'))
    if wifi:
        destination = root / 'etc/NetworkManager/system-connections'
        shutil.copytree(connections, destination, dirs_exist_ok=True)
        for path in destination.iterdir():
            path.chmod(0o600)
        write(root, '/etc/NetworkManager/conf.d/ulsim.conf', '[main]\ndns=systemd-resolved\n')
    write(root, '/etc/ssh/sshd_config.d/10-ulsim.conf',
          'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n'
          'PubkeyAuthentication yes\nAllowUsers ulsim\n')
    chroot(root, ['useradd', '--create-home', '--shell', '/bin/bash', 'ulsim'])
    chroot(root, ['usermod', '--lock', 'ulsim'])
    chroot(root, ['usermod', '--lock', 'root'])
    write(root, '/home/ulsim/.ssh/authorized_keys', plan['authorized_key'].strip() + '\n', 0o600)
    (root / 'home/ulsim/.ssh').chmod(0o700)
    chroot(root, ['chown', '-R', 'ulsim:ulsim', '/home/ulsim/.ssh'])
    # This account is the administrator. Restriction to target's deterministic
    # entry point avoids accidentally granting a general passwordless shell.
    write(root, '/etc/sudoers.d/ulsim',
          'ulsim ALL=(root) NOPASSWD: /usr/bin/python3 -I -m ulsim.target *\n', 0o440)
    chroot(root, ['visudo', '-cf', '/etc/sudoers.d/ulsim'])
    source_key = Path('/etc/ssh/ssh_host_ed25519_key')
    if not source_key.is_file():
        raise RuntimeError('Live ED25519 host identity missing; cannot transfer trust')
    for suffix in ('', '.pub'):
        src = Path(str(source_key) + suffix)
        dst = root / ('etc/ssh/ssh_host_ed25519_key' + suffix)
        shutil.copy2(src, dst)
        dst.chmod(0o600 if not suffix else 0o644)
    # Pin sshd to the transferred identity, never silently rotate host keys.
    write(root, '/etc/ssh/sshd_config.d/20-ulsim-identity.conf',
          'HostKey /etc/ssh/ssh_host_ed25519_key\n')
    write(root, '/etc/ulsim/device-id', report['device_id'] + '\n', 0o644)
    write(root, '/etc/ulsim/installed', plan['plan_id'] + '\n')
    atomic_json(root / 'etc/ulsim/installed.json', {'plan_id': plan['plan_id'], 'device_id': report['device_id']})
    atomic_json(root / 'etc/ulsim/plan.json', plan)
    # Debian's interpreter determines its install scheme inside the chroot.
    result = chroot(root, ['/usr/bin/python3', '-c',
                         'import sysconfig; print(sysconfig.get_path("purelib"))'], capture=True)
    package_dir = root / result.stdout.strip().lstrip('/') / 'ulsim'
    shutil.copytree(Path(__file__).parent, package_dir, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for path in package_dir.rglob('*'):
        if path.is_file():
            path.chmod(0o644)
        elif path.is_dir():
            path.chmod(0o755)
    package_dir.chmod(0o755)
    write(root, '/etc/avahi/services/ulsim.service',
          '<?xml version="1.0" standalone="no"?><!DOCTYPE service-group SYSTEM "avahi-service.dtd">'
          '<service-group><name replace-wildcards="yes">ULSIM %h</name><service>'
          '<type>_ulsim._tcp</type><port>22</port>'
          f'<txt-record>device_id={report["device_id"]}</txt-record>'
          '<txt-record>mode=installed</txt-record></service></service-group>\n')
    write(root, '/etc/nftables.conf', _base_firewall() + 'include "/etc/nftables.d/ulsim-services.nft"\n')
    write(root, '/etc/nftables.d/ulsim-services.nft', '# Application ports are managed by ULSIM.\n')
    write(root, '/etc/systemd/journald.conf.d/ulsim.conf',
          '[Journal]\nSystemMaxUse=64M\nRuntimeMaxUse=32M\nCompress=yes\n')
    write(root, '/etc/default/zramswap', 'ALGO=lz4\nPERCENT=25\nPRIORITY=100\n')
    write(root, '/etc/apt/apt.conf.d/20auto-upgrades',
          'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n')
    for service in ('ssh', 'avahi-daemon', 'nftables', 'systemd-resolved', 'zramswap'):
        run(['systemctl', '--root', root, 'enable', service])
    if wifi:
        run(['systemctl', '--root', root, 'disable', 'systemd-networkd'], check=False)
        run(['systemctl', '--root', root, 'enable', 'NetworkManager'])
    else:
        run(['systemctl', '--root', root, 'enable', 'systemd-networkd'])
        run(['systemctl', '--root', root, 'disable', 'NetworkManager'], check=False)
    resolv = root / 'etc/resolv.conf'
    resolv.unlink(missing_ok=True)
    resolv.symlink_to('/run/systemd/resolve/stub-resolv.conf')


def copy_egress_configuration(root):
    """Preserve explicitly provisioned network trust; never disable TLS checks."""
    for name in ('/etc/ulsim/proxy.json', '/etc/apt/apt.conf.d/80ulsim-proxy'):
        source = Path(name)
        if source.is_file():
            write(root, name, source.read_text(), 0o600)
    certificate = Path('/usr/local/share/ca-certificates/ulsim-network.crt')
    if certificate.is_file():
        write(root, str(certificate), certificate.read_text(), 0o644)
        chroot(root, ['update-ca-certificates'])


def persist_installed_state(root, plan, job):
    """Snapshot recovery data before unmount without releasing the live worker."""
    state = {**status(), 'job_id': job, 'stage': 'ready', 'updated_at': time.time(),
             'reboot_required': True, 'profiles': plan['profiles'], 'hostname': plan['hostname']}
    destination = root / 'var/lib/ulsim'
    atomic_json(destination / 'status.json', state)
    atomic_json(destination / 'plan.json', plan)
    atomic_json(destination / 'jobs' / job / 'state.json', state)
    atomic_json(destination / 'jobs' / job / 'plan.json', plan)
    log = JOB_DIR / job / 'install.log'
    if log.is_file():
        shutil.copyfile(log, destination / 'jobs' / job / 'install.log')
        (destination / 'jobs' / job / 'install.log').chmod(0o600)


def install(plan, job):
    from .planning import validate_plan
    from .hardware import collect
    validate_plan(plan)
    report = collect()
    validate_live_disk(plan, report)
    required = ('debootstrap', 'sfdisk', 'wipefs', 'mkfs.ext4', 'mkfs.vfat', 'udevadm',
                'mount', 'umount', 'chroot', 'lsblk', 'findmnt', 'blockdev', 'systemctl')
    missing = [cmd for cmd in required if not shutil.which(cmd)]
    if missing:
        raise RuntimeError('Missing installer prerequisites: ' + ', '.join(missing))
    if not Path(KEYRING).is_file():
        raise RuntimeError('Debian archive keyring missing')
    if not Path('/etc/ssh/ssh_host_ed25519_key').is_file():
        raise RuntimeError('Live ED25519 host identity missing')
    # Resolve all download/authenticity problems before destructive changes.
    cache = CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    common = ['--variant=minbase', '--arch=amd64', '--components=main,contrib,non-free-firmware',
              '--force-check-gpg', f'--keyring={KEYRING}', f'--cache-dir={cache}',
              '--include=ca-certificates']
    set_state(job, 'preparing', plan_id=plan['plan_id'], device_id=plan['device_id'])
    with tempfile.TemporaryDirectory(prefix='ulsim-download-', dir=cache.parent) as temp:
        run(['debootstrap', '--download-only', *common, 'trixie', temp, MIRROR])
    # Refresh immediately before wipe; the earlier check is not a permission.
    validate_live_disk(plan, collect())
    disk = plan['disk']['path']
    layout, root_number, esp_number = partition_layout(plan)
    root_device = partition_path(disk, root_number)
    esp_device = partition_path(disk, esp_number) if esp_number else None
    set_state(job, 'installing', destination=disk)
    run(['wipefs', '--lock=yes', '--all', disk])
    run(['sfdisk', '--lock=yes', '--wipe', 'always', '--wipe-partitions', 'always', disk], input=layout)
    run(['blockdev', '--rereadpt', disk])
    run(['udevadm', 'settle', '--timeout=30'])
    run(['mkfs.ext4', '-F', '-L', 'ULSIMROOT', root_device])
    if esp_device:
        run(['mkfs.vfat', '-F', '32', '-n', 'ULSIMEFI', esp_device])
    mount_root = MOUNT_DIR / ('ulsim-' + job)
    mount_root.mkdir(mode=0o700)
    mounts = []
    try:
        run(['mount', root_device, mount_root])
        mounts.append(mount_root)
        if esp_device:
            (mount_root / 'boot/efi').mkdir(parents=True)
            run(['mount', esp_device, mount_root / 'boot/efi'])
            mounts.append(mount_root / 'boot/efi')
        run(['debootstrap', *common, 'trixie', mount_root, MIRROR])
        for source in ('/dev', '/proc', '/sys', '/run'):
            destination = mount_root / source.lstrip('/')
            destination.mkdir(parents=True, exist_ok=True)
            run(['mount', '--rbind', source, destination])
            run(['mount', '--make-rslave', destination])
            mounts.append(destination)
        # Prevent packages from starting services on the live host.
        write(mount_root, '/usr/sbin/policy-rc.d', '#!/bin/sh\nexit 101\n', 0o755)
        # Copy resolved bytes, not the live resolv.conf symlink.
        write(mount_root, '/etc/resolv.conf', Path('/etc/resolv.conf').read_text())
        copy_egress_configuration(mount_root)
        chroot(mount_root, ['apt-get', 'update'])
        packages = ['linux-image-amd64', 'systemd-sysv', 'systemd-resolved', 'dbus',
                    'openssh-server', 'sudo', 'python3', 'ca-certificates', 'avahi-daemon',
                    'nftables', 'iproute2', 'iputils-ping', 'curl', 'lsb-release', 'pciutils',
                    'usbutils', 'smartmontools', 'lm-sensors', 'wireless-regdb',
                    'zram-tools', 'unattended-upgrades', 'network-manager', 'wpasupplicant',
                    'firmware-linux-free', 'firmware-iwlwifi', 'firmware-realtek',
                    'firmware-atheros', 'firmware-brcm80211', 'dosfstools']
        packages += ['grub-efi-amd64', 'efibootmgr'] if esp_device else ['grub-pc']
        chroot(mount_root, ['apt-get', 'install', '--yes', '--no-install-recommends', *packages])
        configure_system(mount_root, plan, report)
        root_uuid = run(['blkid', '-s', 'UUID', '-o', 'value', root_device], capture=True).stdout.strip()
        if not root_uuid:
            raise RuntimeError('Cannot determine installed root filesystem UUID')
        fstab = f'UUID={root_uuid} / ext4 defaults,noatime,errors=remount-ro 0 1\n'
        if esp_device:
            esp_uuid = run(['blkid', '-s', 'UUID', '-o', 'value', esp_device], capture=True).stdout.strip()
            fstab += f'UUID={esp_uuid} /boot/efi vfat umask=0077 0 1\n'
        write(mount_root, '/etc/fstab', fstab)
        write(mount_root, '/etc/default/grub',
              'GRUB_DEFAULT=0\nGRUB_TIMEOUT=3\nGRUB_DISTRIBUTOR=Debian\n'
              'GRUB_CMDLINE_LINUX_DEFAULT=""\nGRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200n8"\n'
              'GRUB_DISABLE_OS_PROBER=true\n')
        set_state(job, 'bootloader')
        chroot(mount_root, ['update-initramfs', '-u', '-k', 'all'])
        if esp_device:
            # A removable fallback works even when the live firmware's NVRAM
            # cannot be written, including UEFI virtual machines.
            chroot(mount_root, ['grub-install', '--target=x86_64-efi', '--efi-directory=/boot/efi',
                                '--bootloader-id=ULSIM', '--no-nvram', '--removable'])
        else:
            chroot(mount_root, ['grub-install', '--target=i386-pc', '--recheck', disk])
        chroot(mount_root, ['update-grub'])
        (mount_root / 'usr/sbin/policy-rc.d').unlink()
        chroot(mount_root, ['apt-get', 'clean'])
        persist_installed_state(mount_root, plan, job)
        run(['sync'])
    finally:
        failures = []
        for mount in reversed(mounts):
            result = run(['umount', '--recursive', mount], check=False)
            if result.returncode:
                failures.append(str(mount))
        if failures:
            raise RuntimeError('Could not unmount installed filesystems: ' + ', '.join(failures))
        with contextlib.suppress(OSError):
            mount_root.rmdir()
    # Only advertise reboot readiness after every filesystem was flushed and
    # unmounted. The controller may power off immediately after this response.
    set_state(job, 'ready', reboot_required=True,
              profiles=plan['profiles'], hostname=plan['hostname'])


def start_install(plan, approval):
    """Validate approval and enqueue a durable job; return without awaiting SSH."""
    from .planning import validate_plan
    from .hardware import collect
    if os.geteuid() != 0:
        raise PermissionError('Installation requires root on the ULSIM live target')
    validate_plan(plan)
    if approval != plan['plan_id']:
        raise ValueError('Explicit approval must equal this complete plan_id')
    validate_live_disk(plan, collect())
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE_DIR / 'queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = status()
        if previous.get('stage') in ACTIVE:
            raise ValueError('An installation is already active; inspect status and logs')
        job = uuid.uuid4().hex
        path = JOB_DIR / job
        path.mkdir(mode=0o700, parents=True)
        atomic_json(path / 'plan.json', plan)
        # stdout remains one JSON response for the RPC caller.
        with contextlib.redirect_stdout(sys.stderr):
            set_state(job, 'queued', plan_id=plan['plan_id'], device_id=plan['device_id'])
        try:
            run(['systemd-run', '--quiet', '--collect', '--unit', 'ulsim-install-' + job,
                 '--property=Type=exec', '--property=UMask=0077',
                 '--property=StandardOutput=append:' + str(path / 'install.log'),
                 '--property=StandardError=append:' + str(path / 'install.log'),
                 '/usr/bin/python3', '-I', '-m', 'ulsim.installer', '--job', job], capture=True)
        except Exception:
            with contextlib.redirect_stdout(sys.stderr):
                set_state(job, 'failed', error='Could not launch installation service')
            raise
    return {'job_id': job, 'stage': 'queued', 'plan_id': plan['plan_id']}


def main():
    parser = argparse.ArgumentParser(description='Internal ULSIM installation worker')
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{32}', args.job) or os.geteuid() != 0:
        parser.error('Requires root and a valid queued job identifier')
    with (STATE_DIR / 'install.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            install(read_json(JOB_DIR / args.job / 'plan.json'), args.job)
        except Exception as exc:
            set_state(args.job, 'failed', error=str(exc), reboot_required=False)
            import traceback
            traceback.print_exc()
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
