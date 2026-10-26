#!/usr/bin/env python3
"""Require real ISO9660 payload, BIOS/EFI El Torito entries and a SquashFS root."""
import pathlib
import subprocess
import sys
import tempfile

path = pathlib.Path(sys.argv[1])
if path.stat().st_size < 64 * 1024 * 1024:
    raise SystemExit("Image too small to contain the required Debian live system")
with path.open("rb") as source:
    source.seek(32769)
    if source.read(5) != b"CD001":
        raise SystemExit("Image does not contain an ISO9660 volume")
result = subprocess.run(["xorriso", "-indev", str(path), "-report_el_torito", "plain"],
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
if "BIOS" not in result.stdout or "UEFI" not in result.stdout:
    raise SystemExit("Both BIOS and UEFI boot entries are required\n" + result.stdout)
result = subprocess.run(["xorriso", "-indev", str(path), "-ls", "/live/filesystem.squashfs"],
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
if "filesystem.squashfs" not in result.stdout:
    raise SystemExit("Missing live root filesystem")
source_root = pathlib.Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="ulsim-boot-audit-") as temporary:
    for image_path, source_name in [("/isolinux/isolinux.cfg", "isolinux.cfg"), ("/boot/grub/config.cfg", "grub.cfg")]:
        extracted = pathlib.Path(temporary) / source_name
        subprocess.run(["xorriso", "-osirrox", "on", "-indev", str(path), "-extract", image_path, str(extracted)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        if extracted.read_bytes() != (source_root / "boot/configuration" / source_name).read_bytes():
            raise SystemExit("Boot configuration differs from the tested automatic-boot settings: " + image_path)
print("Validated hybrid image: ISO9660, BIOS, UEFI, and live SquashFS present")
