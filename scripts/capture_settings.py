"""Capture maximized Settings screenshots for the README (01–05 and the scrolled 10–12).

Usage (repo root):
    python scripts/capture_settings.py                  # 01–05, 10–12 into screenshots/v<version>/
    python scripts/capture_settings.py --at out.png "Voice Providers" 0.5
                                                        # one tab, scrolled (0 = top, 0.5 = middle, 1 = bottom)

Runs against a temporary home folder, so your real ~/.fluentvoice settings are never
read or changed (screens show default settings). 06 tray menu, 07 tray icon, 08 (Automation
scrolled to Preferred Voices), 09 portable prompt and 13 tray offline voices are captured by
hand; then run scripts/build_collage.py.
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
REAL_HOME = str(Path.home())  # read before the temporary profile replaces HOME / USERPROFILE
TABS = [  # (file, tab, scroll position or None for the top)
    ("01-settings-reader.png", "Direct Text Reader", None),
    ("02-settings-voice.png", "Voice & Speech", None),
    ("03-settings-voice-providers.png", "Voice Providers", None),
    ("04-settings-automation.png", "Automation & System", None),
    ("05-settings-about-updates.png", "About & Developer", None),
    ("10-settings-voice-providers-mid.png", "Voice Providers", 0.48),
    ("11-settings-voice-providers-bottom.png", "Voice Providers", 1.0),
    ("12-settings-automation-bottom.png", "Automation & System", 1.0),
]


def render_window(hwnd: int, frame: wintypes.RECT):
    """The window drawn by itself (PrintWindow): no mouse cursor or overlapping windows."""
    from PIL import Image

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    for fn, res, args in (
        (user32.GetDC, wintypes.HDC, [wintypes.HWND]),
        (user32.ReleaseDC, ctypes.c_int, [wintypes.HWND, wintypes.HDC]),
        (user32.PrintWindow, wintypes.BOOL, [wintypes.HWND, wintypes.HDC, wintypes.UINT]),
        (gdi32.CreateCompatibleDC, wintypes.HDC, [wintypes.HDC]),
        (gdi32.CreateCompatibleBitmap, wintypes.HBITMAP, [wintypes.HDC, ctypes.c_int, ctypes.c_int]),
        (gdi32.SelectObject, wintypes.HGDIOBJ, [wintypes.HDC, wintypes.HGDIOBJ]),
        (gdi32.GetDIBits, ctypes.c_int, [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                         ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]),
        (gdi32.DeleteObject, wintypes.BOOL, [wintypes.HGDIOBJ]),
        (gdi32.DeleteDC, wintypes.BOOL, [wintypes.HDC]),
    ):
        fn.restype, fn.argtypes = res, args
    wr = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wr))
    width, height = wr.right - wr.left, wr.bottom - wr.top
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bmp = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    gdi32.SelectObject(mem_dc, bmp)
    try:
        if not user32.PrintWindow(hwnd, mem_dc, 2):  # PW_RENDERFULLCONTENT
            raise OSError("PrintWindow failed")
        header = (ctypes.c_uint32 * 10)(40, width, -height, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)  # top-down 32-bit
        buf = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(mem_dc, bmp, 0, height, buf, header, 0)
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
    im = Image.frombuffer("RGB", (width, height), buf, "raw", "BGRX", 0, 1)
    return im.crop((frame.left - wr.left, frame.top - wr.top, frame.right - wr.left, frame.bottom - wr.top))


def capture(out: Path, tab: str, position: float | None = None) -> None:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    home = tempfile.mkdtemp(prefix="fv-capture-")
    atexit.register(shutil.rmtree, home, ignore_errors=True)
    os.environ["HOME"] = os.environ["USERPROFILE"] = home
    sys.path.insert(0, str(ROOT))
    from fluentvoice.gui import FluentVoiceSettingsWindow

    w = FluentVoiceSettingsWindow(initial_tab=tab)
    w.attributes("-topmost", True)
    w.after(400, lambda: w.state("zoomed"))

    def scroll():
        stack = [w.tabview.tab(tab)]
        while stack:
            c = stack.pop()
            cv = getattr(c, "_parent_canvas", None)
            if cv is not None:
                w.update_idletasks()
                cv.configure(scrollregion=cv.bbox("all"))
                w.update_idletasks()
                first, last = cv.yview()
                cv.yview_moveto(position * (1.0 - (last - first)))
            stack.extend(c.winfo_children())

    def hide_real_home():
        """Public screenshots never show the Windows user name: real home -> %USERPROFILE%."""
        import customtkinter as ctk
        stack = [w]
        while stack:
            c = stack.pop()
            stack.extend(c.winfo_children())
            if isinstance(c, ctk.CTkLabel) and REAL_HOME.lower() in str(c.cget("text")).lower():
                text = str(c.cget("text"))
                i = text.lower().index(REAL_HOME.lower())
                c.configure(text=text[:i] + "%USERPROFILE%" + text[i + len(REAL_HOME):])

    def shot():
        hide_real_home()
        w.lift()
        w.update()
        hwnd = ctypes.windll.user32.GetParent(w.winfo_id())
        r = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r))  # frame bounds
        render_window(hwnd, r).save(out)
        w.destroy()

    if position:
        w.after(1800, scroll)
    w.after(2600, shot)
    w.mainloop()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", nargs=3, metavar=("PNG", "TAB", "POS"), help="capture one tab scrolled to POS (0–1)")
    a = ap.parse_args()
    if a.at:
        capture(Path(a.at[0]), a.at[1], float(a.at[2]))
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        for name, tab, pos in TABS:  # one process per window: Tk can't reopen a CTk root cleanly
            subprocess.run([sys.executable, __file__, "--at", str(OUT / name), tab, str(pos or 0)], check=True)
            print("captured", OUT / name)


if __name__ == "__main__":
    main()
