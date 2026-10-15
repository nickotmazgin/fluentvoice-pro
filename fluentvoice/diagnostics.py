"""Settings → About & Developer → Components & sources.

- components(): what FluentVoice is built from (version, licence, source).
- run_checks(): a live check of every voice provider, the hotkeys, audio output and recent
  errors, each with a plain-language diagnosis, the fix and the alternatives.
- verify_offline_voices() / repair_offline_voices(): hash the downloaded Piper / Kokoro files
  against their pinned SHA-256 and download damaged ones again (official hosts only, via
  localtts.install, which checks every byte again).
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from importlib import metadata

from . import __version__, local_catalog as cat, localtts, voices
from .config import APP_DIR, CACHE_DIR, load_config

LOG_FILE = APP_DIR / "tray.log"
CONNECTIVITY_URL = "http://www.msftconnecttest.com/connecttest.txt"  # Windows' own internet check
RECENT_ERRORS_HOURS = 24

# (name, distribution, module, used for, licence, source)
_COMPONENTS = (
    ("FluentVoice Pro", "", "", "the app", "MIT", "https://github.com/nickotmazgin/fluentvoice-pro"),
    ("edge-tts", "edge-tts", "edge_tts", "Microsoft online voices", "LGPL-3.0", "https://github.com/rany2/edge-tts"),
    ("piper-tts", "piper-tts", "piper", "Piper offline HD voices", "GPL-3.0-or-later",
     "https://github.com/OHF-Voice/piper1-gpl"),
    ("sherpa-onnx", "sherpa-onnx", "sherpa_onnx", "Kokoro offline HD voices", "Apache-2.0",
     "https://github.com/k2-fsa/sherpa-onnx"),
    ("ONNX Runtime", "onnxruntime", "onnxruntime", "runs the offline voice models", "MIT",
     "https://github.com/microsoft/onnxruntime"),
    ("langdetect", "langdetect", "langdetect", "language detection", "Apache-2.0",
     "https://github.com/Mimino666/langdetect"),
    ("pystray", "pystray", "pystray", "tray icon", "LGPL-3.0", "https://github.com/moses-palmer/pystray"),
    ("CustomTkinter", "customtkinter", "customtkinter", "Settings window", "MIT",
     "https://github.com/TomSchimansky/CustomTkinter"),
    ("Pillow", "Pillow", "PIL", "icons, images", "MIT-CMU (HPND)", "https://github.com/python-pillow/Pillow"),
    ("pywin32", "pywin32", "win32api", "Windows voices, shortcuts", "PSF-2.0", "https://github.com/mhammond/pywin32"),
)


def _version(dist: str, module: str) -> str:
    if not dist:
        return __version__
    try:
        return metadata.version(dist)
    except Exception:
        pass
    try:
        mod = __import__(module)
        return str(getattr(mod, "__version__", "") or "included")
    except Exception:
        return "missing"


def components() -> list[dict]:
    return [{"name": n, "version": _version(d, m), "use": u, "licence": lic, "source": src}
            for n, d, m, u, lic, src in _COMPONENTS]


def components_text() -> str:
    lines = ["Components & sources (full list and licence texts: THIRD_PARTY_NOTICES.md)", ""]
    for c in components():
        lines.append(f"• {c['name']} {c['version']} — {c['use']} • {c['licence']} • {c['source']}")
    lines += ["", "Offline voice files are downloaded only from huggingface.co (Piper) and github.com "
                  "(Kokoro, sherpa-onnx releases), and each file must match its pinned SHA-256."]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------- checks
@dataclass
class Finding:
    area: str
    level: str  # "ok", "info", "warn" or "error"
    summary: str
    fixes: list = field(default_factory=list)  # what to do, then the alternatives


ICONS = {"ok": "✔", "info": "ℹ", "warn": "⚠", "error": "✖"}

_OFFLINE_FIXES = [
    "Keep reading without internet: download a Piper or Kokoro offline HD voice "
    "(Voice Providers tab); FluentVoice switches to it by itself when the online voices fail.",
    "Windows offline voices always work as the last fallback (Voice Providers → Windows offline voices).",
]


def internet_ok(timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(CONNECTIVITY_URL, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def classify_online_error(error: str, internet: bool, host: str = "") -> Finding:
    """Turn an online-voice failure into a diagnosis, the fix and the alternatives."""
    e = error or ""
    low = e.lower()
    area = "Microsoft online voices"
    where = host or "the Microsoft voice server"
    if "403" in e or "401" in e:
        return Finding(area, "error",
                       "Microsoft's voice server refused the connection (HTTP 403), on both its classic and its "
                       "newer address. This is a change or outage on Microsoft's side that affects every app "
                       "using these voices, not a fault on this PC.",
                       ["Check that Windows' clock is right (Settings → Time & language → Date & time → "
                        "Set time automatically): the connection key depends on the time.",
                        "Check for Updates (Updates section above): a fixed version follows when the service changes.",
                        *_OFFLINE_FIXES])
    if re.search(r"\b429\b", e) or "too many requests" in low:
        return Finding(area, "warn",
                       "Microsoft is limiting requests for a moment (HTTP 429: too many in a short time). "
                       "Nothing is wrong on this PC.",
                       ["Wait a minute, then press Test providers again.", *_OFFLINE_FIXES])
    if not internet:
        return Finding(area, "error", "This PC is not connected to the internet, so the online voices can't be reached.",
                       ["Connect to Wi-Fi or a network, then press Test providers again.", *_OFFLINE_FIXES])
    if "certificate" in low or "ssl" in low:
        return Finding(area, "error",
                       "The secure connection to the voice server failed. This is usually antivirus HTTPS "
                       "scanning, a company proxy, or a wrong Windows clock.",
                       [f"Allow FluentVoice / {where} in the antivirus' web or HTTPS scanning.",
                        "Check that Windows' clock and time zone are right.", *_OFFLINE_FIXES])
    if "no audio" in low:
        return Finding(area, "warn",
                       "The voice server answered but sent no audio for this voice. Microsoft may have "
                       "retired or paused it.",
                       ["Pick another voice of the same language (Voice & Speech tab).", *_OFFLINE_FIXES])
    if "timeout" in low or "did not respond" in low or "cannot connect" in low or "getaddrinfo" in low \
            or "connect" in low:
        return Finding(area, "error",
                       f"The internet works, but {where} can't be reached. A firewall, proxy, VPN or school / "
                       "work network filter may be blocking it, or the service is down.",
                       [f"Allow {where} in the firewall or proxy, or try another network (or turn the VPN off / on).",
                        "Try again in a few minutes: short outages fix themselves.", *_OFFLINE_FIXES])
    return Finding(area, "error", f"The online voices failed: {e[:160]}",
                   ["Press Test providers again in a minute.", *_OFFLINE_FIXES])


def check_online(cfg: dict, synth=None, internet=internet_ok, host=None) -> Finding:
    area = "Microsoft online voices"
    if cfg.get("offline_only"):
        return Finding(area, "info", "Not tested: Privacy mode (Offline only) is on, so no text goes online.",
                       ["To use them, turn off Voice Providers → Privacy → Offline only."])
    from . import core
    synth = synth or core._synthesize_to_file
    host = host or core.edge_server_host
    voice = cfg.get("voice", "")
    if not voices.is_online(voice):
        voice = voices.DEFAULT_VOICE
    out = str(CACHE_DIR / f"speech_check_{os.getpid()}_{int(time.time() * 1000)}.mp3")
    t0 = time.time()
    try:
        ok, err = synth("Test.", voice, out, rate="+0%", pitch="+0Hz", volume=100)
    finally:
        try:
            os.remove(out)
        except OSError:
            pass
    if ok:
        took = time.time() - t0
        fixes = [] if took < 4 else ["Slow answers delay the start of reading; a wired or faster connection helps."]
        return Finding(area, "ok", f"Working: {voices.short_name(voice)} answered in {took:.1f} s "
                                   f"(server: {host() or 'Microsoft'}).", fixes)
    return classify_online_error(err, internet(), host())


def check_offline_hd(cfg: dict) -> list[Finding]:
    area = "Offline HD voices (Piper / Kokoro)"
    out = []
    for prov in ("piper", "kokoro"):
        if not localtts.engine_available(prov):
            out.append(Finding(area, "error", f"The {localtts.PROVIDER_NAMES[prov]} engine is missing from this copy.",
                               ["Reinstall FluentVoice from the official release (GitHub, winget, Scoop or the "
                                "Microsoft Store).", "From source: pip install -r requirements.txt"]))
    installed = localtts.installed_voices()
    if not installed:
        out.append(Finding(area, "warn", "No offline HD voice is downloaded, so without internet FluentVoice falls "
                                         "back to the more robotic Windows voices.",
                           ["Download one in Voice Providers (Piper: about 63 MB per voice; Kokoro: one 350 MB "
                            "pack with 28 voices). Text then never needs to leave this PC."]))
    else:
        names = ", ".join(sorted({v["name"] for v in installed}))
        out.append(Finding(area, "ok", f"{len(installed)} downloaded: {names}. "
                                       "Use Verify / repair to check their files."))
    family = voices.family_of(cfg.get("voice", ""))
    if installed and voices.is_online(cfg.get("voice", "")) and family in voices.LANGUAGES \
            and not any(v["family"] == family for v in installed) and localtts.voices_for(family):
        out.append(Finding(area, "info", f"No offline HD voice for {voices.language_name(family)} (your voice's "
                                         "language) is downloaded.",
                           [f"Download a Piper or Kokoro voice for {voices.language_name(family)} so an outage or "
                            "Offline only mode keeps the same language in HD."]))
    return out


def check_windows_voices(cfg: dict, tokens=None) -> Finding:
    area = "Windows offline voices"
    try:
        if tokens is None:
            from . import core
            tokens = [d for d, _ in core._offline_voice_tokens()]
    except Exception as e:
        return Finding(area, "error", f"Windows speech could not be opened ({type(e).__name__}).",
                       ["Restart Windows; if it persists, repair Windows speech (Settings → Time & language → Speech)."])
    if not tokens:
        return Finding(area, "error", "No Windows voice is installed, so there is no last-resort fallback.",
                       ["Add one: Settings → Time & language → Speech → Manage voices → Add voices."])
    fams = {voices.family_of(d) for d in tokens}
    family = voices.family_of(cfg.get("voice", ""))
    langs = ", ".join(sorted(voices.language_name(f) for f in fams if f in voices.LANGUAGES))
    if family in voices.LANGUAGES and family not in fams:
        return Finding(area, "info", f"{len(tokens)} installed ({langs}), none for "
                                     f"{voices.language_name(family)}.",
                       [f"Optional: add a {voices.language_name(family)} voice in Settings → Time & language → "
                        "Speech → Add voices, for an offline fallback in that language."])
    return Finding(area, "ok", f"{len(tokens)} installed ({langs}).")


def check_hotkeys(cfg: dict, tray_running: bool, status: dict) -> Finding:
    area = "Tray & hotkeys"
    if not tray_running:
        return Finding(area, "warn", "The tray isn't running, so the hotkey and Auto-Read are off "
                                     "(this window can still read text).",
                       ["Start FluentVoice Pro from the Start menu, or Automation & System → System Tray Daemon."])
    if not cfg.get("hotkey_enabled", True):
        return Finding(area, "info", "The tray is running; the global hotkey is turned off.",
                       ["Turn it on in Automation & System → Global Hotkey."])
    bad = [f"{(status.get(k) or {}).get('chord')} ({(status.get(k) or {}).get('error') or 'not registered'})"
           for k in ("read", "stop") if (status.get(k) or {}).get("chord") and not (status.get(k) or {}).get("ok")]
    if bad:
        return Finding(area, "error", "Another app already uses: " + ", ".join(bad) + ".",
                       ["Pick another chord in Automation & System → Global Hotkey (e.g. ctrl+alt+r).",
                        "Or close the app that owns it, then restart the tray.",
                        "Alternative: turn on Auto-Read and just copy text (Ctrl+C)."])
    chord = (status.get("read") or {}).get("chord") or cfg.get("hotkey", "")
    return Finding(area, "ok", f"Tray running; hotkey {chord} registered.")


def check_audio(num_devices=None) -> Finding:
    area = "Audio output"
    try:
        if num_devices is None:
            import ctypes
            num_devices = ctypes.windll.winmm.waveOutGetNumDevs()
    except Exception:
        return Finding(area, "info", "Could not query the audio devices.")
    if not num_devices:
        return Finding(area, "error", "Windows reports no audio output device, so nothing can be heard.",
                       ["Plug in or turn on speakers / headphones, or pick an output in Settings → System → Sound."])
    return Finding(area, "ok", f"{num_devices} output device{'s' if num_devices != 1 else ''} available.")


_LOG_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ \[(ERROR|WARNING)\] \([^)]*\) (.*)$")


def check_recent_errors(lines=None, now: float | None = None) -> Finding:
    area = "Recent problems (tray log, last 24 h)"
    if lines is None:
        try:
            lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
    now = now or time.time()
    errors, warnings = [], 0
    for line in lines:
        m = _LOG_LINE.match(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        if now - ts > RECENT_ERRORS_HOURS * 3600:
            continue
        if m.group(2) == "ERROR":
            errors.append(m.group(3).split(", url=")[0])
        else:
            warnings += 1
    if not errors:
        extra = f" ({warnings} warning{'s' if warnings != 1 else ''}, e.g. a short online outage)" if warnings else ""
        return Finding(area, "ok", f"No errors{extra}.")
    latest = list(dict.fromkeys(reversed(errors)))[:3]
    summary = f"{len(errors)} error{'s' if len(errors) != 1 else ''}; latest: " + " | ".join(x[:140] for x in latest)
    fixes = []
    if any("403" in x for x in latest):
        fixes.append("403 = the online voice server refused: see Microsoft online voices above.")
    fixes += ["If it keeps happening: Open log folder, then Report Bug / Feedback with tray.log attached "
              "(check it for any text you'd rather not share)."]
    return Finding(area, "warn", summary, fixes)


def run_checks(cfg: dict | None = None, *, tray_running: bool | None = None, hotkey_status: dict | None = None,
               progress=None) -> list[Finding]:
    """Every check, slowest (network) first. progress(text) reports the step in progress."""
    cfg = cfg or load_config()
    if tray_running is None:
        from .lifecycle import is_tray_running
        tray_running = is_tray_running()
    if hotkey_status is None:
        from .hotkeys import read_status
        hotkey_status = read_status()
    steps = (
        ("Testing the Microsoft online voices…", lambda: [check_online(cfg)]),
        ("Checking the offline HD voices…", lambda: check_offline_hd(cfg)),
        ("Checking the Windows voices…", lambda: [check_windows_voices(cfg)]),
        ("Checking the tray and hotkeys…", lambda: [check_hotkeys(cfg, tray_running, hotkey_status)]),
        ("Checking audio output…", lambda: [check_audio()]),
        ("Reading the tray log…", lambda: [check_recent_errors()]),
    )
    out = []
    for text, fn in steps:
        if progress:
            progress(text)
        try:
            out += fn()
        except Exception as e:
            out.append(Finding(text.rstrip("…").replace("Checking ", "").replace("Testing ", ""), "error",
                               f"The check itself failed: {type(e).__name__}: {e}"))
    return out


def report_lines(findings: list[Finding]) -> list[tuple[str, str]]:
    """[(text, level)] for the Settings report: a headline, then each finding with its fixes."""
    worst = max((("ok", "info", "warn", "error").index(f.level) for f in findings), default=0)
    head = {0: "All voice providers work.", 1: "All voice providers work.",
            2: "Working, with warnings: see the suggestions below.",
            3: "Problems found: each one lists what to do and the alternatives."}[worst]
    lines = [(f"{head}  ({datetime.now():%Y-%m-%d %H:%M})", ("ok", "ok", "warn", "error")[worst]), ("", "ok")]
    for f in findings:
        lines.append((f"{ICONS[f.level]} {f.area}: {f.summary}", f.level))
        for fix in f.fixes:
            lines.append((f"     → {fix}", "fix"))
    return lines


# ------------------------------------------------------------------------- verify / repair
def _hash_ok(path, sha256: str, size: int, progress=None) -> str:
    """'' when the file matches, else what is wrong."""
    if not path.exists():
        return "missing"
    if path.stat().st_size != size:
        return "wrong size"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
            if progress:
                progress(len(block))
    return "" if h.hexdigest() == sha256 else "damaged (checksum mismatch)"


def _downloaded_items() -> list[dict]:
    items = []
    for model in cat.PIPER_MODELS:
        if (localtts.PIPER_DIR / model).exists():
            vs = [v for v in localtts.VOICES if v.get("model") == model]
            if vs:
                files = [(dst, sha, size) for _url, sha, size, dst in localtts._piper_files(model)]
                items.append({"key": model, "voice": vs[0]["id"], "name": " / ".join(v["name"] for v in vs)
                              + f" (Piper, {voices.language_name(vs[0]['family'])})", "files": files})
    folder = localtts._kokoro_folder()
    if folder.exists():
        files = [(folder / n, sha, size) for n, (sha, size) in cat.KOKORO_PACK["files"].items()]
        items.append({"key": "kokoro", "voice": next(v["id"] for v in localtts.VOICES if v["provider"] == "kokoro"),
                      "name": "Kokoro pack (28 voices)", "files": files})
    return items


def verify_offline_voices(progress=None) -> list[dict]:
    """Hash every downloaded offline voice file. progress(done_bytes, total_bytes).
    Returns [{"key", "voice", "name", "ok", "problem", "size"}]."""
    items = _downloaded_items()
    total = sum(size for it in items for _p, _s, size in it["files"]) or 1
    done = [0]

    def step(n):
        done[0] += n
        if progress:
            progress(done[0], total)

    out = []
    for it in items:
        problems = []
        for path, sha, size in it["files"]:
            p = _hash_ok(path, sha, size, step)
            if p:
                problems.append(f"{path.name}: {p}")
        out.append({"key": it["key"], "voice": it["voice"], "name": it["name"], "ok": not problems,
                    "problem": "; ".join(problems), "size": localtts.download_size(it["voice"])})
    return out


def repair_offline_voices(bad: list[dict], progress=None, cancel=None) -> list[tuple[str, bool, str]]:
    """Delete and download again each damaged voice (official hosts + pinned SHA-256 only).
    Returns [(name, ok, message)]."""
    out = []
    for item in bad:
        voice = item["voice"]
        localtts.remove(voice)
        if localtts.is_installed(voice):
            out.append((item["name"], False, "its files are in use: quit the tray (tray menu → Exit), then repair again"))
            continue
        try:
            localtts.install(voice, progress=progress, cancel=cancel)
            out.append((item["name"], True, "downloaded again and verified"))
        except localtts.Cancelled:
            out.append((item["name"], False, "cancelled"))
            break
        except Exception as e:
            out.append((item["name"], False, f"{e} (check the internet connection and try again)"))
    return out
