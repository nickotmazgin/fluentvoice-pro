"""FluentVoice Pro - Windows Setup, Desktop Shortcuts & Registry Installer
Author: Nick Otmazgin
"""

import os
import winreg
from pathlib import Path

from . import shortcuts


def _remove_old(paths, what):
    for p in paths:
        if p.exists():
            try:
                p.unlink()
                print(f"[CLEAN] Removed outdated {what}: {p.name}")
            except Exception:
                pass


def install_all():
    print("=" * 65)
    print("       FluentVoice Pro - Automated Windows 11/10 Installer      ")
    print("                     Author: Nick Otmazgin                      ")
    print("=" * 65)

    ico_path = shortcuts.icon_path()
    desktop = shortcuts.special_folder("Desktop")
    startup = shortcuts.special_folder("Startup")

    # Clean old obsolete shortcuts (one desktop icon only: Settings)
    _remove_old([
        desktop / "Read Aloud.lnk",
        desktop / "Natural Voice Reader.lnk",
        desktop / "FluentVoice Settings.lnk",
        desktop / "FluentVoice Emergency Stop.lnk",  # stop lives in Settings UI + Start Menu
    ], "desktop shortcut")
    _remove_old([
        startup / "Read Aloud.lnk",
        startup / "Natural Voice Reader.lnk",
        startup / "Natural Voice Reader Tray.lnk",
    ], "startup shortcut")

    # 1. Desktop icon → Settings & Control Center, plus Start Menu failsafes
    for p in shortcuts.create_shortcuts():
        print(f"[OK] Shortcut: {p}")

    # 2. Taskbar Quick-Toggle Shortcut: "FluentVoice Pro.lnk" (1-Click Read / Stop)
    tb = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"))
    if tb.exists():
        _remove_old([tb / "Read Aloud.lnk"], "taskbar shortcut")
        tb_lnk = shortcuts._write_lnk(tb / "FluentVoice Pro.lnk", ("--toggle",), "FluentVoice Pro (1-Click Speak / Stop)")
        print(f"[OK] Taskbar Quick-Toggle Shortcut: {tb_lnk}")

    # 3. Start with Windows (tray daemon; pythonw / portable EXE have no console window)
    shortcuts.set_startup(True)
    print(f"[OK] Windows Startup Integration: {shortcuts.startup_path()}")

    # 4. Windows Explorer Context Menus
    def add_context_menu(key_path, name, flag):
        try:
            target, args = shortcuts.launch_command(flag)
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.SetValue(key, "", winreg.REG_SZ, name)
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, str(ico_path))

            cmd_key = winreg.CreateKey(key, "command")
            winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{target}" {args}')
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
