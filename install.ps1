# FluentVoice Pro - One-Click PowerShell Installer
# Author: Nick Otmazgin

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       FluentVoice Pro - One-Click Setup (Windows)        " -ForegroundColor White
Write-Host "              Author: Nick Otmazgin                       " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Install dependencies
Write-Host "`n[1/3] Installing Python dependencies..." -ForegroundColor Yellow
python -m pip install -r requirements.txt --quiet
python -m pip install -e . --no-deps --quiet

# 2. Run Windows shortcut & registry setup
Write-Host "[2/3] Configuring Desktop, Startup, and Context Menus..." -ForegroundColor Yellow
python -m fluentvoice.installer

# 3. Launch Tray Daemon
Write-Host "[3/3] Starting FluentVoice Pro Tray Daemon..." -ForegroundColor Yellow
wscript.exe "$PSScriptRoot\start_fluentvoice_silent.vbs"

Write-Host "`n[DONE] FluentVoice Pro is installed, active, and running in your tray!" -ForegroundColor Green
Write-Host "Left-Click the tray icon or press the Desktop shortcut to speak aloud." -ForegroundColor Cyan
