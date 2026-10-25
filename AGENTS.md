# ULSIM controller instructions for Codex CLI

Run Codex from this repository on the Windows controller using the user's existing ChatGPT login. No OpenAI API key, target-side Codex, WSL, or AI backend is needed. Prefer deterministic `ulsim` commands with `--json`; do not invent command results or hardware facts.

## Workflow

1. `ulsim discover --json` reports untrusted LAN advertisements. If discovery is blocked by Windows firewall/router isolation, ask for the console IP and use manual pairing. Never treat mDNS as identity evidence.
2. Pair using the physical provisioning record: `ulsim pair --host ADDRESS --record RECORD.json --name NAME --json`. A manual fingerprint must come from the physical target console, never `ssh-keyscan` or the discovery response. Do not disable host key verification.
3. `ulsim devices --json`, `ulsim inspect --device NAME --json`, and `ulsim recommend --device NAME --json` establish actual hardware. Explain unknowns, memory budgets, combined service costs, network limits, and direct-streaming versus transcoding. Ask the user's intended use and storage location before choosing applications.
4. Generate `ulsim plan --device NAME --disk /dev/DISK --hostname NAME --profile web --output plan.json --json`. Profiles can repeat. Review the full JSON with the user: disk path, serial/WWN, capacity, boot mode, partition table, filesystem, applications, security and data paths. Existing external data drives are never formatted or automatically mounted. Configure their mount separately with explicit authorization.
5. **Obtain explicit approval for this exact plan before `ulsim install`.** A statement that a disk is usually empty is not approval. The plan hash is an acknowledgement, not authentication. `ulsim install --plan plan.json --approve EXACT_PLAN_ID --wait --json` authorizes the single identified disk and follows installation, reboot, pinned reconnect, application deployment and verification. Do not add routine approval prompts within an already approved plan.
6. If a command is interrupted, inspect `ulsim status` and `ulsim logs`. Use `ulsim install --plan plan.json --resume --wait` to resume orchestration. It never repeats disk partitioning. A failed partial disk installation needs investigation and a fresh approved attempt, not automatic retries. If live USB wins boot order, remove it when instructed by status=ready and reboot to the installed disk.
7. Verify with `ulsim connect`, `ulsim health`, and `ulsim services --verify --json`. Report failures. A completed installer does not prove the machine rebooted or a service works.

## Future management

`ulsim servers --json` lists inventory. `ulsim health --device NAME --json` reports real system health. `ulsim services --device NAME --profile web --configure --json` deploys a selected application; `--config config.json` provides validated profile settings. `ulsim update --device NAME --yes --json` and `ulsim reboot --device NAME --yes --json` should only be used when the user authorized those actions. Never put passwords in plan files, command arguments, transcripts, or logs. Samba prompts locally without echo. Never configure router forwarding or expose services publicly without separate explicit authorization.

## Development

Use the existing checkout: cloud tasks are isolated; do not create Git worktrees unless explicitly requested. Install with `python -m pip install -e '.[test]'`, test with `python -m pytest`. Image and VM validation instructions are in docs/development.md. Preserve secure defaults, signed apt metadata and TLS verification. Mock tests are not a substitute for disposable-VM installation tests. Update PROGRESS.md with measured results and limitations; never claim image builds, CI, physical Windows, or hardware tests ran unless evidenced.
