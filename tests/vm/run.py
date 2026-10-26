#!/usr/bin/env python3
"""Destructive end-to-end tests restricted to newly created disposable VM disks.

No installation behavior is mocked. A successful result requires booting the live
image, installing Debian, removing the installer, booting the installed disk,
reusing the pinned SSH identity, and serving HTTP from installed nginx.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fingerprint(public_key: Path) -> str:
    import base64
    return "SHA256:" + base64.b64encode(
        hashlib.sha256(base64.b64decode(public_key.read_text().split()[1])).digest()
    ).decode().rstrip("=")


def prepare_configuration(work: Path, network: Path | None = None) -> tuple[Path, Path, str]:
    """Physical USB trust establishment, using fresh ephemeral test-only keys."""
    key = work / "controller"
    host_key = work / "ssh_host_ed25519_key"
    for path in (key, host_key):
        run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path))
    (work / "authorized_keys").write_text(key.with_suffix(".pub").read_text())
    configuration = work / "configuration.img"
    with configuration.open("wb") as stream:
        stream.truncate(64 * 1024 * 1024)
    run("mkfs.vfat", "-n", "ULSIMCFG", str(configuration))
    for name in ("authorized_keys", "ssh_host_ed25519_key", "ssh_host_ed25519_key.pub"):
        run("mcopy", "-i", str(configuration), str(work / name), "::/" + name)
    if network:
        for name in ("proxy.json", "trusted-ca.crt"):
            source = network / name
            if source.exists():
                if source.is_symlink() or not source.is_file() or source.stat().st_size > 65536:
                    raise ValueError(f"Invalid private network provisioning file: {name}")
                run("mcopy", "-i", str(configuration), str(source), "::/" + name)
    return configuration, key, fingerprint(host_key.with_suffix(".pub"))


class VirtualMachine:
    def __init__(self, args, work: Path, disk: Path, config: Path):
        self.args, self.work, self.disk, self.config = args, work, disk, config
        self.process: subprocess.Popen | None = None
        self.ssh_port, self.http_port = free_port(), free_port()
        self.serial_path = work / "serial-live.log"
        self.error_stream = None
        self.vars_path = work / "OVMF_VARS.fd"
        if args.firmware == "uefi":
            shutil.copyfile(args.ovmf_vars, self.vars_path)

    def start(self, live: bool) -> None:
        if self.process is not None:
            raise RuntimeError("VM is already running")
        phase = "live" if live else "installed"
        self.serial_path = self.work / f"serial-{phase}.log"
        command = [
            "qemu-system-x86_64", "-machine", "q35", "-accel", self.args.accel,
            "-m", str(self.args.memory), "-smp", "2", "-display", "none",
            "-monitor", "none", "-serial", f"file:{self.serial_path}",
            "-device", "virtio-rng-pci", "-device", "qemu-xhci",
            "-drive", f"file={self.disk},if=none,id=target,format=qcow2",
            "-device", f"virtio-blk-pci,drive=target,serial=ULSIMTESTDISK,bootindex={2 if live else 1}",
            "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{self.ssh_port}-:22,hostfwd=tcp:127.0.0.1:{self.http_port}-:80",
            "-device", "virtio-net-pci,netdev=net0,mac=52:54:00:12:34:56",
        ]
        if self.args.firmware == "uefi":
            command += ["-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={self.args.ovmf_code}",
                        "-drive", f"if=pflash,format=raw,unit=1,file={self.vars_path}"]
        if live:
            command += ["-no-reboot"]
            command += [
                "-drive", f"file={self.args.image},if=none,id=live,format=raw,readonly=on",
                "-device", "usb-storage,drive=live,removable=on,serial=ULSIMLIVE,bootindex=1",
                "-drive", f"file={self.config},if=none,id=config,format=raw",
                "-device", "usb-storage,drive=config,removable=on,serial=ULSIMCFG",
            ]
        self.error_stream = (self.work / f"qemu-{phase}.log").open("w")
        self.process = subprocess.Popen(command, stdout=self.error_stream, stderr=subprocess.STDOUT)

    def ensure_running(self) -> None:
        if not self.process or self.process.poll() is not None:
            raise RuntimeError(f"QEMU exited; inspect {self.work} logs")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
        if self.error_stream:
            self.error_stream.close()
            self.error_stream = None


def wait_remote(vm: VirtualMachine, remote, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    last_error = "SSH not attempted"
    while time.monotonic() < deadline:
        vm.ensure_running()
        try:
            identity = remote.rpc("identity")
            if not identity.get("device_id"):
                raise RuntimeError(f"Missing device identity: {identity}")
            return identity
        except Exception as exc:
            last_error = str(exc)
            # Identity mismatches must never be retried as connectivity failures.
            if "mismatch" in last_error.lower() or "host key changed" in last_error.lower():
                raise
        time.sleep(3)
    raise TimeoutError(f"SSH unavailable after {timeout}s: {last_error}; logs: {vm.serial_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--firmware", choices=("bios", "uefi"), required=True)
    parser.add_argument("--work-dir", required=True, type=Path,
                        help="Must not exist; contains only newly created disposable VM artifacts")
    parser.add_argument("--partition-table", choices=("gpt", "mbr"), default="gpt")
    parser.add_argument("--accel", choices=("tcg", "kvm"), default="tcg")
    parser.add_argument("--memory", type=int, default=2048)
    parser.add_argument("--all-profiles", action="store_true",
                        help="After required web acceptance, deploy and verify DNS, Samba, WireGuard and DLNA")
    parser.add_argument("--provision-network", type=Path,
                        help="Private directory with optional proxy.json/trusted-ca.crt for this VM only")
    parser.add_argument("--boot-timeout", type=int, default=600)
    parser.add_argument("--install-timeout", type=int, default=3600)
    parser.add_argument("--ovmf-code", default="/usr/share/OVMF/OVMF_CODE_4M.fd")
    parser.add_argument("--ovmf-vars", default="/usr/share/OVMF/OVMF_VARS_4M.fd")
    args = parser.parse_args()
    if not args.image.is_file() or args.image.stat().st_size < 64 * 1024 * 1024:
        parser.error("A real, uncompressed live image is required")
    if args.firmware == "uefi" and args.partition_table != "gpt":
        parser.error("UEFI requires GPT")
    args.image = args.image.resolve()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    os.chmod(work, 0o700)
    digest = hashlib.sha256()
    with args.image.open('rb') as image_file:
        for block in iter(lambda: image_file.read(1024 * 1024), b''):
            digest.update(block)
    result = {"firmware": args.firmware, "partition_table": args.partition_table,
              "image": str(args.image), "image_sha256": digest.hexdigest(), "passed": False, "checks": []}
    vm = None
    installer_process = None
    installer_output = None
    installer_errors = None

    def controller(*arguments):
        command = [sys.executable, '-m', 'ulsim', '--state-dir', str(work / 'controller-state'),
                   *map(str, arguments), '--json']
        process = subprocess.run(command, cwd=Path(__file__).resolve().parents[2],
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            response = json.loads(process.stdout)
        except ValueError:
            raise RuntimeError(f'Controller {arguments[0]} returned invalid JSON (exit {process.returncode})') from None
        if process.returncode:
            raise RuntimeError(f'Controller {arguments[0]} failed: {response.get("error", "unknown error")}')
        return response

    def passed(check: str) -> None:
        result["checks"].append(check)
        print(f"PASS: {check}", flush=True)
        (work / "result.json").write_text(json.dumps(result, indent=2))

    try:
        from ulsim.ssh import Remote
        from ulsim.planning import create_plan
        config, key, host_fingerprint = prepare_configuration(work, args.provision_network)
        disk = work / "target.qcow2"
        run("qemu-img", "create", "-f", "qcow2", str(disk), "16G")
        vm = VirtualMachine(args, work, disk, config)
        remote = Remote("127.0.0.1", vm.ssh_port, str(key), host_fingerprint, username="ulsim")
        vm.start(live=True)
        live_identity = wait_remote(vm, remote, args.boot_timeout)
        assert live_identity["mode"] == "live" and live_identity["os_id"] == "debian"
        paired = controller('pair', '--host', '127.0.0.1', '--port', vm.ssh_port,
                            '--fingerprint', host_fingerprint, '--key', key, '--name', 'vm')
        assert paired['device_id'] == live_identity['device_id']
        passed("live boot, DHCP, CLI pairing, SSH key authentication and pinned host identity")
        report = controller('inspect', '--device', 'vm')
        (work / "hardware.json").write_text(json.dumps(report, indent=2))
        assert report["boot_mode"] == args.firmware, report.get("boot_mode")
        assert report["architecture"] == "x86_64", report.get("architecture")
        targets = [disk for disk in report["disks"] if disk.get("serial") == "ULSIMTESTDISK"]
        assert len(targets) == 1, f"Expected one disposable target: {report['disks']}"
        assert not targets[0]["installer"] and not targets[0]["mounted"]
        protected = [disk for disk in report["disks"] if disk.get("installer")]
        assert protected, "Live installer medium must be identified and protected"
        public_key = key.with_suffix(".pub").read_text().strip()
        for protected_disk in protected:
            try:
                create_plan(report, protected_disk["path"], "vm-ulsim", ["web"], public_key)
            except ValueError:
                pass
            else:
                raise AssertionError("Installer medium was accepted as install target")
        passed("hardware report, disposable disk identity, active installer protection")
        proposed = controller('plan', '--device', 'vm', '--disk', targets[0]['path'],
                              '--hostname', 'vm-ulsim', '--profile', 'web',
                              '--partition-table', args.partition_table, '--output', work / 'plan.json')
        plan = proposed['plan']
        assert plan == json.loads((work / 'plan.json').read_text())
        try:
            remote.rpc("install", {"plan": plan, "approval": "unapproved"})
        except RuntimeError as exc:
            if "approval" not in str(exc).lower():
                raise
        else:
            raise AssertionError("Target accepted installation without valid explicit approval")
        passed("installation plan and rejection of missing approval")
        # Exercise the complete public orchestration command while this harness
        # handles the physical act of removing the USB at the reboot boundary.
        installer_output = (work / 'controller-install.json').open('w')
        installer_errors = (work / 'controller-install.log').open('w')
        installer_process = subprocess.Popen(
            [sys.executable, '-m', 'ulsim', '--state-dir', str(work / 'controller-state'),
             'install', '--plan', str(work / 'plan.json'), '--approve', plan['plan_id'],
             '--wait', '--timeout', str(args.install_timeout), '--json'],
            cwd=Path(__file__).resolve().parents[2], stdout=installer_output, stderr=installer_errors)
        deadline = time.monotonic() + args.install_timeout
        previous = None
        def controller_reboot_started():
            from ulsim.inventory import Inventory
            journal = Inventory(work / 'controller-state').job(plan['plan_id'])
            return journal and journal['stage'] in {'rebooting', 'reconnecting', 'configuring', 'verifying', 'complete'}
        while time.monotonic() < deadline:
            if vm.process.poll() is not None and controller_reboot_started():
                break
            vm.ensure_running()
            try:
                state = remote.rpc("status")
            except Exception:
                if controller_reboot_started():
                    break  # CLI already received ready and initiated the real reboot.
                raise
            (work / "installation-status.json").write_text(json.dumps(state, indent=2))
            stage = state.get("stage", state.get("state"))
            if stage != previous:
                print(f"INSTALL: {stage}", flush=True)
                previous = stage
            if stage in ("failed", "Failed") or state.get("error"):
                raise RuntimeError(f"Installation failed: {state}")
            if stage in ("ready", "installed", "ready_to_reboot", "complete", "Complete", "rebooting"):
                break
            time.sleep(5)
        else:
            raise TimeoutError(f"Installation did not finish after {args.install_timeout}s")
        try:
            (work / "installation-logs.json").write_text(json.dumps(remote.rpc("logs"), indent=2))
        except Exception:
            if not controller_reboot_started():
                raise
        passed("Debian debootstrap, kernel, partitioning and bootloader installation")
        # Request the actual reboot. -no-reboot makes QEMU stop at firmware reset,
        # allowing USB removal without racing the live image's next boot.
        # The running CLI requests reboot itself after seeing ready.
        vm.process.wait(timeout=90)
        # Cold boot with neither live USB nor config disk attached proves the installed
        # disk boots independently. It also exercises trust transfer, not TOFU.
        vm.stop()
        vm.start(live=False)
        installed_identity = wait_remote(vm, remote, args.boot_timeout)
        assert installed_identity["device_id"] == live_identity["device_id"]
        assert installed_identity["mode"] == "installed"
        assert installed_identity["plan_id"] == plan["plan_id"]
        assert installed_identity["os_id"] == "debian" and installed_identity["os_version"] == "13"
        installed_report = remote.rpc("inspect")
        assert installed_report["boot_mode"] == args.firmware
        (work / "installation-logs.json").write_text(json.dumps(remote.rpc("logs"), indent=2))
        passed("installed-disk boot, DHCP, SSH reconnection and host identity continuity")
        installer_process.wait(timeout=900)
        installer_output.flush()
        completion = json.loads((work / 'controller-install.json').read_text())
        assert installer_process.returncode == 0 and completion.get('stage') == 'complete', completion
        passed("controller install --wait automatically reconnects, configures, verifies and completes its journal")
        controller('pair', '--host', '127.0.0.1', '--port', vm.ssh_port,
                   '--fingerprint', host_fingerprint, '--key', key, '--name', 'vm')
        inventory = controller('servers')
        assert len(inventory['devices']) == 1 and inventory['devices'][0]['installed']
        health = controller('health', '--device', 'vm')
        (work / "health.json").write_text(json.dumps(health, indent=2))
        configured = controller('services', '--device', 'vm', '--profile', 'web', '--configure')
        (work / "configure.json").write_text(json.dumps(configured, indent=2))
        local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with local_http.open(f"http://127.0.0.1:{vm.http_port}/", timeout=30) as response:
            body = response.read().decode()
            assert response.status == 200 and "ulsim" in body.lower(), body[:200]
        passed("nginx deployment and HTTP response through the installed server firewall")
        services = controller('services', '--device', 'vm', '--profile', 'web', '--verify')
        (work / "services.json").write_text(json.dumps(services, indent=2))
        assert services.get("ok") is True and services.get("profiles", {}).get("web", {}).get("ok") is True
        if args.all_profiles:
            # This credential only exists in memory and the disposable VM's Samba
            # database. Never place it in argv, files, result documents, or logs.
            config = {"fileserver": {"password": secrets.token_urlsafe(24)}}
            profiles = ["dns", "fileserver", "vpn", "web", "media"]
            configured = remote.rpc("configure", {"profiles": profiles, "config": config})
            (work / "all-profiles.json").write_text(json.dumps(configured, indent=2))
            assert configured.get("ok") is True
            status = remote.rpc("services", {"profiles": profiles, "verify": True})
            assert status.get("ok") is True and set(status.get("profiles", {})) == set(profiles)
            assert all(value.get("ok") is True for value in status["profiles"].values())
            (work / "all-profiles-status.json").write_text(json.dumps(status, indent=2))
            passed("all five native service profiles installed and functionally verified")
        result["passed"] = True
        print("PASS: complete end-to-end installation", flush=True)
        return 0
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        if vm and vm.process and vm.process.poll() is None:
            try:
                (work / "failure-installation-logs.json").write_text(json.dumps(remote.rpc("logs"), indent=2))
            except Exception:
                pass  # Serial and QEMU logs remain available even if SSH is down.
        print(f"FAIL: {result['error']}", file=sys.stderr, flush=True)
        return 1
    finally:
        if installer_process and installer_process.poll() is None:
            installer_process.terminate()
            try:
                installer_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                installer_process.kill()
                installer_process.wait()
        if installer_output:
            installer_output.close()
        if installer_errors:
            installer_errors.close()
        if vm:
            vm.stop()
        (work / "result.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
