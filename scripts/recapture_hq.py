# -*- coding: utf-8 -*-
"""Re-capture FluentVoice Pro screenshots after layout fix (HQ)."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time
from pathlib import Path

import pyautogui
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "screenshots" / "v1.4.3"
OUT.mkdir(parents=True, exist_ok=True)
SOCIAL = Path.home() / "Downloads" / "fluentvoice-pro-socials-v1.4.3"
SOCIAL.mkdir(parents=True, exist_ok=True)

user32 = ctypes.windll.user32
SW_MAXIMIZE = 3
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.12


def stay_awake():
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)


def grab_rect(left, top, right, bottom) -> Image.Image:
    import mss
    with mss.MSS() as sct:
        box = {
            "left": int(left),
            "top": int(top),
            "width": max(1, int(right - left)),
            "height": max(1, int(bottom - top)),
        }
        shot = sct.grab(box)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def grab_screen() -> Image.Image:
    import mss
    with mss.MSS() as sct:
        mon = sct.monitors[1]
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def save(img: Image.Image, name: str) -> Path:
    path = OUT / name
    img.save(path, "PNG", optimize=True)
    img.save(SOCIAL / name, "PNG", optimize=True)
    img.convert("RGB").save(SOCIAL / (Path(name).stem + ".jpg"), "JPEG", quality=95, optimize=True)
    print("saved", name, img.size)
    return path


def capture_settings():
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
    time.sleep(0.8)

    hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
    # First: comfortable large window (not necessarily OS-maximize) for crisp content
    app.geometry("1100x820")
    app.update()
    time.sleep(0.5)

    paths = []
    for fname, tab in tabs:
        app.tabview.set(tab)
        app._on_window_configure()
        app.update()
        app.update_idletasks()
        time.sleep(0.7)
        hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
        l, t, r, b = window_rect(hwnd)
        paths.append(save(grab_rect(l + 1, t + 1, r - 1, b - 1), fname))

    # Automation scrolled mid for preferred voices
    app.tabview.set("Automation & System")
    app.update()
    time.sleep(0.3)
    try:
        for child in app.tab_options.winfo_children():
            canvas = getattr(child, "_parent_canvas", None)
            if canvas is not None:
                canvas.yview_moveto(0.42)
                app.update()
                time.sleep(0.45)
                l, t, r, b = window_rect(hwnd)
                paths.append(save(grab_rect(l + 1, t + 1, r - 1, b - 1), "03b-settings-automation-scrolled.png"))
                canvas.yview_moveto(0.0)
                break
    except Exception as e:
        print("scroll skip", e)

    # Maximized reader + voice for "full screen settings" social shots
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    app.update()
    time.sleep(0.7)
    for fname, tab in (
        ("01m-settings-reader-maximized.png", "Direct Text Reader"),
        ("02m-settings-voice-maximized.png", "Voice & Speech"),
        ("03m-settings-automation-maximized.png", "Automation & System"),
        ("04m-settings-about-maximized.png", "About & Developer"),
    ):
        app.tabview.set(tab)
        app._on_window_configure()
        app.update()
        app.update_idletasks()
        time.sleep(0.75)
        hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
        l, t, r, b = window_rect(hwnd)
        paths.append(save(grab_rect(l + 1, t + 1, r - 1, b - 1), fname))

    try:
        app.destroy()
    except Exception:
        pass
    return paths


def find_tray_icon_pos():
    """Template-match tray icon in bottom-right taskbar / overflow."""
    icon_path = ROOT / "assets" / "tray_icon.png"
    if not icon_path.exists():
        icon_path = ROOT / "assets" / "icon.png"
    needle = Image.open(icon_path).convert("RGB")
    # Try multiple scales
    screen = grab_screen()
    w, h = screen.size
    region = screen.crop((int(w * 0.55), h - 70, w, h))
    # Also try opening overflow first
    return region, (int(w * 0.55), h - 70), needle


def capture_tray_menu():
    from fluentvoice.lifecycle import ensure_tray_running

    ensure_tray_running(1.5)
    time.sleep(1.2)

    screen = grab_screen()
    w, h = screen.size
    save(grab_rect(0, h - 60, w, h), "05-taskbar-tray-strip.png")

    # Open overflow (Win11 chevron usually ~120-180px from right)
    for ox in (120, 150, 180, 100, 220):
        pyautogui.click(w - ox, h - 22)
        time.sleep(0.45)
        overflow = grab_screen()
        save(overflow, "05b-tray-overflow-or-area.png")
        # Search for cyan-ish tray icon pixels in bottom-right quadrant
        # Then right-click nearby icons in overflow flyout
        fly_l, fly_t = w - 360, h - 420
        fly_r, fly_b = w - 40, h - 48
        # Probe grid of points in overflow panel
        found = False
        for y in range(fly_t + 20, fly_b - 10, 36):
            for x in range(fly_l + 20, fly_r - 20, 40):
                pyautogui.moveTo(x, y, duration=0.05)
                pyautogui.click(button="right")
                time.sleep(0.4)
                shot = grab_screen()
                # Look for FluentVoice menu strings via rough color + tall dark popup
                crop = shot.crop((max(0, x - 380), max(0, y - 520), min(w, x + 30), min(h, y + 30)))
                # Count near-black pixels
                small = crop.resize((60, 80)).convert("RGB")
                dark = 0
                for py_ in range(small.height):
                    for px_ in range(small.width):
                        r, g, b = small.getpixel((px_, py_))
                        if r < 45 and g < 55 and b < 70:
                            dark += 1
                # FluentVoice menu is tall (~12+ items) => many dark pixels
                if dark > 2200 and crop.height > 300:
                    # Hover mid-list row for highlight
                    pyautogui.moveTo(x - 160, y - 300, duration=0.2)
                    time.sleep(0.3)
                    # Nudge a few rows to get strong hover
                    pyautogui.moveRel(0, 28, duration=0.15)
                    time.sleep(0.25)
                    highlighted = grab_screen()
                    save(highlighted, "06-tray-menu-full.png")
                    ml = max(0, x - 420)
                    mt = max(0, y - 560)
                    mr = min(w, x + 24)
                    mb = min(h, y + 36)
                    save(highlighted.crop((ml, mt, mr, mb)), "06b-tray-menu-crop.png")
                    # Also save a tighter menu-only guess
                    pyautogui.press("escape")
                    found = True
                    break
                pyautogui.press("escape")
                time.sleep(0.08)
            if found:
                break
        if found:
            return True
        pyautogui.press("escape")
    print("WARN: could not confirm FluentVoice tray menu")
    return False


def capture_desktop_icon():
    full = grab_screen()
    save(full, "00-desktop-full.png")
    # Crop left desktop icon column roughly
    w, h = full.size
    left_icons = full.crop((0, 0, min(320, w // 4), h - 60))
    save(left_icons, "00-desktop-icons-column.png")

    ico = ROOT / "assets" / "icon.png"
    if ico.exists():
        icon = Image.open(ico).convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (640, 720), (8, 12, 20, 255))
        canvas.paste(icon, (64, 48), icon)
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("segoeui.ttf", 30)
        except Exception:
            font = ImageFont.load_default()
        draw.text((320, 640), "FluentVoice Pro", fill=(230, 237, 243, 255), font=font, anchor="mm")
        draw.text((320, 678), "Desktop shortcut icon", fill=(139, 148, 158, 255), font=font, anchor="mm")
        save(canvas.convert("RGB"), "00-desktop-icon-asset.png")


def build_collage():
    order = [
        "00-desktop-icon-asset.png",
        "01-settings-reader.png",
        "02-settings-voice.png",
        "03-settings-automation.png",
        "03b-settings-automation-scrolled.png",
        "04-settings-about.png",
        "05-taskbar-tray-strip.png",
        "06b-tray-menu-crop.png",
    ]
    imgs = []
    for name in order:
        p = OUT / name
        if p.exists():
            imgs.append(Image.open(p).convert("RGB"))
    if len(imgs) < 4:
        imgs = [Image.open(p).convert("RGB") for p in sorted(OUT.glob("0*.png"))[:8]]

    cols = 4
    rows = (len(imgs) + cols - 1) // cols
    tile_w, tile_h = 720, 500
    pad, gap, title_h = 48, 32, 120
    W = pad * 2 + cols * tile_w + (cols - 1) * gap
    H = title_h + pad + rows * tile_h + (rows - 1) * gap + pad
    bg = Image.new("RGB", (W, H), (8, 12, 20))
    glow = Image.new("RGB", (W, H), (0, 50, 70))
    bg = Image.blend(bg, glow, 0.10)
    draw = ImageDraw.Draw(bg)
    try:
        font_title = ImageFont.truetype("segoeuib.ttf", 42)
        font_sub = ImageFont.truetype("segoeui.ttf", 22)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = font_title
    draw.text((pad, 34), "FluentVoice Pro v1.4.3", fill=(0, 210, 255), font=font_title)
    draw.text(
        (pad, 84),
        "Windows 11 TTS Suite  ·  Tray · Reader · Voices · Automation  ·  2026",
        fill=(180, 190, 200),
        font=font_sub,
    )

    def round_fit(im: Image.Image) -> Image.Image:
        im = im.copy()
        im.thumbnail((tile_w - 18, tile_h - 18), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (tile_w, tile_h), (16, 22, 34))
        canvas.paste(im, ((tile_w - im.width) // 2, (tile_h - im.height) // 2))
        mask = Image.new("L", (tile_w, tile_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile_w - 1, tile_h - 1), radius=14, fill=255)
        out = Image.new("RGB", (tile_w, tile_h), (8, 12, 20))
        out.paste(canvas, (0, 0), mask)
        return out

    for i, im in enumerate(imgs[:8]):
        r, c = divmod(i, cols)
        x = pad + c * (tile_w + gap)
        y = title_h + pad + r * (tile_h + gap)
        tile = round_fit(im)
        shadow = Image.new("RGBA", (tile_w + 22, tile_h + 22), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((8, 10, tile_w + 8, tile_h + 10), radius=14, fill=(0, 0, 0, 120))
        shadow = shadow.filter(ImageFilter.GaussianBlur(7))
        bg.paste(shadow, (x - 6, y - 4), shadow)
        bg.paste(tile, (x, y))

    out = OUT / "collage-v1.4.3-2026.jpg"
    bg.save(out, "JPEG", quality=95, optimize=True)
    bg.save(SOCIAL / "collage-v1.4.3-2026.jpg", "JPEG", quality=95, optimize=True)
    bg.save(SOCIAL / "collage-v1.4.3-2026.png", "PNG", optimize=True)
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
    capture_desktop_icon()
    capture_settings()
    capture_tray_menu()
    build_collage()
    print("DONE", OUT)


if __name__ == "__main__":
    main()
