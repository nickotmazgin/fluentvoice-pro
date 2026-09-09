# Build a single-folder FluentVoice Pro executable with PyInstaller.
# Usage (from repo root):
#   pip install pyinstaller
#   powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Installing PyInstaller if needed..."
python -m pip install -q pyinstaller

$Icon = Join-Path $Root "assets\icon.ico"
$Tray = Join-Path $Root "assets\tray_icon.ico"
$Name = "FluentVoicePro"

Write-Host "Building $Name (onedir)..."
python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name $Name `
  --icon $Icon `
  --add-data "assets\icon.ico;assets" `
  --add-data "assets\tray_icon.ico;assets" `
  --hidden-import=fluentvoice `
  --hidden-import=fluentvoice.tray `
  --hidden-import=fluentvoice.cli `
  --hidden-import=fluentvoice.gui `
  --hidden-import=fluentvoice.core `
  --hidden-import=edge_tts `
  --hidden-import=pystray `
  --hidden-import=customtkinter `
  --hidden-import=langdetect `
  --collect-all customtkinter `
  --collect-all edge_tts `
  "fluentvoice\__launcher__.py"

Write-Host ""
Write-Host "Done. Output: dist\$Name\$Name.exe"
Write-Host "Tip: run installer via: python -m fluentvoice.installer (dev) or ship dist\$Name folder."
