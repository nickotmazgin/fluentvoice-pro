# Build attested release ZIPs for FluentVoice Pro (Windows).
# Outputs under dist/:
#   fluentvoice-pro-<ver>-windows.zip          (source + install.ps1)  [recommended]
#   FluentVoicePro-<ver>-portable-win64.zip    (PyInstaller onedir)
#
# Usage (repo root):
#   powershell -ExecutionPolicy Bypass -File .\scripts\create-release-zips.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Ver = (Select-String -Path "fluentvoice\__init__.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $Ver) { throw "Could not parse version from fluentvoice/__init__.py" }

$Dist = Join-Path $Root "dist"
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

$SourceName = "fluentvoice-pro-$Ver-windows"
$SourceDir = Join-Path $Dist $SourceName
$SourceZip = Join-Path $Dist "$SourceName.zip"

Write-Host "=== Source ZIP ($Ver) ===" -ForegroundColor Cyan
if (Test-Path $SourceDir) { Remove-Item -Recurse -Force $SourceDir }
if (Test-Path $SourceZip) { Remove-Item -Force $SourceZip }
New-Item -ItemType Directory -Force -Path $SourceDir | Out-Null

$Include = @(
  "fluentvoice",
  "assets",
  "docs",
  "tests",
  "screenshots",
  "install.ps1",
  "uninstall.ps1",
  "requirements.txt",
  "pyproject.toml",
  "README.md",
  "CHANGELOG.md",
  "LICENSE",
  "CONTRIBUTORS.md"
)

foreach ($item in $Include) {
  $src = Join-Path $Root $item
  if (-not (Test-Path $src)) { Write-Host "skip missing $item"; continue }
  $dst = Join-Path $SourceDir $item
  if (Test-Path $src -PathType Container) {
    Copy-Item -Recurse -Force $src $dst
  } else {
    New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
    Copy-Item -Force $src $dst
  }
}

# Drop capture diagnostics / local-only junk from screenshots
Get-ChildItem -Recurse $SourceDir -Include "_diag*","_cursor*","*.tmp.png" -ErrorAction SilentlyContinue |
  Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse (Join-Path $SourceDir "fluentvoice") -Filter "__pycache__" -Directory -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Portable run note
@"
FluentVoice Pro $Ver — Windows install ZIP
========================================
1) Right-click install.ps1 → Properties → Unblock (if shown) → Apply
2) Right-click install.ps1 → Run with PowerShell
3) Tray icon appears near the clock

If SmartScreen or PowerShell blocks the script:
  Unblock-File .\install.ps1
  Set-ExecutionPolicy -Scope Process Bypass
  .\install.ps1

Docs: docs\WINDOWS_TRUST.md
"@ | Set-Content -Encoding UTF8 (Join-Path $SourceDir "INSTALL.txt")

Compress-Archive -Path (Join-Path $SourceDir "*") -DestinationPath $SourceZip -Force
Write-Host "Wrote $SourceZip"

Write-Host "=== Portable PyInstaller ZIP ===" -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\build_exe.ps1")
$PortableSrc = Join-Path $Dist "FluentVoicePro"
if (-not (Test-Path (Join-Path $PortableSrc "FluentVoicePro.exe"))) {
  throw "PyInstaller output missing: dist\FluentVoicePro\FluentVoicePro.exe"
}

@"
FluentVoice Pro $Ver — Portable (no Python install required)
===========================================================
1) Extract this ZIP anywhere
2) Right-click FluentVoicePro.exe → Properties → Unblock (if shown)
3) Double-click FluentVoicePro.exe (starts tray daemon)

First launch may show Windows SmartScreen on unsigned builds:
  More info → Run anyway
  Or: Unblock-File .\FluentVoicePro.exe

This build is GitHub Artifact Attested when downloaded from Releases.
Firewall: outbound HTTPS only (Edge neural voices). No inbound ports.
See docs\WINDOWS_TRUST.md in the source ZIP / repo.
"@ | Set-Content -Encoding UTF8 (Join-Path $PortableSrc "README-PORTABLE.txt")

$PortableZip = Join-Path $Dist "FluentVoicePro-$Ver-portable-win64.zip"
if (Test-Path $PortableZip) { Remove-Item -Force $PortableZip }
Compress-Archive -Path (Join-Path $PortableSrc "*") -DestinationPath $PortableZip -Force
Write-Host "Wrote $PortableZip"

Write-Host ""
Write-Host "SOURCE_ZIP=$SourceZip"
Write-Host "PORTABLE_ZIP=$PortableZip"
Write-Host "VERSION=$Ver"
