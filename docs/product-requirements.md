# BUILD A COMPLETE PRODUCT: Universal AI Linux Installer & Server Manager (ULSIM)

## YOUR MISSION

You are an autonomous senior software engineering agent with expertise in:

- Linux kernel and operating-system architecture
- Linux system installation and provisioning
- Legacy x86 computer hardware
- BIOS and UEFI boot processes
- Embedded Linux
- Debian, Alpine Linux, and Ubuntu Server
- Windows system administration
- Python development
- Bash scripting
- PowerShell
- Networking and SSH
- Infrastructure automation
- GitHub Actions and CI/CD
- Linux server administration
- AI-assisted system management

Your mission is to **design, develop, build, test, and deliver a complete, working product** called:

# Universal Linux Server Installer & Manager (ULSIM)

The product must allow me to take an old computer with no operating system, insert a specially prepared USB flash drive, boot it, and then use OpenAI Codex CLI running on my main Windows computer to remotely install Linux and configure the old computer as a useful server.

This is a complete software development assignment.

**Do not stop after creating a prototype, proof of concept, architecture document, or hardware inspection utility.**

Implement the complete installation workflow.

You have a substantial development budget. Use it to implement and validate the entire product.

Prioritize working functionality, reliability, and automated testing over unnecessary features.

Do not ask me routine implementation questions. Make appropriate engineering decisions autonomously.

When a feature can be implemented and tested without my physical hardware, implement and test it.

Only require my involvement for actions that genuinely need physical hardware, authentication, security-sensitive approval, or a decision about the intended use of the target computer.

---

# 1. MY HARDWARE AND ENVIRONMENT

## 1.1 Main management computer

My primary computer runs:

**Windows 11**

It has a locally installed Codex CLI authenticated through my ChatGPT subscription.

The Windows computer will act as the controller.

The controller will:

- Discover computers booted using ULSIM USB drives.
- Connect to them over the local network.
- Inspect their hardware.
- Recommend appropriate Linux distributions.
- Suggest potential server applications.
- Discuss my preferences interactively through Codex.
- Install Linux.
- Configure applications.
- Monitor installed servers.

The controller must not require WSL for ordinary use.

It should work directly in Windows PowerShell.

Using SSH from Windows is acceptable.

## 1.2 Target computers

The targets are primarily old computers and laptops.

Some may have:

- Very old Intel processors.
- Low-power Intel Atom or Celeron CPUs.
- CPUs soldered to motherboards.
- 1–4 GB RAM.
- Traditional mechanical hard drives.
- Small soldered eMMC storage.
- Slow flash storage.
- Legacy BIOS.
- UEFI firmware.
- Basic Ethernet adapters.
- Older Wi-Fi adapters.
- Limited computing power.

Some computers may be newer and more capable.

Therefore, design the system to support a wide range of x86 hardware.

Prioritize x86-64 with BIOS and UEFI.

Consider 32-bit x86 support where realistically feasible, but do not delay the complete x86-64 product to implement it.

If a separate image is needed for 32-bit systems, explain and implement that architecture separately when practical.

The target machines contain no important data that needs to be preserved.

Nevertheless, disk identification must be reliable to avoid accidentally erasing the wrong drive.

## 1.3 Network

The target and controller will be connected to the same residential local network.

Connections may use:

- Ethernet
- Wi-Fi

The first installation should work using Ethernet without needing Wi-Fi credentials.

Wi-Fi support is also required.

The product must handle ordinary residential routers using DHCP.

No public IP address or internet-exposed SSH service should be necessary.

## 1.4 Development environment

You are running as **Codex Cloud connected to a GitHub repository**.

You are responsible for producing the complete codebase.

The cloud development environment does not have direct access to my physical local network.

Do not assume that it does.

Develop the application using the GitHub repository and available development tools.

Use GitHub Actions for reproducible image builds and automated testing.

I will later download the finished image and test it on my physical hardware.

---

# 2. THE REQUIRED USER EXPERIENCE

The final user experience should be as simple as possible.

## Step 1: Download USB image

I open GitHub Releases.

I download a file similar to:

`ulsim-live-amd64.img.xz`

The release must include a SHA-256 checksum and clear instructions.

## Step 2: Create USB flash drive

I use Rufus or balenaEtcher on Windows to write the image to a USB flash drive.

I should not need to build the Linux image myself.

## Step 3: Boot old computer

I insert the USB flash drive into the target computer.

I select USB boot from BIOS/UEFI.

The computer boots into the ULSIM environment.

No installed operating system is required.

The environment should start automatically without a graphical interface.

## Step 4: Establish networking

The ULSIM environment automatically detects Ethernet and attempts DHCP.

If Wi-Fi is required, the environment should support secure network provisioning.

## Step 5: Discover computer

On my Windows computer, I run:

```powershell
ulsim discover
```

The application finds the booted target computer.

If automatic discovery does not work, I can enter the target's IP address manually.

## Step 6: Connect

I securely pair with the target.

The connection uses SSH keys.

The application verifies the target's identity.

## Step 7: Hardware analysis

I can execute:

```powershell
ulsim inspect
```

The application gathers a comprehensive hardware report.

It identifies the CPU, RAM, storage devices, network adapters, and hardware limitations.

## Step 8: Discuss potential uses

I open Codex CLI and say:

"Find my old computer and tell me what useful things I could do with it."

Codex examines the hardware report.

It suggests practical server applications.

It explains which services are appropriate and which would perform poorly.

It asks me what I would like to install.

## Step 9: Installation planning

Codex recommends an operating system.

It proposes:

- Linux distribution.
- Disk partitioning.
- Filesystem.
- Network configuration.
- Server applications.
- Performance optimizations.
- Security configuration.

I can discuss and modify the recommendations.

## Step 10: Install Linux

After I approve the plan, Codex initiates the remote installation.

The selected Linux distribution is installed on the target's HDD, SSD, eMMC, or another approved destination.

No graphical installer should be necessary.

## Step 11: Reboot

The target computer reboots into the newly installed Linux system.

The controller reconnects automatically.

SSH access must be preserved.

## Step 12: Configure server

Codex installs the server applications we selected.

It configures networking, storage, services, and necessary security settings.

## Step 13: Verify

The controller checks:

- Whether Linux booted successfully.
- Whether networking works.
- Whether SSH access works.
- Whether requested applications are installed.
- Whether services are running.
- Whether the computer is operating normally.

## Step 14: Future management

I can later use Codex to manage the server.

Examples:

"Check whether my file server is running correctly."

"Install a lightweight media server."

"Update Debian."

"How much memory is available?"

"Can this server run another application?"

This complete workflow must be implemented.

---

# 3. ARCHITECTURE

Use three major components.

## Component A: Bootable USB environment

A minimal Linux environment that boots the target computer.

Responsibilities:

- Booting.
- Networking.
- Secure SSH access.
- Hardware inspection.
- Disk inspection.
- Installation preparation.
- Executing approved installation procedures.

Do not install Codex on the target.

The USB environment should remain lightweight.

## Component B: Windows controller

A Windows-compatible Python application named:

`ulsim`

Responsibilities:

- Device discovery.
- SSH connectivity.
- Device authentication.
- Hardware reporting.
- Installation planning.
- Remote installation orchestration.
- Tracking installation progress.
- Reconnection after reboot.
- Server inventory.
- Remote administration.

This application must function independently of AI.

It should expose reliable CLI commands and JSON output.

## Component C: Codex integration

Codex CLI on Windows acts as the intelligent conversational interface.

Codex should use the deterministic commands provided by `ulsim`.

It can:

- Interpret hardware reports.
- Recommend Linux distributions.
- Suggest server applications.
- Explain technical tradeoffs.
- Generate installation plans.
- Invoke approved installation procedures.
- Troubleshoot failures.

The complete project must work without a separate OpenAI API key.

Use the user's existing locally authenticated Codex CLI.

Do not implement a separate paid AI backend.

---

# 4. BOOTABLE USB IMAGE

Create a real bootable Linux image.

Preferred initial approach:

A lightweight Debian- or Alpine-based live environment.

Choose the base according to reliability, hardware support, and ease of creating reproducible images.

Requirements:

- x86-64.
- Legacy BIOS where supported.
- UEFI.
- Headless operation.
- DHCP networking.
- SSH server.
- Hardware inspection tools.
- Disk management utilities.
- Filesystem utilities.
- Installation utilities.
- Network diagnostics.
- Reliable logging.
- Minimal memory consumption.

The image must be suitable for direct writing to a USB flash drive.

Do not merely generate an ISO containing source files.

Do not produce placeholder image files.

The image must boot into a functional Linux environment.

Use maintained upstream bootloaders and distribution tooling.

Do not write a custom bootloader.

## Important

The installer USB must not automatically erase any attached storage during boot.

Disk modifications should occur only during an explicitly approved installation operation.

---

# 5. GITHUB ACTIONS BUILD SYSTEM

Implement GitHub Actions workflows that build the USB image automatically.

The workflow must:

1. Check out the repository.
2. Set up image-building dependencies.
3. Download required upstream Linux components.
4. Verify upstream release authenticity and integrity.
5. Assemble the bootable environment.
6. Configure networking and SSH.
7. Include ULSIM target-side tools.
8. Generate the bootable image.
9. Compress the image.
10. Calculate SHA-256 checksums.
11. Perform automated validation.
12. Upload the image as a downloadable build artifact.

For tagged releases, publish the generated image as a GitHub Release asset when permissions allow.

Use an appropriate supported GitHub Actions runner.

Do not make the release process depend on an unavailable local development machine.

Do not claim a workflow passed unless its successful execution is verified.

If the current Codex environment cannot directly trigger or inspect GitHub Actions, still implement the workflow, validate it locally as far as possible, and provide exact instructions for running it.

---

# 6. NETWORKING

## Ethernet

Automatically:

- Detect Ethernet interfaces.
- Activate interfaces.
- Request DHCP addresses.
- Determine network routes.
- Identify usable IP addresses.
- Start the management service.
- Start SSH.

Prioritize Ethernet during initial development.

## Wi-Fi

Support Wi-Fi when drivers and firmware are available.

Implement a practical Windows-side configuration tool.

Example:

```powershell
ulsim configure-wifi
```

It should allow me to provide:

- SSID.
- Wi-Fi password.

Never include Wi-Fi credentials in a public repository.

Provide a secure local method of writing Wi-Fi settings to the USB drive.

Account for the fact that Windows may not directly mount Linux partitions.

Choose a practical provisioning design compatible with Windows.

Do not print passwords into logs.

## Discovery

Support:

- mDNS discovery.
- Manual IP connections.
- Distinguishable hostnames.
- Multiple target computers.

For example:

`ulsim-8f32a1.local`

Avoid relying on invasive network scanning.

---

# 7. AUTHENTICATION AND SECURITY

Implement SSH-key authentication.

Requirements:

- Generate or use an existing Windows SSH key.
- Securely provision the authorized public key.
- Verify target host identity during pairing.
- Disable unauthenticated administrative access.
- Avoid common default passwords.
- Prevent unrestricted internet exposure.
- Maintain a record of trusted targets.

The public GitHub image must not contain a shared private key.

Do not embed an identical SSH server host private key into every downloaded image.

Generate unique host identity during boot or through another secure provisioning mechanism.

Provide a practical physical-trust establishment process suitable for headless computers.

The system must remain usable on an ordinary home network.

Security should not introduce unnecessary complexity, but authentication must be real.

---

# 8. HARDWARE DETECTION

Implement actual hardware inspection.

Use established Linux utilities and system interfaces.

Detect:

### CPU

- Model.
- Manufacturer.
- Architecture.
- Core count.
- Thread count.
- Instruction sets.
- Virtualization support.

### Memory

- Total RAM.
- Available RAM.
- Swap configuration.

### Storage

- HDD.
- SSD.
- eMMC.
- SD.
- USB storage.
- Capacity.
- Partitions.
- Filesystems.
- Existing operating systems where detectable.
- Drive health where available.

### Motherboard

- Manufacturer.
- Model.
- BIOS or UEFI.
- Firmware version.

### Networking

- Ethernet hardware.
- Wi-Fi hardware.
- Drivers.
- Network speed where available.

### Other

- USB controllers.
- Sensors.
- Temperatures.
- Graphics hardware.
- Hardware decoding capabilities where identifiable.

Output:

1. Human-readable report.
2. Machine-readable JSON.

Do not invent hardware information.

Mark unavailable information as unknown.

---

# 9. LINUX DISTRIBUTION SELECTION

Implement a recommendation system.

Evaluate at least:

- Debian Minimal.
- Alpine Linux.
- Ubuntu Server.

Base recommendations on:

- Hardware compatibility.
- RAM.
- CPU.
- Storage capacity.
- Boot compatibility.
- Intended server applications.
- Maintenance.
- Security support.
- Software availability.

**Implement Debian Minimal as the first fully supported installation target.**

Debian should support:

- Headless installation.
- SSH.
- DHCP.
- Basic firewall configuration.
- Package installation.
- Server profiles.

After completing the Debian installation workflow, implement Alpine Linux installation if feasible.

Do not let additional distributions delay the delivery of a complete Debian installation solution.

Avoid unsupported or end-of-life distributions.

---

# 10. AI-ASSISTED SERVER RECOMMENDATIONS

This is a critical feature.

Codex must help me understand what an old computer can usefully do.

The Windows controller must provide a catalog of possible server workloads.

Include:

## Networking

- AdGuard Home.
- Pi-hole.
- Unbound.
- WireGuard.
- Tailscale.
- Network monitoring.
- DNS caching.
- NTP.

## File management

- Samba.
- SFTP.
- NFS.
- Syncthing.
- Backup services.

## Media

- Jellyfin.
- Lightweight DLNA server.
- Music server.
- Simple HTTP media hosting.

## Home automation

- Mosquitto MQTT.
- Node-RED.
- Home Assistant when hardware permits.

## Web services

- Nginx.
- Caddy.
- Static website hosting.
- Python web applications.
- Small databases.

## Gaming

- Lightweight game servers.
- Appropriate dedicated multiplayer servers.

Codex must consider:

- CPU requirements.
- Memory requirements.
- Storage requirements.
- Network capacity.
- Expected performance.
- Whether multiple services can run together.

For example:

A computer with 1 GB RAM should not automatically be recommended for a resource-intensive Minecraft server.

A weak CPU may still work well as a basic file server or DNS server.

A media server may work for direct streaming even when transcoding is impractical.

The system should explain such differences.

---

# 11. CONVERSATIONAL PLANNING

Create an `AGENTS.md` file with instructions for locally running Codex CLI.

Example conversation:

USER:

"Find my old computer."

CODEX:

"One ULSIM computer was discovered at 192.168.1.120."

USER:

"Analyze it."

CODEX:

"The machine has 2 GB RAM, an older Intel Atom processor, and 16 GB of eMMC storage."

USER:

"What can I do with it?"

CODEX:

"It is suitable for lightweight network services, DNS filtering, and some basic file-sharing applications. It is poorly suited to video transcoding."

USER:

"I want a VPN server and file server."

CODEX:

"Both are possible. I recommend Debian Minimal with WireGuard and Samba. Do you have an external storage drive?"

USER:

"Yes."

CODEX:

"I can use the internal storage for Linux and the external drive for shared files. Here is the installation plan."

The actual responses must reflect detected hardware.

Codex should ask relevant questions before choosing the final configuration.

Do not blindly install arbitrary server applications.

---

# 12. REMOTE OPERATING SYSTEM INSTALLATION

Implement actual remote Linux installation.

This must be working software, not a future roadmap item.

Use an established supported installation mechanism.

Possible approaches include:

- Debian automated installation.
- Debian debootstrap-based installation where appropriate.
- Official distribution installation tooling.

Choose the most reliable architecture.

Support:

- GPT partition tables.
- MBR partition tables.
- UEFI boot.
- Legacy BIOS boot.
- ext4 filesystems.
- Internal HDDs.
- SATA SSDs.
- eMMC.
- Suitable USB installation targets.

Use filesystem and bootloader configurations appropriate for the hardware.

Do not assume all old computers support UEFI.

## Installation procedure

The system must:

1. Inspect available storage devices.
2. Identify the approved destination disk.
3. Display the partitioning plan.
4. Obtain explicit approval.
5. Prepare the disk.
6. Install the operating system.
7. Install an appropriate kernel.
8. Configure bootloader.
9. Configure system networking.
10. Install SSH.
11. Provision authorized access.
12. Configure an administrative account.
13. Configure package repositories.
14. Install basic system tools.
15. Configure the selected hostname.
16. Prepare post-installation automation.
17. Reboot.
18. Reconnect.
19. Verify the installed operating system.

No graphical installer should be required.

## Disk approval

I confirm that the target computers generally contain no data I need.

Therefore, the software may support completely wiping the selected destination disk.

However:

- Never wipe storage during initial discovery.
- Never wipe a disk just because it appears empty.
- Clearly identify the target disk.
- Require approval before destructive operations.
- Never overwrite the active installer USB.
- Do not silently erase additional storage devices.

The user should not be forced through unnecessary confirmations after explicitly approving a complete installation plan.

---

# 13. INSTALLATION REBOOT AND RECOVERY

Handle the transition from the USB environment to the installed Linux system.

The controller must maintain an installation state machine.

Possible stages:

- Discovered
- Paired
- Inspected
- Planned
- Approved
- Preparing
- Installing
- Bootloader configuration
- Rebooting
- Reconnecting
- Configuring applications
- Verifying
- Complete
- Failed

Save installation state.

After the target restarts:

- Detect the target.
- Verify its identity.
- Establish SSH access.
- Confirm the expected OS is running.
- Continue configuration.

The installation must not depend on an active SSH session surviving a reboot.

Use persistent target-side provisioning state or resumable controller-side automation.

Maintain secure host identity across installation using an explicitly designed trust-transfer mechanism.

Provide recovery procedures for boot failures.

Do not falsely report success when reconnection fails.

---

# 14. AUTOMATIC APPLICATION INSTALLATION

Implement working server deployment profiles.

Use Ansible where useful.

Do not require installing Ansible on the target computers.

The initial complete product must support at least these application profiles:

## Profile 1: DNS filtering

Install and configure either Pi-hole or AdGuard Home.

Verify that the DNS service responds.

## Profile 2: File server

Install and configure Samba.

Allow selection of the storage location.

Configure appropriate access controls.

Verify that the service starts correctly.

## Profile 3: VPN server

Install WireGuard.

Generate secure configuration.

Do not automatically expose the VPN port to the internet or configure router forwarding.

Explain any additional steps required for remote access.

## Profile 4: Web server

Install Nginx.

Deploy a basic test website.

Verify that it responds over the local network.

## Profile 5: Lightweight media server

Install an appropriate DLNA server.

Use software suitable for limited hardware.

Avoid requiring video transcoding.

Other service profiles may be added after these are implemented.

Each application profile should support installation, configuration, verification, and status inspection.

---

# 15. OPTIMIZATION FOR OLD HARDWARE

The product should be designed specifically for old computers.

Consider:

- Minimal Linux installations.
- No graphical desktop.
- Low RAM consumption.
- Slow mechanical HDDs.
- Limited eMMC capacity.
- Low-power CPUs.
- Minimal unnecessary services.
- Reduced unnecessary storage writes.
- Appropriate swap configuration.
- Lightweight filesystems and mount options.
- Sensible logging policies.

Do not disable essential security protections simply to improve performance.

Avoid unnecessary Docker containers on low-memory systems.

Prefer native packages where appropriate.

Allow the user to choose external storage for application data.

---

# 16. WINDOWS CONTROLLER COMMANDS

Implement a real Python command-line application.

The command should be:

`ulsim`

Required commands include:

```powershell
ulsim discover
ulsim devices
ulsim pair
ulsim connect
ulsim inspect
ulsim recommend
ulsim plan
ulsim install
ulsim status
ulsim logs
ulsim servers
ulsim services
ulsim health
ulsim update
ulsim reboot
```

Use conventional command-line argument parsing.

Provide `--help` for every command.

Provide `--json` where appropriate.

Provide clear errors.

The management software should store known devices locally.

Use SQLite or another lightweight persistence mechanism.

The application should support multiple managed servers.

---

# 17. WINDOWS INSTALLATION

Provide a PowerShell installation procedure.

For example:

```powershell
.\install-windows.ps1
```

The script should:

1. Detect Python.
2. Check dependencies.
3. Install the ULSIM application.
4. Configure the CLI.
5. Verify SSH availability.
6. Verify installation.
7. Explain how to start Codex CLI.

Use a supported Python version.

Do not assume WSL is installed.

Avoid requiring Visual Studio or a Linux development environment.

Make the installation instructions understandable for a Windows user.

---

# 18. CODEX CLI INTEGRATION

Create comprehensive `AGENTS.md` instructions.

The local Codex agent should know how to:

- Discover ULSIM computers.
- Inspect hardware.
- Interpret reports.
- Recommend server workloads.
- Generate installation plans.
- Execute installation commands.
- Verify server installations.
- Troubleshoot connectivity.
- Manage installed services.

Codex should prefer using the provided ULSIM CLI instead of inventing ad hoc SSH commands.

It should never fabricate output from commands.

Use structured JSON where possible.

The system must be compatible with a locally installed Codex CLI authenticated through a ChatGPT subscription.

Do not require additional API billing.

---

# 19. DEVICE MANAGEMENT AFTER INSTALLATION

Maintain a local inventory.

Store:

- Device name.
- Device identifier.
- Hardware summary.
- IP address.
- SSH host identity.
- Operating system.
- Installed server applications.
- Last successful connection.
- Relevant system health information.

Allow future Codex sessions to manage existing servers.

Example requests:

"Check all my servers."

"Update the software on Server 2."

"How much disk space remains on my file server?"

"Check whether my DNS server is responding."

"Install another application on my old laptop."

Implement deterministic management commands supporting these workflows.

---

# 20. TESTING

This is mandatory.

Do not deliver untested code while describing it as a finished product.

Implement:

## Unit tests

Test:

- Hardware report parsing.
- Disk identification.
- Configuration validation.
- Installation planning.
- Recommendation rules.
- Device inventory.
- State transitions.

## Integration tests

Test:

- SSH command execution.
- Authentication handling.
- Network discovery.
- Configuration deployment.
- Controller/target communication.

## Virtual-machine tests

Use QEMU/KVM or an equivalent available virtualization system.

Test at least:

1. Booting the USB environment.
2. Obtaining a DHCP address.
3. Starting SSH.
4. Establishing authenticated remote access.
5. Returning a hardware report.
6. Identifying a disposable virtual disk.
7. Generating an installation plan.
8. Installing Debian onto the virtual disk.
9. Installing the bootloader.
10. Rebooting into Debian.
11. Reconnecting through SSH.
12. Executing post-installation configuration.
13. Installing at least one server application.
14. Verifying that the server application works.

Prefer testing both BIOS and UEFI.

Use disposable virtual disks.

Never run destructive tests against ordinary host disks.

If a test cannot run due to missing CI capabilities, implement the test and clearly document what remains unverified.

Do not substitute mocked installation results for end-to-end installation tests.

---

# 21. GITHUB REPOSITORY STRUCTURE

Use a maintainable repository structure.

Suggested layout:

```text
ULSIM/
|
|-- README.md
|-- AGENTS.md
|-- PROGRESS.md
|-- LICENSE
|-- pyproject.toml
|
|-- .github/
|   |-- workflows/
|       |-- build-image.yml
|       |-- test.yml
|       |-- release.yml
|
|-- boot/
|   |-- build/
|   |-- configuration/
|   |-- scripts/
|   |-- services/
|
|-- controller/
|   |-- cli/
|   |-- discovery/
|   |-- ssh/
|   |-- hardware/
|   |-- planning/
|   |-- installation/
|   |-- inventory/
|
|-- installers/
|   |-- debian/
|   |-- alpine/
|
|-- profiles/
|   |-- dns/
|   |-- fileserver/
|   |-- vpn/
|   |-- web/
|   |-- media/
|
|-- scripts/
|   |-- install-windows.ps1
|   |-- configure-usb.ps1
|
|-- tests/
|   |-- unit/
|   |-- integration/
|   |-- vm/
|
|-- docs/
|   |-- getting-started.md
|   |-- create-usb.md
|   |-- networking.md
|   |-- windows-controller.md
|   |-- installation.md
|   |-- troubleshooting.md
|   |-- security.md
```

You may improve this structure.

Avoid unnecessary complexity and empty placeholder files.

---

# 22. DEVELOPMENT STRATEGY

You should complete the entire project.

Use internal milestones to maintain progress, but do not stop after the first milestone.

## Milestone 1

Implement the bootable USB environment.

Verify booting, networking, and SSH.

## Milestone 2

Implement Windows discovery, SSH pairing, and hardware inspection.

Verify real controller/target communication in a virtualized network.

## Milestone 3

Implement hardware recommendations and installation planning.

## Milestone 4

Implement complete Debian installation.

Verify a complete installation in a virtual machine.

## Milestone 5

Implement reboot recovery and automatic reconnection.

## Milestone 6

Implement the core server deployment profiles.

## Milestone 7

Implement persistent server management.

## Milestone 8

Complete documentation, automated testing, and GitHub image builds.

## Milestone 9

Perform final integration testing and address discovered issues.

Do not spend excessive development effort on optional visual interfaces.

The priority is a complete, functional command-line product.

---

# 23. LONG-TASK CONTINUITY

This project may require substantial development time and multiple context windows.

Maintain:

`PROGRESS.md`

Record:

- Completed components.
- Current development stage.
- Important architectural decisions.
- Test results.
- Known issues.
- Outstanding work.
- Next implementation steps.

Update progress as meaningful milestones are completed.

Commit completed implementation work in logical increments when repository permissions and task settings allow.

Do not discard completed work merely because the task becomes long.

If the execution environment supports continuation within the same task, use it.

If a task must end because of usage limits, interruption, or environment restrictions, preserve as much completed work as possible and provide a precise continuation checkpoint.

Do not claim that work will continue independently if the environment has actually stopped.

---

# 24. RELEASE AND DELIVERY

The final product should have a release containing:

### 1. Bootable USB image

Example:

`ulsim-live-amd64.img.xz`

This must be an actual bootable Linux environment.

### 2. Image checksum

Example:

`SHA256SUMS.txt`

### 3. Windows controller

A Python package or straightforward Windows installation package.

### 4. PowerShell installation script

A script that installs the management application.

### 5. User documentation

Clear instructions for creating the USB drive and connecting to a target computer.

### 6. Codex configuration

An `AGENTS.md` file describing how Codex CLI should manage installations.

### 7. Automated tests

Tests covering both individual components and complete installation workflows.

### 8. Build automation

Working GitHub Actions workflows.

### 9. Release notes

Include:

- Implemented features.
- Supported hardware.
- Tested boot modes.
- Tested distributions.
- Known limitations.
- Features requiring further hardware testing.

---

# 25. DEFINITION OF DONE

The project is not complete merely because source code exists.

The primary acceptance test is:

**I can download a bootable image from GitHub, write it to a USB flash drive, boot my old computer, and remotely install Debian Linux through the ULSIM controller running on Windows.**

The system must then:

- Reboot into the installed Linux operating system.
- Reestablish secure remote access.
- Install at least one selected server application.
- Verify that application.
- Register the computer for future management.

The equivalent workflow must first succeed in an automated virtual-machine test.

Actual physical hardware compatibility will require my subsequent local testing.

Do not claim physical hardware testing occurred in the cloud environment.

If some optional capabilities remain incomplete, list them accurately.

**A functioning Debian installation path is mandatory for the first complete release. Alpine Linux support and additional distributions are secondary.**

---

# 26. IMPORTANT ENGINEERING PRIORITIES

Prioritize these requirements in order:

1. Bootable USB reliability.
2. Working network connectivity.
3. Secure remote access.
4. Accurate hardware inspection.
5. Safe installation planning.
6. Successful Debian installation.
7. Reliable bootloader configuration.
8. Reconnection after reboot.
9. Application deployment.
10. Server management.
11. Additional Linux distributions.
12. Advanced features.

Avoid overengineering.

Reuse established Linux utilities.

Prefer standard protocols.

Make the system easy to debug.

Be particularly careful with old hardware and small eMMC devices.

---

# 27. FINAL INSTRUCTIONS

Start development immediately.

Inspect the repository.

Create the necessary source files.

Implement the complete system.

Build and test the bootable image.

Implement and test the Windows controller.

Implement and test remote Debian installation.

Implement the necessary server profiles.

Create GitHub Actions workflows.

Fix problems found during testing.

Produce comprehensive documentation.

Commit and push changes or create the appropriate pull request using the permissions available in the environment.

Do not stop after generating documentation or a prototype.

Do not mark the project complete until the required implementation and automated verification have succeeded.

If GitHub permissions, runner restrictions, or missing credentials prevent publishing a release, report the exact obstacle and provide the working build artifacts or reproducible release procedure available in the environment.

At completion, provide:

1. A summary of implemented functionality.
2. The repository branch or pull request containing the work.
3. The location of the downloadable USB image, if successfully published.
4. The exact image filename.
5. The build workflow status.
6. The automated testing results.
7. Any remaining limitations.
8. The exact instructions I must follow on Windows to create the USB drive.
9. The exact commands I must execute to discover my target computer and begin Linux installation.

**The expected deliverable is a complete, usable software product that can be tested on real hardware—not merely a collection of scripts or a development plan.**

BEGIN IMPLEMENTATION NOW.