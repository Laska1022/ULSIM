# AI continuation checkpoint

Continue the existing ULSIM implementation. Do not restart the project or replace its architecture. The user requested a complete working product and explicitly requested that this checkpoint and continuation instructions be saved on GitHub.

## Read first

1. [AGENTS.md](AGENTS.md): operating rules, especially physical disk approval and SSH trust.
2. [PROGRESS.md](PROGRESS.md): current measured status.
3. [Original user requirements](docs/product-requirements.md): the complete uploaded assignment, including long-task continuity and delivery requirements.
4. [Validation records](docs/validation/README.md), [development](docs/development.md), and [VM testing](tests/vm/README.md).

Repository: `https://github.com/Laska1022/ULSIM`, branch `feature/ulsim-initial`. This was also the remote default branch at the checkpoint; the originally empty repository had no `main` commit. Preserve the existing branch/workflow. In the current cloud instance the checkout is `/workspace/ULSIM`; use it directly rather than creating a worktree. Inspect `git status` and recent commits before making changes. Code and curated evidence are in Git; private VM disks and large images are not.

## Completed and verified

- Debian 13 amd64 live image, controller CLI, secure provisioning/pairing, real hardware inspection, approved disk installation, resumable orchestration, installed identity transfer, and five native profiles are implemented.
- Local suite: **154 passed**, including real SSH and mDNS tests. Ruff undefined-name/import checks, shell syntax, and Python wheel/source builds passed.
- GitHub Windows/Linux Python 3.11/3.13 tests and the real Windows PowerShell installer smoke check passed at `a78289d`: [run 40412694400](https://github.com/Laska1022/ULSIM/actions/runs/40412694400).
- Clean-image BIOS/GPT and UEFI/GPT installation passed on image source revision `956be8ffbf1081b173a6e3df7d3b7d9146b2398c`: automatic live boot, DHCP, pinned SSH, disk protection, explicit plan approval, real Debian/kernel/GRUB installation, USB removal, independent installed-disk boot, automatic `install --wait` completion, and Nginx HTTP.
- BIOS run `bios-05` additionally installed and functionally verified all five profiles. UEFI run `uefi-05` tested the web profile.
- `profile-persistence-03` separately passed reconfiguration, unchanged Samba credentials and WireGuard identity, a real target RPC reboot with a changed kernel boot ID, pinned reconnection, all five services, and external HTTP. This was a development overlay, not a fresh-image installation.

The important remaining distinction: `bios-05` started before the new persistence helper was added to the runner. Do not count that older process as having performed the combined installation-plus-profile-reboot check. That combined check is now running as `bios-06`.

## Immediate next action: inspect the two started tests

At this checkpoint, these Docker tests have been started. Processes may finish, fail, or disappear before the next AI resumes; inspect actual state instead of assuming they are still running.

| Container | Private result directory | Required check |
| --- | --- | --- |
| `ulsim-accept-bios-mbr-01` | `/workspace/ulsim-vm-artifacts/bios-mbr-01` | BIOS/MBR installation with 1024 MiB RAM |
| `ulsim-accept-bios-06` | `/workspace/ulsim-vm-artifacts/bios-06` | BIOS/GPT clean installation, all five profiles, reconfiguration and real reboot persistence |

```sh
docker ps -a --filter name=ulsim-accept --format '{{.Names}} {{.Status}}'
docker logs --tail 40 ulsim-accept-bios-mbr-01
docker logs --tail 40 ulsim-accept-bios-06
cat /workspace/ulsim-vm-artifacts/bios-mbr-01/result.json
cat /workspace/ulsim-vm-artifacts/bios-06/result.json
```

`result.json` is also written while a test is running, initially with `passed: false`; that alone is not a final failure. Require completed container exit status, the final `passed` value, and the expected checks. A missing result is not a success. Preserve failures and diagnose them. Never restart partitioning on an existing test disk; reruns use a new work directory.

These use QEMU TCG without `/dev/kvm`. The cloud CPU quota was four cores, so concurrent tests can take tens of minutes. Their installation timeout is 3600 seconds. Allow meaningful progress time. Use `installation-status.json`, serial logs and controller logs to diagnose stalls. The workspace has limited free space; check `df -h /workspace` before more images or disks. Superseded generated images/disks were removed after retaining their curated evidence. Do not delete a qcow2 backing disk that retained overlays still need.

## Image provenance and reusable local artifacts

The current verified build is in `/workspace/ulsim-release-output` if this cloud filesystem was preserved:

- `ulsim-live-amd64.img`: SHA256 `88f22fe81d1c3e24d761d18990b45c9693447aaa9d1435333bf646612b6e0221`.
- `ulsim-live-amd64.img.xz`: SHA256 `3dd494c38bb0bd02e93667e368a3a8cb68d9b62ea8d1d1324773ab542bab8a21`.
- `BUILD-INFO.txt`, `SOURCE-SHA256SUMS.txt`, package manifest, and checksum file accompany it. Their contents are preserved in [release-image-build.json](docs/validation/release-image-build.json).

The build passed structural and extracted-root audits. All 16 embedded source files still matched the checkout at this checkpoint; later changes were tests/workflows/docs. Rebuild if embedded code or boot configuration changes. Do not claim that an old image contains a subsequent fix. Debian package updates make rebuilds repeatable by procedure, not byte-identical across dates.

Other current-instance conveniences: `/workspace/ulsim-venv`, Docker images `ulsim-image-builder` and `ulsim-vm-test-runner`, build-cache volume `ulsim-repro-build`, and private network provisioning in `/workspace/ulsim-private-vm-network`. Check their existence and validity; they are not guaranteed to survive a new environment. The original standalone profile-recheck helpers are outside the repository; their useful persistence logic is now in `tests/vm/run.py`.

## Commands when checks must be rerun

From the existing checkout, with Python 3.11+:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
python -m build
```

Prefer the already working `/workspace/ulsim-venv/bin/python` in the preserved cloud instance. No controller daemon needs to start. For a fresh Linux machine, follow `tests/vm/README.md` to install QEMU/OVMF/mtools/dosfstools. Build a missing image with `bash boot/build/docker-build.sh`, then use new work directories:

```sh
python tests/vm/run.py --image dist/ulsim-live-amd64.img --firmware bios --partition-table mbr --memory 1024 --work-dir dist/vm-bios-mbr-next
python tests/vm/run.py --image dist/ulsim-live-amd64.img --firmware bios --partition-table gpt --all-profiles --work-dir dist/vm-bios-full-next
python tests/vm/run.py --image dist/ulsim-live-amd64.img --firmware uefi --work-dir dist/vm-uefi-next
```

Do not repeat unchanged checks that have already passed unless a new change or unresolved concern warrants it. The current pending tests use the existing Docker runner with the repository and image mounted read-only, the artifact directory mounted writable, and optional private network provisioning mounted read-only. The same runner can be recreated with `docker build -t ulsim-vm-test-runner tests/vm`.

For this restricted cloud network, the successful image build used:

```sh
ULSIM_OUTPUT_DIR=/workspace/ulsim-release-output-next \
ULSIM_BUILD_VOLUME=ulsim-repro-build \
ULSIM_BUILD_CA_DIR=/usr/local/share/ca-certificates \
DOCKER_CONFIG=/tmp/ulsim-boot-docker \
python boot/build/docker-build.py
```

Those paths are current-instance details. Check that the trust directory and Docker configuration exist before reuse. On a normal network omit these overrides. The builder strips build-only trust material before auditing the public image. The VM helper `tests/vm/provision_cloud_network.py --output NEW_PRIVATE_DIRECTORY` can create fresh private provisioning from the environment's credential-free proxy and CA; pass that directory as `--provision-network`. Never disable TLS or Debian signature validation.

## Remaining delivery work, in order

1. Finish and inspect the two pending local checks above. Add curated results to `docs/validation` and update this file and `PROGRESS.md` with actual outcomes.
2. Confirm controller CI for the pushed checkpoint. The workflows now also require Windows PowerShell installation, BIOS/GPT with profile persistence, UEFI/GPT, and BIOS/MBR with 1 GiB RAM. CI uses KVM only when the runner can access it; otherwise it uses TCG.
3. Run the actual **Build and verify live image** workflow on the intended source revision. It has not yet been observed passing end to end on GitHub. Inspect all three VM jobs and their artifacts; configured jobs are not executed evidence.
4. After required checks pass, publish the first reviewed `v*` tag using the repository's existing release workflow. It gates publication on controller and image/VM tests, builds the wheel/source archive, and publishes image/checksum/manifests with `docs/release-notes.md`. No release tag or public image release has been created at this checkpoint. Check remote tags/releases first to avoid duplicates.
5. Verify the actual release asset links/checksum and record the public release URL and remaining physical-hardware limitations. Update README's integration-status wording only when supported by those results.

Git reads and pushes already work through platform authentication. GitHub API access previously returned proxy `403 CONNECT`; public GitHub web Actions summaries worked through ordinary HTTPS. An absent `GH_TOKEN` does not mean Git access is unavailable. Do not extract proxy credentials or request a token without checking existing capabilities. If API access remains denied, use the permitted public summary pages for read-only status; workflow dispatch may need the GitHub Actions UI or an environment network-setting change. Do not bypass the network policy.

## Known limits and lessons

- Debian amd64 installation only; Alpine/Ubuntu are recommendations. No i386 or Secure Boot support. External data mounts require explicit preparation. WireGuard is server access by default, without automatic router forwarding or internet gateway routing.
- Service checks prove DNS blocking, authenticated Samba, a WireGuard interface/public key, and web/DLNA HTTP. They do not prove a VPN client handshake, media playback, or every public DNS list download. Physical Wi-Fi, disks and firmware variations need later hardware validation.
- AdGuard fixes are complete: the pinned upstream archive uses a leading `./`, and systemd must create its private data directory. Windows test imports of Linux-only `fcntl` were also fixed. Do not redo these changes.
- The first persistence probes used a fixture whose VM was stopped abruptly and retained only old profile state. The corrected test explicitly configures all five profiles before testing a normal RPC reboot. Preserve that distinction from a product failure.
- Do not publish private keys, provisioned configuration USB images, VM disks, proxy/CA settings, credentials, or unreviewed raw cloud logs. Curated evidence and build manifests are committed. Large clean images belong in release assets, not Git history.
- Cloud setup/start instructions and additional network domains were saved as an environment draft. Saving is not applying or publishing; fresh-task restoration has not been verified. User review/publication of environment settings is separate from GitHub publication.

## Prompt for the next AI

> Continue ULSIM on `feature/ulsim-initial`. Read `AGENTS.md`, `AI_HANDOFF.md`, `PROGRESS.md`, and the saved user requirements. Inspect the two named VM tests and current GitHub CI first. Preserve completed work, fix only demonstrated failures, finish the remaining release gates, update measured evidence, and publish through the existing workflow when verified. Do not restart the project or claim unrun tests passed.
