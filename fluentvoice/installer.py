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

    # Clean old obsolete shortcuts from Desktop
    old_desktop_shortcuts = [
        desktop / "Read Aloud.lnk",
        desktop / "Natural Voice Reader.lnk",
        desktop / "FluentVoice Settings.lnk"
    ]
    for old_s in old_desktop_shortcuts:
        if old_s.exists():
            try:
                old_s.unlink()
                print(f"[CLEAN] Removed outdated desktop shortcut: {old_s.name}")
            except Exception:
                pass

    # 1. Single Official Desktop Shortcut: "FluentVoice Pro.lnk" (Opens Settings & Control Center)
    desktop_lnk = desktop / "FluentVoice Pro.lnk"
    sc = shell.CreateShortcut(str(desktop_lnk))
    sc.TargetPath = str(pythonw)
    sc.Arguments = '-m fluentvoice.cli --gui'
    sc.WorkingDirectory = str(base_dir)
    sc.IconLocation = f"{ico_path},0"
    sc.Description = "FluentVoice Pro - Settings & Voice Control Center"
    sc.Save()
    print(f"[OK] Single Unified Desktop Shortcut: {desktop_lnk}")

    # 2. Taskbar Quick-Toggle Shortcut: "FluentVoice Pro.lnk" (1-Click Read / Stop)
    tb = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"))
    if tb.exists():
        # Clean any old Read Aloud
        old_tb = tb / "Read Aloud.lnk"
        if old_tb.exists():
            try:
                old_tb.unlink()
            except Exception:
                pass
        tb_lnk = tb / "FluentVoice Pro.lnk"
        sc_tb = shell.CreateShortcut(str(tb_lnk))
        sc_tb.TargetPath = str(pythonw)
        sc_tb.Arguments = '-m fluentvoice.cli --toggle'
        sc_tb.WorkingDirectory = str(base_dir)
        sc_tb.IconLocation = f"{ico_path},0"
        sc_tb.Description = "FluentVoice Pro (1-Click Speak / Stop)"
        sc_tb.Save()
        print(f"[OK] Taskbar Quick-Toggle Shortcut: {tb_lnk}")

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
    vbs_content = (
        f'Set WshShell = CreateObject("WScript.Shell")\r\n'
        f'WshShell.CurrentDirectory = "{base_dir}"\r\n'
        f'WshShell.Run """{pythonw}"" -m fluentvoice.tray", 0, False\r\n'
    )
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

    # 5. Force Windows Explorer to instantly refresh Desktop and Icon Cache
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x7FFFFFFF, 0x1000, None, None)
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass

    print("\n[SUCCESS] FluentVoice Pro installation & desktop shortcuts configured cleanly.")

if __name__ == "__main__":
    install_all()
