# -*- coding: utf-8 -*-
"""Capture one Settings tab in an isolated process. Args: tab_name out_png [max|scroll=0.4]"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time
from pathlib import Path

import mss
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

user32 = ctypes.windll.user32
SW_MAXIMIZE = 3


def grab_rect(l, t, r, b):
    with mss.MSS() as sct:
        box = {"left": int(l), "top": int(t), "width": max(1, int(r - l)), "height": max(1, int(b - t))}
        shot = sct.grab(box)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def main():
    tab = sys.argv[1]
    out = Path(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 else "normal"

    from fluentvoice.gui import FluentVoiceSettingsWindow

    app = FluentVoiceSettingsWindow(initial_tab=tab)
    app.geometry("1220x880")
    app.lift()
    app.focus_force()
    try:
        app.attributes("-topmost", True)
    except Exception:
        pass

    # Wait for Map + CTk delayed grid_forget (~100ms) + our ensure
    for _ in range(10):
        app.update()
        app.update_idletasks()
        time.sleep(0.15)
    app._ensure_active_tab_visible()
    for _ in range(4):
        app.update()
        app.update_idletasks()
        time.sleep(0.12)

    hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)

    do_max = mode == "max" or mode.startswith("max+")
    scroll_frac = None
    if "scroll=" in mode:
        scroll_frac = float(mode.split("scroll=", 1)[1].split("+", 1)[0])

    if do_max:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        app.update()
        app._ensure_active_tab_visible()
        app._on_window_configure()
        for _ in range(8):
            app.update()
            app.update_idletasks()
            time.sleep(0.2)
        time.sleep(0.8)

    if scroll_frac is not None:
        scrolled = False
        # Prefer the real scrollable canvas (partial yview), not tiny widget canvases
        candidates = []
        stack = list(app.tab_options.winfo_children())
        while stack:
            w = stack.pop()
            canvas = getattr(w, "_parent_canvas", None)
            if canvas is not None:
                candidates.append(canvas)
            elif w.__class__.__name__ == "Canvas" and hasattr(w, "yview_moveto"):
                try:
                    lo, hi = w.yview()
                    if float(hi) - float(lo) < 0.999:
                        candidates.append(w)
                except Exception:
                    pass
            try:
                stack.extend(w.winfo_children())
            except Exception:
                pass
        for canvas in candidates:
            try:
                canvas.yview_moveto(scroll_frac)
                scrolled = True
                print("scrolled to", scroll_frac, "yview", canvas.yview())
            except Exception as e:
                print("scroll err", e)
        for _ in range(5):
            app.update()
            time.sleep(0.2)
        time.sleep(0.5)
        if not scrolled:
            print("WARN: scroll canvas not found")

    # Final settle + keep FluentVoice on top for grab
    hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
    user32.SetForegroundWindow(hwnd)
    for _ in range(4):
        app.update()
        app.update_idletasks()
        time.sleep(0.2)
    time.sleep(0.4)

    hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    img = grab_rect(rect.left + 1, rect.top + 1, rect.right - 1, rect.bottom - 1)
    try:
        app.attributes("-topmost", False)
    except Exception:
        pass
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    # also social jpg
    social = Path.home() / "Downloads" / "fluentvoice-pro-socials-v1.4.3"
    social.mkdir(parents=True, exist_ok=True)
    img.save(social / out.name, "PNG", optimize=True)
    img.convert("RGB").save(social / (out.stem + ".jpg"), "JPEG", quality=97, subsampling=0)
    print("OK", out.name, img.size)
    try:
        app.destroy()
    except Exception:
        pass
    # hard exit to kill lingering after() callbacks
    os_exit = True
    if os_exit:
        import os
        os._exit(0)


if __name__ == "__main__":
    main()
