"""FluentVoice Pro - Tray lifecycle helpers (ensure daemon is running)."""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

MUTEX_NAME = "Global\\FluentVoice_Pro_SingleInstance_Mutex"


def project_root() -> Path:
    return Path(__file__).parent.parent.resolve()


def pythonw_path() -> Path:
    p = Path(sys.executable)
    candidate = p.parent / "pythonw.exe"
    return candidate if candidate.exists() else p


def is_tray_running() -> bool:
    """True if the FluentVoice tray single-instance mutex already exists."""
    try:
        user32 = ctypes.windll.kernel32
        # SYNCHRONIZE = 0x00100000
        handle = user32.OpenMutexW(0x00100000, False, MUTEX_NAME)
        if handle:
            user32.CloseHandle(handle)
            return True
        # ERROR_FILE_NOT_FOUND (2) => not running
        return False
    except Exception:
        return False


def ensure_tray_running(wait_sec: float = 0.8) -> bool:
    """Start the tray daemon if it is not already running. Returns True if tray is up."""
    if is_tray_running():
        return True
    try:
        creation = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            [str(pythonw_path()), "-m", "fluentvoice.tray"],
            cwd=str(project_root()),
            creationflags=creation,
        )
        deadline = time.time() + max(wait_sec, 0.2)
        while time.time() < deadline:
            if is_tray_running():
                return True
            time.sleep(0.1)
        return is_tray_running()
    except Exception:
        return False
