"""Windows-native deterministic CLI for Codex and human operators."""
from __future__ import annotations
import argparse
import getpass
import json
import sys
from pathlib import Path
from .inventory import Inventory, now
from .orchestration import remote_for, finish_install
from .provision import configure_usb


def parser():
    p = argparse.ArgumentParser(prog="ulsim", description="Secure remote Debian installer and server manager")
    p.add_argument("--state-dir", type=Path, help="Controller inventory/key directory")
    p.add_argument("--version", action="version", version="ulsim 0.1.0")
    commands = p.add_subparsers(dest="command", required=True)
    for name, help_ in {
        "discover":"Discover ULSIM hosts using mDNS", "devices":"List trusted devices", "servers":"List installed servers",
        "pair":"Pair using a physical USB record or console host fingerprint", "connect":"Check authenticated SSH access",
        "inspect":"Read actual target hardware", "recommend":"Recommend workloads and distributions", "plan":"Create a reviewable installation plan",
        "install":"Execute an explicitly approved plan and optionally follow through reboot", "status":"Read installation progress",
        "logs":"Read target installation logs", "services":"Configure or verify server applications", "health":"Inspect system health",
        "update":"Install Debian package security and maintenance updates", "reboot":"Reboot the selected device",
        "configure-usb":"Write identity and optional Wi-Fi to an existing ULSIMCFG FAT volume",
        "configure-wifi":"Provision USB identity and Wi-Fi together before first boot",
    }.items():
        sub = commands.add_parser(name, help=help_, description=help_)
        sub.add_argument("--json", action="store_true", help="Machine-readable JSON output")
        if name not in {"discover","devices","servers","pair","configure-usb","configure-wifi","install"}:
            sub.add_argument("--device", help="Known device ID or unique name; may omit if only one paired")
        if name == "discover":
            sub.add_argument("--timeout", type=float, default=3)
        if name == "pair":
            sub.add_argument("--host", required=True, help="Manual IP or hostname")
            sub.add_argument("--port", type=int, default=22)
            sub.add_argument("--record", type=Path, help="Physical USB provisioning record generated on this controller")
            sub.add_argument("--fingerprint", help="SHA256 host fingerprint read from physical console")
            sub.add_argument("--key", type=Path, help="Controller private SSH key")
            sub.add_argument("--name", help="Friendly inventory name")
        if name in {"configure-usb","configure-wifi"}:
            sub.add_argument("--volume", type=Path, required=True, help="Mounted FAT volume labelled ULSIMCFG, e.g. E:\\")
            sub.add_argument("--key", type=Path)
            sub.add_argument("--ssid", required=name == "configure-wifi")
        if name == "recommend":
            sub.add_argument("--report", type=Path, help="Use a previously saved hardware JSON report")
        if name == "inspect":
            sub.add_argument("--output", type=Path)
        if name == "plan":
            sub.add_argument("--disk", required=True, help="Exact target path from inspect, e.g. /dev/sda")
            sub.add_argument("--hostname", required=True)
            sub.add_argument("--profile", action="append", default=[], choices=["dns","fileserver","vpn","web","media"])
            sub.add_argument("--partition-table", choices=["gpt","mbr"], default="gpt")
            sub.add_argument("--config", type=Path, help="Profile configuration JSON; no passwords")
            sub.add_argument("--output", type=Path, required=True)
        if name == "install":
            sub.add_argument("--plan", type=Path, required=True)
            sub.add_argument("--approve", help="Exact plan_id SHA256 after reviewing entire plan; authorizes one disk erase")
            sub.add_argument("--wait", action="store_true", help="Wait, reboot, reconnect, configure and verify applications")
            sub.add_argument("--resume", action="store_true", help="Resume an existing approved journal; never reformat disk")
            sub.add_argument("--timeout", type=int, default=3600)
        if name == "services":
            sub.add_argument("--profile", action="append", default=[])
            sub.add_argument("--configure", action="store_true", help="Install/configure explicitly selected profiles")
            sub.add_argument("--config", type=Path)
            sub.add_argument("--verify", action="store_true")
        if name in {"update","reboot"}:
            sub.add_argument("--yes", action="store_true", help="Approve this operation noninteractively")
    return p


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def emit(value, as_json=False):
    # Human output retains all evidence and unknown fields instead of hiding detail.
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(value, indent=2, ensure_ascii=False))


def secrets_for(profiles):
    if "fileserver" in profiles:
        if not sys.stdin.isatty():
            raise ValueError("Initial Samba setup requires a password via an interactive terminal. Run install --resume --wait interactively, or configure fileserver separately")
        password = getpass.getpass("Samba password (leave empty to retain existing account password): ")
        return {"fileserver": {"password": password}} if password else {}
    return {}


def execute(args, inventory):
    name = args.command
    if name == "discover":
        from .discovery import discover
        return {"devices": discover(args.timeout)}
    if name in {"devices","servers"}:
        devices = inventory.devices()
        return {"devices": [d for d in devices if name != "servers" or d.get("installed")]}
    if name in {"configure-usb","configure-wifi"}:
        password = getpass.getpass("Wi-Fi password: ") if args.ssid else None
        return configure_usb(args.volume, inventory.directory, args.key, args.ssid, password)
    if name == "pair":
        from .ssh import Remote
        record = read_json(args.record) if args.record else {}
        key_path = args.key or record.get("key_path")
        fp = args.fingerprint or record.get("host_fingerprint")
        if not key_path or not fp:
            raise ValueError("Provide --record, or both --key and a physically verified --fingerprint")
        remote = Remote(args.host, args.port, key_path, fp)
        identity = remote.rpc("identity")
        if record.get("device_id") and record["device_id"] != identity.get("device_id"):
            raise ValueError("Target identity does not match the physically provisioned device")
        return inventory.save_device({**identity, "name": args.name or identity.get("hostname"), "address": args.host,
                                      "port": args.port,"key_path":str(Path(key_path).resolve()),"host_fingerprint":fp,"last_seen":now()})
    if name == "install":
        from .planning import validate_plan
        plan = read_json(args.plan)
        validate_plan(plan)
        device = inventory.get_device(plan["device_id"])
        if args.resume:
            if not inventory.job(plan["plan_id"]):
                raise ValueError("No installation journal exists for this plan")
            return finish_install(inventory, plan, args.timeout, resume=True, secrets=secrets_for(plan["profiles"]) if args.wait else {}) if args.wait else inventory.job(plan["plan_id"])
        if args.approve != plan["plan_id"]:
            raise ValueError("Review the disk identity and complete plan, then supply --approve with the exact plan_id")
        if inventory.job(plan["plan_id"]):
            raise ValueError("This plan already has a journal. Inspect status and use --resume; an erase will not be repeated")
        # Collect secrets before initiating irreversible work, keep only in process memory.
        credentials = secrets_for(plan["profiles"]) if args.wait else {}
        inventory.new_job(plan)
        inventory.transition(plan["plan_id"], "approved")
        try:
            result = remote_for(device).rpc("install", {"plan":plan,"approval":args.approve})
            inventory.transition(plan["plan_id"], "preparing", result)
        except Exception as exc:
            inventory.transition(plan["plan_id"], "failed", {"error":str(exc), "resume_stage":"preparing"})
            raise
        return finish_install(inventory, plan, args.timeout, secrets=credentials) if args.wait else result
    if name == "recommend" and args.report:
        from .planning import recommend
        return recommend(read_json(args.report))
    device = inventory.get_device(args.device)
    remote = remote_for(device)
    if name == "plan":
        from .planning import create_plan, partition_layout
        report = remote.rpc("inspect")
        public_key = Path(device["key_path"] + ".pub").read_text().strip()
        config = read_json(args.config) if args.config else None
        plan = create_plan(report, args.disk, args.hostname, args.profile, public_key,
                           partition_table=args.partition_table, profile_config=config)
        if args.output.exists():
            raise ValueError("Plan output already exists; choose a new file to preserve prior approval")
        args.output.write_text(json.dumps(plan, indent=2) + "\n")
        return {"plan":plan,"partition_layout":partition_layout(plan),"saved_to":str(args.output),"warning":"Installation erases ONLY the identified destination disk. Review every field before approving its plan_id."}
    if name in {"inspect","recommend"}:
        report = remote.rpc("inspect")
        inventory.save_device({"device_id":device["device_id"],"hardware":report,"last_seen":now()})
        if name == "recommend":
            from .planning import recommend
            return recommend(report)
        if args.output:
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        return report
    if name == "services":
        profiles = args.profile or device.get("profiles", [])
        config = read_json(args.config) if args.config else {}
        if args.configure:
            if not args.profile:
                raise ValueError("Choose explicit --profile entries to configure")
            for profile, secret in secrets_for(profiles).items():
                config.setdefault(profile, {}).update(secret)
            result = remote.rpc("configure", {"profiles":profiles,"config":config})
            inventory.save_device({"device_id":device["device_id"],"profiles":sorted(set(device.get("profiles",[])) | set(profiles))})
            return result
        return remote.rpc("services", {"profiles":profiles,"verify":args.verify})
    if name in {"update","reboot"} and not args.yes:
        if not sys.stdin.isatty() or input(f"{name.capitalize()} {device.get('name',device['device_id'])}? [y/N] ").lower() != "y":
            raise ValueError("Operation not approved; use --yes for explicitly authorized automation")
    result = remote.rpc("identity" if name == "connect" else name)
    inventory.save_device({"device_id":device["device_id"],"last_seen":now(), **({"health":result} if name == "health" else {})})
    return result


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        result = execute(args, Inventory(args.state_dir))
        emit(result, args.json)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        message = "Interrupted; use status before resuming" if isinstance(exc, KeyboardInterrupt) else str(exc)
        if args.json:
            print(json.dumps({"error":message}), file=sys.stdout)
        else:
            print(f"ulsim: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
