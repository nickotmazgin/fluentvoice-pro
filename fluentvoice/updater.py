"""FluentVoice Pro - Update checker (GitHub Releases).

Privacy: a single anonymous HTTPS GET to the public GitHub Releases API, at most once
per day (or when you click "Check for Updates"). No telemetry, no identifiers.
Can be switched off in Settings → About & Developer → Updates.

Downloads are verified with SHA-256 against the digest GitHub publishes for each
release asset (and/or the release's SHA256SUMS.txt) before they are handed to you.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path

try:
    from . import __version__ as CURRENT_VERSION
    from .config import APP_DIR, load_config, save_config
except (ImportError, ValueError):  # pragma: no cover - script mode
    from fluentvoice import __version__ as CURRENT_VERSION
    from fluentvoice.config import APP_DIR, load_config, save_config

REPO = "nickotmazgin/fluentvoice-pro"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
STATE_FILE = APP_DIR / "update_state.json"
CHECK_INTERVAL_SEC = 24 * 3600
USER_AGENT = f"FluentVoicePro/{CURRENT_VERSION} (+https://github.com/{REPO})"


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------
def parse_version(v: str) -> tuple:
    """'v1.4.17' -> (1, 4, 17, 1); '1.5.0-beta.2' -> (1, 5, 0, 0, 2). Pre-releases sort lower."""
    v = (v or "").strip().lstrip("vV")
    m = re.match(r"^(\d+(?:\.\d+)*)(?:[-.+]?([A-Za-z]+)\.?(\d+)?)?", v)
    if not m:
        return (0,)
    nums = [int(x) for x in m.group(1).split(".")]
    while len(nums) < 3:
        nums.append(0)
    if m.group(2):
        return tuple(nums) + (0, int(m.group(3) or 0))
    return tuple(nums) + (1,)


def is_newer(remote: str, local: str = CURRENT_VERSION) -> bool:
    return parse_version(remote) > parse_version(local)


# ---------------------------------------------------------------------------
# State (last check / cached result / skipped version)
# ---------------------------------------------------------------------------
def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def skip_version(version: str):
    cfg = load_config()
    cfg["skipped_update_version"] = version
    save_config(cfg)


def auto_check_enabled() -> bool:
    return bool(load_config().get("check_updates", True))


def set_auto_check(enabled: bool):
    cfg = load_config()
    cfg["check_updates"] = bool(enabled)
    save_config(cfg)


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
def _http_get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_assets(release: dict) -> list:
    out = []
    for a in release.get("assets", []) or []:
        digest = a.get("digest") or ""
        out.append({
            "name": a.get("name", ""),
            "url": a.get("browser_download_url", ""),
            "size": int(a.get("size") or 0),
            "sha256": digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
        })
    return out


def _summarize(release: dict) -> dict:
    latest = (release.get("tag_name") or "").lstrip("vV")
    return {
        "latest": latest,
        "current": CURRENT_VERSION,
        "url": release.get("html_url") or RELEASES_PAGE,
        "name": release.get("name") or f"FluentVoice Pro {latest}",
        "published": release.get("published_at", ""),
        "notes": (release.get("body") or "").strip(),
        "assets": _pick_assets(release),
    }


def check_for_update(*, force: bool = False, timeout: float = 8.0, fetch=None) -> dict:
    """Returns {"status": "update"|"current"|"skipped"|"disabled"|"cached"|"error", ...}.

    force=True ignores the daily interval, the skipped version and the auto-check switch
    (used by the "Check for Updates" button). `fetch` is injectable for tests.
    """
    state = _load_state()
    now = time.time()
    cfg = load_config()

    if not force:
        if not cfg.get("check_updates", True):
            return {"status": "disabled", "current": CURRENT_VERSION}
        if now - float(state.get("last_check", 0)) < CHECK_INTERVAL_SEC and state.get("result"):
            res = dict(state["result"])
            res["current"] = CURRENT_VERSION
            if is_newer(res.get("latest", "0"), CURRENT_VERSION) and cfg.get("skipped_update_version") != res.get("latest"):
                res["status"] = "update"
            else:
                res["status"] = "cached"
            return res

    try:
        release = (fetch or _http_get_json)(API_LATEST, timeout)
        info = _summarize(release)
    except Exception as e:
        return {"status": "error", "current": CURRENT_VERSION, "message": f"{type(e).__name__}: {e}",
                "url": RELEASES_PAGE}

    state.update(last_check=now, result=info)
    _save_state(state)

    if not is_newer(info["latest"], CURRENT_VERSION):
        return dict(info, status="current")
    if not force and cfg.get("skipped_update_version") == info["latest"]:
        return dict(info, status="skipped")
    return dict(info, status="update")


def preferred_asset(info: dict, portable: bool | None = None) -> dict | None:
    """Pick the source ZIP for Python installs, the portable ZIP for frozen EXE builds."""
    import sys
    if portable is None:
        portable = bool(getattr(sys, "frozen", False))
    assets = [a for a in info.get("assets", []) if a["name"].lower().endswith(".zip")]
    want = "portable" if portable else "-windows.zip"
    for a in assets:
        if want in a["name"].lower():
            return a
    return assets[0] if assets else None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _expected_sha(info: dict, asset: dict, timeout: float) -> str:
    if asset.get("sha256"):
        return asset["sha256"]
    sums = next((a for a in info.get("assets", []) if a["name"].upper().startswith("SHA256SUMS")), None)
    if not sums:
        return ""
    req = urllib.request.Request(sums["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for line in resp.read().decode("utf-8", "replace").splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[-1].lstrip("*") == asset["name"]:
                return parts[0].lower()
    return ""


def download_update(info: dict, dest_dir: Path | None = None, progress=None, timeout: float = 30.0) -> dict:
    """Download the preferred asset to Downloads and verify SHA-256.

    Returns {"ok": bool, "path": str, "sha256": str, "verified": bool, "message": str}.
    A checksum mismatch deletes the file and returns ok=False.
    """
    asset = preferred_asset(info)
    if not asset or not asset.get("url"):
        return {"ok": False, "message": "No downloadable ZIP found on the latest release."}
    dest_dir = Path(dest_dir or (Path.home() / "Downloads"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / asset["name"]
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length") or asset.get("size") or 0)
            done = 0
            while True:
                block = resp.read(1 << 16)
                if not block:
                    break
                f.write(block)
                done += len(block)
                if progress:
                    try:
                        progress(done, total)
                    except Exception:
                        pass
        actual = _sha256_file(tmp)
        expected = ""
        try:
            expected = _expected_sha(info, asset, timeout)
        except Exception:
            expected = ""
        if expected and actual != expected:
            tmp.unlink(missing_ok=True)
            return {"ok": False, "message": "Checksum mismatch — download discarded for your safety.",
                    "sha256": actual}
        os.replace(tmp, dest)
        return {
            "ok": True, "path": str(dest), "sha256": actual, "verified": bool(expected),
            "message": "SHA-256 verified ✓" if expected else "Downloaded (no published checksum to verify)",
        }
    except Exception as e:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return {"ok": False, "message": f"Download failed: {type(e).__name__}: {e}"}


def short_notes(notes: str, max_lines: int = 14) -> str:
    """Trim release notes to the changelog highlights for a popup."""
    text = notes or ""
    if "### Changelog" in text:
        text = text.split("### Changelog", 1)[1]
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip() and not ln.startswith("---")]
    lines = [re.sub(r"\*\*(.+?)\*\*", r"\1", ln) for ln in lines]
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["…"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# One-click install of a *verified* download
# ---------------------------------------------------------------------------
def install_root() -> Path:
    """Folder the running copy lives in (repo/extract root, or the portable EXE folder)."""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_git_checkout(root: Path | None = None) -> bool:
    """Developer installs (git clone) must update with `git pull`, never by overwriting."""
    return (Path(root or install_root()) / ".git").exists()


def _safe_extract(zip_path: Path, dest: Path):
    """Extract a ZIP refusing absolute paths / '..' entries (zip-slip)."""
    import zipfile
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if dest != target and dest not in target.parents:
                raise ValueError(f"Unsafe path in archive: {member.filename}")
        zf.extractall(dest)


def prepare_install(zip_path: str, info: dict, root: Path | None = None) -> dict:
    """Extract a verified release ZIP next to the current install and build the launch command.

    Returns {"ok", "folder", "command", "portable", "message"}. Nothing is executed here.
    """
    root = Path(root or install_root())
    zip_path = Path(zip_path)
    if is_git_checkout(root):
        return {"ok": False, "message": "This copy is a git checkout — update it with `git pull` "
                                        "(then run install.ps1) instead of the one-click installer."}
    portable = "portable" in zip_path.name.lower()
    ver = info.get("latest", "new")
    folder = root.parent / (f"FluentVoicePro-{ver}" if portable else f"fluentvoice-pro-{ver}")
    if folder.exists():
        folder = root.parent / f"{folder.name}-{int(time.time())}"
    try:
        _safe_extract(zip_path, folder)
    except Exception as e:
        return {"ok": False, "message": f"Could not extract update: {type(e).__name__}: {e}"}

    if portable:
        exe = next(folder.rglob("FluentVoicePro.exe"), None)
        if not exe:
            return {"ok": False, "message": "FluentVoicePro.exe not found in the portable ZIP."}
        ps = (
            "Start-Sleep -Seconds 2; "
            "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*.exe' -and "
            "$_.CommandLine -like '*fluentvoice*') -or ($_.Name -eq 'FluentVoicePro.exe' -and "
            f"$_.ExecutablePath -ne '{exe}') }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force "
            "-ErrorAction SilentlyContinue }; "
            f"Start-Process -FilePath '{exe}'"
        )
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", ps]
    else:
        script = next(folder.rglob("install.ps1"), None)
        if not script:
            return {"ok": False, "message": "install.ps1 not found in the source ZIP."}
        # Visible window so the user sees pip/installer progress; install.ps1 stops the old tray itself.
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    return {"ok": True, "folder": str(folder), "command": cmd, "portable": portable,
            "message": f"Extracted to {folder}"}


def launch_install(plan: dict) -> bool:
    import subprocess
    if not plan.get("ok"):
        return False
    flags = 0
    if plan.get("portable"):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(plan["command"], cwd=plan["folder"], creationflags=flags)
    return True
