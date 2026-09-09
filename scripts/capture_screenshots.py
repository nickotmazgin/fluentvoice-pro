# -*- coding: utf-8 -*-
"""Capture FluentVoice Pro HD screenshots for README / socials.

Usage (from repo root):
  python scripts/capture_screenshots.py
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "screenshots" / "v1.4.3"
OUT.mkdir(parents=True, exist_ok=True)
SOCIAL = Path.home() / "Downloads" / "fluentvoice-pro-socials-v1.4.3"
SOCIAL.mkdir(parents=True, exist_ok=True)

user32 = ctypes.windll.user32
SW_MAXIMIZE = 3
SW_RESTORE = 9
SRCCOPY = 0x00CC0020


def stay_awake():
    # ES_CONTINUOUS | SYSTEM_REQUIRED | DISPLAY_REQUIRED
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)


def grab_screen() -> Image.Image:
    import mss
    with mss.mss() as sct:
        mon = sct.monitors[1]
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def grab_rect(left: int, top: int, right: int, bottom: int) -> Image.Image:
    import mss
    with mss.mss() as sct:
        box = {"left": left, "top": top, "width": max(1, right - left), "height": max(1, bottom - top)}
        shot = sct.grab(box)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def find_window_hwnd(title_substr: str):
    matches = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if title_substr.lower() in buf.value.lower():
            matches.append((hwnd, buf.value))
        return True

    user32.EnumWindows(enum_proc, 0)
    return matches


def window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def save(img: Image.Image, name: str, also_social: bool = True) -> Path:
    path = OUT / name
    img.save(path, "PNG", optimize=True)
    if also_social:
        img.save(SOCIAL / name, "PNG", optimize=True)
        # HQ JPEG for social upload friendliness
        jpg = SOCIAL / (Path(name).stem + ".jpg")
        img.convert("RGB").save(jpg, "JPEG", quality=95, optimize=True)
    print("saved", path, img.size)
    return path


def capture_settings_tabs():
    """Open Settings maximized and screenshot each tab."""
    import customtkinter as ctk
    from fluentvoice.gui import FluentVoiceSettingsWindow

    tabs = [
        ("01-settings-reader.png", "Direct Text Reader"),
        ("02-settings-voice.png", "Voice & Speech"),
        ("03-settings-automation.png", "Automation & System"),
        ("04-settings-about.png", "About & Developer"),
    ]

    app = FluentVoiceSettingsWindow(initial_tab="Direct Text Reader")
    app.update()
    app.update_idletasks()
    hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    app.update()
    time.sleep(0.6)

    paths = []
    for i, (fname, tab) in enumerate(tabs):
        app.tabview.set(tab)
        # Scroll Automation / Voice to top if scrollable children exist
        app.update()
        app.update_idletasks()
        time.sleep(0.45)
        # Capture window client area via screen grab of window rect
        hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
        l, t, r, b = window_rect(hwnd)
        # Slight inset to avoid shadow artifacts
        img = grab_rect(l + 2, t + 2, r - 2, b - 2)
        paths.append(save(img, fname))

        # For Automation tab also capture scrolled-down preferred voices mid-section
        if tab == "Automation & System":
            # Page-down feel via scrolling canvas if present
            try:
                for child in app.tab_options.winfo_children():
                    # CTkScrollableFrame has _parent_canvas
                    canvas = getattr(child, "_parent_canvas", None)
                    if canvas is not None:
                        canvas.yview_moveto(0.35)
                        app.update()
                        time.sleep(0.35)
                        l, t, r, b = window_rect(hwnd)
                        paths.append(save(grab_rect(l + 2, t + 2, r - 2, b - 2), "03b-settings-automation-scrolled.png"))
                        canvas.yview_moveto(0.0)
                        break
            except Exception as e:
                print("scroll capture skip:", e)

    # Non-destructive close
    try:
        app.destroy()
    except Exception:
        pass
    return paths


def capture_desktop_icon():
    """Capture desktop region around FluentVoice Pro shortcut if present."""
    desktop = Path.home() / "Desktop"
    lnk = desktop / "FluentVoice Pro.lnk"
    if not lnk.exists():
        print("desktop shortcut missing")
        return None

    # Screenshot full desktop then crop bottom-left / typical icon grid — better: full desktop
    full = grab_screen()
    # Save full desktop context
    save(full, "00-desktop-full.png")

    # Prefer a tight crop: Windows 11 icons often near left. Also export icon asset itself.
    ico = ROOT / "assets" / "icon.png"
    if ico.exists():
        icon = Image.open(ico).convert("RGBA")
        # Upscale for social clarity
        icon = icon.resize((512, 512), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (640, 640), (8, 12, 20, 255))
        canvas.paste(icon, (64, 40), icon)
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("segoeui.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
        draw.text((320, 580), "FluentVoice Pro", fill=(230, 237, 243, 255), font=font, anchor="mm")
        save(canvas.convert("RGB"), "00-desktop-icon-asset.png")
    return True


def capture_tray_area_and_menu():
    """Focus notification area, open FluentVoice tray menu, capture with hover."""
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.15

    # Ensure tray daemon
    from fluentvoice.lifecycle import ensure_tray_running
    ensure_tray_running(1.5)
    time.sleep(1.0)

    screen = grab_screen()
    w, h = screen.size

    # Capture taskbar / tray strip
    tray_strip = grab_rect(0, h - 56, w, h)
    save(tray_strip, "05-taskbar-tray-strip.png")

    # Win+B focuses tray notification area; then arrows / Enter to open
    pyautogui.hotkey("win", "b")
    time.sleep(0.4)
    # Try to land on FluentVoice by cycling a few icons with left/right then AppsKey/Shift+F10
    # Heuristic: open overflow (^) first on Win11
    # Click near bottom-right chevron / show hidden icons
    overflow_x = w - 140
    overflow_y = h - 24
    pyautogui.click(overflow_x, overflow_y)
    time.sleep(0.5)
    save(grab_screen(), "05b-tray-overflow-or-area.png")

    # Right-click around likely tray icon positions (scan bottom-right)
    candidates = []
    for dx in range(40, 420, 28):
        candidates.append((w - dx, h - 24))

    menu_shot = None
    for x, y in candidates:
        pyautogui.moveTo(x, y, duration=0.05)
        pyautogui.click(button="right")
        time.sleep(0.35)
        shot = grab_screen()
        # Detect dark menu: look for cyan-ish / dark popup near click
        crop = shot.crop((max(0, x - 420), max(0, y - 520), min(w, x + 40), min(h, y + 20)))
        # Heuristic: menu has many dark pixels
        dark = sum(1 for p in crop.resize((80, 80)).getdata() if p[0] < 50 and p[1] < 60 and p[2] < 80)
        if dark > 1800:
            # Hover a mid row for highlight
            pyautogui.moveTo(x - 180, y - 280, duration=0.2)
            time.sleep(0.25)
            menu_shot = grab_screen()
            save(menu_shot, "06-tray-menu-full.png")
            # Tight crop around menu
            ml = max(0, x - 460)
            mt = max(0, y - 560)
            mr = min(w, x + 20)
            mb = min(h, y + 40)
            save(menu_shot.crop((ml, mt, mr, mb)), "06b-tray-menu-crop.png")
            # Escape to close
            pyautogui.press("escape")
            time.sleep(0.2)
            break
        pyautogui.press("escape")
        time.sleep(0.1)

    if menu_shot is None:
        print("WARN: tray menu not auto-found; saved overflow/area shots for manual crop")
    return menu_shot is not None


def build_collage(paths: list[Path]) -> Path:
    """Dark neon collage similar to ClipFlow / EaseHub style (simplified)."""
    imgs = [Image.open(p).convert("RGB") for p in paths if p and Path(p).exists()]
    if not imgs:
        raise SystemExit("No images for collage")

    # Prefer a curated set if present
    order = [
        "00-desktop-icon-asset.png",
        "01-settings-reader.png",
        "02-settings-voice.png",
        "03-settings-automation.png",
        "04-settings-about.png",
        "05-taskbar-tray-strip.png",
        "06b-tray-menu-crop.png",
        "06-tray-menu-full.png",
    ]
    curated = []
    for name in order:
        p = OUT / name
        if p.exists():
            curated.append(Image.open(p).convert("RGB"))
    if len(curated) >= 4:
        imgs = curated[:8]

    cols = 2 if len(imgs) <= 4 else (3 if len(imgs) <= 6 else 4)
    rows = (len(imgs) + cols - 1) // cols
    tile_w, tile_h = 720, 480
    pad, gap, title_h = 48, 36, 120
    W = pad * 2 + cols * tile_w + (cols - 1) * gap
    H = title_h + pad + rows * tile_h + (rows - 1) * gap + pad

    bg = Image.new("RGB", (W, H), (8, 12, 20))
    draw = ImageDraw.Draw(bg)
    # subtle cyan vignette corners
    overlay = Image.new("RGB", (W, H), (0, 40, 60))
    bg = Image.blend(bg, overlay, 0.12)
    draw = ImageDraw.Draw(bg)

    try:
        font_title = ImageFont.truetype("segoeuib.ttf", 42)
        font_sub = ImageFont.truetype("segoeui.ttf", 22)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = font_title

    draw.text((pad, 36), "FluentVoice Pro v1.4.3", fill=(0, 210, 255), font=font_title)
    draw.text(
        (pad, 86),
        "Windows 11 TTS Suite  ·  Tray · Reader · Voices · Automation  ·  2026",
        fill=(180, 190, 200),
        font=font_sub,
    )

    def round_fit(im: Image.Image) -> Image.Image:
        im = im.copy()
        im.thumbnail((tile_w - 16, tile_h - 16), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (tile_w, tile_h), (16, 22, 34))
        x = (tile_w - im.width) // 2
        y = (tile_h - im.height) // 2
        canvas.paste(im, (x, y))
        # rounded mask
        mask = Image.new("L", (tile_w, tile_h), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((0, 0, tile_w - 1, tile_h - 1), radius=14, fill=255)
        out = Image.new("RGB", (tile_w, tile_h), (8, 12, 20))
        out.paste(canvas, (0, 0), mask)
        return out

    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        x = pad + c * (tile_w + gap)
        y = title_h + pad + r * (tile_h + gap)
        tile = round_fit(im)
        # soft shadow
        shadow = Image.new("RGBA", (tile_w + 20, tile_h + 20), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rounded_rectangle((8, 10, tile_w + 8, tile_h + 10), radius=14, fill=(0, 0, 0, 110))
        shadow = shadow.filter(ImageFilter.GaussianBlur(6))
        bg.paste(shadow, (x - 6, y - 4), shadow)
        bg.paste(tile, (x, y))

    out = OUT / "collage-v1.4.3-2026.jpg"
    bg.save(out, "JPEG", quality=95, optimize=True)
    bg.save(SOCIAL / "collage-v1.4.3-2026.jpg", "JPEG", quality=95, optimize=True)
    bg.save(SOCIAL / "collage-v1.4.3-2026.png", "PNG", optimize=True)
    # GitHub OG
    og = bg.copy()
    og.thumbnail((1280, 640), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1280, 640), (8, 12, 20))
    canvas.paste(og, ((1280 - og.width) // 2, (640 - og.height) // 2))
    canvas.save(OUT / "social-preview-1280x640.jpg", "JPEG", quality=95)
    canvas.save(SOCIAL / "social-preview-1280x640.jpg", "JPEG", quality=95)
    print("collage", out)
    return out


def main():
    stay_awake()
    print("OUT", OUT)
    print("SOCIAL", SOCIAL)

    capture_desktop_icon()
    print("--- settings tabs ---")
    tab_paths = capture_settings_tabs()
    time.sleep(0.5)
    print("--- tray ---")
    capture_tray_area_and_menu()

    # Build collage from whatever we got
    shots = sorted(OUT.glob("*.png"))
    build_collage(shots)
    print("DONE")


if __name__ == "__main__":
    main()
