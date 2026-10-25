import io
import json

import pytest

from ulsim import target


def test_dispatch_rejects_arbitrary_operations_and_fields():
    with pytest.raises(ValueError):
        target.dispatch('shell', {'command': 'id'})
    with pytest.raises(ValueError):
        target.dispatch('identity', {'command': 'id'})


def test_identity_distinguishes_live_and_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(target, 'CONFIG', tmp_path)
    (tmp_path / 'device-id').write_text('test-device')
    assert not target.identity()['installed']
    (tmp_path / 'installed.json').write_text(json.dumps({'plan_id': 'a' * 64, 'device_id': 'test-device'}))
    identity = target.identity()
    assert identity['installed']
    assert identity['device_id'] == 'test-device'
    assert identity['plan_id'] == 'a' * 64


def test_main_outputs_exactly_json_even_if_helper_prints(monkeypatch, capsys):
    monkeypatch.setattr(target.sys, 'stdin', io.StringIO('{}'))
    def dispatch(operation, payload):
        print('diagnostics')
        return {'ok': True}
    monkeypatch.setattr(target, 'dispatch', dispatch)
    assert target.main(['identity']) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {'ok': True}
    assert output.err.strip() == 'diagnostics'


def test_oversized_request_fails(monkeypatch, capsys):
    monkeypatch.setattr(target.sys, 'stdin', io.StringIO('x' * (target.MAX_REQUEST + 1)))
    assert target.main(['identity']) == 1
    assert 'exceeds' in json.loads(capsys.readouterr().out)['error']


def test_mutations_require_root(monkeypatch):
    monkeypatch.setattr(target.os, 'geteuid', lambda: 1000, raising=False)
    with pytest.raises(PermissionError):
        target.dispatch('update', {})


def test_configure_rejects_live_environment(monkeypatch):
    monkeypatch.setattr(target.os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setattr(target, 'identity', lambda: {'installed': False})
    with pytest.raises(ValueError, match='installed Debian'):
        target.dispatch('configure', {'profiles': ['web']})
