"""Retake HD tray menu + live desktop icon; no Desktop clutter; restore Cursor after."""
from __future__ import annotations

import ctypes
import io
import shutil
import time
import winreg
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageGrab

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots" / "v1.4.14"
OUT.mkdir(parents=True, exist_ok=True)
DESK = Path.home() / "Desktop"

SW_HIDE = 0
SW_MINIMIZE = 6
SW_RESTORE = 9
SW_SHOW = 5
SW_SHOWNA = 8

VK_ESCAPE = 0x1B


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("guidItem", ctypes.c_byte * 16),
    ]


def enum_windows_by_title(substr: str) -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if substr.lower() in buf.value.lower():
            found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found


def window_placement(hwnd: int) -> int:
    """Return current show cmd from WINDOWPLACEMENT.showCmd."""
    class WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint),
            ("flags", ctypes.c_uint),
            ("showCmd", ctypes.c_uint),
            ("ptMinPosition", POINT),
            ("ptMaxPosition", POINT),
            ("rcNormalPosition", RECT),
        ]

    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(WINDOWPLACEMENT)
    user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
    return int(wp.showCmd)


def minimize_hwnd(hwnd: int):
    user32.ShowWindow(hwnd, SW_MINIMIZE)


def restore_hwnd(hwnd: int):
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)


def press_escape():
    user32.keybd_event(VK_ESCAPE, 0, 0, 0)
    user32.keybd_event(VK_ESCAPE, 0, 2, 0)


def mouse_move(x: int, y: int):
    user32.SetCursorPos(int(x), int(y))


def mouse_click(x: int, y: int, right: bool = False):
    mouse_move(x, y)
    time.sleep(0.12)
    down = 0x0008 if right else 0x0002
    up = 0x0010 if right else 0x0004
    user32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(up, 0, 0, 0, 0)


def load_icon_snapshot() -> Image.Image | None:
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, r"Control Panel\NotifyIconSettings"
    )
    i = 0
    best = None
    while True:
        try:
            name = winreg.EnumKey(key, i)
            i += 1
        except OSError:
            break
        sk = winreg.OpenKey(key, name)
        try:
            tip = ""
            try:
                tip = winreg.QueryValueEx(sk, "Tooltip")[0] or ""
            except OSError:
                pass
            if "fluentvoice" not in tip.lower():
                continue
            snap = winreg.QueryValueEx(sk, "IconSnapshot")[0]
            best = Image.open(io.BytesIO(snap)).convert("RGBA")
        except OSError:
            pass
        finally:
            winreg.CloseKey(sk)
    winreg.CloseKey(key)
    return best


def get_visible_tooltip_text() -> str:
    texts: list[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value.lower() not in ("tooltips_class32", "tooltip"):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if not n:
            # TTN sometimes keeps text in window text even if length API lags
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if buf.value:
                texts.append(buf.value)
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value:
            texts.append(buf.value)
        return True

    user32.EnumWindows(cb, 0)
    return " | ".join(texts)


def find_tray_icon_by_hover() -> tuple[int, int] | None:
    """Sweep tray icons leftward from the clock; stop on FluentVoice tooltip."""
    screen = ImageGrab.grab()
    w, h = screen.size
    # Win11 tray icons sit left of clock/system area. Sweep Y around taskbar mid.
    y = h - 28
    # Start left of clock (~120–160px from right) and walk left across tray.
    x_start = w - 150
    x_end = w - 520
    print(f"hover-scanning tray x={x_start}->{x_end} y={y}")
    for x in range(x_start, x_end, -14):
        mouse_move(x, y)
        time.sleep(0.38)  # allow tooltip to appear
        tip = get_visible_tooltip_text()
        if tip:
            print(f"  tip @ {x},{y}: {tip[:120]}")
        if "fluentvoice" in tip.lower() or "natural voice reader" in tip.lower():
            print(f"FOUND tray via tooltip at {x},{y}")
            return (x, y)
    # Try one row higher (some setups)
    y2 = h - 42
    for x in range(x_start, x_end, -14):
        mouse_move(x, y2)
        time.sleep(0.38)
        tip = get_visible_tooltip_text()
        if tip:
            print(f"  tip @ {x},{y2}: {tip[:120]}")
        if "fluentvoice" in tip.lower() or "natural voice reader" in tip.lower():
            print(f"FOUND tray via tooltip at {x},{y2}")
            return (x, y2)
    return None


def find_tray_icon_via_shell() -> tuple[int, int] | None:
    """Locate FluentVoice notify icon rect via Shell_NotifyIconGetRect + process HWNDs."""
    import subprocess

    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine -like '*fluentvoice.tray*' } | "
                "Select-Object -ExpandProperty ProcessId",
            ],
            text=True,
            timeout=15,
        )
        pids = {int(x.strip()) for x in out.splitlines() if x.strip().isdigit()}
    except Exception as e:
        print("pid lookup failed", e)
        pids = set()
    if not pids:
        print("no fluentvoice.tray process")
        return None

    hwnds: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            hwnds.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    print(f"fluentvoice hwnds: {len(hwnds)} pids={pids}")

    shell32.Shell_NotifyIconGetRect.argtypes = [
        ctypes.POINTER(NOTIFYICONIDENTIFIER),
        ctypes.POINTER(RECT),
    ]
    shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long  # HRESULT

    for hwnd in hwnds:
        for uid in (0, 1, 2, 3, 4, 100, 101):
            ident = NOTIFYICONIDENTIFIER()
            ident.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
            ident.hWnd = hwnd
            ident.uID = uid
            rc = RECT()
            hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(ident), ctypes.byref(rc))
            if hr == 0 and rc.right > rc.left and rc.bottom > rc.top:
                cx = (rc.left + rc.right) // 2
                cy = (rc.top + rc.bottom) // 2
                print(f"Shell_NotifyIconGetRect hwnd={hwnd} uid={uid} -> {rc.left},{rc.top}-{rc.right},{rc.bottom}")
                return (cx, cy)
    return None


def find_tray_icon_center(template: Image.Image) -> tuple[int, int] | None:
    """Shell rect first, then tooltip hover scan, then template fallback."""
    hit = find_tray_icon_via_shell()
    if hit:
        return hit
    hit = find_tray_icon_by_hover()
    if hit:
        return hit
    screen = ImageGrab.grab()
    w, h = screen.size
    region = screen.crop((max(0, w - 560), max(0, h - 90), w, h)).convert("RGB")
    ox, oy = max(0, w - 560), max(0, h - 90)
    best_score = None
    best_xy = None
    for side in (16, 20, 24, 28, 32):
        t = template.resize((side, side), Image.Resampling.LANCZOS).convert("RGB")
        tw, th = t.size
        rp = region.load()
        tp = t.load()
        for y in range(0, region.height - th, 2):
            for x in range(0, region.width - tw, 2):
                sad = 0
                samples = 0
                for yy in range(0, th, 2):
                    for xx in range(0, tw, 2):
                        a = rp[x + xx, y + yy]
                        b = tp[xx, yy]
                        sad += abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
                        samples += 1
                score = sad / max(1, samples)
                if best_score is None or score < best_score:
                    best_score = score
                    best_xy = (ox + x + tw // 2, oy + y + th // 2)
    print(f"tray template fallback score={best_score} at {best_xy}")
    if best_score is not None and best_score < 120:
        return best_xy
    return None


def find_popup_menu_rect() -> RECT | None:
    """Find the open FluentVoice pystray/#32768 popup near the tray."""
    best = None
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        nonlocal best
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value not in ("#32768", "Qt5152QWindowToolSaveBits", "Windows.UI.Core.CoreWindow"):
            # pystray on Win uses #32768 for classic menus
            if cls.value != "#32768":
                return True
        rc = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        ww = rc.right - rc.left
        hh = rc.bottom - rc.top
        if ww < 160 or hh < 180:
            return True
        # Prefer menus in the lower-right quadrant
        if rc.left < screen_w * 0.35 or rc.top < screen_h * 0.25:
            return True
        area = ww * hh
        if best is None or area > (best[0]):
            best = (area, rc.left, rc.top, rc.right, rc.bottom, cls.value)
        return True

    user32.EnumWindows(cb, 0)
    if not best:
        return None
    rc = RECT(best[1], best[2], best[3], best[4])
    print(f"menu hwnd class area={best[0]} rect=({rc.left},{rc.top})-({rc.right},{rc.bottom}) cls={best[5]}")
    return rc


def find_desktop_icon_rect(label_substr: str = "FluentVoice") -> tuple[int, int, int, int] | None:
    """Locate desktop icon via SysListView32 + LVM_GETITEMRECT."""
    import struct

    hwnd_progman = user32.FindWindowW("Progman", None)
    hwnd_defview = user32.FindWindowExW(hwnd_progman, 0, "SHELLDLL_DefView", None)
    if not hwnd_defview:
        # WorkerW fallback
        worker = 0

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enum_worker(hwnd, _lp):
            nonlocal worker, hwnd_defview
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value == "WorkerW":
                dv = user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
                if dv:
                    hwnd_defview = dv
                    worker = hwnd
                    return False
            return True

        user32.EnumWindows(enum_worker, 0)
    if not hwnd_defview:
        return None
    listview = user32.FindWindowExW(hwnd_defview, 0, "SysListView32", None)
    if not listview:
        return None

    LVM_GETITEMCOUNT = 0x1004
    LVM_GETITEMTEXTW = 0x1073
    LVM_GETITEMRECT = 0x100E
    LVIR_BOUNDS = 0
    PROCESS_VM_OPERATION = 0x0008
    PROCESS_VM_READ = 0x0010
    PROCESS_VM_WRITE = 0x0020
    PROCESS_QUERY_INFORMATION = 0x0400
    MEM_COMMIT = 0x1000
    MEM_RELEASE = 0x8000
    PAGE_READWRITE = 0x04

    kernel32 = ctypes.windll.kernel32
    count = user32.SendMessageW(listview, LVM_GETITEMCOUNT, 0, 0)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(listview, ctypes.byref(pid))
    hproc = kernel32.OpenProcess(
        PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION,
        False,
        pid.value,
    )
    if not hproc:
        return None

    remote = None
    try:
        buf_size = 4096
        remote = kernel32.VirtualAllocEx(hproc, None, buf_size, MEM_COMMIT, PAGE_READWRITE)
        if not remote:
            return None
        local_text = ctypes.create_unicode_buffer(512)
        for i in range(count):
            class LVITEMW(ctypes.Structure):
                _fields_ = [
                    ("mask", ctypes.c_uint),
                    ("iItem", ctypes.c_int),
                    ("iSubItem", ctypes.c_int),
                    ("state", ctypes.c_uint),
                    ("stateMask", ctypes.c_uint),
                    ("pszText", ctypes.c_uint64),
                    ("cchTextMax", ctypes.c_int),
                    ("iImage", ctypes.c_int),
                    ("lParam", ctypes.c_int64),
                    ("iIndent", ctypes.c_int),
                    ("iGroupId", ctypes.c_int),
                    ("cColumns", ctypes.c_uint),
                    ("puColumns", ctypes.c_uint64),
                    ("piColFmt", ctypes.c_uint64),
                    ("iGroup", ctypes.c_int),
                ]

            text_remote = remote + 512
            item = LVITEMW()
            item.mask = 1  # LVIF_TEXT
            item.iItem = i
            item.iSubItem = 0
            item.pszText = text_remote
            item.cchTextMax = 256
            kernel32.WriteProcessMemory(hproc, remote, ctypes.byref(item), ctypes.sizeof(item), None)
            user32.SendMessageW(listview, LVM_GETITEMTEXTW, i, remote)
            kernel32.ReadProcessMemory(
                hproc, text_remote, local_text, 512, None
            )
            name = local_text.value or ""
            if label_substr.lower() not in name.lower():
                continue
            # Get bounds rect
            r = RECT(LVIR_BOUNDS, 0, 0, 0)
            kernel32.WriteProcessMemory(hproc, remote, ctypes.byref(r), ctypes.sizeof(r), None)
            user32.SendMessageW(listview, LVM_GETITEMRECT, i, remote)
            kernel32.ReadProcessMemory(hproc, remote, ctypes.byref(r), ctypes.sizeof(r), None)
            # Client to screen
            pt = POINT(r.left, r.top)
            user32.ClientToScreen(listview, ctypes.byref(pt))
            x0, y0 = pt.x, pt.y
            pt2 = POINT(r.right, r.bottom)
            user32.ClientToScreen(listview, ctypes.byref(pt2))
            print(f"FOUND desktop icon '{name}' screen=({x0},{y0})-({pt2.x},{pt2.y})")
            return (x0, y0, pt2.x, pt2.y)
    finally:
        if remote:
            kernel32.VirtualFreeEx(hproc, remote, 0, MEM_RELEASE)
        kernel32.CloseHandle(hproc)
    return None


def upscale(img: Image.Image, factor: int = 2) -> Image.Image:
    return img.resize(
        (img.width * factor, img.height * factor), Image.Resampling.LANCZOS
    )


def load_font(size: int, bold: bool = False):
    p = r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf"
    return ImageFont.truetype(p, size)


def fit(img: Image.Image, box: tuple[int, int], pad: int = 8) -> Image.Image:
    tw, th = box
    c = Image.new("RGB", (tw, th), (13, 19, 29))
    im = img.convert("RGB")
    scale = min((tw - pad * 2) / im.width, (th - pad * 2) / im.height)
    nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
    r = im.resize((nw, nh), Image.Resampling.LANCZOS)
    c.paste(r, ((tw - nw) // 2, (th - nh) // 2))
    return c


def rebuild_collages():
    shots = {
        "reader": Image.open(OUT / "01-settings-reader.png"),
        "voice": Image.open(OUT / "02-settings-voice.png"),
        "auto": Image.open(OUT / "03-settings-automation.png"),
        "about": Image.open(OUT / "04-settings-about.png"),
        "footer": Image.open(OUT / "05-footer-emergency-stop.png")
        if (OUT / "05-footer-emergency-stop.png").exists()
        else Image.open(OUT / "04-settings-about.png"),
        "tray": Image.open(OUT / "06b-tray-menu-crop.png"),
        "desk": Image.open(OUT / "00-desktop-icon-live.png"),
        "trayicon": Image.open(OUT / "05c-tray-icon-closeup.png"),
    }
    W, H = 1920, 1280
    bg = Image.new("RGB", (W, H), (8, 12, 20))
    d = ImageDraw.Draw(bg)
    d.rectangle((0, 0, W, 8), fill=(0, 210, 255))
    d.text((48, 28), "FluentVoice Pro", fill=(0, 210, 255), font=load_font(42, True))
    d.text(
        (48, 82),
        "v1.4.14  •  Tray right-click menu (HD)  •  Live desktop icon  •  Factory Reset  •  Emergency Stop",
        fill=(200, 209, 217),
        font=load_font(20),
    )
    d.text(
        (48, 114),
        "Nick Otmazgin  •  github.com/nickotmazgin/fluentvoice-pro",
        fill=(139, 148, 158),
        font=load_font(16),
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
        d.text((x + 4, y), label, fill=(230, 237, 243), font=load_font(16, True))
    bg.save(OUT / "collage-v1.4.14-2026.jpg", "JPEG", quality=96, optimize=True)
    bg.save(ROOT / "screenshots" / "collage.jpg", "JPEG", quality=96, optimize=True)

    S = 1080
    sq = Image.new("RGB", (S, S), (8, 12, 20))
    ds = ImageDraw.Draw(sq)
    ds.rectangle((0, 0, S, 10), fill=(0, 210, 255))
    ds.text((40, 30), "FluentVoice Pro", fill=(0, 210, 255), font=load_font(48, True))
    ds.text((40, 90), "v1.4.14  •  Tray menu + Desktop icon", fill=(230, 237, 243), font=load_font(24))
    ds.text((40, 130), "Right-click tray · Live desktop shortcut", fill=(139, 148, 158), font=load_font(18))
    t = fit(shots["tray"], (1000, 520), 8)
    di = fit(shots["desk"], (480, 280), 8)
    ti = fit(shots["trayicon"], (480, 280), 8)
    for im, pos in [(t, (40, 180)), (di, (40, 730)), (ti, (560, 730))]:
        b = Image.new("RGB", (im.width + 4, im.height + 4), (0, 210, 255))
        b.paste(im, (2, 2))
        sq.paste(b, pos)
    sq.save(OUT / "social-collage-1080-v1.4.14.jpg", "JPEG", quality=96, optimize=True)

    og = Image.new("RGB", (1280, 640), (8, 12, 20))
    do = ImageDraw.Draw(og)
    do.rectangle((0, 0, 12, 640), fill=(0, 210, 255))
    do.text((40, 28), "FluentVoice Pro", fill=(0, 210, 255), font=load_font(44, True))
    do.text(
        (40, 88),
        "v1.4.14 — Tray menu · Desktop · Control Center",
        fill=(230, 237, 243),
        font=load_font(22),
    )
    L = fit(shots["voice"], (620, 440), 6)
    R = fit(shots["tray"], (560, 440), 6)
    for im, pos in [(L, (40, 160)), (R, (700, 160))]:
        b = Image.new("RGB", (im.width + 4, im.height + 4), (0, 210, 255))
        b.paste(im, (2, 2))
        og.paste(b, pos)
    og.save(OUT / "social-preview-1280x640.jpg", "JPEG", quality=96, optimize=True)
    og.save(ROOT / "screenshots" / "social-preview.jpg", "JPEG", quality=96, optimize=True)
    print("collages rebuilt in repo only")


def clear_desktop_copies():
    removed = []
    for p in DESK.glob("FluentVoice-Pro-v1.4.14-*"):
        p.unlink(missing_ok=True)
        removed.append(p.name)
    # also any loose tray/desktop naming
    for p in DESK.glob("*FluentVoice*tray*"):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            p.unlink(missing_ok=True)
            removed.append(p.name)
    for p in DESK.glob("*FluentVoice*desktop*icon*"):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            p.unlink(missing_ok=True)
            removed.append(p.name)
    print("removed from Desktop:", removed or "(none)")


def main():
    cursor_hwnds = enum_windows_by_title("Cursor")
    settings_hwnds = enum_windows_by_title("FluentVoice Pro - Settings")
    cursor_state = {h: window_placement(h) for h in cursor_hwnds}
    settings_state = {h: window_placement(h) for h in settings_hwnds}
    print("Cursor windows:", cursor_hwnds, cursor_state)
    print("Settings windows:", settings_hwnds, settings_state)

    try:
        for h in cursor_hwnds:
            minimize_hwnd(h)
        for h in settings_hwnds:
            minimize_hwnd(h)
        time.sleep(0.8)

        # Move pointer away from tray so no stale tooltip
        mouse_move(400, 400)
        press_escape()
        time.sleep(0.4)

        snap = load_icon_snapshot()
        if snap is None:
            asset = ROOT / "assets" / "tray_icon.ico"
            snap = Image.open(asset).convert("RGBA")
        center = find_tray_icon_center(snap)
        if not center:
            # Fallback: known Win11 tray cluster — try clicking promoted icon slots right of clock area
            raise SystemExit("Could not locate FluentVoice tray icon visually")

        cx, cy = center
        print(f"tray icon center {cx},{cy}")

        # Closeup of tray icon (no menu)
        mouse_move(cx - 80, cy - 40)  # not hovering icon
        time.sleep(0.5)
        full = ImageGrab.grab()
        pad = 28
        tray_close = full.crop(
            (max(0, cx - 40), max(0, cy - 40), min(full.width, cx + 40), min(full.height, cy + 40))
        )
        upscale(tray_close, 4).save(OUT / "05c-tray-icon-closeup.png")
        strip = full.crop((max(0, full.width - 520), max(0, full.height - 72), full.width, full.height))
        upscale(strip, 2).save(OUT / "05-taskbar-tray-strip.png")
        print("saved tray closeup + strip")

        # Open menu with right-click
        mouse_click(cx, cy, right=True)
        time.sleep(0.55)

        menu = find_popup_menu_rect()
        if not menu:
            # retry once
            press_escape()
            time.sleep(0.3)
            mouse_click(cx, cy, right=True)
            time.sleep(0.7)
            menu = find_popup_menu_rect()
        if not menu:
            raise SystemExit("Tray context menu did not appear")

        # Move mouse INTO the menu (upper-middle) so tray hover tooltip dismisses
        mx = (menu.left + menu.right) // 2
        my = menu.top + 80
        mouse_move(mx, my)
        time.sleep(0.35)
        # Nudge slightly so any transient tip is gone; keep pointer on menu
        mouse_move(mx, my + 40)
        time.sleep(0.9)  # wait for tooltip fade — do not rush

        full = ImageGrab.grab()
        # Full menu with breathing room (include tray icon under it, no need for tooltip)
        pad_l, pad_t, pad_r, pad_b = 24, 24, 24, 48
        x0 = max(0, menu.left - pad_l)
        y0 = max(0, menu.top - pad_t)
        x1 = min(full.width, menu.right + pad_r)
        y1 = min(full.height, max(menu.bottom + pad_b, cy + 36))
        menu_full = full.crop((x0, y0, x1, y1))
        # Save native HD + 2x for README readability
        menu_full.save(OUT / "06-tray-menu-full.png")
        upscale(menu_full, 2).save(OUT / "06b-tray-menu-crop.png")
        print("saved tray menu HD", menu_full.size, "-> 2x", (menu_full.width * 2, menu_full.height * 2))

        # Dismiss menu before desktop crop
        press_escape()
        time.sleep(0.35)
        mouse_move(200, 200)
        time.sleep(0.25)

        # Live desktop icon
        desk = find_desktop_icon_rect("FluentVoice")
        full = ImageGrab.grab()
        if desk:
            x0, y0, x1, y1 = desk
            pad = 36
            crop = full.crop(
                (max(0, x0 - pad), max(0, y0 - pad), min(full.width, x1 + pad), min(full.height, y1 + pad))
            )
            upscale(crop, 3).save(OUT / "00-desktop-icon-live.png")
            print("saved desktop live", crop.size, "-> 3x")
            # column context
            full.crop((0, 0, min(700, full.width), min(980, full.height))).save(
                OUT / "00-desktop-icons-column.png"
            )
        else:
            print("WARNING: desktop icon not found via ListView")

        rebuild_collages()
        clear_desktop_copies()
        print("OK capture complete")
    finally:
        # Always restore Cursor (and Settings)
        for h, show in settings_state.items():
            if user32.IsWindow(h):
                if show == 3:  # maximized
                    user32.ShowWindow(h, 3)
                else:
                    restore_hwnd(h)
        for h, show in cursor_state.items():
            if user32.IsWindow(h):
                if show == 3:
                    user32.ShowWindow(h, 3)
                    user32.SetForegroundWindow(h)
                else:
                    restore_hwnd(h)
        # Prefer bringing Cursor Agents to front
        for h in enum_windows_by_title("Cursor"):
            restore_hwnd(h)
            break
        print("restored Cursor / Settings")


if __name__ == "__main__":
    main()
