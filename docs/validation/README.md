# Recorded validation runs

These JSON files preserve measured results. Each record identifies its test environment and source or image; none establishes physical-hardware compatibility.

- `*-integration.json`: baseline BIOS/GPT and UEFI/GPT installation, independent installed-disk boot, pinned SSH identity, and Nginx passed on the audited integration build.
- `uefi-clean-build.json`: the clean build completed the public `install --wait` workflow and web checks. Additional profiles were not requested.
- `bios-clean-build.json`: the same clean build completed installation, reboot, controller orchestration, and web checks, then failed its extended profile test because the upstream AdGuard executable path begins with `./`. Its `passed: false` records that failure.
- `profiles-development-recheck.json`: all five profiles passed on a development overlay with the corrected extractor and AdGuard data directory. This is distinct from a fresh installation of the rebuilt image.
- `controller-ci.json`: successful GitHub Windows/Linux Python 3.11/3.13 jobs, including the real Windows PowerShell installer and installed CLI smoke check. The record links to the public run summary.
- `bios-release-image.json` and `uefi-release-image.json`: both fresh installations passed on the corrected clean image from `956be8f`. BIOS also verified all five profiles. These runs did not include the newly added combined profile-persistence step.
- `profiles-persistence.json`: successful reconfiguration and real reboot with preserved Samba credentials/WireGuard identity and all five services, on a separate development overlay. Before/after kernel boot IDs establish that a reboot occurred.
- `release-image-build.json`: exact image hashes, source/build provenance and resolved package/source manifests for the clean image used by those tests. The image binary itself is retained outside Git; publication is pending.

Clean-build hashes were calculated from the retained, unchanged image after the test. These historical records must not be relabelled as validation of a later source revision or image.
