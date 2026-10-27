# Real installation acceptance tests

These tests execute destructive disk operations **inside disposable QEMU guests
only**. The runner creates a new 16 GiB qcow2 disk and refuses an existing work
directory. It never accepts a host disk as an installation destination. No
installation success is mocked.

Build the live image first using `bash boot/build/docker-build.sh`. On Debian/Ubuntu install
QEMU, OVMF, mtools, dosfstools, openssh-client, and the controller dependencies.
Then, from the repository root:

```sh
python tests/vm/run.py --image dist/ulsim-live-amd64.img --firmware bios --work-dir dist/vm-bios
python tests/vm/run.py --image dist/ulsim-live-amd64.img --firmware uefi --work-dir dist/vm-uefi
python tests/vm/run.py --image dist/ulsim-live-amd64.img --firmware bios --partition-table mbr --work-dir dist/vm-bios-mbr
```

Or build `tests/vm/Dockerfile` and mount the checkout at `/src` in that container.
Use `--accel kvm` and pass `/dev/kvm` only when available; the default is portable
TCG. Allocate at least 4 GiB memory to the runner and 20 GiB disk for image and
logs. Debian mirror network access is required inside the guest. No port is
bound beyond loopback. Boot and installation timeouts are explicit options.

The runner verifies:

1. Live BIOS/UEFI boot, DHCP, SSH public-key authentication, and a host key pinned
   through the FAT provisioning volume.
2. Actual controller CLI pairing, inventory, hardware inspection, installation planning,
   queued installation, and the unique disposable disk identity, plus rejection of
   the active live medium as an installation target.
3. Rejection of an unapproved installation.
4. Actual partitioning, debootstrap, kernel, bootloader and SSH installation.
5. Cold boot **with both USB drives removed**, DHCP, and SSH with the original
   pinned host identity and device ID.
6. nginx deployment and a real HTTP response through the target firewall.

Each invocation writes `result.json`, both serial logs, QEMU logs, the hardware
report, installation plan, installation status/logs, and post-installation
reports under its work directory. A nonzero exit or `passed: false` means the
acceptance test did not pass. Retained SSH private keys are ephemeral test
credentials, but the work directory remains private; do not upload key files
as CI artifacts. Upload only JSON reports and logs. Installation failure logs
must be preserved before attempting another new work directory.

The loopback SSH integration tests under `tests/integration/` exercise the real
SSH wire protocol, key rejection, host pinning, and JSON RPC transport. They do
not replace this VM acceptance test.

## Restricted cloud networks

Ordinary CI and home networks need no proxy settings. For a cloud network with
an explicit HTTPS inspection proxy, use physical provisioning rather than
weakening certificate verification or embedding private infrastructure in a
public image:

```sh
python tests/vm/provision_cloud_network.py --output /private/ulsim-network
python tests/vm/run.py --image dist/ulsim-live-amd64.img --firmware bios \
  --work-dir /private/vm-bios --provision-network /private/ulsim-network
```

The helper reads the current process's proxy variables and the certificate file
named by `CODEX_PROXY_CERT` (or `--ca-file`). It resolves the proxy alias to an IP
for guests without access to the controller's DNS, rejects URLs with embedded
credentials, and writes a new directory with owner-only permissions. The boot
script imports the optional certificate from the physically trusted FAT volume
and applies the optional HTTP/HTTPS proxy. Debian's archive signatures and HTTPS
verification remain enabled. The installer carries this explicit network
configuration into the installed server so package operations continue to work.
Never publish the private directory, configuration disk, or VM disk. This option
does not modify the public image and is not required on an ordinary home LAN.

## Extended profile validation

Add `--all-profiles` to a BIOS or UEFI acceptance run to deploy AdGuard Home,
Samba, WireGuard, Nginx and MiniDLNA after the core installed-disk HTTP test.
The runner generates an ephemeral Samba password in memory; it never appears
in argv, saved plans or artifacts. This extended check needs GitHub release
and DNS upstream access in addition to Debian mirrors. A failure is reported
as a failed acceptance run, with individual check evidence retained.

The extended run then configures the same profiles again without supplying a new
Samba password, confirms the existing credential still authenticates, and checks
that the WireGuard public key is unchanged. It requests a real installed-server
reboot and requires a different kernel boot ID before accepting reconnection.
After reboot, the original pinned SSH/device identity, all five functional
service checks, Samba login, WireGuard key, and external Nginx HTTP response must
still pass. Results are retained in `all-profiles-reconfigured.json` and
`all-profiles-after-reboot.json`. These checks do not establish a VPN client
handshake, media playback, or successful download of every public DNS filter list.
