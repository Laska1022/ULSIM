import copy
from unittest.mock import patch

import pytest

from ulsim.hardware import collect, parse_cpuinfo, parse_meminfo, parse_storage, validate_destination


def tree():
    return {'blockdevices': [
        {'name': 'sda', 'path': '/dev/sda', 'type': 'disk', 'size': 8 * 1024**3,
         'serial': 'INSTALLER', 'tran': 'usb', 'rm': True, 'rota': False,
         'children': [{'name': 'sda1', 'path': '/dev/sda1', 'type': 'part', 'size': 1024**3,
                       'mountpoints': ['/run/live/medium'], 'fstype': 'iso9660'}]},
        {'name': 'vda', 'path': '/dev/vda', 'type': 'disk', 'size': 16 * 1024**3,
         'serial': 'DESTINATION', 'tran': 'virtio', 'rm': False, 'rota': False,
         'children': [{'name': 'vda1', 'path': '/dev/vda1', 'type': 'part', 'size': 8 * 1024**3,
                       'mountpoints': [None], 'fstype': 'ext4'}]},
    ]}


def report():
    disks, media = parse_storage(tree(), ['/dev/sda1'])
    return {'disks': disks, 'installer_media': media}


def identity(report, index=1):
    return {key: report['disks'][index][key] for key in ('path', 'size_bytes', 'serial', 'wwn')}


def test_memory_units_and_unknowns():
    result = parse_meminfo('MemTotal: 2048 kB\nMemAvailable: 1024 kB\nSwapTotal: 0 kB\n')
    assert result['total_bytes'] == 2097152
    assert result['available_bytes'] == 1048576
    assert result['swap_total_bytes'] == 0
    assert result['swap_free_bytes'] is None
    assert parse_meminfo('garbage')['total_bytes'] is None


def test_cpu_cores_threads_and_flags():
    block = 'processor: {p}\nmodel name: Intel Atom\nvendor_id: GenuineIntel\nphysical id: 0\ncore id: {c}\nflags: lm vmx sse2'
    result = parse_cpuinfo('\n\n'.join(block.format(p=p, c=p // 2) for p in range(4)))
    assert result['threads'] == 4
    assert result['cores'] == 2
    assert result['virtualization'] == 'vmx'
    assert result['manufacturer'] == 'GenuineIntel'
    assert parse_cpuinfo('')['cores'] is None


def test_live_medium_marked_by_ancestry():
    disks, media = parse_storage(tree(), ['/dev/sda1'])
    assert media['identified'] is True
    assert media['disk_paths'] == ['/dev/sda']
    assert disks[0]['installer'] is True
    assert disks[0]['mounted'] is True
    assert disks[1]['installer'] is False
    assert disks[1]['mounted'] is False
    assert disks[1]['partitions'][0]['filesystem'] == 'ext4'


def test_usb_transport_does_not_determine_installer():
    source = tree()
    source['blockdevices'][1]['tran'] = 'usb'
    disks, _ = parse_storage(source, ['/dev/sda1'])
    assert not disks[1]['installer']
    assert disks[1]['medium'] == 'USB'


@pytest.mark.parametrize('sources', [[], ['/dev/missing'], ['/dev/sda1', '/dev/missing'], ['overlay']])
def test_unknown_live_ancestry_disables_installs(sources):
    _, media = parse_storage(tree(), sources)
    assert media['identified'] is False


def test_cdrom_installer_is_identifiable():
    source = tree()
    source['blockdevices'].append({'name': 'sr0', 'type': 'rom', 'path': '/dev/sr0', 'mountpoints': ['/run/live/medium']})
    disks, media = parse_storage(source, ['/dev/sr0'])
    assert media == {'identified': True, 'sources': ['/dev/sr0'], 'disk_paths': ['/dev/sr0']}
    assert all(d['path'] != '/dev/sr0' for d in disks)


def test_device_mapper_ancestor_is_protected():
    source = tree()
    source['blockdevices'][0]['children'][0]['children'] = [
        {'name': 'dm-0', 'path': '/dev/mapper/live', 'type': 'crypt', 'mountpoints': ['/run/live/medium']}]
    _, media = parse_storage(source, ['/dev/mapper/live'])
    assert media['disk_paths'] == ['/dev/sda']


def test_pkname_works_without_nested_tree():
    source = tree()
    child = source['blockdevices'][0].pop('children')[0]
    child['pkname'] = 'sda'
    source['blockdevices'].append(child)
    _, media = parse_storage(source, ['/dev/sda1'])
    assert media['identified']


def test_approved_destination_is_validated_again():
    current = report()
    assert validate_destination(current, identity(current))['path'] == '/dev/vda'


@pytest.mark.parametrize('field,value', [('serial', 'REPLACED'), ('wwn', 'CHANGED'), ('size_bytes', 42)])
def test_changed_disk_identity_rejected(field, value):
    current = report()
    disk = identity(current)
    current['disks'][1][field] = value
    with pytest.raises(ValueError, match='changed'):
        validate_destination(current, disk)


def test_installer_disk_rejected():
    current = report()
    with pytest.raises(ValueError, match='installer medium'):
        validate_destination(current, identity(current, 0))


@pytest.mark.parametrize('field', ['mounted', 'read_only'])
def test_in_use_disk_rejected(field):
    current = report()
    current['disks'][1][field] = True
    with pytest.raises(ValueError, match='mounted|read-only'):
        validate_destination(current, identity(current))


def test_duplicate_serial_rejected():
    current = report()
    duplicate = copy.deepcopy(current['disks'][1])
    duplicate['path'] = '/dev/vdb'
    current['disks'].append(duplicate)
    with pytest.raises(ValueError, match='duplicated'):
        validate_destination(current, identity(current))


def test_swap_on_child_counts_as_mounted():
    source = tree()
    source['blockdevices'][1]['children'][0]['mountpoints'] = ['[SWAP]']
    disks, _ = parse_storage(source, ['/dev/sda1'])
    assert disks[1]['mounted']


def test_collection_reports_unavailable_without_fabrication():
    with patch('ulsim.hardware._json', return_value=None), patch('ulsim.hardware._run', return_value=None), \
            patch('ulsim.hardware._read', return_value=None):
        result = collect()
    assert result['cpu']['model'] is None
    assert result['memory']['total_bytes'] is None
    assert result['disks'] == []
    assert result['device_id'] is None
    assert result['installer_media']['identified'] is False
    assert any('unavailable' in note for note in result['unknowns'])
