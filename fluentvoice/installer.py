"""FluentVoice Pro - Windows Setup & Shortcut Registry Installer
Author: Nick Otmazgin
"""

import os
import sys
import winreg
import win32com.client
from pathlib import Path

def install_all():
    print("=" * 65)
    print("       FluentVoice Pro - Automated Windows 11/10 Installer      ")
    print("                     Author: Nick Otmazgin                      ")
    print("=" * 65)

    base_dir = Path(__file__).parent.parent.resolve()
    assets_dir = base_dir / "assets"
    ico_path = assets_dir / "icon.ico"
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    
    if not pythonw.exists():
        pythonw = Path(sys.executable)

    shell = win32com.client.Dispatch("WScript.Shell")

    # 1. Desktop Shortcut
    desktop = Path.home() / "Desktop"
    desktop_lnk = desktop / "FluentVoice Pro.lnk"
    sc = shell.CreateShortcut(str(desktop_lnk))
    sc.TargetPath = str(pythonw)
    sc.Arguments = '-m fluentvoice.cli --toggle'
    sc.WorkingDirectory = str(base_dir)
    sc.IconLocation = f"{ico_path},0"
    sc.Description = "FluentVoice Pro (1-Click Speak / Stop)"
    sc.Save()
    print(f"[OK] Desktop Shortcut: {desktop_lnk}")

    # 2. Startup Silent Launcher Shortcut
    startup = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"))
    vbs_path = base_dir / "start_fluentvoice_silent.vbs"
    
    # Write VBS script for zero-window silent startup
    vbs_content = f'Set WshShell = CreateObject("WScript.Shell")\r\nWshShell.Run """{pythonw}"" -m fluentvoice.tray", 0, False\r\n'
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs_content)

    tray_lnk = startup / "FluentVoice Pro Tray.lnk"
    sc_tray = shell.CreateShortcut(str(tray_lnk))
    sc_tray.TargetPath = "wscript.exe"
    sc_tray.Arguments = f'"{vbs_path}"'
    sc_tray.WorkingDirectory = str(base_dir)
    sc_tray.IconLocation = f"{ico_path},0"
    sc_tray.Description = "FluentVoice Pro System Tray Daemon"
    sc_tray.Save()
    print(f"[OK] Windows Startup Integration: {tray_lnk}")

    # 3. Windows Explorer Right-Click Context Menu
    def add_context_menu(key_path, name):
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.SetValue(key, "", winreg.REG_SZ, name)
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, str(ico_path))
            
            cmd_key = winreg.CreateKey(key, "command")
            winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{pythonw}" -m fluentvoice.cli --toggle')
            winreg.CloseKey(cmd_key)
            winreg.CloseKey(key)
            print(f"[OK] Context Menu: {name} -> {key_path}")
        except Exception as e:
            print(f"[Warning] Context menu error ({key_path}): {e}")

    add_context_menu(r"Software\Classes\DesktopBackground\Shell\FluentVoicePro", "🔊 FluentVoice Pro (Read Aloud)")
    add_context_menu(r"Software\Classes\Directory\Background\Shell\FluentVoicePro", "🔊 FluentVoice Pro (Read Aloud)")

    print("\n[SUCCESS] FluentVoice Pro installation completed cleanly.")

if __name__ == "__main__":
    install_all()
