# Build the Microsoft Store package (MSIX) from the PyInstaller one-folder build.
# Needs the Windows SDK (makeappx.exe); GitHub's windows-latest runners have it.
# Usage (from repo root, after scripts\build_exe.ps1):
#   powershell -ExecutionPolicy Bypass -File .\scripts\build_msix.ps1
# The package is unsigned on purpose: the Microsoft Store signs it on submission.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = (Select-String -Path "fluentvoice\__init__.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$Layout = Join-Path $Root "build\msix"
$Out = Join-Path $Root "dist\FluentVoicePro-$Version-x64.msix"

python scripts\make_msix_layout.py --src dist\FluentVoicePro --out $Layout
if ($LASTEXITCODE -ne 0) { throw "make_msix_layout.py failed" }

$MakeAppx = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\makeappx.exe" -ErrorAction SilentlyContinue |
  Sort-Object FullName -Descending | Select-Object -First 1
if (-not $MakeAppx) { throw "makeappx.exe not found: install the Windows 10/11 SDK" }
Write-Host "Using $($MakeAppx.FullName)"

if (Test-Path $Out) { Remove-Item $Out -Force }
& $MakeAppx.FullName pack /d $Layout /p $Out /o
if ($LASTEXITCODE -ne 0) { throw "makeappx pack failed" }

Write-Host ""
Write-Host "Done. Output: $Out"
