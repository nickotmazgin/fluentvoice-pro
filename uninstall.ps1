# FluentVoice Pro - Clean Uninstaller
# Author: Nick Otmazgin

Write-Host "Uninstalling FluentVoice Pro..." -ForegroundColor Yellow

# 1. Stop FluentVoice processes only (previously killed EVERY pythonw.exe on the machine)
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { ($_.Name -like "python*.exe" -and $_.CommandLine -like "*fluentvoice*") -or $_.Name -eq "FluentVoicePro.exe" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 2. Remove Shortcuts
$paths = @(
    [System.IO.Path]::Combine($HOME, "Desktop", "FluentVoice Pro.lnk"),
    [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs\Startup", "FluentVoice Pro Tray.lnk"),
    [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar", "FluentVoice Pro.lnk")
)
foreach ($p in $paths) { if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue } }

$sm = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs", "FluentVoice Pro")
if (Test-Path $sm) { Remove-Item $sm -Recurse -Force -ErrorAction SilentlyContinue }

# 3. Remove Registry Context Menus
$regPaths = @(
    "HKCU:\Software\Classes\DesktopBackground\Shell\FluentVoicePro",
    "HKCU:\Software\Classes\Directory\Background\Shell\FluentVoicePro"
)
foreach ($p in $regPaths) {
    if (Test-Path $p) { Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue }
}

Write-Host "FluentVoice Pro uninstalled cleanly." -ForegroundColor Green
Write-Host "Your settings remain in $HOME\.fluentvoice (delete that folder to remove them too)." -ForegroundColor DarkGray
