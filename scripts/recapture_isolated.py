# -*- coding: utf-8 -*-
"""Orchestrate isolated per-tab captures, rebuild gradient collage, restore Cursor."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots" / "v1.4.3"
SOCIAL = Path.home() / "Downloads" / "fluentvoice-pro-socials-v1.4.3"
HWND_FILE = OUT / "_cursor_hwnds.txt"
ONE = ROOT / "scripts" / "_capture_one_tab.py"
user32 = ctypes.windll.user32
SW_MINIMIZE, SW_RESTORE, SW_SHOW = 6, 9, 5


def cursor_pids():
    pids = set()
    out = subprocess.check_output(
        ["tasklist", "/FI", "IMAGENAME eq Cursor.exe", "/FO", "CSV"],
        text=True,
        errors="ignore",
    )
    for line in out.splitlines()[1:]:
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 2:
            try:
                pids.add(int(parts[1]))
            except ValueError:
                pass
    return pids


def minimize_cursor():
    pids = cursor_pids()
    saved = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, _lparam):
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right - rect.left < 120 or rect.bottom - rect.top < 40:
            return True
        if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            print("min", int(hwnd))
        saved.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc, 0)
    HWND_FILE.write_text("\n".join(str(h) for h in sorted(set(saved))), encoding="utf-8")
    time.sleep(0.8)


def restore_cursor():
    pids = cursor_pids()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, _lparam):
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.ShowWindow(hwnd, SW_SHOW)
            try:
                user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            print("restored", int(hwnd))
        return True

    user32.EnumWindows(enum_proc, 0)


def run_one(tab, name, mode="normal"):
    out = OUT / name
    cmd = [sys.executable, str(ONE), tab, str(out), mode]
    print("RUN", tab, name, mode)
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f"failed {name}")
    im = Image.open(out)
    g = im.convert("L").resize((140, 90))
    pix = list(g.getdata())
    mean = sum(pix) / len(pix)
    var = sum((p - mean) ** 2 for p in pix) / len(pix)
    print(f"  -> {im.size} var={var:.0f}")
    if var < 200:
        print("  RETRY (low contrast)")
        subprocess.run(cmd, cwd=str(ROOT))
        im = Image.open(out)
        g = im.convert("L").resize((140, 90))
        pix = list(g.getdata())
        mean = sum(pix) / len(pix)
        var = sum((p - mean) ** 2 for p in pix) / len(pix)
        print(f"  -> retry {im.size} var={var:.0f}")
        if var < 200:
            print("  WARN still low contrast")
    return out


def make_gradient(size):
    w, h = size
    img = Image.new("RGB", (w, h))
    px = img.load()
    c_tl, c_tr, c_bl, c_br = (118, 52, 180), (30, 120, 220), (20, 170, 110), (255, 140, 40)
    for y in range(h):
        v = y / max(h - 1, 1)
        for x in range(w):
            u = x / max(w - 1, 1)
            top = tuple(int(c_tl[i] * (1 - u) + c_tr[i] * u) for i in range(3))
            bot = tuple(int(c_bl[i] * (1 - u) + c_br[i] * u) for i in range(3))
            col = tuple(int(top[i] * (1 - v) + bot[i] * v) for i in range(3))
            edge = min(u, v, 1 - u, 1 - v)
            shade = 0.78 + 0.22 * min(1.0, edge * 4)
            px[x, y] = tuple(max(0, min(255, int(c * shade))) for c in col)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle((0, 0, w, 160), fill=(10, 12, 28, 120))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def build_collage():
    order = [
        "00-desktop-icon-asset.png",
        "01-settings-reader.png",
        "02-settings-voice.png",
        "03-settings-automation.png",
        "03b-settings-automation-scrolled.png",
        "04-settings-about.png",
        "05c-tray-icon-closeup.png",
        "06b-tray-menu-crop.png",
    ]
    imgs = [Image.open(OUT / n).convert("RGB") for n in order if (OUT / n).exists()]
    cols = 4
    rows = (len(imgs) + cols - 1) // cols
    tile_w, tile_h = 760, 520
    pad, gap, title_h = 52, 36, 130
    W = pad * 2 + cols * tile_w + (cols - 1) * gap
    H = title_h + pad + rows * tile_h + (rows - 1) * gap + pad
    bg = make_gradient((W, H))
    draw = ImageDraw.Draw(bg)
    try:
        ft = ImageFont.truetype("segoeuib.ttf", 46)
        fs = ImageFont.truetype("segoeui.ttf", 23)
    except Exception:
        ft = fs = ImageFont.load_default()
    draw.text((pad + 2, 38), "FluentVoice Pro v1.4.3", fill=(0, 0, 0), font=ft)
    draw.text((pad, 36), "FluentVoice Pro v1.4.3", fill=(255, 255, 255), font=ft)
    sub = "Windows 11 TTS Suite  ·  Tray · Reader · Voices · Automation  ·  2026"
    draw.text((pad + 1, 91), sub, fill=(0, 0, 0), font=fs)
    draw.text((pad, 90), sub, fill=(235, 240, 255), font=fs)

    def round_fit(im):
        im = im.copy()
        im.thumbnail((tile_w - 20, tile_h - 20), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (tile_w, tile_h), (14, 18, 30))
        canvas.paste(im, ((tile_w - im.width) // 2, (tile_h - im.height) // 2))
        mask = Image.new("L", (tile_w, tile_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile_w - 1, tile_h - 1), radius=16, fill=255)
        out = Image.new("RGB", (tile_w, tile_h), (0, 0, 0))
        out.paste(canvas, (0, 0), mask)
        return out

    for i, im in enumerate(imgs[:8]):
        r, c = divmod(i, cols)
        x = pad + c * (tile_w + gap)
        y = title_h + pad + r * (tile_h + gap)
        tile = round_fit(im)
        shadow = Image.new("RGBA", (tile_w + 28, tile_h + 28), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((10, 12, tile_w + 10, tile_h + 12), radius=16, fill=(0, 0, 0, 140))
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        bg.paste(shadow, (x - 8, y - 4), shadow)
        rim = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
        ImageDraw.Draw(rim).rounded_rectangle((1, 1, tile_w - 2, tile_h - 2), radius=16, outline=(220, 240, 255, 170), width=2)
        bg.paste(tile, (x, y))
        bg.paste(rim, (x, y), rim)

    bg.save(OUT / "collage-v1.4.3-2026.jpg", "JPEG", quality=97, subsampling=0)
    bg.save(SOCIAL / "collage-v1.4.3-2026.jpg", "JPEG", quality=97, subsampling=0)
    bg.save(SOCIAL / "collage-v1.4.3-2026.png", "PNG")
    canvas = make_gradient((1280, 640))
    og = bg.copy()
    og.thumbnail((1280, 640), Image.Resampling.LANCZOS)
    canvas.paste(og, ((1280 - og.width) // 2, (640 - og.height) // 2))
    canvas.save(OUT / "social-preview-1280x640.jpg", "JPEG", quality=97, subsampling=0)
    canvas.save(SOCIAL / "social-preview-1280x640.jpg", "JPEG", quality=97, subsampling=0)
    print("collage", bg.size)


def main():
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
    minimize_cursor()
    try:
        jobs = [
            ("Direct Text Reader", "01-settings-reader.png", "normal"),
            ("Voice & Speech", "02-settings-voice.png", "normal"),
            ("Automation & System", "03-settings-automation.png", "normal"),
            ("Automation & System", "03b-settings-automation-scrolled.png", "scroll=0.42"),
            ("About & Developer", "04-settings-about.png", "normal"),
            ("Direct Text Reader", "01m-settings-reader-maximized.png", "max"),
            ("Voice & Speech", "02m-settings-voice-maximized.png", "max"),
            ("Automation & System", "03m-settings-automation-maximized.png", "max"),
            ("About & Developer", "04m-settings-about-maximized.png", "max"),
        ]
        for tab, name, mode in jobs:
            run_one(tab, name, mode)
        build_collage()
        print("PASS")
    finally:
        restore_cursor()


if __name__ == "__main__":
    main()
