"""Start-with-Windows + desktop / Start Menu shortcuts.

Works for both layouts:
- source install:  pythonw.exe -m fluentvoice.tray / -m fluentvoice.cli --gui ...
- portable EXE:    FluentVoicePro.exe / FluentVoicePro.exe --gui ...  (see __launcher__)

Folders come from WScript.Shell.SpecialFolders, so OneDrive-redirected Desktops work.
"""

from __future__ import annotations

import sys
from pathlib import Path

STARTUP_LNK = "FluentVoice Pro Tray.lnk"
DESKTOP_LNK = "FluentVoice Pro.lnk"
START_MENU_DIR = "FluentVoice Pro"
PORTABLE_EXE = "FluentVoicePro.exe"

# (file name, CLI flag, description) — Start Menu failsafes
START_MENU_ITEMS = [
    ("FluentVoice Settings.lnk", "--gui", "Open Settings & Control Center"),
    ("FluentVoice Direct Text Reader.lnk", "--reader", "Open Direct Text Reader"),
    ("FluentVoice Emergency Stop.lnk", "--stop", "Stop speech immediately (Start Menu failsafe)"),
    ("Restart FluentVoice Tray.lnk", "--restart-tray", "Restart the system tray daemon"),
    ("Toggle Speak Stop.lnk", "--toggle", "Toggle Speak / Stop"),
]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Folder the app runs from (portable folder, or the source checkout)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def icon_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / "icon.ico"


def launch_command(*cli_args: str) -> tuple[str, str]:
    """(target, arguments) that start FluentVoice with ``cli_args``; no args = tray daemon."""
    if is_frozen():
        return str(Path(sys.executable).resolve()), " ".join(cli_args)
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    target = pyw if pyw.exists() else exe
    module = "fluentvoice.cli" if cli_args else "fluentvoice.tray"
    return str(target), " ".join(["-m", module, *cli_args])


def _shell():
    import pythoncom
    import win32com.client

    # COM must be initialised per thread; the tray calls this from a worker thread
    # (without it: "CoInitialize has not been called"). Repeat calls are harmless.
    pythoncom.CoInitialize()
    return win32com.client.Dispatch("WScript.Shell")


def special_folder(name: str) -> Path:
    """'Desktop', 'Startup' or 'Programs' for the current user."""
    return Path(str(_shell().SpecialFolders(name)))


def _write_lnk(path: Path, cli_args: tuple[str, ...], description: str) -> Path:
    target, args = launch_command(*cli_args)
    path.parent.mkdir(parents=True, exist_ok=True)
    sc = _shell().CreateShortcut(str(path))
    sc.TargetPath = target
    sc.Arguments = args
    sc.WorkingDirectory = str(app_dir())
    sc.IconLocation = f"{icon_path()},0"
    sc.Description = description
    sc.Save()
    return path


def _lnk_target(path: Path) -> str:
    try:
        return str(_shell().CreateShortcut(str(path)).TargetPath)
    except Exception:
        return ""


def _notify_shell() -> None:
    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass


# --- Start with Windows ---------------------------------------------------

def startup_path() -> Path:
    return special_folder("Startup") / STARTUP_LNK


def startup_enabled() -> bool:
    try:
        return startup_path().exists()
    except Exception:
        return False


def set_startup(enabled: bool) -> bool:
    """Create or remove the Startup shortcut that launches the tray at sign-in."""
    p = startup_path()
    if enabled:
        _write_lnk(p, (), "FluentVoice Pro System Tray Daemon")
    else:
        p.unlink(missing_ok=True)
    return startup_enabled()


# --- Desktop + Start Menu -------------------------------------------------

def desktop_path() -> Path:
    return special_folder("Desktop") / DESKTOP_LNK


def start_menu_dir() -> Path:
    return special_folder("Programs") / START_MENU_DIR


def shortcuts_installed() -> bool:
    try:
        return desktop_path().exists()
    except Exception:
        return False


def create_shortcuts() -> list[Path]:
    """Desktop icon (opens Settings) + Start Menu folder with the failsafe entries."""
    made = [_write_lnk(desktop_path(), ("--gui",), "FluentVoice Pro - Settings & Voice Control Center")]
    sm = start_menu_dir()
    for name, flag, desc in START_MENU_ITEMS:
        made.append(_write_lnk(sm / name, (flag,), desc))
    _notify_shell()
    return made


def remove_shortcuts() -> None:
    desktop_path().unlink(missing_ok=True)
    sm = start_menu_dir()
    if sm.exists():
        for p in sm.glob("*.lnk"):
            p.unlink(missing_ok=True)
        try:
            sm.rmdir()
        except OSError:
            pass
    _notify_shell()


def _all_lnks() -> list[Path]:
    sm = start_menu_dir()
    return [startup_path(), desktop_path(), *(sm / name for name, _, _ in START_MENU_ITEMS)]


def repair_moved_portable() -> int:
    """Portable EXE moved or updated to a new folder → re-point our shortcuts at it.

    Only touches shortcuts that target some other FluentVoicePro.exe; returns how many
    were rewritten. No-op for source installs.
    """
    if not is_frozen():
        return 0
    here = str(Path(sys.executable).resolve()).lower()
    fixed = 0
    by_path = {str(desktop_path()): (("--gui",), "FluentVoice Pro - Settings & Voice Control Center"),
               str(startup_path()): ((), "FluentVoice Pro System Tray Daemon")}
    for name, flag, desc in START_MENU_ITEMS:
        by_path[str(start_menu_dir() / name)] = ((flag,), desc)
    for p in _all_lnks():
        if not p.exists():
            continue
        target = _lnk_target(p)
        if target.lower().endswith(PORTABLE_EXE.lower()) and target.lower() != here:
            args, desc = by_path[str(p)]
            _write_lnk(p, args, desc)
            fixed += 1
    if fixed:
        _notify_shell()
    return fixed
