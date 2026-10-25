"""Persistent controller workflow. Never repeat disk writes on resume."""
from __future__ import annotations
import time
from .inventory import Inventory, now
from .ssh import Remote


def remote_for(device):
    return Remote(device["address"], device.get("port", 22), device["key_path"], device["host_fingerprint"], device.get("username", "ulsim"))


def reconnect(inventory, device, timeout=600):
    """Try known address and matching mDNS IDs; every candidate must pass pinned SSH."""
    from .discovery import discover
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        candidates = [(device["address"], device.get("port", 22))]
        if attempt % 3 == 0:
            try:
                for entry in discover(2):
                    if entry.get("device_id") == device["device_id"] and entry.get("address"):
                        candidates.append((entry["address"], entry["port"]))
            except OSError:
                pass
        for host, port in candidates:
            candidate = {**device, "address": host, "port": port}
            try:
                remote = remote_for(candidate)
                identity = remote.rpc("identity")
                if identity.get("device_id") != device["device_id"]:
                    continue
                if identity.get("mode") != "installed":
                    continue
                inventory.save_device({**candidate, "last_seen": now(), "os": identity.get("os")})
                return remote, identity
            except Exception as exc:
                # Host-key failure is not silently accepted, even if another IP is discovered.
                if "Host identity mismatch" in str(exc):
                    raise
        attempt += 1
        time.sleep(5)
    raise TimeoutError("Installed system did not reconnect. Check boot order/remove installer USB, inspect console, then use install --resume. No disk writes were retried.")


def finish_install(inventory: Inventory, plan: dict, timeout=3600, resume=False, secrets=None):
    job_id = plan["plan_id"]
    device = inventory.get_device(plan["device_id"])
    remote = remote_for(device)
    job = inventory.job(job_id)
    if not job:
        raise ValueError("No approved installation journal exists")
    if job["stage"] == "complete":
        return job
    if job["stage"] == "failed":
        if not resume:
            raise ValueError("Installation failed; inspect logs before using --resume. Resume never repartitions a disk")
        inventory.transition(job_id, "reconnecting")
    try:
        if job["stage"] in {"approved", "preparing", "installing", "bootloader"}:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                status = remote.rpc("status")
                state = status.get("stage", status.get("state"))
                if status.get("plan_id") not in (None, job_id):
                    raise RuntimeError("Target job does not match the approved plan")
                if state == "failed":
                    raise RuntimeError(f"Target installation failed: {status.get('error', 'see ulsim logs')}")
                if state in {"ready", "installed", "rebooting", "complete"}:
                    inventory.transition(job_id, "rebooting", status)
                    break
                current = inventory.job(job_id)["stage"]
                if state in {"preparing", "installing", "bootloader"} and state != current:
                    inventory.transition(job_id, state, status)
                time.sleep(3)
            else:
                raise TimeoutError("Installation timed out; inspect status/logs before resuming")
        stage = inventory.job(job_id)["stage"]
        if stage == "rebooting":
            remote.rpc("reboot")
            inventory.transition(job_id, "reconnecting")
            time.sleep(5)
        if inventory.job(job_id)["stage"] == "reconnecting":
            remote, identity = reconnect(inventory, device, min(timeout, 600))
            osinfo = identity.get("os", {})
            if isinstance(osinfo, dict) and osinfo.get("ID", osinfo.get("id")) != "debian":
                raise RuntimeError("Reconnected system is not Debian")
            if identity.get("plan_id") != plan["plan_id"]:
                raise RuntimeError("Installed OS does not match the approved plan")
            inventory.transition(job_id, "configuring", identity)
        if inventory.job(job_id)["stage"] == "configuring":
            # Credentials are supplied only in-memory via SSH stdin; never saved in plan/journal.
            config = {k: dict(v) for k, v in plan.get("profile_config", {}).items()}
            for name, values in (secrets or {}).items():
                config.setdefault(name, {}).update(values)
            remote.rpc("configure", {"profiles": plan["profiles"], "config": config})
            inventory.transition(job_id, "verifying")
        if inventory.job(job_id)["stage"] == "verifying":
            services = remote.rpc("services", {"profiles": plan["profiles"], "verify": True})
            if services.get("ok") is not True or set(services.get("profiles", {})) != set(plan["profiles"]):
                raise RuntimeError("Application verification failed; see ulsim services")
            health = remote.rpc("health")
            inventory.save_device({"device_id": plan["device_id"], "profiles": plan["profiles"], "hostname": plan["hostname"],
                                   "os": "debian", "installed": True, "health": health, "last_seen": now()})
            return inventory.transition(job_id, "complete", {"services": services, "health": health})
    except Exception as exc:
        if inventory.job(job_id)["stage"] != "failed":
            inventory.transition(job_id, "failed", {"error": str(exc)})
        raise
