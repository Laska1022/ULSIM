import json
import pytest
from ulsim.cli import main, parser
from ulsim.ssh import validate_fingerprint


def test_every_command_help():
    commands = ['discover','devices','servers','pair','connect','inspect','recommend','plan','install','status','logs','services','health','update','reboot','configure-usb','configure-wifi']
    for command in commands:
        with pytest.raises(SystemExit) as exc:
            parser().parse_args([command,'--help'])
        assert exc.value.code == 0


def test_cli_json_empty_inventory(tmp_path,capsys):
    assert main(['--state-dir',str(tmp_path),'devices','--json']) == 0
    assert json.loads(capsys.readouterr().out) == {'devices':[]}


def test_pair_requires_physical_trust(tmp_path,capsys):
    assert main(['--state-dir',str(tmp_path),'pair','--host','localhost','--json']) == 1
    assert 'physically verified' in json.loads(capsys.readouterr().out)['error']


def test_fingerprint_rejects_md5_and_malformed():
    for value in ['','MD5:00','SHA256:any','SHA256:' + ';'*43]:
        with pytest.raises(ValueError):
            validate_fingerprint(value)
