"""FluentVoice Pro - Windows Setup, Desktop Shortcuts & Registry Installer
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
    desktop = Path.home() / "Desktop"

    # Clean old obsolete shortcuts
    old_desktop_shortcuts = [
        desktop / "Read Aloud.lnk",
        desktop / "Natural Voice Reader.lnk"
    ]
    for old_s in old_desktop_shortcuts:
        if old_s.exists():
            try:
                old_s.unlink()
                print(f"[CLEAN] Removed outdated shortcut: {old_s.name}")
            except Exception:
                pass

    # 1. Main Desktop Shortcut: "FluentVoice Pro.lnk" (1-Click Read / Stop)
    desktop_lnk = desktop / "FluentVoice Pro.lnk"
    sc = shell.CreateShortcut(str(desktop_lnk))
    sc.TargetPath = str(pythonw)
    sc.Arguments = '-m fluentvoice.cli --toggle'
    sc.WorkingDirectory = str(base_dir)
    sc.IconLocation = f"{ico_path},0"
    sc.Description = "FluentVoice Pro (1-Click Speak / Stop)"
    sc.Save()
    print(f"[OK] Desktop Shortcut: {desktop_lnk}")

    # 2. Settings Desktop Shortcut: "FluentVoice Settings.lnk" (Open Control Center)
    settings_lnk = desktop / "FluentVoice Settings.lnk"
    sc_set = shell.CreateShortcut(str(settings_lnk))
    sc_set.TargetPath = str(pythonw)
    sc_set.Arguments = '-m fluentvoice.cli --gui'
    sc_set.WorkingDirectory = str(base_dir)
    sc_set.IconLocation = f"{ico_path},0"
    sc_set.Description = "FluentVoice Pro Control Center & Settings"
    sc_set.Save()
    print(f"[OK] Settings Shortcut: {settings_lnk}")

    # 3. Startup Silent Launcher Shortcut
    startup = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"))
    
    # Clean old startup shortcuts
    old_startups = [
        startup / "Read Aloud.lnk",
        startup / "Natural Voice Reader.lnk",
        startup / "Natural Voice Reader Tray.lnk"
    ]
    for old_st in old_startups:
        if old_st.exists():
            try:
                old_st.unlink()
                print(f"[CLEAN] Removed outdated startup shortcut: {old_st.name}")
            except Exception:
                pass

    vbs_path = base_dir / "start_fluentvoice_silent.vbs"
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

    # 4. Windows Explorer Context Menus
    def add_context_menu(key_path, name, cmd_args):
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.SetValue(key, "", winreg.REG_SZ, name)
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, str(ico_path))
            
            cmd_key = winreg.CreateKey(key, "command")
            winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{pythonw}" -m fluentvoice.cli {cmd_args}')
            winreg.CloseKey(cmd_key)
            winreg.CloseKey(key)
            print(f"[OK] Context Menu: {name}")
        except Exception as e:
            print(f"[Warning] Context menu error: {e}")

    add_context_menu(r"Software\Classes\DesktopBackground\Shell\FluentVoicePro", "FluentVoice Pro (Read Aloud)", "--toggle")
    add_context_menu(r"Software\Classes\Directory\Background\Shell\FluentVoicePro", "FluentVoice Pro (Read Aloud)", "--toggle")
    add_context_menu(r"Software\Classes\DesktopBackground\Shell\FluentVoiceSettings", "FluentVoice Pro Settings", "--gui")

    print("\n[SUCCESS] FluentVoice Pro installation & desktop shortcuts configured cleanly.")

if __name__ == "__main__":
    install_all()
