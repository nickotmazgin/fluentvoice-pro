"""Prepare the MSIX package folder for the Microsoft Store build.

Copies the PyInstaller one-folder build (dist/FluentVoicePro) to build/msix, writes the tile
images from assets/icon.png and fills packaging/AppxManifest.xml.in with the version.
scripts/build_msix.ps1 then packs the folder with makeappx (Windows SDK).

Usage: python scripts/make_msix_layout.py [--src dist/FluentVoicePro] [--out build/msix]
"""
import argparse
import re
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

# (file name, width, height): the logos the manifest references, plus the unplated
# taskbar icon size Windows prefers for desktop apps.
TILES = [
    ("StoreLogo.png", 50, 50),
    ("Square44x44Logo.png", 44, 44),
    ("Square44x44Logo.targetsize-44_altform-unplated.png", 44, 44),
    ("Square44x44Logo.targetsize-256_altform-unplated.png", 256, 256),
    ("Square150x150Logo.png", 150, 150),
    ("Wide310x150Logo.png", 310, 150),
]


def msix_version() -> str:
    ver = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "fluentvoice" / "__init__.py").read_text()).group(1)
    nums = [int(x) for x in re.findall(r"\d+", ver)[:3]]
    return ".".join(str(n) for n in nums + [0])  # MSIX needs four parts, the last one 0 for the Store


def tile(icon: Image.Image, w: int, h: int) -> Image.Image:
    side = min(w, h)
    pad = round(side * 0.08) if w == h and side >= 150 else 0
    img = icon.resize((side - 2 * pad, side - 2 * pad), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2), img)
    return canvas


def build(src: Path, out: Path) -> Path:
    if not (src / "FluentVoicePro.exe").exists():
        raise SystemExit(f"missing {src / 'FluentVoicePro.exe'}: run scripts/build_exe.ps1 first")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)
    (out / "README-PORTABLE.txt").unlink(missing_ok=True)  # portable-only instructions (shortcuts, Unblock)
    assets = out / "Assets"
    assets.mkdir()
    icon = Image.open(ROOT / "assets" / "icon.png").convert("RGBA")
    for name, w, h in TILES:
        tile(icon, w, h).save(assets / name)
    manifest = (ROOT / "packaging" / "AppxManifest.xml.in").read_text(encoding="utf-8")
    (out / "AppxManifest.xml").write_text(manifest.replace("{VERSION}", msix_version()), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "dist" / "FluentVoicePro"))
    ap.add_argument("--out", default=str(ROOT / "build" / "msix"))
    a = ap.parse_args()
    print(build(Path(a.src), Path(a.out)))
