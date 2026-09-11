"""Capture FluentVoice Pro v1.4.16 Settings screens + rebuild collages.
Minimizes Cursor during capture, restores after.
"""
from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots" / "v1.4.16"
PREV = ROOT / "screenshots" / "v1.4.14"
OUT.mkdir(parents=True, exist_ok=True)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32
SW_MINIMIZE, SW_RESTORE = 6, 9


def enum_title(substr: str) -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
        else:
            n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if substr.lower() in buf.value.lower():
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found


def find_settings() -> int | None:
    for h in enum_title("FluentVoice Pro - Settings"):
        if user32.IsWindow(h):
            return h
    return None


def grab_hwnd(hwnd: int) -> Image.Image:
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.35)
    rc = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    return ImageGrab.grab(bbox=(rc.left, rc.top, rc.right, rc.bottom))


def open_tab(tab: str):
    # Close existing settings then reopen on tab via module entry
    hwnd = find_settings()
    if hwnd:
        user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        time.sleep(0.4)
    subprocess.Popen(
        [sys.executable, "-m", "fluentvoice.gui", tab],
        cwd=str(ROOT),
    )
    for _ in range(40):
        time.sleep(0.25)
        if find_settings():
            time.sleep(0.5)
            return
    raise SystemExit(f"Settings did not open for tab {tab}")


def font(sz: int, bold: bool = False):
    p = r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf"
    return ImageFont.truetype(p, sz)


def fit(img: Image.Image, box: tuple[int, int], pad: int = 8) -> Image.Image:
    tw, th = box
    c = Image.new("RGB", (tw, th), (13, 19, 29))
    im = img.convert("RGB")
    scale = min((tw - pad * 2) / im.width, (th - pad * 2) / im.height)
    nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
    r = im.resize((nw, nh), Image.Resampling.LANCZOS)
    c.paste(r, ((tw - nw) // 2, (th - nh) // 2))
    return c


def main():
    cursor = enum_title("Cursor")
    for h in cursor:
        user32.ShowWindow(h, SW_MINIMIZE)
    time.sleep(0.4)

    try:
        shots = {}
        tabs = [
            ("Direct Text Reader", "01-settings-reader.png", "reader"),
            ("Voice & Speech", "02-settings-voice.png", "voice"),
            ("Automation & System", "03-settings-automation.png", "auto"),
            ("About & Developer", "04-settings-about.png", "about"),
        ]
        for tab, name, key in tabs:
            open_tab(tab)
            hwnd = find_settings()
            img = grab_hwnd(hwnd)
            img.save(OUT / name, "PNG", optimize=True)
            shots[key] = img
            print("saved", name, img.size)

        # Reuse live tray/desktop from prior HD set if present
        for src_name, dst_name in [
            ("06b-tray-menu-crop.png", "06b-tray-menu-crop.png"),
            ("00-desktop-icon-live.png", "00-desktop-icon-live.png"),
            ("05c-tray-icon-closeup.png", "05c-tray-icon-closeup.png"),
        ]:
            src = PREV / src_name
            if src.exists():
                shutil.copy2(src, OUT / dst_name)

        tray = Image.open(OUT / "06b-tray-menu-crop.png") if (OUT / "06b-tray-menu-crop.png").exists() else shots["voice"]
        desk = Image.open(OUT / "00-desktop-icon-live.png") if (OUT / "00-desktop-icon-live.png").exists() else shots["about"]
        shots["tray"] = tray
        shots["desk"] = desk

        # Collage 1920x1280
        W, H = 1920, 1280
        bg = Image.new("RGB", (W, H), (8, 12, 20))
        d = ImageDraw.Draw(bg)
        d.rectangle((0, 0, W, 8), fill=(0, 210, 255))
        d.text((48, 28), "FluentVoice Pro", fill=(0, 210, 255), font=font(42, True))
        d.text(
            (48, 82),
            "v1.4.16  •  Clear Voice Profile layout  •  Hard-stop  •  Readable tabs  •  Factory Reset",
            fill=(200, 209, 217),
            font=font(20),
        )
        d.text(
            (48, 114),
            "Nick Otmazgin  •  github.com/nickotmazgin/fluentvoice-pro",
            fill=(139, 148, 158),
            font=font(16),
        )
        cells = [
            ("01 Direct Text Reader", shots["reader"], (40, 160)),
            ("02 Voice & Speech", shots["voice"], (660, 160)),
            ("03 Automation & System", shots["auto"], (1280, 160)),
            ("04 About · Factory Reset", shots["about"], (40, 700)),
            ("05 Tray right-click menu", shots["tray"], (660, 700)),
            ("06 Desktop icon (live)", shots["desk"], (1280, 700)),
        ]
        for label, img, (x, y) in cells:
            frame = fit(img, (600, 470), 10)
            border = Image.new("RGB", (frame.width + 4, frame.height + 4), (0, 210, 255))
            border.paste(frame, (2, 2))
            bg.paste(border, (x, y + 24))
            d.text((x + 4, y), label, fill=(230, 237, 243), font=font(16, True))
        bg.save(OUT / "collage-v1.4.16-2026.jpg", "JPEG", quality=96, optimize=True)
        bg.save(ROOT / "screenshots" / "collage.jpg", "JPEG", quality=96, optimize=True)

        # Social 1080
        S = 1080
        sq = Image.new("RGB", (S, S), (8, 12, 20))
        ds = ImageDraw.Draw(sq)
        ds.rectangle((0, 0, S, 10), fill=(0, 210, 255))
        ds.text((40, 30), "FluentVoice Pro", fill=(0, 210, 255), font=font(48, True))
        ds.text((40, 90), "v1.4.16  •  Settings · Tray · Desktop", fill=(230, 237, 243), font=font(24))
        t = fit(shots["voice"], (1000, 520), 8)
        di = fit(shots["desk"], (480, 280), 8)
        ti = fit(shots["tray"], (480, 280), 8)
        for im, pos in [(t, (40, 180)), (di, (40, 730)), (ti, (560, 730))]:
            b = Image.new("RGB", (im.width + 4, im.height + 4), (0, 210, 255))
            b.paste(im, (2, 2))
            sq.paste(b, pos)
        sq.save(OUT / "social-collage-1080-v1.4.16.jpg", "JPEG", quality=96, optimize=True)

        # OG 1280x640 — letterbox the full 6-panel collage (not a 2-panel substitute)
        og = Image.new("RGB", (1280, 640), (8, 12, 20))
        fitted = bg.copy()
        fitted.thumbnail((1280, 640), Image.Resampling.LANCZOS)
        og.paste(fitted, ((1280 - fitted.width) // 2, (640 - fitted.height) // 2))
        ImageDraw.Draw(og).rectangle((0, 0, 8, 640), fill=(0, 210, 255))
        og.save(OUT / "social-preview-1280x640.jpg", "JPEG", quality=96, optimize=True)
        og.save(ROOT / "screenshots" / "social-preview.jpg", "JPEG", quality=96, optimize=True)
        print("collages OK")
    finally:
        for h in enum_title("Cursor"):
            user32.ShowWindow(h, SW_RESTORE)
            user32.SetForegroundWindow(h)
            break
        print("Cursor restored")


if __name__ == "__main__":
    main()
