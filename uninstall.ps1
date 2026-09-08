# FluentVoice Pro - Clean Uninstaller
# Author: Nick Otmazgin

Write-Host "Uninstalling FluentVoice Pro..." -ForegroundColor Yellow

# 1. Stop background processes
Stop-Process -Name pythonw -ErrorAction SilentlyContinue

# 2. Remove Shortcuts
$desktop = [System.IO.Path]::Combine($HOME, "Desktop", "FluentVoice Pro.lnk")
if (Test-Path $desktop) { Remove-Item $desktop -Force }

$startup = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs\Startup", "FluentVoice Pro Tray.lnk")
if (Test-Path $startup) { Remove-Item $startup -Force }

# 3. Remove Registry Context Menus
$regPaths = @(
    "HKCU:\Software\Classes\DesktopBackground\Shell\FluentVoicePro",
    "HKCU:\Software\Classes\Directory\Background\Shell\FluentVoicePro"
)
foreach ($p in $regPaths) {
    if (Test-Path $p) { Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue }
}

Write-Host "FluentVoice Pro uninstalled cleanly." -ForegroundColor Green
