# Run from an extracted ULSIM source release in Windows PowerShell 5.1 or newer.
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Install Python 3.11 or newer from https://www.python.org/downloads/windows/ including the py launcher, then reopen PowerShell.'
}
& py -3 -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
if (-not (Get-Command ssh-keygen -ErrorAction SilentlyContinue)) {
    throw 'Enable OpenSSH Client in Windows Settings > System > Optional features, then rerun this script.'
}
$Venv = Join-Path $env:LOCALAPPDATA 'ULSIM\venv'
& py -3 -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
$Python = Join-Path $Venv 'Scripts\python.exe'
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip installation failed.' }
& $Python -m pip install $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'ULSIM installation failed.' }
$Bin = Join-Path $Venv 'Scripts'
$UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($UserPath -split ';') -notcontains $Bin) {
    [Environment]::SetEnvironmentVariable('Path', "$UserPath;$Bin", 'User')
}
$env:Path = "$Bin;$env:Path"
& ulsim --version
if ($LASTEXITCODE -ne 0) { throw 'CLI verification failed.' }
Write-Host 'ULSIM installed. No WSL or API key is required.'
Write-Host 'Run ulsim --help. Start your authenticated Codex CLI from this source directory so it reads AGENTS.md.'
Write-Host 'New PowerShell windows inherit the updated PATH.'
