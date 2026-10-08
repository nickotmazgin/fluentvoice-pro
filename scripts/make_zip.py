"""Zip a folder's contents for a release: python scripts/make_zip.py <folder> <out.zip>

Entry names use forward slashes, as the ZIP format requires. Compress-Archive in
Windows PowerShell 5.1 writes backslashes, and winget's archive scan rejects those ZIPs.
"""
import sys
import zipfile
from pathlib import Path


def make_zip(folder, out):
    folder, out = Path(folder), Path(out)
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    out.unlink(missing_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            z.write(p, p.relative_to(folder).as_posix())
    return len(files)


if __name__ == "__main__":
    n = make_zip(sys.argv[1], sys.argv[2])
    print(f"Wrote {sys.argv[2]} ({n} files)")
