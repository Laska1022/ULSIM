import pytest
from ulsim.inventory import Inventory


def test_inventory_persists_and_ambiguity_fails(tmp_path):
    inventory = Inventory(tmp_path)
    inventory.save_device({'device_id':'a','name':'one','address':'192.168.1.2'})
    inventory.save_device({'device_id':'b','name':'two'})
    assert Inventory(tmp_path).get_device('one')['address'] == '192.168.1.2'
    with pytest.raises(ValueError):
        inventory.get_device(None)
    inventory.save_device({'device_id':'a','os':'debian'})
    assert inventory.get_device('a')['address'] == '192.168.1.2'


def test_state_machine_rejects_false_completion(tmp_path):
    inventory = Inventory(tmp_path)
    plan = {'plan_id':'hash','device_id':'a'}
    inventory.new_job(plan)
    with pytest.raises(ValueError):
        inventory.transition('hash','complete')
    for stage in ['approved','preparing','installing','bootloader','rebooting','reconnecting','configuring','verifying','complete']:
        inventory.transition('hash',stage)
    assert Inventory(tmp_path).job('hash')['stage'] == 'complete'


def test_failed_resume_does_not_allow_disk_rewrite(tmp_path):
    inventory = Inventory(tmp_path)
    inventory.new_job({'plan_id':'hash','device_id':'a'})
    inventory.transition('hash','approved')
    inventory.transition('hash','failed')
    with pytest.raises(ValueError):
        inventory.transition('hash','approved')
    inventory.transition('hash','reconnecting')
