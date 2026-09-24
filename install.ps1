# FluentVoice Pro - One-Click PowerShell Installer (also used for upgrades)
# Author: Nick Otmazgin

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       FluentVoice Pro - One-Click Setup (Windows)        " -ForegroundColor White
Write-Host "              Author: Nick Otmazgin                       " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

# 0. Preflight: Python 3.10+
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[X] Python 3.10+ not found on PATH. Install it from https://www.python.org/downloads/ (tick 'Add to PATH') or use the Portable EXE ZIP." -ForegroundColor Red
    exit 1
}
$ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]"3.10") {
    Write-Host "[X] Python $ver found - FluentVoice Pro needs 3.10 or newer." -ForegroundColor Red
    exit 1
}

# 0b. Upgrade-safe: stop a running FluentVoice tray (only FluentVoice, never other python apps)
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { ($_.Name -like "python*.exe" -and $_.CommandLine -like "*fluentvoice*") -or $_.Name -eq "FluentVoicePro.exe" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 1. Install dependencies
Write-Host "`n[1/3] Installing Python dependencies..." -ForegroundColor Yellow
python -m pip install -r requirements.txt --quiet
python -m pip install -e . --no-deps --quiet

# 2. Run Windows shortcut & registry setup (Desktop, Start Menu, Startup, right-click menu)
Write-Host "[2/3] Configuring Desktop, Startup, and Context Menus..." -ForegroundColor Yellow
python -m fluentvoice.installer

# 3. Launch Tray Daemon
Write-Host "[3/3] Starting FluentVoice Pro Tray Daemon..." -ForegroundColor Yellow
# v1.4.19+: Startup runs pythonw directly; the old VBS launcher is no longer used.
$vbs = Join-Path $PSScriptRoot "start_fluentvoice_silent.vbs"
if (Test-Path $vbs) { Remove-Item $vbs -Force -ErrorAction SilentlyContinue }
Start-Process -WindowStyle Hidden -FilePath "pythonw" -ArgumentList "-m", "fluentvoice.tray" -WorkingDirectory $PSScriptRoot

$v = & python -c "import fluentvoice; print(fluentvoice.__version__)"
Write-Host "`n[DONE] FluentVoice Pro v$v is installed, active, and running in your tray!" -ForegroundColor Green
Write-Host "Left-Click the tray icon or press the Desktop shortcut to speak aloud." -ForegroundColor Cyan
