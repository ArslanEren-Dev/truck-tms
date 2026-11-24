# Builds dist\TruckTMS-Setup.exe from dist\TruckTMS.exe with Inno Setup 6 (free: https://jrsoftware.org/isinfo.php).
# Usage (from the project folder, after packaging\build_exe.ps1):
#   powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

if (-not (Test-Path dist\TruckTMS.exe)) { throw "dist\TruckTMS.exe is missing: run packaging\build_exe.ps1 first" }
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isinfo.php" }

$version = (Select-String -Path truck_tms\__init__.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
& $iscc "/DAppVersion=$version" packaging\TruckTMS.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

Write-Host "Done: dist\TruckTMS-Setup.exe ($version)"
