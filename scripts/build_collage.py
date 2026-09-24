"""Build the README collage + social images from screenshots/v<version>/.

Usage:  python scripts/build_collage.py            (version read from fluentvoice/__init__.py)
Writes: screenshots/v<ver>/collage-v<ver>.jpg          3840 wide  README hero (3x3, 01–09)
        screenshots/v<ver>/social-collage-1080.jpg     1080x1080  social posts
        screenshots/v<ver>/social-preview-1280x640.jpg 1280x640   GitHub OG preview
        + copies to screenshots/collage.jpg, screenshots/social-preview.jpg, .github/social-preview.{jpg,png}
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "fluentvoice" / "__init__.py").read_text()).group(1)
SRC = ROOT / "screenshots" / f"v{VERSION}"

TITLE = "FluentVoice Pro™"
SUBTITLE = "Windows 11 / 10 text-to-speech & read-aloud tray suite"
HIGHLIGHTS = "Start with Windows (portable too)  •  Streaming Direct Text Reader  •  Check for Updates (SHA-256 verified)  •  Neural + offline voices"
FOOTER = "Nick Otmazgin  •  github.com/nickotmazgin/fluentvoice-pro  •  MIT License"

PANELS = [  # (file, number, label) in reading order
    ("01-settings-reader.png", "01", "Direct Text Reader"),
    ("02-settings-voice.png", "02", "Voice & Speech"),
    ("03-settings-automation.png", "03", "Automation & System"),
    ("04-settings-about-updates.png", "04", "About · Updates & Factory Reset"),
    ("05-tray-menu.png", "05", "Tray right-click menu"),
    ("06-desktop-icon-live.png", "06", "Desktop icon"),
    ("07-tray-icon-closeup.png", "07", "Tray icon near the clock"),
    ("08-settings-automation-updates.png", "08", "Automation · Startup & Shortcuts"),
    ("09-portable-first-launch.png", "09", "Portable first launch"),
]

CYAN = (0, 210, 255)
VIOLET = (124, 92, 255)
TEXT = (230, 237, 243)
MUTED = (139, 148, 158)
CARD = (16, 24, 38)
BG_A = (6, 10, 18)
BG_B = (10, 34, 52)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient_bg(w: int, h: int) -> Image.Image:
    """Diagonal navy→teal gradient with a soft cyan glow top-right."""
    small = Image.new("RGB", (64, 64))
    px = small.load()
    for y in range(64):
        for x in range(64):
            px[x, y] = lerp(BG_A, BG_B, (x + y) / 126)
    bg = small.resize((w, h), Image.Resampling.BICUBIC)
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((int(w * 0.55), -int(h * 0.5), int(w * 1.3), int(h * 0.45)), fill=60)
    glow = glow.filter(ImageFilter.GaussianBlur(w // 12))
    return Image.composite(Image.new("RGB", (w, h), (0, 90, 120)), bg, glow)


def accent_bar(img: Image.Image, h: int) -> None:
    d = ImageDraw.Draw(img)
    for x in range(img.width):
        d.line([(x, 0), (x, h)], fill=lerp(CYAN, VIOLET, x / img.width))


def rounded(im: Image.Image, r: int) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), r, fill=255)
    out = Image.new("RGBA", im.size)
    out.paste(im.convert("RGB"), (0, 0), mask)
    return out


def fit(im: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """Scale to fit the box; small captures (tray menu, dialog, icons) may grow up to 1.8x."""
    k = min(box_w / im.width, box_h / im.height, 1.8)
    return im.resize((round(im.width * k), round(im.height * k)), Image.Resampling.LANCZOS)


def panel(canvas: Image.Image, im: Image.Image, num: str, label: str, x: int, y: int, w: int, h: int, s: float = 1.0) -> None:
    """Framed card: shadow, gradient border, number badge + label, screenshot centred."""
    shadow = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x + 6, y + 10, x + w + 6, y + h + 10), int(18 * s), fill=150)
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(14 * s)))
    canvas.paste(Image.new("RGB", canvas.size, (0, 0, 0)), (0, 0), shadow)

    border = Image.new("RGB", (w, h))
    bd = ImageDraw.Draw(border)
    for i in range(w):
        bd.line([(i, 0), (i, h)], fill=lerp(CYAN, VIOLET, i / w))
    bmask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(bmask).rounded_rectangle((0, 0, w - 1, h - 1), int(18 * s), fill=255)
    canvas.paste(border, (x, y), bmask)
    bw = max(2, int(3 * s))
    ImageDraw.Draw(canvas).rounded_rectangle((x + bw, y + bw, x + w - bw, y + h - bw), int(16 * s), fill=CARD)

    d = ImageDraw.Draw(canvas)
    head = int(58 * s)
    r = int(17 * s)
    cx, cy = x + int(30 * s), y + head // 2 + int(2 * s)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=CYAN)
    d.text((cx, cy), num, fill=(8, 12, 20), font=font(int(17 * s), True), anchor="mm")
    d.text((cx + r + int(12 * s), cy), label, fill=TEXT, font=font(int(24 * s), True), anchor="lm")

    pad = int(16 * s)
    area_w, area_h = w - 2 * pad, h - head - pad
    shot = rounded(fit(im, area_w, area_h), int(10 * s))
    canvas.paste(shot, (x + (w - shot.width) // 2, y + head + (area_h - shot.height) // 2), shot)


def header(canvas: Image.Image, s: float, x: int, y: int, compact: bool = False) -> int:
    d = ImageDraw.Draw(canvas)
    tf = font(int(76 * s), True)
    d.text((x, y), TITLE, fill=CYAN, font=tf)
    tw = d.textlength(TITLE, font=tf)
    pf = font(int(28 * s), True)
    pill = f"v{VERSION}"
    pw = d.textlength(pill, font=pf) + int(36 * s)
    px, py = x + tw + int(24 * s), y + int(22 * s)
    d.rounded_rectangle((px, py, px + pw, py + int(48 * s)), int(24 * s), fill=CYAN)
    d.text((px + pw / 2, py + int(24 * s)), pill, fill=(8, 12, 20), font=pf, anchor="mm")
    y += int(100 * s)
    d.text((x, y), SUBTITLE, fill=TEXT, font=font(int(34 * s)))
    y += int(50 * s)
    if not compact:
        d.text((x, y), HIGHLIGHTS, fill=(160, 220, 240), font=font(int(24 * s)))
        y += int(40 * s)
    d.text((x, y), FOOTER, fill=MUTED, font=font(int(22 * s)))
    return y + int(40 * s)


def main() -> None:
    shots = {f: Image.open(SRC / f) for f, _, _ in PANELS}

    # README hero collage — 3x3 grid (01–09), 4K wide (matches the other repos' HD collages).
    # Panel height follows the Settings window aspect so screens fill their frames.
    s, W = 1.6, 3840
    m, gap = int(56 * s), int(36 * s)
    pw = (W - 2 * m - 2 * gap) // 3
    pad, head = int(16 * s), int(58 * s)
    ph = head + round((pw - 2 * pad) * 1140 / 1920) + pad
    probe = gradient_bg(W, 10)
    top = header(probe, s, int(64 * s), int(40 * s))  # measure header height
    rows = (len(PANELS) + 2) // 3
    H = top + rows * ph + (rows - 1) * gap + m
    c = gradient_bg(W, H)
    accent_bar(c, int(10 * s))
    header(c, s, int(64 * s), int(40 * s))
    for i, (f, n, label) in enumerate(PANELS):
        panel(c, shots[f], n, label, m + (i % 3) * (pw + gap), top + (i // 3) * (ph + gap), pw, ph, s=s)
    collage = SRC / f"collage-v{VERSION}.jpg"
    c.save(collage, "JPEG", quality=94, optimize=True, subsampling=0)

    # Square social — 2x2 of the headline screens
    S = 1080
    q = gradient_bg(S, S)
    accent_bar(q, 8)
    top = header(q, 0.62, 40, 30, compact=True)
    picks = [PANELS[0], PANELS[7], PANELS[4], PANELS[8]]  # 01 Reader, 08 Startup, 05 tray, 09 portable prompt
    m, gap = 36, 24
    pw, ph = (S - 2 * m - gap) // 2, (S - top - m - gap) // 2
    for i, (f, n, label) in enumerate(picks):
        panel(q, shots[f], n, label, m + (i % 2) * (pw + gap), top + (i // 2) * (ph + gap), pw, ph, s=0.62)
    q.save(SRC / "social-collage-1080.jpg", "JPEG", quality=94, optimize=True, subsampling=0)

    # GitHub OG preview 1280x640 — title + wide Reader panel + tray menu
    og = gradient_bg(1280, 640)
    accent_bar(og, 6)
    top = header(og, 0.5, 36, 22, compact=True)
    # Two equal panels sized to the Settings window aspect, centred in the space left.
    m, gap, s = 28, 18, 0.5
    pw = (1280 - 2 * m - gap) // 2
    ph = int(29 * s) + round((pw - 2 * int(8 * s)) * 1140 / 1920) + int(8 * s)
    y = top + max(0, (640 - top - m - ph) // 2)
    for i, (f, n, label) in enumerate((PANELS[0], PANELS[4])):
        panel(og, shots[f], n, label, m + i * (pw + gap), y, pw, ph, s=s)
    og_path = SRC / "social-preview-1280x640.jpg"
    og.save(og_path, "JPEG", quality=94, optimize=True, subsampling=0)

    shutil.copyfile(collage, ROOT / "screenshots" / "collage.jpg")
    shutil.copyfile(og_path, ROOT / "screenshots" / "social-preview.jpg")
    shutil.copyfile(og_path, ROOT / ".github" / "social-preview.jpg")
    og.save(ROOT / ".github" / "social-preview.png", optimize=True)
    print(f"collages OK for v{VERSION} -> {SRC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
