"""Real mDNS packet discovery on loopback, without scanning the local network."""
import socket
import uuid

from zeroconf import IPVersion, ServiceInfo, Zeroconf

from ulsim import discovery


def test_mdns_advertisement_is_discovered_but_never_trusted(monkeypatch):
    name = "test-" + uuid.uuid4().hex[:8]
    options = {"interfaces": ["127.0.0.1"], "ip_version": IPVersion.V4Only}
    monkeypatch.setattr(discovery, "Zeroconf", lambda: Zeroconf(**options))
    info = ServiceInfo(discovery.SERVICE, name + "." + discovery.SERVICE,
                       addresses=[socket.inet_aton("127.0.0.1")], port=22222,
                       properties={b"device_id": b"protocol-test-device"},
                       server=name + ".local.")
    with Zeroconf(**options) as advertiser:
        advertiser.register_service(info)
        try:
            records = discovery.discover(timeout=2)
        finally:
            advertiser.unregister_service(info)
    matches = [record for record in records if record["device_id"] == "protocol-test-device"]
    assert len(matches) == 1
    assert matches[0]["address"] == "127.0.0.1"
    assert matches[0]["port"] == 22222
    assert matches[0]["hostname"] == name + ".local"
    assert matches[0]["trusted"] is False
