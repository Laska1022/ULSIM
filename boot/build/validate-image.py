#!/usr/bin/env python3
"""Require real ISO9660 payload, BIOS/EFI El Torito entries and a SquashFS root."""
import pathlib
import subprocess
import sys

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
print("Validated hybrid image: ISO9660, BIOS, UEFI, and live SquashFS present")
