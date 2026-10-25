"""Controller resume and verification contracts; VM tests prove the real install."""
import pytest
from ulsim.inventory import Inventory
from ulsim import orchestration as flow


def setup_job(tmp_path, stage='preparing'):
    inventory = Inventory(tmp_path)
    inventory.save_device({'device_id':'target','address':'192.168.1.2','key_path':'key','host_fingerprint':'SHA256:'+'A'*43})
    plan = {'plan_id':'approved-plan','device_id':'target','profiles':['web'],'profile_config':{},'hostname':'server'}
    inventory.new_job(plan)
    for state in ['approved','preparing','rebooting','reconnecting','configuring','verifying']:
        inventory.transition(plan['plan_id'],state)
        if state == stage:
            break
    return inventory, plan


class Remote:
    def __init__(self, verification=True):
        self.ops=[]
        self.verification=verification
    def rpc(self, op, payload=None):
        self.ops.append(op)
        return {'status':{'stage':'ready','plan_id':'approved-plan'},'reboot':{'ok':True},
                'configure':{'ok':True},'services':{'ok':self.verification,'profiles':{'web':{'ok':self.verification}}},
                'health':{'memory':{'available_bytes':100}}}[op]


def test_completed_install_verifies_plan_and_services(tmp_path,monkeypatch):
    inventory,plan=setup_job(tmp_path)
    remote=Remote()
    monkeypatch.setattr(flow,'remote_for',lambda device:remote)
    monkeypatch.setattr(flow.time,'sleep',lambda seconds:None)
    monkeypatch.setattr(flow,'reconnect',lambda *a: (remote,{'plan_id':'approved-plan','os':{'id':'debian'}}))
    assert flow.finish_install(inventory,plan)['stage']=='complete'
    assert remote.ops==['status','reboot','configure','services','health']
    assert inventory.get_device('target')['installed']


def test_failed_services_cannot_mark_complete(tmp_path,monkeypatch):
    inventory,plan=setup_job(tmp_path,'verifying')
    remote=Remote(False)
    monkeypatch.setattr(flow,'remote_for',lambda device:remote)
    with pytest.raises(RuntimeError,match='verification failed'):
        flow.finish_install(inventory,plan)
    assert inventory.job(plan['plan_id'])['stage']=='failed'
    assert 'health' not in remote.ops


def test_wrong_installed_plan_never_configures(tmp_path,monkeypatch):
    inventory,plan=setup_job(tmp_path,'reconnecting')
    remote=Remote()
    monkeypatch.setattr(flow,'remote_for',lambda device:remote)
    monkeypatch.setattr(flow,'reconnect',lambda *a: (remote,{'plan_id':'different','os':{'id':'debian'}}))
    with pytest.raises(RuntimeError,match='approved plan'):
        flow.finish_install(inventory,plan)
    assert 'configure' not in remote.ops


def test_resume_never_starts_an_installer(tmp_path,monkeypatch):
    inventory,plan=setup_job(tmp_path,'reconnecting')
    inventory.transition(plan['plan_id'],'failed')
    remote=Remote()
    monkeypatch.setattr(flow,'remote_for',lambda device:remote)
    monkeypatch.setattr(flow,'reconnect',lambda *a: (remote,{'plan_id':'approved-plan','os':{'id':'debian'}}))
    assert flow.finish_install(inventory,plan,resume=True)['stage']=='complete'
    assert 'install' not in remote.ops
    assert 'reboot' not in remote.ops
