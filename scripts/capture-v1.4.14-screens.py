"""Capture HD FluentVoice Pro v1.4.14 screenshots for README + social collages."""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots" / "v1.4.14"
OUT.mkdir(parents=True, exist_ok=True)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32


def find_settings_hwnd():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "FluentVoice Pro - Settings" in buf.value and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def grab_hwnd(hwnd) -> Image.Image:
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.25)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))


def click_tab(hwnd, label: str):
    """Best-effort: focus window then use CustomTkinter via sendkeys is fragile.
    Caller opens with --gui TAB already; we use pyautogui-less approach via CLI reopen.
    """
    pass


def save(img: Image.Image, name: str):
    p = OUT / name
    img.save(p, "PNG", optimize=True)
    print("saved", p, img.size)
    return p


def load_font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def fit(img: Image.Image, box: tuple[int, int], pad: int = 8) -> Image.Image:
    tw, th = box
    canvas = Image.new("RGB", (tw, th), (13, 19, 29))
    scale = min((tw - pad * 2) / img.width, (th - pad * 2) / img.height)
    nw, nh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    x = (tw - nw) // 2
    y = (th - nh) // 2
    canvas.paste(resized, (x, y))
    return canvas


def make_collage(shots: dict[str, Image.Image]) -> Image.Image:
    W, H = 1920, 1280
    bg = Image.new("RGB", (W, H), (8, 12, 20))
    draw = ImageDraw.Draw(bg)
    # accent bar
    draw.rectangle((0, 0, W, 8), fill=(0, 210, 255))
    title = load_font(42, bold=True)
    sub = load_font(22)
    small = load_font(18)
    draw.text((48, 28), "FluentVoice Pro", fill=(0, 210, 255), font=title)
    draw.text((48, 82), "v1.4.14  •  Windows 11/10 Suite  •  Settings, Tray, Factory Reset, Emergency Stop", fill=(200, 209, 217), font=sub)
    draw.text((48, 118), "Nick Otmazgin  •  github.com/nickotmazgin/fluentvoice-pro", fill=(139, 148, 158), font=small)

    # 2x3 grid
    cells = [
        ("01 Direct Text Reader", shots["reader"], (40, 170)),
        ("02 Voice & Speech", shots["voice"], (660, 170)),
        ("03 Automation & System", shots["auto"], (1280, 170)),
        ("04 About · Factory Reset", shots["about"], (40, 720)),
        ("05 Footer · Emergency Stop", shots["footer"], (660, 720)),
        ("06 Tray icon", shots["tray"], (1280, 720)),
    ]
    cell_w, cell_h = 600, 480
    label_font = load_font(16, bold=True)
    for label, img, (x, y) in cells:
        frame = fit(img.convert("RGB"), (cell_w, cell_h - 28), pad=10)
        # cyan border
        border = Image.new("RGB", (cell_w + 4, cell_h - 24), (0, 210, 255))
        border.paste(frame, (2, 2))
        bg.paste(border, (x, y + 24))
        draw.text((x + 4, y), label, fill=(230, 237, 243), font=label_font)
    return bg


def make_social(shots: dict[str, Image.Image]) -> tuple[Image.Image, Image.Image]:
    # Wide OG 1280x640
    W, H = 1280, 640
    og = Image.new("RGB", (W, H), (8, 12, 20))
    d = ImageDraw.Draw(og)
    d.rectangle((0, 0, 12, H), fill=(0, 210, 255))
    title = load_font(48, bold=True)
    sub = load_font(24)
    d.text((48, 36), "FluentVoice Pro", fill=(0, 210, 255), font=title)
    d.text((48, 100), "v1.4.14 — Native Windows TTS Suite", fill=(230, 237, 243), font=sub)
    d.text((48, 145), "Emergency Stop  •  Factory Reset  •  Hardened Tray  •  Multi-Language", fill=(139, 148, 158), font=load_font(18))

    left = fit(shots["voice"].convert("RGB"), (620, 420), pad=6)
    right = fit(shots["about"].convert("RGB"), (520, 420), pad=6)
    border_l = Image.new("RGB", (left.width + 4, left.height + 4), (0, 210, 255))
    border_l.paste(left, (2, 2))
    border_r = Image.new("RGB", (right.width + 4, right.height + 4), (0, 210, 255))
    border_r.paste(right, (2, 2))
    og.paste(border_l, (40, 190))
    og.paste(border_r, (700, 190))

    # Square 1080 social
    S = 1080
    sq = Image.new("RGB", (S, S), (8, 12, 20))
    ds = ImageDraw.Draw(sq)
    ds.rectangle((0, 0, S, 10), fill=(0, 210, 255))
    ds.text((40, 36), "FluentVoice Pro", fill=(0, 210, 255), font=load_font(52, bold=True))
    ds.text((40, 100), "v1.4.14  •  Windows TTS Control Center", fill=(230, 237, 243), font=load_font(26))
    ds.text((40, 145), "New: Factory Reset · Emergency Stop · Tray fix", fill=(139, 148, 158), font=load_font(20))
    top = fit(shots["voice"].convert("RGB"), (1000, 420), pad=8)
    bot = fit(shots["footer"].convert("RGB"), (1000, 360), pad=8)
    b1 = Image.new("RGB", (top.width + 4, top.height + 4), (0, 210, 255))
    b1.paste(top, (2, 2))
    b2 = Image.new("RGB", (bot.width + 4, bot.height + 4), (218, 54, 51))
    b2.paste(bot, (2, 2))
    sq.paste(b1, (40, 200))
    sq.paste(b2, (40, 650))
    return og, sq


def main():
    # Expect settings already open; capture current then reopen per tab via subprocess
    import subprocess

    pyw = Path(sys.executable).parent / "pythonw.exe"
    if not pyw.exists():
        pyw = Path(sys.executable)

    tabs = [
        ("Voice & Speech", "02-settings-voice.png", "voice"),
        ("Direct Text Reader", "01-settings-reader.png", "reader"),
        ("Automation & System", "03-settings-automation.png", "auto"),
        ("About & Developer", "04-settings-about.png", "about"),
    ]
    shots: dict[str, Image.Image] = {}

    for tab, fname, key in tabs:
        # kill existing settings windows
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process pythonw,python -ErrorAction SilentlyContinue | "
                "Where-Object { $_.MainWindowTitle -match 'FluentVoice' } | "
                "Stop-Process -Force",
            ],
            capture_output=True,
        )
        time.sleep(0.6)
        subprocess.Popen(
            [str(pyw), "-m", "fluentvoice.cli", "--gui", tab],
            cwd=str(ROOT),
        )
        hwnd = None
        for _ in range(40):
            time.sleep(0.25)
            hwnd = find_settings_hwnd()
            if hwnd:
                break
        if not hwnd:
            raise SystemExit(f"Settings window not found for tab {tab}")
        user32.MoveWindow(hwnd, 80, 20, 980, 1000, True)
        time.sleep(0.8)
        img = grab_hwnd(hwnd)
        save(img, fname)
        shots[key] = img
        if key == "about":
            # scroll-ish: also save footer crop from voice later
            pass
        if key == "voice":
            # footer crop from voice window (shows Emergency Stop layout)
            footer = img.crop((0, max(0, img.height - 220), img.width, img.height))
            save(footer, "05-footer-emergency-stop.png")
            shots["footer"] = footer

    # Desktop + tray strip
    full = ImageGrab.grab()
    save(full, "00-desktop-full.tmp.png")  # ignored by gitignore pattern? 00-desktop-full.png is ignored
    # tray corner
    w, h = full.size
    tray = full.crop((max(0, w - 720), h - 90, w, h))
    save(tray, "05-taskbar-tray-strip.png")
    shots["tray"] = tray
    # desktop icons left
    desk = full.crop((0, 0, min(520, w), min(700, h)))
    save(desk, "00-desktop-icons-column.png")
    # icon asset
    icon = Image.open(ROOT / "assets" / "icon.png").convert("RGBA")
    icon_canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    icon_r = icon.resize((220, 220), Image.Resampling.LANCZOS)
    icon_canvas.paste(icon_r, (18, 18), icon_r)
    icon_canvas.convert("RGB").save(OUT / "00-desktop-icon-asset.png")

    collage = make_collage(shots)
    collage_path = OUT / "collage-v1.4.14-2026.jpg"
    collage.save(collage_path, "JPEG", quality=95, optimize=True)
    print("collage", collage_path, collage.size)

    og, sq = make_social(shots)
    og_path = OUT / "social-preview-1280x640.jpg"
    sq_path = OUT / "social-collage-1080-v1.4.14.jpg"
    og.save(og_path, "JPEG", quality=95, optimize=True)
    sq.save(sq_path, "JPEG", quality=95, optimize=True)
    print("social", og_path, sq_path)

    # root convenience copies
    collage.save(ROOT / "screenshots" / "collage.jpg", "JPEG", quality=95, optimize=True)
    og.save(ROOT / "screenshots" / "social-preview.jpg", "JPEG", quality=95, optimize=True)
    print("DONE")


if __name__ == "__main__":
    main()
