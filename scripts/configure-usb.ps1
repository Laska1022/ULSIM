param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z]:\\?$')][string]$Volume,
    [string]$SSID
)
$ErrorActionPreference = 'Stop'
$DriveLetter = $Volume.Substring(0,1)
$DiskVolume = Get-Volume -DriveLetter $DriveLetter
if ($DiskVolume.FileSystemLabel -ne 'ULSIMCFG' -or $DiskVolume.FileSystem -notin @('FAT','FAT32')) {
    throw 'Choose an existing FAT/FAT32 USB volume labelled ULSIMCFG. This script does not format disks.'
}
$Root = "${DriveLetter}:\"
if ($SSID) { & ulsim configure-wifi --volume $Root --ssid $SSID }
else { & ulsim configure-usb --volume $Root }
if ($LASTEXITCODE -ne 0) { throw 'USB provisioning failed.' }
Write-Host 'Keep the configuration USB private. Safely eject it and attach it alongside the installer USB before boot.'
