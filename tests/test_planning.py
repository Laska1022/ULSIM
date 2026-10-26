import base64
import copy
import struct

import pytest

from ulsim.planning import canonical_plan_id, create_plan, normalize_authorized_key, partition_layout, recommend, validate_plan


def key():
    kind = b'ssh-ed25519'
    blob = struct.pack('>I', len(kind)) + kind + struct.pack('>I', 32) + bytes(range(32))
    return 'ssh-ed25519 ' + base64.b64encode(blob).decode()


def report():
    return {'device_id': 'test-device', 'hostname': 'live', 'architecture': 'x86_64', 'boot_mode': 'bios',
            'memory': {'total_bytes': 1024**3}, 'cpu': {'threads': 2, 'model': 'Intel Atom'},
            'installer_media': {'identified': True, 'disk_paths': ['/dev/sdb']},
            'disks': [{'path': '/dev/vda', 'size_bytes': 16*1024**3, 'serial': 'VM-DISK-1', 'wwn': None,
                       'installer': False, 'mounted': False, 'read_only': False}]}


def plan():
    return create_plan(report(), '/dev/vda', 'my-server', ['web'], key())


def rehash(plan):
    plan['plan_id'] = canonical_plan_id(plan)
    return plan


def test_plan_binds_all_approved_values():
    proposed = plan()
    assert validate_plan(proposed) == proposed
    assert proposed['profile_config'] == {'web': {}}
    assert proposed['disk']['serial'] == 'VM-DISK-1'
    assert len(proposed['plan_id']) == 64
    changed = copy.deepcopy(proposed)
    changed['hostname'] = 'other-server'
    with pytest.raises(ValueError, match='checksum'):
        validate_plan(changed)


def test_hash_is_order_independent():
    proposed = plan()
    assert canonical_plan_id(proposed) == canonical_plan_id(dict(reversed(list(proposed.items()))))


def test_normalize_key_removes_comment_and_outer_whitespace():
    assert normalize_authorized_key('  ' + key() + ' workstation\n') == key()


@pytest.mark.parametrize('value', ['command="id" ' + key(), key() + '\n' + key(), 'ssh-ed25519 AA==', 'ssh-rsa !!!', 12, ''])
def test_reject_unsafe_or_malformed_keys(value):
    with pytest.raises(ValueError):
        normalize_authorized_key(value)


@pytest.mark.parametrize('field,value', [
    ('hostname', 'bad;reboot'), ('hostname', '-option'), ('hostname', 'server\nname'),
    ('device_id', '../escape'), ('distro', 'alpine'), ('suite', 'stretch'),
    ('architecture', 'i386'), ('admin_user', 'root'), ('profiles', ['arbitrary']),
    ('profiles', ['web', 'web']), ('version', True), ('partition_table', 'arbitrary'),
    ('boot_mode', 'arbitrary'), ('profile_config', {'web': {'password': 'secret'}}),
])
def test_reject_invalid_plan_fields_even_with_recalculated_hash(field, value):
    proposed = plan()
    proposed[field] = value
    with pytest.raises(ValueError):
        validate_plan(rehash(proposed))


@pytest.mark.parametrize('field,value', [('path', '/dev/vda1'), ('path', '/dev/vda;id'), ('path', '/dev/disk/by-id/x'),
                                        ('size_bytes', 3*1024**3), ('size_bytes', True), ('serial', 'bad\nserial')])
def test_reject_invalid_disk_fields(field, value):
    proposed = plan()
    proposed['disk'][field] = value
    with pytest.raises(ValueError):
        validate_plan(rehash(proposed))


def test_reject_unknown_plan_fields():
    proposed = plan()
    proposed['shell_command'] = 'touch /tmp/no'
    with pytest.raises(ValueError, match='fields'):
        validate_plan(rehash(proposed))


def test_disk_identity_required():
    hardware = report()
    hardware['disks'][0]['serial'] = None
    with pytest.raises(ValueError, match='serial'):
        create_plan(hardware, '/dev/vda', 'server', [], key())


def test_uefi_requires_gpt():
    hardware = report()
    hardware['boot_mode'] = 'uefi'
    with pytest.raises(ValueError, match='GPT'):
        create_plan(hardware, '/dev/vda', 'server', [], key(), partition_table='mbr')
    proposed = create_plan(hardware, '/dev/vda', 'server', [], key())
    assert partition_layout(proposed)[0]['purpose'] == 'EFI system'


def test_bios_gpt_and_mbr():
    assert partition_layout(plan())[0]['purpose'] == 'BIOS boot'
    proposed = create_plan(report(), '/dev/vda', 'server', [], key(), partition_table='mbr')
    assert len(partition_layout(proposed)) == 1


def test_mbr_limit():
    hardware = report()
    hardware['disks'][0]['size_bytes'] = 3*1024**4
    with pytest.raises(ValueError, match='2 TiB'):
        create_plan(hardware, '/dev/vda', 'server', [], key(), partition_table='mbr')


def test_configuration_secrets_not_saved_in_plan():
    with pytest.raises(ValueError, match='credentials'):
        create_plan(report(), '/dev/vda', 'server', ['fileserver'], key(), profile_config={'fileserver': {'password': 'supersecurepassword'}})


def test_profile_defaults_are_hashed():
    proposed = create_plan(report(), '/dev/vda', 'server', ['vpn', 'fileserver'], key())
    assert proposed['profile_config']['vpn']['listen_port'] == 51820
    assert proposed['profile_config']['fileserver']['path'] == '/srv/ulsim/share'
    assert 'password' not in proposed['profile_config']['fileserver']


def test_unknown_live_media_prevents_plan():
    hardware = report()
    hardware['installer_media']['identified'] = False
    with pytest.raises(ValueError, match='installer medium'):
        create_plan(hardware, '/dev/vda', 'server', [], key())


def test_recommendations_respect_old_hardware():
    result = recommend(report())
    apps = {a['id']: a for a in result['workloads']}
    assert apps['minecraft']['suitability'] == 'not_recommended'
    assert apps['wireguard']['suitability'] == 'suitable'
    assert apps['samba']['suitability'] == 'suitable'
    assert apps['home-assistant']['suitability'] == 'not_recommended'
    assert apps['dlna']['installation_profile'] == 'media'
    assert result['distributions'][0]['installation_supported']
    assert not result['distributions'][1]['installation_supported']
    assert len(apps) >= 27


def test_unknown_hardware_does_not_invent_recommendation():
    result = recommend({})
    assert all(a['suitability'] == 'unknown' for a in result['workloads'])
    assert result['budget']['ram_bytes'] is None


@pytest.mark.parametrize('boot_mode,table,expected', [
    ('bios', 'gpt', [
        {'number': 1, 'purpose': 'BIOS boot', 'filesystem': None, 'size_mib': 2},
        {'number': 2, 'purpose': 'Linux root', 'filesystem': 'ext4', 'size_mib': 'remaining'},
    ]),
    ('bios', 'mbr', [
        {'number': 1, 'purpose': 'Linux root (bootable)', 'filesystem': 'ext4', 'size_mib': 'remaining'},
    ]),
    ('uefi', 'gpt', [
        {'number': 1, 'purpose': 'EFI system', 'filesystem': 'fat32', 'size_mib': 512},
        {'number': 2, 'purpose': 'Linux root', 'filesystem': 'ext4', 'size_mib': 'remaining'},
    ]),
])
def test_controller_partition_preview_on_every_platform(boot_mode, table, expected):
    # Controller planning must run without importing the Linux-only installer.
    hardware = report()
    hardware['boot_mode'] = boot_mode
    proposed = create_plan(hardware, '/dev/vda', 'server', [], key(), partition_table=table)
    assert partition_layout(proposed) == expected
