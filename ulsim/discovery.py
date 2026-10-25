"""LAN mDNS discovery; advertisements never establish trust."""
import threading
from zeroconf import ServiceBrowser, Zeroconf

SERVICE = "_ulsim._tcp.local."


def discover(timeout=3.0) -> list[dict]:
    if not 0 < timeout <= 120:
        raise ValueError("Discovery timeout must be between 0 and 120 seconds")
    found = {}
    lock = threading.Lock()

    class Listener:
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name, timeout=1500)
            if info:
                addresses = info.parsed_scoped_addresses()
                addresses.sort(key=lambda a: ":" in a)
                props = {k.decode(errors="replace"): (v or b"").decode(errors="replace") for k, v in info.properties.items()}
                with lock:
                    found[name] = {"hostname": (info.server or name).rstrip("."), "address": addresses[0] if addresses else None,
                                   "addresses": addresses, "port": info.port, "device_id": props.get("device_id"),
                                   "trusted": False}
        update_service = add_service
        def remove_service(self, zc, type_, name):
            with lock:
                found.pop(name, None)

    with Zeroconf() as zc:
        browser = ServiceBrowser(zc, SERVICE, Listener())
        threading.Event().wait(timeout)
        browser.cancel()
    return sorted(found.values(), key=lambda d: d["hostname"])
