# -*- coding: utf-8 -*-
"""Recapture tray menu + Automation bottom, rebuild collage."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
import sys
import time
from pathlib import Path

import mss
import pyautogui
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots" / "v1.4.3"
SOCIAL = Path.home() / "Downloads" / "fluentvoice-pro-socials-v1.4.3"
ONE = ROOT / "scripts" / "_capture_one_tab.py"
sys.path.insert(0, str(ROOT))

user32 = ctypes.windll.user32
SW_MINIMIZE, SW_RESTORE, SW_SHOW = 6, 9, 5
pyautogui.FAILSAFE = False


def grab_rect(l, t, r, b):
    with mss.MSS() as sct:
        box = {
            "left": int(l),
            "top": int(t),
            "width": max(1, int(r - l)),
            "height": max(1, int(b - t)),
        }
        shot = sct.grab(box)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def grab_screen():
    with mss.MSS() as sct:
        mon = sct.monitors[0]
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def save(img: Image.Image, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    SOCIAL.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    tmp = OUT / (name + ".tmp.png")
    # Large full-screen grabs can fail PNG optimize on Windows; write temp then replace
    img.save(tmp, "PNG")
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass
    tmp.replace(path)
    img.save(SOCIAL / name, "PNG")
    img.convert("RGB").save(SOCIAL / (Path(name).stem + ".jpg"), "JPEG", quality=95, subsampling=0)
    g = img.convert("L").resize((120, 80))
    pix = list(g.getdata())
    mean = sum(pix) / len(pix)
    var = sum((p - mean) ** 2 for p in pix) / len(pix)
    print(f"OK {name} {img.size} var={var:.0f}")
    return path


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

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, _lparam):
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            print("min", int(hwnd))
        return True

    user32.EnumWindows(enum_proc, 0)
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


def capture_tray_menu():
    from fluentvoice.lifecycle import ensure_tray_running
    from fluentvoice.tray import apply_win32_dark_menus
    from pywinauto import Desktop

    ensure_tray_running(2.0)
    time.sleep(1.2)
    for _ in range(4):
        apply_win32_dark_menus()
        time.sleep(0.12)

    full = grab_screen()
    w, h = full.size
    save(grab_rect(0, h - 58, w, h), "05-taskbar-tray-strip.png")

    desk = Desktop(backend="uia")
    tray = desk.window(class_name="Shell_TrayWnd")
    found = None
    for d in tray.descendants():
        try:
            t = d.window_text() or ""
            if "FluentVoice" in t:
                found = d
                break
        except Exception:
            pass

    # Also search NotifyIconOverflowWindow
    if not found:
        try:
            overflow = desk.window(class_name="NotifyIconOverflowWindow")
            for d in overflow.descendants():
                try:
                    t = d.window_text() or ""
                    if "FluentVoice" in t:
                        found = d
                        break
                except Exception:
                    pass
        except Exception:
            pass

    if not found:
        # Open overflow chevron and retry
        pyautogui.hotkey("win", "b")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.6)
        for d in Desktop(backend="uia").windows():
            try:
                for child in d.descendants():
                    t = (child.window_text() or "")
                    if "FluentVoice" in t:
                        found = child
                        break
            except Exception:
                pass
            if found:
                break

    if not found:
        print("WARN: tray icon not found — saving bottom-right taskbar area")
        save(grab_rect(w - 520, h - 420, w, h), "06-tray-menu-full.png")
        return False

    r = found.rectangle()
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    print(f"tray icon at {cx},{cy} text={found.window_text()!r}")
    apply_win32_dark_menus()
    pyautogui.moveTo(cx, cy)
    time.sleep(0.35)
    save(grab_rect(cx - 100, cy - 90, cx + 140, cy + 50), "05c-tray-icon-closeup.png")

    pyautogui.click(button="right")
    time.sleep(0.55)
    apply_win32_dark_menus()
    # Hover mid-menu for dark highlight look
    pyautogui.moveTo(cx - 160, cy - 380, duration=0.2)
    time.sleep(0.45)

    shot = grab_screen()
    save(shot, "06-tray-menu-full.png")
    crop = shot.crop(
        (
            max(0, cx - 440),
            max(0, cy - 620),
            min(shot.width, cx + 60),
            min(shot.height, cy + 50),
        )
    )
    save(crop, "06b-tray-menu-crop.png")
    pyautogui.press("escape")
    time.sleep(0.2)
    return True


def capture_automation_bottom():
    """Scroll Automation tab fully to bottom (Tray Daemon + How to Trigger)."""
    # Maximized + scroll=1.0 so full tips card fits in viewport
    out = OUT / "03c-settings-automation-bottom.png"
    cmd = [sys.executable, str(ONE), "Automation & System", str(out), "max+scroll=1.0"]
    print("RUN", cmd[-3:])
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0 or not out.exists():
        # fallback normal scroll
        cmd = [sys.executable, str(ONE), "Automation & System", str(out), "scroll=1.0"]
        r = subprocess.run(cmd, cwd=str(ROOT))
        if r.returncode != 0 or not out.exists():
            raise SystemExit("automation bottom capture failed")
    im = Image.open(out)
    g = im.convert("L").resize((140, 90))
    pix = list(g.getdata())
    mean = sum(pix) / len(pix)
    var = sum((p - mean) ** 2 for p in pix) / len(pix)
    print(f"  -> {im.size} var={var:.0f}")
    out_b = OUT / "03b-settings-automation-scrolled.png"
    cmd_b = [sys.executable, str(ONE), "Automation & System", str(out_b), "scroll=0.85"]
    print("RUN", cmd_b[-3:])
    subprocess.run(cmd_b, cwd=str(ROOT))
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
        "03c-settings-automation-bottom.png",
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
    sub = "Windows 11 TTS Suite  ·  Tray Menu · Reader · Voices · Automation  ·  2026"
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
        ImageDraw.Draw(shadow).rounded_rectangle(
            (10, 12, tile_w + 10, tile_h + 12), radius=16, fill=(0, 0, 0, 140)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        bg.paste(shadow, (x - 8, y - 4), shadow)
        rim = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
        ImageDraw.Draw(rim).rounded_rectangle(
            (1, 1, tile_w - 2, tile_h - 2), radius=16, outline=(220, 240, 255, 170), width=2
        )
        bg.paste(tile, (x, y))
        bg.paste(rim, (x, y), rim)

    SOCIAL.mkdir(parents=True, exist_ok=True)
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
        print("=== tray menu ===")
        ok = capture_tray_menu()
        print("tray ok=", ok)
        print("=== automation bottom ===")
        capture_automation_bottom()
        print("=== collage ===")
        build_collage()
        print("PASS")
    finally:
        restore_cursor()


if __name__ == "__main__":
    main()
