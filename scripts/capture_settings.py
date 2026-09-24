"""Capture maximized Settings screenshots for the README (01–04, optional Automation bottom).

Usage (repo root):
    python scripts/capture_settings.py                  # 01–04 into screenshots/v<version>/
    python scripts/capture_settings.py --bottom out.png # Automation tab scrolled to the bottom

Runs against a temporary home folder, so your real ~/.fluentvoice settings are never
read or changed (screens show default settings). 05 tray menu, 06/07 icons and 09 portable
prompt are captured by hand; then run scripts/build_collage.py.
"""
from __future__ import annotations

import argparse
import atexit
import ctypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "fluentvoice" / "__init__.py").read_text()).group(1)
OUT = ROOT / "screenshots" / f"v{VERSION}"
TABS = [
    ("01-settings-reader.png", "Direct Text Reader"),
    ("02-settings-voice.png", "Voice & Speech"),
    ("03-settings-automation.png", "Automation & System"),
    ("04-settings-about-updates.png", "About & Developer"),
]


def capture(out: Path, tab: str, scroll_bottom: bool = False) -> None:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    home = tempfile.mkdtemp(prefix="fv-capture-")
    atexit.register(shutil.rmtree, home, ignore_errors=True)
    os.environ["HOME"] = os.environ["USERPROFILE"] = home
    sys.path.insert(0, str(ROOT))
    from PIL import ImageGrab
    from fluentvoice.gui import FluentVoiceSettingsWindow

    w = FluentVoiceSettingsWindow(initial_tab=tab)
    w.attributes("-topmost", True)
    w.after(400, lambda: w.state("zoomed"))

    def scroll():
        stack = [w.tab_options]
        while stack:
            c = stack.pop()
            cv = getattr(c, "_parent_canvas", None)
            if cv is not None:
                w.update_idletasks()
                cv.configure(scrollregion=cv.bbox("all"))
                cv.yview_moveto(1.0)
            stack.extend(c.winfo_children())

    def shot():
        w.lift()
        w.update()
        hwnd = ctypes.windll.user32.GetParent(w.winfo_id())
        r = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r))  # frame bounds
        ImageGrab.grab((r.left, r.top, r.right, r.bottom), all_screens=True).save(out)
        w.destroy()

    if scroll_bottom:
        w.after(1800, scroll)
    w.after(2600, shot)
    w.mainloop()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bottom", metavar="PNG", help="capture the Automation tab scrolled to the bottom")
    ap.add_argument("--one", nargs=2, metavar=("PNG", "TAB"), help=argparse.SUPPRESS)  # child-process mode
    a = ap.parse_args()
    if a.one:
        capture(Path(a.one[0]), a.one[1])
    elif a.bottom:
        capture(Path(a.bottom), "Automation & System", scroll_bottom=True)
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        for name, tab in TABS:  # one process per window: Tk can't reopen a CTk root cleanly
            subprocess.run([sys.executable, __file__, "--one", str(OUT / name), tab], check=True)
            print("captured", OUT / name)


if __name__ == "__main__":
    main()
