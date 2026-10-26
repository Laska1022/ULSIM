"""Installer tests never open, mount, partition or erase real host disks."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import sys
if sys.platform == "win32":
    pytest.skip("Target installer requires Linux; exercised in Linux CI", allow_module_level=True)

from ulsim import installer as inst


def result(stdout='', code=0):
    return SimpleNamespace(stdout=stdout, returncode=code)


@pytest.mark.parametrize('boot_mode,table', [('bios', 'gpt'), ('bios', 'mbr'), ('uefi', 'gpt')])
def test_partition_preview_matches_installer_partition_sizes(boot_mode, table):
    from ulsim.planning import create_plan, partition_layout
    hardware = {
        'device_id': 'layout-test', 'architecture': 'x86_64', 'boot_mode': boot_mode,
        'installer_media': {'identified': True, 'disk_paths': ['/dev/sdb']},
        'disks': [{'path': '/dev/vda', 'size_bytes': 16 * 1024**3, 'serial': 'LAYOUT-DISK',
                   'wwn': None, 'installer': False, 'mounted': False, 'read_only': False}],
    }
    key = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f'
    proposed = create_plan(hardware, '/dev/vda', 'server', [], key, partition_table=table)
    preview = partition_layout(proposed)
    script, root_partition, esp_partition = inst.partition_layout(proposed)
    assert preview[-1]['number'] == root_partition
    assert preview[-1]['filesystem'] == 'ext4'
    if len(preview) > 1:
        assert f"size={preview[0]['size_mib']}M," in script
    assert (esp_partition is not None) == (boot_mode == 'uefi')


def test_partitions_cover_all_supported_boot_modes():
    layout, root, esp = inst.partition_layout({'boot_mode': 'uefi', 'partition_table': 'gpt'})
    assert 'label: gpt' in layout and 'size=512M' in layout
    assert root == 2 and esp == 1
    assert 'C12A7328' in layout
    layout, root, esp = inst.partition_layout({'boot_mode': 'bios', 'partition_table': 'gpt'})
    assert '21686148' in layout and root == 2 and esp is None
    layout, root, esp = inst.partition_layout({'boot_mode': 'bios', 'partition_table': 'mbr'})
    assert 'label: dos' in layout and 'bootable' in layout and root == 1 and esp is None
    with pytest.raises(ValueError, match='GPT'):
        inst.partition_layout({'boot_mode': 'uefi', 'partition_table': 'mbr'})


@pytest.mark.parametrize('disk,expected', [('/dev/sda', '/dev/sda2'), ('/dev/vda', '/dev/vda2'),
                                          ('/dev/nvme0n1', '/dev/nvme0n1p2'),
                                          ('/dev/mmcblk0', '/dev/mmcblk0p2')])
def test_partition_names(disk, expected):
    assert inst.partition_path(disk, 2) == expected


def test_live_usb_ancestry_not_just_partition():
    def command(args, **kwargs):
        if args[0] == 'findmnt':
            return result('/dev/sdb1\n') if args[-1] == '/run/live/medium' else result(code=1)
        return result(json.dumps({'blockdevices': [{'path': '/dev/sdb1', 'type': 'part',
            'children': [{'path': '/dev/sdb', 'type': 'disk'}]}]}))
    with patch.object(inst, 'run', side_effect=command):
        assert inst.protected_disks() == {'/dev/sdb'}


def test_fail_closed_without_live_medium():
    with patch.object(inst, 'run', return_value=result(code=1)):
        with pytest.raises(ValueError, match='Cannot identify'):
            inst.protected_disks()


def test_reject_nonblock_medium():
    with pytest.raises(ValueError, match='block device'):
        inst._ancestry('overlay')


def test_reject_changed_serial_before_any_destructive_command():
    disk = {'path': '/dev/vda', 'size_bytes': 8192, 'serial': 'approved', 'wwn': ''}
    plan = {'disk': disk, 'device_id': 'one', 'boot_mode': 'bios'}
    report = {'device_id': 'one', 'boot_mode': 'bios'}
    tree = {'blockdevices': [{**disk, 'size': disk['size_bytes'], 'serial': 'different', 'type': 'disk', 'ro': False, 'mountpoints': []}]}
    with patch('ulsim.hardware.validate_destination'), patch.object(inst, 'protected_disks', return_value={'/dev/sdb'}), \
            patch.object(inst, 'run', return_value=result(json.dumps(tree))) as run:
        with pytest.raises(ValueError, match='serial changed'):
            inst.validate_live_disk(plan, report)
        assert all(call.args[0][0] == 'lsblk' for call in run.call_args_list)


def test_reject_installer_even_if_report_is_wrong():
    disk = {'path': '/dev/sdb', 'size_bytes': 8192, 'serial': 'x', 'wwn': ''}
    with patch('ulsim.hardware.validate_destination'), patch.object(inst, 'protected_disks', return_value={'/dev/sdb'}):
        with pytest.raises(ValueError, match='installer USB'):
            inst.validate_live_disk({'disk': disk, 'device_id': 'one', 'boot_mode': 'bios'},
                                    {'device_id': 'one', 'boot_mode': 'bios'})


@pytest.mark.parametrize('node', [{'path': '/dev/vda1', 'mountpoints': ['/mnt/data']},
                                 {'path': '/dev/vda2', 'mountpoints': ['[SWAP]']},
                                 {'path': '/dev/vda1', 'ro': True}])
def test_reject_mounted_or_readonly_children(node):
    disk = {'path': '/dev/vda', 'size_bytes': 8192, 'serial': 'approved', 'wwn': ''}
    tree = {'blockdevices': [{**disk, 'size': disk['size_bytes'], 'type': 'disk', 'children': [node]}]}
    with patch('ulsim.hardware.validate_destination'), patch.object(inst, 'protected_disks', return_value={'/dev/sdb'}), \
            patch.object(inst, 'run', return_value=result(json.dumps(tree))):
        with pytest.raises(ValueError, match='read-only or mounted'):
            inst.validate_live_disk({'disk': disk, 'device_id': 'one', 'boot_mode': 'bios'},
                                    {'device_id': 'one', 'boot_mode': 'bios'})


def test_atomic_state_retains_job_and_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(inst, 'STATE_DIR', tmp_path)
    monkeypatch.setattr(inst, 'JOB_DIR', tmp_path / 'jobs')
    inst.set_state('a' * 32, 'preparing', plan_id='approved')
    inst.set_state('a' * 32, 'failed', error='download unavailable')
    state = inst.status()
    assert state['stage'] == 'failed'
    assert state['plan_id'] == 'approved'
    assert state['error'] == 'download unavailable'
    assert (tmp_path / 'status.json').stat().st_mode & 0o777 == 0o600


def test_logs_only_access_valid_job(tmp_path, monkeypatch):
    monkeypatch.setattr(inst, 'STATE_DIR', tmp_path)
    monkeypatch.setattr(inst, 'JOB_DIR', tmp_path / 'jobs')
    inst.atomic_json(tmp_path / 'status.json', {'job_id': '../../secret', 'stage': 'failed'})
    assert inst.logs()['lines'] == []


def test_approval_rejected_before_hardware_or_disk_access():
    with patch('ulsim.planning.validate_plan'), patch.object(inst.os, 'geteuid', return_value=0), \
            patch('ulsim.hardware.collect') as collect:
        with pytest.raises(ValueError, match='Explicit approval'):
            inst.start_install({'plan_id': 'approved'}, 'different')
        collect.assert_not_called()


def test_chroot_write_replaces_absolute_symlink_without_touching_host(tmp_path):
    root = tmp_path / 'root'
    (root / 'etc').mkdir(parents=True)
    outside = tmp_path / 'live-resolv.conf'
    outside.write_text('live resolver\n')
    (root / 'etc/resolv.conf').symlink_to(outside)
    inst.write(root, '/etc/resolv.conf', 'installed resolver\n')
    assert outside.read_text() == 'live resolver\n'
    assert not (root / 'etc/resolv.conf').is_symlink()
    assert (root / 'etc/resolv.conf').read_text() == 'installed resolver\n'


def test_chroot_write_rejects_escaping_parent(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'etc').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='escapes'):
        inst.write(root, '/etc/hostname', 'server\n')
    assert not (tmp_path / 'hostname').exists()


def test_recovery_state_and_logs_survive_installation(tmp_path, monkeypatch):
    monkeypatch.setattr(inst, 'STATE_DIR', tmp_path / 'live')
    monkeypatch.setattr(inst, 'JOB_DIR', tmp_path / 'live/jobs')
    job = 'a' * 32
    inst.set_state(job, 'bootloader', plan_id='approved')
    (inst.JOB_DIR / job / 'install.log').write_text('GRUB installed successfully\n')
    root = tmp_path / 'installed'
    inst.persist_installed_state(root, {'profiles': ['web'], 'hostname': 'server'}, job)
    assert inst.status()['stage'] == 'bootloader'
    monkeypatch.setattr(inst, 'STATE_DIR', root / 'var/lib/ulsim')
    monkeypatch.setattr(inst, 'JOB_DIR', root / 'var/lib/ulsim/jobs')
    assert inst.status()['stage'] == 'ready'
    assert inst.logs()['lines'] == ['GRUB installed successfully']


@pytest.mark.parametrize('unmount_failure', [False, True])
def test_no_reboot_readiness_before_clean_unmount(tmp_path, monkeypatch, unmount_failure):
    """Mock subprocesses to verify ordering, never to claim a real OS install."""
    monkeypatch.setattr(inst, 'STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr(inst, 'JOB_DIR', tmp_path / 'state/jobs')
    monkeypatch.setattr(inst, 'MOUNT_DIR', tmp_path)
    monkeypatch.setattr(inst, 'CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(inst.shutil, 'which', lambda cmd: '/bin/' + cmd)
    monkeypatch.setattr(inst, 'validate_live_disk', lambda *args: None)
    monkeypatch.setattr(inst, 'configure_system', lambda *args: None)
    monkeypatch.setattr(inst, 'copy_egress_configuration', lambda *args: None)
    monkeypatch.setattr(Path, 'is_file', lambda path: True)
    monkeypatch.setattr(inst.shutil, 'copyfile', lambda *args: None)
    # This test omits log copying, which is covered separately above.
    monkeypatch.setattr(inst, 'persist_installed_state', lambda *args: None)
    commands = []
    def command(args, **kwargs):
        commands.append([str(a) for a in args])
        if args[0] == 'umount':
            assert inst.status()['stage'] != 'ready'
            return result(code=1 if unmount_failure else 0)
        return result('UUID-TEST\n' if args[0] == 'blkid' else '')
    monkeypatch.setattr(inst, 'run', command)
    plan = {'plan_id': 'approved', 'device_id': 'device', 'disk': {'path': '/dev/vda'},
            'boot_mode': 'bios', 'partition_table': 'gpt', 'profiles': [], 'hostname': 'server'}
    with patch('ulsim.hardware.collect', return_value={}), patch('ulsim.planning.validate_plan'):
        if unmount_failure:
            with pytest.raises(RuntimeError, match='Could not unmount'):
                inst.install(plan, 'a' * 32)
            assert inst.status()['stage'] != 'ready'
        else:
            inst.install(plan, 'a' * 32)
            assert inst.status()['stage'] == 'ready'
            assert commands[-1][0] == 'umount'
