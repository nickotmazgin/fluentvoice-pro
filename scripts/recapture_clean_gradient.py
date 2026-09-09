# -*- coding: utf-8 -*-
"""Minimize Cursor, recapture FluentVoice HQ shots, rebuild gradient collage, restore Cursor."""
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
sys.path.insert(0, str(ROOT))

OUT = ROOT / "screenshots" / "v1.4.3"
OUT.mkdir(parents=True, exist_ok=True)
SOCIAL = Path.home() / "Downloads" / "fluentvoice-pro-socials-v1.4.3"
SOCIAL.mkdir(parents=True, exist_ok=True)
HWND_FILE = OUT / "_cursor_hwnds.txt"

user32 = ctypes.windll.user32
SW_MINIMIZE = 6
SW_RESTORE = 9
SW_SHOW = 5
SW_MAXIMIZE = 3

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.1


def stay_awake():
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)


def cursor_pids() -> set[int]:
    pids: set[int] = set()
    try:
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
    except Exception:
        pass
    return pids


def minimize_cursor() -> list[int]:
    pids = cursor_pids()
    saved: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, _lparam):
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(max(length, 1) + 1)
        if length:
            user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        # Keep any visible Cursor top-level window (including Agents)
        if user32.IsIconic(hwnd):
            saved.append(int(hwnd))
            return True
        if w >= 200 and h >= 80:
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            saved.append(int(hwnd))
            print("minimized", int(hwnd), title[:60] or f"{w}x{h}")
        return True

    user32.EnumWindows(enum_proc, 0)
    # Also always include known Agents hwnd if present
    HWND_FILE.write_text("\n".join(str(h) for h in sorted(set(saved))), encoding="utf-8")
    time.sleep(0.9)
    return saved


def restore_cursor():
    if not HWND_FILE.exists():
        print("no hwnd file")
        return
    for line in HWND_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        hwnd = int(line)
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetForegroundWindow(hwnd)
        print("restored", hwnd)
    time.sleep(0.4)


def grab_screen() -> Image.Image:
    with mss.MSS() as sct:
        mon = sct.monitors[1]
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def grab_rect(left, top, right, bottom) -> Image.Image:
    with mss.MSS() as sct:
        box = {
            "left": int(left),
            "top": int(top),
            "width": max(1, int(right - left)),
            "height": max(1, int(bottom - top)),
        }
        shot = sct.grab(box)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def save(img: Image.Image, name: str) -> Path:
    path = OUT / name
    # Upscale slightly if too soft? Keep native pixels — HQ means sharp native capture.
    img.save(path, "PNG", optimize=True)
    img.save(SOCIAL / name, "PNG", optimize=True)
    img.convert("RGB").save(SOCIAL / (Path(name).stem + ".jpg"), "JPEG", quality=97, optimize=True, subsampling=0)
    print("saved", name, img.size)
    return path


def assert_readable(path: Path, min_w: int = 900, min_h: int = 600):
    im = Image.open(path)
    w, h = im.size
    if w < min_w or h < min_h:
        raise SystemExit(f"LOW RES {path.name}: {w}x{h}")
    # Basic contrast check — stddev of luminance
    g = im.convert("L").resize((160, 100))
    pixels = list(g.getdata())
    mean = sum(pixels) / len(pixels)
    var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
    print(f"check {path.name}: {w}x{h} contrast_var={var:.1f}")
    if var < 80:
        print("WARN low contrast", path.name)


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
    time.sleep(0.7)
    app.geometry("1200x860")
    app.lift()
    app.focus_force()
    app.update()
    time.sleep(0.6)

    hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
    for fname, tab in tabs:
        app.tabview.set(tab)
        app._on_window_configure()
        app.update()
        app.update_idletasks()
        time.sleep(0.75)
        hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
        l, t, r, b = window_rect(hwnd)
        save(grab_rect(l + 1, t + 1, r - 1, b - 1), fname)

    # scrolled automation
    app.tabview.set("Automation & System")
    app.update()
    time.sleep(0.3)
    try:
        for child in app.tab_options.winfo_children():
            canvas = getattr(child, "_parent_canvas", None)
            if canvas is not None:
                canvas.yview_moveto(0.45)
                app.update()
                time.sleep(0.5)
                l, t, r, b = window_rect(hwnd)
                save(grab_rect(l + 1, t + 1, r - 1, b - 1), "03b-settings-automation-scrolled.png")
                canvas.yview_moveto(0.0)
                break
    except Exception as e:
        print("scroll skip", e)

    # maximized
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    app.update()
    time.sleep(0.8)
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
        time.sleep(0.8)
        hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
        l, t, r, b = window_rect(hwnd)
        save(grab_rect(l + 1, t + 1, r - 1, b - 1), fname)

    try:
        app.destroy()
    except Exception:
        pass


def capture_desktop_and_tray():
    from fluentvoice.lifecycle import ensure_tray_running
    from fluentvoice.tray import apply_win32_dark_menus
    from pywinauto import Desktop

    ensure_tray_running(1.5)
    time.sleep(1.0)
    full = grab_screen()
    save(full, "00-desktop-full.png")

    # Live desktop icon via cyan score on left side
    import numpy as np

    arr = np.asarray(full)
    best = None
    for y0 in range(40, 1100, 8):
        for x0 in range(0, 700, 6):
            patch = arr[y0 : y0 + 90, x0 : x0 + 90]
            if patch.shape[0] < 80:
                continue
            r, g, b = patch[:, :, 0].astype(int), patch[:, :, 1].astype(int), patch[:, :, 2].astype(int)
            cyan = int(((b > 150) & (g > 100) & (r < 120)).sum())
            if best is None or cyan > best[0]:
                best = (cyan, x0, y0)
    if best and best[0] > 200:
        _, x0, y0 = best
        save(full.crop((max(0, x0 - 20), max(0, y0 - 10), min(full.width, x0 + 120), min(full.height, y0 + 130))), "00-desktop-icon-live.png")
        print("desktop icon cyan", best[0], x0, y0)

    # Brand plate
    ico = ROOT / "assets" / "icon.png"
    if ico.exists():
        icon = Image.open(ico).convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (720, 780), (12, 16, 28, 255))
        canvas.paste(icon, (104, 60), icon)
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("segoeui.ttf", 34)
            font2 = ImageFont.truetype("segoeui.ttf", 20)
        except Exception:
            font = font2 = ImageFont.load_default()
        draw.text((360, 640), "FluentVoice Pro", fill=(230, 237, 243, 255), font=font, anchor="mm")
        draw.text((360, 685), "Desktop shortcut", fill=(160, 170, 180, 255), font=font2, anchor="mm")
        save(canvas.convert("RGB"), "00-desktop-icon-asset.png")

    w, h = full.size
    save(grab_rect(0, h - 58, w, h), "05-taskbar-tray-strip.png")

    for _ in range(3):
        apply_win32_dark_menus()
        time.sleep(0.1)

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
    if not found:
        print("WARN: tray icon not found")
        return
    r = found.rectangle()
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    apply_win32_dark_menus()
    pyautogui.moveTo(cx, cy)
    time.sleep(0.25)
    save(grab_rect(cx - 90, cy - 80, cx + 130, cy + 45), "05c-tray-icon-closeup.png")
    pyautogui.click(button="right")
    time.sleep(0.4)
    # Hover Direct Text Reader row
    pyautogui.moveTo(cx - 150, cy - 430, duration=0.18)
    time.sleep(0.35)
    shot = grab_screen()
    save(shot, "06-tray-menu-full.png")
    save(
        shot.crop((max(0, cx - 420), max(0, cy - 560), min(shot.width, cx + 40), min(shot.height, cy + 45))),
        "06b-tray-menu-crop.png",
    )
    pyautogui.press("escape")


def make_gradient(size: tuple[int, int]) -> Image.Image:
    """Beautiful purple → blue → green → orange blend background."""
    w, h = size
    img = Image.new("RGB", (w, h))
    px = img.load()
    # Corner colors
    # TL purple, TR blue, BL green, BR orange
    c_tl = (118, 52, 180)   # purple
    c_tr = (30, 120, 220)   # blue
    c_bl = (20, 170, 110)   # green
    c_br = (255, 140, 40)   # orange
    for y in range(h):
        v = y / max(h - 1, 1)
        for x in range(w):
            u = x / max(w - 1, 1)
            # bilinear blend
            top = tuple(int(c_tl[i] * (1 - u) + c_tr[i] * u) for i in range(3))
            bot = tuple(int(c_bl[i] * (1 - u) + c_br[i] * u) for i in range(3))
            col = tuple(int(top[i] * (1 - v) + bot[i] * v) for i in range(3))
            # soft vignette darken edges slightly for tile contrast
            edge = min(u, v, 1 - u, 1 - v)
            shade = 0.78 + 0.22 * min(1.0, edge * 4)
            px[x, y] = tuple(max(0, min(255, int(c * shade))) for c in col)
    # Soft blur for silky blend
    img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
    # Overlay subtle dark navy for readability under title
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 0, w, 160), fill=(10, 12, 28, 110))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img


def build_collage():
    order = [
        "00-desktop-icon-asset.png",
        "00-desktop-icon-live.png",
        "01-settings-reader.png",
        "02-settings-voice.png",
        "03-settings-automation.png",
        "04-settings-about.png",
        "05c-tray-icon-closeup.png",
        "06b-tray-menu-crop.png",
    ]
    imgs = [Image.open(OUT / n).convert("RGB") for n in order if (OUT / n).exists()]
    if len(imgs) < 4:
        raise SystemExit("not enough images for collage")

    cols = 4
    rows = (len(imgs) + cols - 1) // cols
    tile_w, tile_h = 760, 520
    pad, gap, title_h = 52, 36, 130
    W = pad * 2 + cols * tile_w + (cols - 1) * gap
    H = title_h + pad + rows * tile_h + (rows - 1) * gap + pad
    bg = make_gradient((W, H))
    draw = ImageDraw.Draw(bg)
    try:
        font_title = ImageFont.truetype("segoeuib.ttf", 46)
        font_sub = ImageFont.truetype("segoeui.ttf", 23)
    except Exception:
        font_title = font_sub = ImageFont.load_default()

    # Title with soft shadow for readability on colorful bg
    draw.text((pad + 2, 36 + 2), "FluentVoice Pro v1.4.3", fill=(0, 0, 0), font=font_title)
    draw.text((pad, 36), "FluentVoice Pro v1.4.3", fill=(255, 255, 255), font=font_title)
    draw.text(
        (pad + 1, 90 + 1),
        "Windows 11 TTS Suite  ·  Tray · Reader · Voices · Automation  ·  2026",
        fill=(0, 0, 0),
        font=font_sub,
    )
    draw.text(
        (pad, 90),
        "Windows 11 TTS Suite  ·  Tray · Reader · Voices · Automation  ·  2026",
        fill=(235, 240, 255),
        font=font_sub,
    )

    def round_fit(im: Image.Image) -> Image.Image:
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
        # thin white/cyan rim
        rim = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
        ImageDraw.Draw(rim).rounded_rectangle(
            (1, 1, tile_w - 2, tile_h - 2), radius=16, outline=(220, 240, 255, 170), width=2
        )
        bg.paste(tile, (x, y))
        bg.paste(rim, (x, y), rim)

    out = OUT / "collage-v1.4.3-2026.jpg"
    bg.save(out, "JPEG", quality=97, optimize=True, subsampling=0)
    bg.save(SOCIAL / "collage-v1.4.3-2026.jpg", "JPEG", quality=97, optimize=True, subsampling=0)
    bg.save(SOCIAL / "collage-v1.4.3-2026.png", "PNG", optimize=True)
    og = bg.copy()
    og.thumbnail((1280, 640), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1280, 640), (20, 24, 48))
    # fill OG with mini gradient too
    canvas = make_gradient((1280, 640))
    canvas.paste(og, ((1280 - og.width) // 2, (640 - og.height) // 2))
    canvas.save(OUT / "social-preview-1280x640.jpg", "JPEG", quality=97, subsampling=0)
    canvas.save(SOCIAL / "social-preview-1280x640.jpg", "JPEG", quality=97, subsampling=0)
    print("collage", out, bg.size)
    return out


def quality_pass():
    must = [
        "01-settings-reader.png",
        "02-settings-voice.png",
        "03-settings-automation.png",
        "04-settings-about.png",
        "06b-tray-menu-crop.png",
        "collage-v1.4.3-2026.jpg",
    ]
    for name in must:
        p = OUT / name
        if not p.exists():
            raise SystemExit(f"missing {name}")
        if name.endswith(".jpg"):
            im = Image.open(p)
            print(f"check {name}: {im.size}")
            if im.size[0] < 1600:
                print("WARN collage narrower than expected")
        else:
            assert_readable(p, min_w=400 if "menu" in name or "tray" in name else 900, min_h=300 if "menu" in name else 500)


def main():
    stay_awake()
    print("=== minimize Cursor ===")
    minimize_cursor()
    try:
        print("=== capture settings ===")
        capture_settings()
        print("=== capture desktop/tray ===")
        capture_desktop_and_tray()
        print("=== collage ===")
        build_collage()
        print("=== quality pass ===")
        quality_pass()
        print("PASS")
    finally:
        print("=== restore Cursor ===")
        restore_cursor()


if __name__ == "__main__":
    main()
