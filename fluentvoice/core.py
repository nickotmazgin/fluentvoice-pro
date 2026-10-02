"""FluentVoice Pro - Single-Stream Audio & Speech Synthesis Engine
Author: Nick Otmazgin
"""

import sys
import os
import re
import time
import json
import asyncio
import threading
import ctypes
import unicodedata
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from .config import APP_DIR, CACHE_DIR, load_config, save_config
    from . import config as _config
    from . import voices
except (ImportError, ValueError):
    from config import APP_DIR, CACHE_DIR, load_config, save_config
    import config as _config
    import voices

# ---------------------------------------------------------------------------
# Speech diagnostics log (~/.fluentvoice/speech.log). Errors used to be swallowed
# silently, which made "stuck on Synthesizing" impossible to diagnose.
# ---------------------------------------------------------------------------
_log = logging.getLogger("fluentvoice.speech")
if not _log.handlers:
    try:
        _fh = RotatingFileHandler(APP_DIR / "speech.log", maxBytes=256_000, backupCount=1, encoding="utf-8")
        _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] pid=%(process)d (%(threadName)s) %(message)s"))
        _log.addHandler(_fh)
        _log.setLevel(logging.INFO)
        _log.propagate = False
    except Exception:
        _log.addHandler(logging.NullHandler())

_PID = os.getpid()
# Cross-process single-stream signal: the tray daemon and the Settings window are
# separate processes, so a Stop / new Read Aloud in one must be able to cut the other.
STOP_SIGNAL_FILE = APP_DIR / "stop_signal.txt"
_signal_cache = {"pid": 0, "ts": 0.0, "kind": ""}

# Neural synthesis tuning
SYNTH_IDLE_TIMEOUT_SEC = 15.0     # max silence from the TTS service (connect / between chunks)
FIRST_CHUNK_CHARS = 200           # small first chunk => speech starts as soon as possible
SECOND_CHUNK_CHARS = 450
CHUNK_CHARS = 700                 # later chunks; several are prepared in parallel ahead of playback
PREFETCH_WORKERS = 3              # chunks synthesized at the same time
PREFETCH_AHEAD = 4                # never prepare more than this many chunks ahead of the one playing
MAX_SPEAK_CHARS = 100_000         # ~1.5 h of speech; longer texts are read up to here (flood guard)
LOCAL_FIRST_CHUNK_CHARS = 120     # offline HD voices compute on this PC: a shorter first chunk starts sooner
PLAYBACK_STALL_SEC = 8.0          # MCI "playing" but position frozen => treat as stalled
CACHE_MAX_AGE_SEC = 15 * 60

# Global synchronization
_current_generation = 0
_engine_lock = threading.Lock()
_is_speaking = False
_notify_callback = None
_active_requests = 0  # speak requests in flight in this process (incl. synthesis)
_requests_lock = threading.Lock()
_sapi_voice = None  # shared SpVoice so purge hits the speaking instance
_last_notify_key = None
_last_notify_ts = 0.0
_NOTIFY_MIN_INTERVAL_SEC = 1.6

MCI_DEVICE_ALIAS = "FluentVoiceDevice"
# SAPI flags: SVSFlagsAsync=1, SVSFPurgeBeforeSpeak=2
_SVSF_PURGE_ASYNC = 3

def set_notify_callback(cb):
    """Registers a notification handler (e.g. from the system tray daemon)."""
    global _notify_callback
    _notify_callback = cb

def trigger_notification(title: str, message: str, *, force: bool = False, important: bool = False):
    """Sends a notification with tact (dedupe / rate-limit), honouring the notification level.

    important=True: errors and fallbacks, shown on "Important only" and "All".
    important=False: routine per-read info (Speaking…, auto-route, stopped), shown only on "All".
    """
    global _last_notify_key, _last_notify_ts
    level = load_config().get("notification_level", "important")
    if level == "off" or (level == "important" and not important):
        return
    if not _notify_callback:
        return
    now = time.time()
    key = f"{title}|{message}"
    if not force:
        if key == _last_notify_key and (now - _last_notify_ts) < _NOTIFY_MIN_INTERVAL_SEC:
            return
        if (now - _last_notify_ts) < 0.45:
            # Hard ceiling: never stack toasts faster than ~2/sec
            return
    _last_notify_key = key
    _last_notify_ts = now
    try:
        _notify_callback(title, message)
    except Exception:
        pass

def _halt_audio_engines():
    """Stop MCI + purge SAPI without touching generation counters."""
    global _sapi_voice
    winmm = ctypes.windll.winmm
    try:
        winmm.mciSendStringW(f"stop {MCI_DEVICE_ALIAS}", None, 0, None)
        winmm.mciSendStringW(f"close {MCI_DEVICE_ALIAS}", None, 0, None)
    except Exception:
        pass
    try:
        winmm.mciSendStringW("stop all", None, 0, None)
        winmm.mciSendStringW("close all", None, 0, None)
    except Exception:
        pass

    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        import win32com.client
        # Purge the live shared voice first (same COM object that is speaking).
        if _sapi_voice is not None:
            try:
                _sapi_voice.Speak("", _SVSF_PURGE_ASYNC)
            except Exception:
                try:
                    _sapi_voice.Speak("", 2)
                except Exception:
                    pass
        # Backup purge on a fresh instance (covers odd OneCore edge cases).
        try:
            sp = win32com.client.Dispatch("SAPI.SpVoice")
            sp.Speak("", _SVSF_PURGE_ASYNC)
        except Exception:
            pass
    except Exception:
        pass

def _broadcast_signal(kind: str):
    """kind='all' stops every FluentVoice process; kind='claim' stops every *other* process."""
    try:
        STOP_SIGNAL_FILE.write_text(f"{_PID} {time.time():.6f} {kind}", encoding="utf-8")
    except Exception as e:
        _log.warning("could not write stop signal: %s", e)

def _read_signal() -> dict:
    """Tiny file, read on each playback tick (~12/s) — cheap and immune to coarse mtimes."""
    try:
        pid_s, ts_s, kind = STOP_SIGNAL_FILE.read_text(encoding="utf-8").split()[:3]
        _signal_cache.update(pid=int(pid_s), ts=float(ts_s), kind=kind)
    except Exception:
        pass
    return _signal_cache

def _foreign_stop_since(start_ts) -> bool:
    if start_ts is None:
        return False
    sig = _read_signal()
    if sig["ts"] <= start_ts:
        return False
    if sig["kind"] == "all":
        return True
    return sig["kind"] == "claim" and sig["pid"] != _PID

def _should_abort(my_gen: int, start_ts=None) -> bool:
    return my_gen != _current_generation or _foreign_stop_since(start_ts)

SPEAKING_FILE = APP_DIR / "speaking.txt"
_last_heartbeat = 0.0
HEARTBEAT_STALE_SEC = 3.0

def _heartbeat(force: bool = False):
    """Tell other FluentVoice processes we are audibly speaking (throttled to ~1/s)."""
    global _last_heartbeat
    now = time.time()
    if not force and now - _last_heartbeat < 1.0:
        return
    _last_heartbeat = now
    try:
        SPEAKING_FILE.write_text(f"{_PID} {now:.3f}", encoding="utf-8")
    except Exception:
        pass

def _clear_heartbeat():
    global _last_heartbeat
    _last_heartbeat = 0.0
    try:
        pid_s = SPEAKING_FILE.read_text(encoding="utf-8").split()[0]
        if int(pid_s) == _PID:
            SPEAKING_FILE.unlink()
    except Exception:
        pass

def is_any_speaking() -> bool:
    """True if this or another FluentVoice process is speaking or preparing to speak."""
    if _is_speaking or _active_requests > 0:
        return True
    try:
        pid_s, ts_s = SPEAKING_FILE.read_text(encoding="utf-8").split()[:2]
        return time.time() - float(ts_s) < HEARTBEAT_STALE_SEC
    except Exception:
        return False

def stop_all_playback(*, notify: bool = True):
    """Instantly halts any active audio — bumps generation so play loops abort.
    Also signals the other FluentVoice process (tray <-> Settings) to stop."""
    global _is_speaking, _current_generation
    with _engine_lock:
        _current_generation += 1
        _is_speaking = False
    _broadcast_signal("all")
    _clear_heartbeat()
    try:
        SPEAKING_FILE.unlink()
    except Exception:
        pass
    _halt_audio_engines()
    if notify:
        trigger_notification("⏹ Speech stopped", "All FluentVoice speech was stopped.", force=True)

# Unicode blocks of scripts that belong to one language family here.
_SCRIPT_BLOCKS = (
    (0x0900, 0x097F, "hindi"),      # Devanagari (Hindi; Marathi voices share it)
    (0x0980, 0x09FF, "bengali"),
    (0x0A80, 0x0AFF, "gujarati"),
    (0x0B80, 0x0BFF, "tamil"),
    (0x0C00, 0x0C7F, "telugu"),
    (0x0C80, 0x0CFF, "kannada"),
    (0x0D00, 0x0D7F, "malayalam"),
    (0x0E00, 0x0E7F, "thai"),
)


def detect_script(text: str) -> str:
    """Script family from Unicode ranges: hebrew, arabic, cyrillic, cjk (Japanese), chinese,
    korean, hindi (Devanagari), bengali, gujarati, tamil, telugu, kannada, malayalam, thai,
    or latin."""
    if not text:
        return "latin"

    counts = {"hebrew": 0, "arabic": 0, "han": 0, "kana": 0, "korean": 0, "cyrillic": 0, "latin": 0}
    counts.update({fam: 0 for _, _, fam in _SCRIPT_BLOCKS})
    for ch in text:
        code = ord(ch)
        if 0x0900 <= code <= 0x0E7F:
            for lo, hi, fam in _SCRIPT_BLOCKS:
                if lo <= code <= hi:
                    counts[fam] += 1
                    break
        elif 0x0590 <= code <= 0x05FF or 0xFB1D <= code <= 0xFB4F:
            counts["hebrew"] += 1
        elif 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
            counts["arabic"] += 1
        elif 0x3040 <= code <= 0x30FF:
            counts["kana"] += 1
        elif 0x4E00 <= code <= 0x9FFF:
            counts["han"] += 1
        elif 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
            counts["korean"] += 1
        elif 0x0400 <= code <= 0x04FF:
            counts["cyrillic"] += 1
        elif (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A) or (0x00C0 <= code <= 0x024F):
            counts["latin"] += 1

    # Kanji + kana is Japanese; Han characters without kana are Chinese.
    if counts["kana"]:
        counts["cjk"] = counts.pop("kana") + counts.pop("han")
    else:
        counts.pop("kana")
        counts["chinese"] = counts.pop("han")
    top_lang = max(counts, key=counts.get)
    if counts[top_lang] == 0:
        return "latin"
    return top_lang

def _heuristic_latin_language(text: str) -> str:
    """Lightweight Latin-language guess without optional deps."""
    lower = text.lower()
    scores = {
        "spanish": len(re.findall(r"\b(el|la|los|las|que|de|y|en|un|una|es|por|para|con|como|más|también)\b", lower)),
        "french": len(re.findall(r"\b(le|la|les|des|une|est|que|et|dans|pour|avec|ce|qui|pas|plus)\b", lower)),
        "german": len(re.findall(r"\b(der|die|das|und|ist|nicht|ein|eine|mit|auf|für|den|dem|auch)\b", lower)),
        "italian": len(re.findall(r"\b(il|lo|la|gli|le|di|che|e|un|una|per|con|sono|come|più)\b", lower)),
        "english": len(re.findall(r"\b(the|and|is|to|of|in|for|that|with|on|as|are|this|be|from)\b", lower)),
    }
    # Accent boosts
    if re.search(r"[áéíóúñ¿¡]", lower):
        scores["spanish"] += 3
    if re.search(r"[àâçéèêëîïôùûüœæ]", lower):
        scores["french"] += 3
    if re.search(r"[äöüß]", lower):
        scores["german"] += 3
    if re.search(r"[àèéìòù]", lower):
        scores["italian"] += 2

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "english"
    return best

def detect_language(text: str) -> str:
    """Detect language for routing.
    Returns a voices.LANGUAGES key (english, hebrew, arabic, spanish, french, german, italian,
    portuguese, cyrillic = Russian, cjk = Japanese, chinese, korean, hindi, marathi, bengali,
    tamil, telugu, gujarati, kannada, malayalam, thai, icelandic).
    """
    script = detect_script(text)
    if script == "hindi":
        # Hindi and Marathi share Devanagari; the language detector tells them apart.
        try:
            from langdetect import detect, DetectorFactory
            DetectorFactory.seed = 0
            return "marathi" if detect((text or "")[:4000]) == "mr" else "hindi"
        except Exception:
            return "hindi"
    if script != "latin":
        return script

    sample = (text or "")[:4000].strip()
    if not sample:
        return "english"
    # Icelandic: the language detector does not know it; þ and ð are (almost) unique to it.
    thorn_eth = sum(sample.count(ch) for ch in "þÞðÐ")
    if thorn_eth >= 2 or (thorn_eth == 1 and len(sample) < 40):
        return "icelandic"

    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0  # repeatable results for short texts
        code = detect(sample)
        mapping = {
            "en": "english",
            "es": "spanish",
            "fr": "french",
            "de": "german",
            "it": "italian",
            "pt": "portuguese",
            "ru": "cyrillic",
            "he": "hebrew",
            "ar": "arabic",
            "ja": "cjk",
            "zh-cn": "chinese",
            "zh-tw": "chinese",
            "ko": "korean",
            "hi": "hindi", "mr": "marathi", "bn": "bengali", "ta": "tamil", "te": "telugu",
            "gu": "gujarati", "kn": "kannada", "ml": "malayalam", "th": "thai",
        }
        return mapping.get(code, "english")
    except Exception:
        return _heuristic_latin_language(sample)

def resolve_route_voice(detected_lang: str, cfg: dict):
    """Return (voice_id, label) from preferred_voices for a detected language, or (None, '')."""
    prefs = cfg.get("preferred_voices") or {}
    key = detected_lang if detected_lang in prefs else (
        "english" if detected_lang == "latin" else detected_lang
    )
    voice = prefs.get(key)
    return voice, (voices.short_name(voice) if voice else "")


# Latin-script language guesses on a few words are unreliable ("Hola, OK" → Spanish?),
# so switching between two Latin-script voices needs at least this many words.
MIN_WORDS_TO_ROUTE_LATIN = 6


def choose_voice(detected_lang: str, voice: str, cfg: dict, text: str):
    """Auto-route decision. Returns (voice_to_use, routed: bool).

    Keeps the chosen voice when it can read the language itself (same language, or a
    Multilingual voice reading a Latin-script language) or when a short Latin-script
    snippet can't be identified reliably. Otherwise uses the preferred voice for the
    detected language.
    """
    if voices.can_read(voice, detected_lang):
        return voice, False
    if (detected_lang in voices.LATIN_FAMILIES and voices.family_of(voice) in voices.LATIN_FAMILIES
            and len((text or "").split()) < MIN_WORDS_TO_ROUTE_LATIN):
        return voice, False
    route_voice, _ = resolve_route_voice(detected_lang, cfg)
    if not route_voice or route_voice == voice:
        return voice, False
    return route_voice, True

def clean_text_for_speech(text: str) -> str:
    """Advanced text sanitizer:
    - Normalizes Unicode (NFKC)
    - Strips invisible zero-width chars and bidirectional marks (LRM/RLM)
    - Strips non-printable control characters
    - Fixes hyphenated line-breaks common in PDFs and OCR scans
    - Strips code blocks, inline backticks, and markdown syntax
    - Simplifies URLs and links
    - Replaces bullet points and symbols with natural pauses
    - Preserves clean Hebrew text (including optional Niqqud)
    """
    if not text:
        return ""

    # 1. Unicode NFKC normalization (ligatures, full-width, special symbols)
    text = unicodedata.normalize("NFKC", text)

    # 2. Strip invisible zero-width characters and bidirectional marks
    text = re.sub(r"[\u200B-\u200D\uFEFF\u00AD\u200E\u200F\u202A-\u202E\u2066-\u2069]", "", text)

    # 3. Strip non-printable control characters
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

    # 4. PDF / OCR hyphenated line break fix: 'inter-\n\rnational' -> 'international'
    text = re.sub(r"(\b\w+)-[\r\n]+\s*(\w+\b)", r"\1\2", text)

    # 5. Markdown code blocks ```code``` -> [Code block omitted]
    text = re.sub(r"```(?:[\w+-]*)?(?:\r?\n)?[\s\S]*?```", " [Code block omitted] ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 6. Markdown links [title](url) -> title
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 7. Raw URLs -> domain name (e.g. 'link to github.com')
    text = re.sub(r"https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[^\s]*", r" link to \1 ", text)

    # 8. Bullet points and common symbols to comma/pause
    text = re.sub(r"[\u2022\u25AA\u25BA\u2714\u2713\u2705\u274C\u2794\u2192\u25CF]", ", ", text)

    # 9. Collapse repeated decorative punctuation like '====', '----', '****'
    text = re.sub(r"[-=_*~#]{3,}", " ", text)

    # 10. Markdown syntax only: headings, list markers, emphasis, quotes, hashtags.
    #     Symbols inside words and maths stay (snake_case, C#, 2*3, a_b).
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])", r"\1", text)
    text = re.sub(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])", r"\1", text)
    text = re.sub(r"(?<![\w#])#(?=[^\W\d_])", "", text)
    text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)

    # 11. Soft line break merge (PDF wrapping): replace single \n with space, keep double \n
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

    # 12. Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text

def get_clipboard_text() -> str:
    """Safely retrieves text from the Windows clipboard with retries, format checks, and guaranteed unlock."""
    try:
        import win32clipboard
        import win32con
    except ImportError:
        return ""

    # Fast pre-check: if neither Unicode nor ANSI text is on clipboard, do not even open it
    try:
        if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
                return ""
    except Exception:
        pass

    for attempt in range(5):
        opened = False
        try:
            win32clipboard.OpenClipboard()
            opened = True
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                return str(data) if data else ""
            elif win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
                data = win32clipboard.GetClipboardData(win32con.CF_TEXT)
                if isinstance(data, bytes):
                    return data.decode("utf-8", errors="replace")
                return str(data) if data else ""
            return ""
        except Exception:
            if attempt < 4:
                time.sleep(0.02)
        finally:
            if opened:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
    return ""

def clipboard_is_private() -> bool:
    """True when the app that copied asked clipboard tools to ignore it.

    Password managers that support it (e.g. KeePass, KeePassXC) and other apps mark secrets with
    these formats; Windows clipboard history honours them, and so does Auto-Read on Copy,
    so a copied password is never read aloud."""
    try:
        import win32clipboard
    except ImportError:
        return False
    try:
        for name in ("ExcludeClipboardContentFromMonitorProcessing", "Clipboard Viewer Ignore"):
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.RegisterClipboardFormat(name)):
                return True
        fmt = win32clipboard.RegisterClipboardFormat("CanIncludeInClipboardHistory")
        if win32clipboard.IsClipboardFormatAvailable(fmt):
            win32clipboard.OpenClipboard()
            try:
                data = win32clipboard.GetClipboardData(fmt)
            finally:
                win32clipboard.CloseClipboard()
            if isinstance(data, (bytes, bytearray)) and len(data) >= 4 and int.from_bytes(data[:4], "little") == 0:
                return True
    except Exception:
        pass
    return False


# Well-known API key / token shapes (GitHub, OpenAI-style, Slack, AWS, Google, JWT).
_SECRET_TOKEN = re.compile(
    r"^(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"
    r"|xox[abpors]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,})$"
)
_NOT_SECRET = re.compile(r"^(?:https?://|www\.|[A-Za-z]:\\|\\\\|~?/|\.{1,2}/)|^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$", re.I)


def looks_like_secret(text: str) -> bool:
    """True for clipboard text that looks like a password, API key or token.

    Such text should neither be read aloud nor sent to the cloud voice service. Only a single
    string without spaces counts: words, sentences, URLs, e-mail addresses and file paths are
    never treated as secrets."""
    s = (text or "").strip()
    if not (8 <= len(s) <= 200) or any(ch.isspace() for ch in s) or _NOT_SECRET.match(s):
        return False
    if _SECRET_TOKEN.match(s):
        return True
    has_digit = any(ch.isdigit() for ch in s)
    has_alpha = any(ch.isalpha() for ch in s)
    mixed_case = any(ch.islower() for ch in s) and any(ch.isupper() for ch in s)
    has_symbol = any(not ch.isalnum() for ch in s)
    if len(s) <= 64 and has_digit and has_alpha and (mixed_case or has_symbol):
        return True  # typical password: letters + digits + case mix or symbols
    # long random-looking token (hex / base64) of 20+ characters
    return len(s) >= 20 and has_digit and has_alpha and re.fullmatch(r"[A-Za-z0-9+/=_-]+", s) is not None


PRIVATE_SKIP_MESSAGE = ("The clipboard looks like a password or key, so it was not read aloud or sent to the "
                        "voice service. To read it anyway, paste it into the Direct Text Reader.")


def clipboard_text_or_private():
    """(text, private): the clipboard text, and whether it must not be read (marked private by a
    password manager, or looks like a password / key)."""
    text = get_clipboard_text()
    return text, bool(text) and (clipboard_is_private() or looks_like_secret(text))


ONECORE_VOICES = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"


def _offline_voice_tokens():
    """[(description, SAPI token)] for classic SAPI5 voices and modern OneCore voices.

    Windows language packs (Settings → Time & language → Speech) install OneCore voices,
    which SAPI.SpVoice.GetVoices() doesn't list; they still speak fine through SpVoice.
    """
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    out, seen = [], set()
    sp = win32com.client.Dispatch("SAPI.SpVoice")
    lists = [sp.GetVoices()]
    try:
        cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
        cat.SetId(ONECORE_VOICES, False)
        lists.append(cat.EnumerateTokens())
    except Exception:
        pass
    for toks in lists:
        for i in range(toks.Count):
            tk = toks.Item(i)
            desc = tk.GetDescription()
            if desc not in seen:
                seen.add(desc)
                out.append((desc, tk))
    return out


_REGION = {"United States": "US", "United Kingdom": "UK", "Great Britain": "UK", "Australia": "AU",
           "Canada": "CA", "India": "IN", "Ireland": "IE", "Israel": "IL"}


def offline_voice_label(desc: str) -> str:
    """'Microsoft George - English (United Kingdom)' → 'Windows George (English UK)'."""
    m = re.match(r"Microsoft (.+?) - (.+?) \((.+)\)$", desc or "")
    if not m:
        return (desc or "").replace("Microsoft ", "Windows ")
    name, lang, region = m.groups()
    return f"Windows {name} ({lang} {_REGION.get(region, region)})"


def get_installed_sapi_voices() -> list:
    """[(label, description)] for every offline Windows voice (SAPI5 + OneCore)."""
    try:
        voices_ = [(offline_voice_label(d), d) for d, _ in _offline_voice_tokens()]
    except Exception:
        voices_ = []
    return voices_ or [("Windows Zira (English US)", "Zira"), ("Windows Hazel (English UK)", "Hazel")]

def speak_offline_sapi(
    text: str,
    voice_pref: str = "Zira",
    rate_mult: float = 1.0,
    volume: int = 100,
    *,
    start_ts=None,
    my_gen=None,
    interrupt=None,
    progress=None,
) -> bool:
    """Zero-latency offline speech using Windows OneCore / SAPI5. Returns True on success.

    interrupt() → stop early (settings changed); progress["pos"] then holds the character
    offset of the sentence being spoken, so the caller can resume from there."""
    global _is_speaking, _sapi_voice
    if my_gen is None:
        my_gen = _current_generation
    _is_speaking = True
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        import win32com.client
        # Reuse one SpVoice so stop_all_playback() can purge the same instance.
        if _sapi_voice is None:
            _sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
        sp = _sapi_voice
        tokens = _offline_voice_tokens()
        if not tokens:
            return False

        pref = (voice_pref or "").lower()
        clean_pref = pref.replace("sapi-", "").replace("windows ", "")
        chosen = next((tk for d, tk in tokens if d.lower() == pref), None) or \
            next((tk for d, tk in tokens if clean_pref and clean_pref in d.lower()), None)
        if chosen is not None:
            sp.Voice = chosen

        sapi_rate = int(round((rate_mult - 1.0) * 8))
        sp.Rate = max(-10, min(10, sapi_rate))
        sp.Volume = max(0, min(100, int(volume)))
        # Async + short waits so Stop / Emergency Stop can purge mid-utterance. WaitUntilDone
        # is used rather than Status.RunningState, which reads "not speaking" for ~0.2 s after
        # an async Speak: the old loop returned at once while the voice kept talking unseen.
        sp.Speak(text, 1)  # SVSFlagsAsync
        while not sp.WaitUntilDone(80):
            _heartbeat()
            if interrupt is not None and interrupt():
                if progress is not None:
                    try:
                        progress["pos"] = int(sp.Status.InputSentencePosition)
                    except Exception:
                        progress["pos"] = 0
                    progress["interrupted"] = True
                try:
                    sp.Speak("", _SVSF_PURGE_ASYNC)
                except Exception:
                    pass
                return False
            if _should_abort(my_gen, start_ts):
                try:
                    sp.Speak("", _SVSF_PURGE_ASYNC)
                except Exception:
                    pass
                return False
        return not _should_abort(my_gen, start_ts)
    except Exception as e:
        _log.error("offline SAPI error: %s", e)
        return False
    finally:
        _is_speaking = False


def _mci_error(code: int) -> str:
    try:
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.winmm.mciGetErrorStringW(code, buf, 256)
        return buf.value or f"MCI error {code}"
    except Exception:
        return f"MCI error {code}"


def play_audio_file(
    file_path: str,
    generation_id: int,
    volume: int = 100,
    *,
    start_ts=None,
    on_progress=None,
    interrupt=None,
    live_volume=None,
) -> bool:
    """Plays audio through a single dedicated MCI device with instant generation abort.

    Returns True when the file played to the end. Returns False on abort, MCI error,
    a playback stall (MCI reports 'playing' but the position never advances), or when
    interrupt() returns True (settings changed mid-read). live_volume() → current volume.
    """
    global _is_speaking
    if _should_abort(generation_id, start_ts):
        return False

    file_path = os.path.abspath(file_path)
    winmm = ctypes.windll.winmm

    winmm.mciSendStringW(f"stop {MCI_DEVICE_ALIAS}", None, 0, None)
    winmm.mciSendStringW(f"close {MCI_DEVICE_ALIAS}", None, 0, None)

    res_open = winmm.mciSendStringW(f'open "{file_path}" type mpegvideo alias {MCI_DEVICE_ALIAS}', None, 0, None)
    if res_open != 0:
        _log.error("MCI open failed (%s) for %s", _mci_error(res_open), file_path)
        return False

    winmm.mciSendStringW(f"set {MCI_DEVICE_ALIAS} time format milliseconds", None, 0, None)
    # MCI volume is 0–1000
    mci_vol = max(0, min(1000, int(volume) * 10))
    winmm.mciSendStringW(f"setaudio {MCI_DEVICE_ALIAS} volume to {mci_vol}", None, 0, None)

    buf = ctypes.create_unicode_buffer(128)
    length_ms = 0
    if winmm.mciSendStringW(f"status {MCI_DEVICE_ALIAS} length", buf, 128, None) == 0:
        try:
            length_ms = int(buf.value or 0)
        except ValueError:
            length_ms = 0

    _is_speaking = True
    res_play = winmm.mciSendStringW(f"play {MCI_DEVICE_ALIAS}", None, 0, None)
    if res_play != 0:
        _log.error("MCI play failed (%s) for %s", _mci_error(res_play), file_path)
        winmm.mciSendStringW(f"close {MCI_DEVICE_ALIAS}", None, 0, None)
        _is_speaking = False
        return False

    finished = True
    last_pos = -1
    last_move = time.time()
    cur_vol = int(volume)
    while True:
        if _should_abort(generation_id, start_ts):
            finished = False
            break
        if interrupt is not None and interrupt():
            finished = False
            break
        if live_volume is not None:
            v = live_volume()
            if v != cur_vol:
                cur_vol = v
                winmm.mciSendStringW(f"setaudio {MCI_DEVICE_ALIAS} volume to {max(0, min(1000, v * 10))}",
                                     None, 0, None)

        winmm.mciSendStringW(f"status {MCI_DEVICE_ALIAS} mode", buf, 128, None)
        mode = buf.value
        if mode not in ("playing", "seeking"):
            break
        _heartbeat()

        pos = 0
        if winmm.mciSendStringW(f"status {MCI_DEVICE_ALIAS} position", buf, 128, None) == 0:
            try:
                pos = int(buf.value or 0)
            except ValueError:
                pos = 0
        now = time.time()
        if pos != last_pos:
            last_pos = pos
            last_move = now
            if on_progress:
                try:
                    on_progress(pos, length_ms)
                except Exception:
                    pass
        elif now - last_move > PLAYBACK_STALL_SEC:
            _log.error("MCI playback stalled at %d/%d ms (mode=%s) for %s", pos, length_ms, mode, file_path)
            finished = False
            break
        time.sleep(0.08)

    winmm.mciSendStringW(f"stop {MCI_DEVICE_ALIAS}", None, 0, None)
    winmm.mciSendStringW(f"close {MCI_DEVICE_ALIAS}", None, 0, None)
    _is_speaking = False
    return finished


_SENTENCE_END = re.compile(r"[.!?…:;׃۔。！？।॥](?:[\"'”’)\]]*)\s")


def split_for_streaming(text: str, first: int = FIRST_CHUNK_CHARS, rest: int = CHUNK_CHARS,
                        second: int = SECOND_CHUNK_CHARS) -> list:
    """Split text into speakable chunks at sentence boundaries.

    Chunks grow (first → second → rest) so speech starts quickly, and every chunk is small
    enough to be synthesized while the ones before it play: one 1,800-character chunk used
    to take ~50 s to prepare and left a long silence after the first sentence or two.
    """
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    limit = first
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        window = text[:limit]
        cut = -1
        for m in _SENTENCE_END.finditer(window):
            cut = m.end()
        if cut < limit * 0.4:
            comma = max(window.rfind(", "), window.rfind("، "), window.rfind("、"))
            if comma > limit * 0.4:
                cut = comma + 1
        if cut < limit * 0.4:
            space = window.rfind(" ")
            cut = space if space > 0 else limit
        piece = text[:cut].strip()
        if piece:
            chunks.append(piece)
        text = text[cut:].strip()
        limit = second if len(chunks) == 1 else rest
    return chunks


def sentence_start_before(text: str, offset: int) -> int:
    """Index where the sentence containing `offset` begins (0 if none): used to resume after
    a voice change from the sentence that was being spoken, not from the chunk start."""
    best = 0
    for m in _SENTENCE_END.finditer(text[:max(0, offset)]):
        best = m.end()
    return best


async def _synthesize_edge(
    text: str,
    voice: str,
    out_file: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: int = 100,
    *,
    idle_timeout=None,
    abort_check=None,
) -> bool:
    """Stream edge-tts audio into out_file (via a .part temp file). Raises on failure."""
    import edge_tts
    if idle_timeout is None:
        idle_timeout = SYNTH_IDLE_TIMEOUT_SEC
    vol_pct = max(0, min(100, int(volume)))
    edge_vol = f"{vol_pct - 100:+d}%"
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=edge_vol)
    tmp = out_file + ".part"
    got_audio = False
    try:
        stream = comm.stream().__aiter__()
        with open(tmp, "wb") as f:
            while True:
                if abort_check and abort_check():
                    raise asyncio.CancelledError("aborted")
                try:
                    chunk = await asyncio.wait_for(stream.__anext__(), idle_timeout)
                except StopAsyncIteration:
                    break
                if chunk.get("type") == "audio" and chunk.get("data"):
                    f.write(chunk["data"])
                    got_audio = True
        if not got_audio:
            raise RuntimeError("TTS service returned no audio")
        os.replace(tmp, out_file)
        return True
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _synthesize_to_file(text, voice, out_file, *, rate, pitch, volume, abort_check=None):
    """Blocking wrapper. Returns (ok, error_message)."""
    try:
        asyncio.run(_synthesize_edge(
            text, voice, out_file, rate=rate, pitch=pitch, volume=volume, abort_check=abort_check
        ))
        return True, ""
    except asyncio.TimeoutError:
        msg = f"No response from the neural voice service for {SYNTH_IDLE_TIMEOUT_SEC:g}s"
    except asyncio.CancelledError:
        return False, "aborted"
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
    _log.error("neural synthesis failed (voice=%s, %d chars): %s", voice, len(text), msg)
    return False, msg


def _cleanup_stale_cache():
    """Remove leftover audio from crashed/closed sessions (never touches fresh files)."""
    now = time.time()
    try:
        for p in CACHE_DIR.glob("speech_*"):
            try:
                st = p.stat()
                age = now - st.st_mtime
                if age > CACHE_MAX_AGE_SEC or (st.st_size == 0 and age > 60):
                    p.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _voice_family(voice: str) -> str:
    return voices.family_of(voice)


def _local_hd_for(family: str, cfg: dict):
    """A downloaded offline HD voice (Piper / Kokoro) for `family`: the Preferred Voice when it
    is one, else the first downloaded voice of that language. None if there is none."""
    try:
        from . import localtts
    except Exception:
        return None
    pref = (cfg.get("preferred_voices") or {}).get(family)
    if pref and voices.is_local_hd(pref) and localtts.is_usable(pref):
        return pref
    for v in localtts.voices_for(family):
        if localtts.is_usable(v["id"]):
            return v["id"]
    return None


def _windows_voice_for(family: str):
    """An installed Windows offline voice for `family` (its SAPI description), or None."""
    try:
        for _label, desc in get_installed_sapi_voices():
            if voices.family_of(desc) == family:
                return desc
    except Exception:
        pass
    return None


def offline_voice_for(family: str, cfg: dict) -> str:
    """The best voice for `family` that keeps the text on this PC: the Preferred Voice when it is
    offline, an offline HD voice of that language, a Windows voice of that language, else Zira."""
    pref = (cfg.get("preferred_voices") or {}).get(family)
    if pref and voices.is_offline(pref):
        return pref
    return _local_hd_for(family, cfg) or _windows_voice_for(family) or _windows_voice_for("english") or "Zira"

def _emit(on_status, phase: str, **info):
    if on_status is None:
        return
    try:
        on_status(phase, info)
    except Exception:
        pass


def speak_text(raw_text: str, on_status=None, auto_route: bool | None = None, voice: str | None = None) -> dict:
    """Main thread-safe speech dispatcher. Returns status dictionary (see _speak_text_impl).

    auto_route=None follows the Settings switch; False plays exactly the chosen voice
    (the Voice & Speech "Speak Test Text" button).
    """
    global _active_requests
    with _requests_lock:
        _active_requests += 1
    try:
        return _speak_text_impl(raw_text, on_status, auto_route, voice)
    except Exception as e:
        _log.exception("speak_text crashed")
        _emit(on_status, "error", message=f"{type(e).__name__}: {e}")
        return {"status": "error", "mode": "failed", "message": f"{type(e).__name__}: {e}"}
    finally:
        with _requests_lock:
            _active_requests -= 1
        _clear_heartbeat()


class _SettingsWatch:
    """Notices changes made in Settings or the tray while a text is being read."""

    def __init__(self):
        self._mtime = self._stat()
        self._next = 0.0

    @staticmethod
    def _stat():
        try:
            return _config.CONFIG_FILE.stat().st_mtime_ns
        except Exception:
            return 0

    def poll(self):
        """Fresh settings if config.json changed since the last poll (checked ≤ 4×/s), else None."""
        now = time.time()
        if now < self._next:
            return None
        self._next = now + 0.25
        m = self._stat()
        if m == self._mtime:
            return None
        self._mtime = m
        return load_config()


def _local_hd_usable(voice: str) -> bool:
    try:
        from . import localtts
        return localtts.is_usable(voice)
    except Exception:
        return False


def _speech_plan(cfg: dict, text: str, detected_lang: str, auto_route_override) -> dict:
    """Voice and prosody for `text` under the given settings (auto-route applied)."""
    chosen = cfg.get("voice", voices.DEFAULT_VOICE)
    auto_route = cfg.get("auto_route_language", True) if auto_route_override is None else auto_route_override
    voice, routed = choose_voice(detected_lang, chosen, cfg, text) if auto_route else (chosen, False)
    family = voices.family_of(voice)
    if auto_route and detected_lang in voices.LANGUAGES and not voices.can_read(voice, detected_lang):
        family = detected_lang
    elif auto_route and detected_lang in voices.LANGUAGES and voices.is_online(voice) and voices.is_multilingual(voice):
        # A Multilingual online voice keeps Spanish / French / … text itself; an offline replacement
        # (privacy mode) must speak the language of the text, not the online voice's own language.
        family = detected_lang
    private = False
    if voices.is_local_hd(voice) and not _local_hd_usable(voice):
        # Offline HD voice picked but its files were removed (or its engine is missing).
        voice = offline_voice_for(family, cfg) if cfg.get("offline_only") else voices.DEFAULT_PREFERRED.get(
            family, voices.DEFAULT_VOICE)
    if cfg.get("offline_only") and voices.is_online(voice):
        # Privacy mode: the text must not leave this PC, so no online voice is used.
        voice, private = offline_voice_for(family, cfg), True
    rate_mult = float(cfg.get("rate_mult", 1.0))
    pct = int(round((rate_mult - 1.0) * 100))
    pitch_hz = int(cfg.get("pitch_hz", 0))
    return {
        "voice": voice, "chosen": chosen, "routed": routed, "auto_route": auto_route, "private": private,
        "rate_mult": rate_mult, "rate": f"{pct:+d}%", "pitch": f"{pitch_hz:+d}Hz",
        "volume": int(cfg.get("volume", 100)),
    }


def _speak_text_impl(raw_text: str, on_status=None, auto_route_override: bool | None = None,
                     voice_override: str | None = None) -> dict:
    """Speech pipeline.

    on_status(phase, info) is called (from this worker thread) as speech progresses:
      "synthesizing" {voice, parts, routed_from, lang} – contacting the neural engine
                                               (routed_from = the chosen voice when auto-route switched it)
      "speaking"     {voice, mode, part, parts, pos_ms, len_ms}
      "fallback"     {reason}                 – cloud failed, switching to offline voice
      "done" / "aborted" / "error" {message}  – terminal states

    Changing the voice, speed or pitch while a text is being read takes effect at once: the
    reading continues from the current sentence with the new settings. Volume changes apply
    to the audio that is playing.
    """
    global _current_generation, _is_speaking

    cfg = load_config()
    if voice_override:  # Settings → Voice Providers "Try": exactly this voice (privacy mode still applies)
        cfg, auto_route_override = dict(cfg, voice=voice_override), False
    if cfg.get("clean_markdown", True):
        cleaned = clean_text_for_speech(raw_text)
    else:
        cleaned = (raw_text or "").strip()
    if not cleaned:
        cleaned = "Nothing to read. Copy text or click to speak."
    if len(cleaned) > MAX_SPEAK_CHARS:
        cut = sentence_start_before(cleaned, MAX_SPEAK_CHARS) or MAX_SPEAK_CHARS
        _log.warning("text of %d chars trimmed to the first %d", len(cleaned), cut)
        cleaned = cleaned[:cut]
        trigger_notification("📄 Long text", f"Reading the first {MAX_SPEAK_CHARS:,} characters (about 1.5 hours).",
                             force=True, important=True)

    detected_lang = detect_language(cleaned)
    plan = _speech_plan(cfg, cleaned, detected_lang, auto_route_override)
    if plan["routed"]:
        trigger_notification(
            "🌐 Auto-route",
            f"{voices.LANGUAGES.get(detected_lang, detected_lang.title())} text → {voices.short_name(plan['voice'])} "
            f"(your voice: {voices.short_name(plan['chosen'])})",
        )
    elif auto_route_override is None and not plan["auto_route"]:
        # Warn on script/voice mismatch when auto-routing is disabled
        voice_lang = _voice_family(plan["voice"])
        script = detect_script(cleaned)
        if script != "latin" and not voices.can_read(plan["voice"], script):
            names = voices.LANGUAGES
            trigger_notification(
                "ℹ Voice notice",
                f"ℹ️ {names.get(detected_lang, detected_lang)} text detected, but the active voice is "
                f"{names.get(voice_lang, voice_lang)}. Turn on Smart Language Auto-Routing or switch voice.",
                important=True,
            )

    with _engine_lock:
        _current_generation += 1
        my_gen = _current_generation
        _is_speaking = False
    start_ts = time.time()
    # Single stream across processes: cut the tray / Settings window if it is talking.
    _broadcast_signal("claim")
    _heartbeat(force=True)  # other FluentVoice processes see "speaking" while the voice is prepared
    # Halt prior audio without a second generation bump / "stopped" toast.
    _halt_audio_engines()
    _cleanup_stale_cache()

    def aborted() -> bool:
        return _should_abort(my_gen, start_ts)

    def aborted_result():
        _emit(on_status, "aborted", message="Stopped")
        return {"status": "aborted", "mode": "superseded"}

    state = {"plan": plan}
    watch = _SettingsWatch()

    def settings_changed() -> bool:
        """True when the voice / speed / pitch changed; volume is applied live instead."""
        fresh = watch.poll()
        if fresh is None:
            return False
        if voice_override:
            fresh = dict(fresh, voice=voice_override)
        new = _speech_plan(fresh, cleaned, detected_lang, auto_route_override)
        cur = state["plan"]
        cur["volume"] = new["volume"]
        if (new["voice"], new["rate"], new["pitch"]) != (cur["voice"], cur["rate"], cur["pitch"]):
            state["next"] = new
            return True
        return False

    def live_volume() -> int:
        return state["plan"]["volume"]

    snippet = (cleaned[:45] + "...") if len(cleaned) > 45 else cleaned
    text_left = cleaned
    first_round = True
    while True:
        plan = state["plan"]
        voice = plan["voice"]
        offline = voices.is_offline(voice)
        local = voices.is_local_hd(voice)
        _log.info("speak request gen=%d voice=%s engine=%s lang=%s chars=%d%s%s", my_gen, voice,
                  "offline" if offline else ("offline-hd" if local else "neural"), detected_lang, len(text_left),
                  f" routed_from={plan['chosen']}" if plan["routed"] else "",
                  "" if first_round else " (settings changed mid-read)")
        first_round = False

        if offline:
            trigger_notification("🔊 Speaking (offline voice)", f"\"{snippet}\"")
            _emit(on_status, "speaking", voice=voice, mode="offline", part=1, parts=1, pos_ms=0, len_ms=0)
            prog = {}
            ok = speak_offline_sapi(text_left, voice_pref=voice, rate_mult=plan["rate_mult"], volume=plan["volume"],
                                    start_ts=start_ts, my_gen=my_gen, interrupt=settings_changed, progress=prog)
            if aborted():
                return aborted_result()
            if prog.get("interrupted") and "next" in state:
                text_left = text_left[prog.get("pos", 0):].strip()
                state["plan"] = state.pop("next")
                if text_left:
                    continue
                ok = True
            if not ok:
                msg = "No local Windows voices found."
                trigger_notification(
                    "⚠ No offline voices",
                    "No Windows offline voices found. Settings → Voice & Speech → Install Windows Offline Voices.",
                    force=True,
                    important=True,
                )
                _emit(on_status, "error", message=msg)
                return {"status": "error", "mode": "offline", "message": msg}
            _emit(on_status, "done", mode="offline")
            return {"status": "success", "mode": "offline", "message": "Played via Windows offline SAPI"}

        result = _speak_neural(text_left, plan, my_gen=my_gen, start_ts=start_ts, on_status=on_status,
                               aborted=aborted, interrupt=settings_changed, live_volume=live_volume,
                               snippet=snippet, lang=detected_lang, local=local)
        kind = result[0]
        if kind == "aborted" or aborted():
            return aborted_result()
        if kind == "changed" and "next" in state:
            text_left = result[1]
            state["plan"] = state.pop("next")
            if text_left:
                continue
            kind = "done"
        if kind == "done":
            mode = "offline_hd" if local else "neural"
            _emit(on_status, "done", mode=mode, voice=voice)
            return {"status": "success", "mode": mode, "voice": voice}
        break

    # ---- Fallback for whatever has not been spoken yet ------------------------------------
    # Online voice failed -> an offline HD voice of the same language (if downloaded) -> a Windows
    # voice of the same language -> Zira. An offline HD voice that failed goes straight to Windows.
    _, remaining, fail_reason, failed_at, parts = result
    family = detected_lang if detected_lang in voices.LANGUAGES else voices.family_of(voice)
    hd = None if local else _local_hd_for(family, load_config())
    if hd:
        _log.warning("online voice failed at part %d/%d (%s); continuing with offline HD voice %s",
                     failed_at + 1, parts, fail_reason, hd)
        trigger_notification(
            "🌐 Offline HD voice in use",
            f"The online voice is unreachable, so FluentVoice continues with {voices.short_name(hd)} (offline).",
            force=True,
            important=True,
        )
        _emit(on_status, "fallback", reason=fail_reason)
        hd_plan = dict(plan, voice=hd)
        result = _speak_neural(remaining, hd_plan, my_gen=my_gen, start_ts=start_ts, on_status=on_status,
                               aborted=aborted, interrupt=lambda: False, live_volume=live_volume,
                               snippet=snippet, lang=detected_lang, local=True)
        if result[0] == "aborted" or aborted():
            return aborted_result()
        if result[0] == "done":
            _emit(on_status, "done", mode="offline_hd", voice=hd)
            return {"status": "fallback", "mode": "offline_hd", "voice": hd,
                    "message": f"Online voice failed ({fail_reason}), continued offline with {hd}."}
        remaining, fail_reason = result[1], result[2]
    win_voice = _windows_voice_for(family) or "Zira"
    _log.warning("falling back to offline SAPI (%s) at part %d/%d: %s", win_voice, failed_at + 1, parts, fail_reason)
    trigger_notification(
        "🌐 Offline voice in use",
        ("The offline HD voice could not speak, so FluentVoice switched to the Windows voice." if local else
         "The online voice is unreachable, so FluentVoice switched to the offline Windows voice."),
        force=True,
        important=True,
    )
    _emit(on_status, "fallback", reason=fail_reason)
    ok = speak_offline_sapi(remaining, voice_pref=win_voice, rate_mult=plan["rate_mult"], volume=plan["volume"],
                            start_ts=start_ts, my_gen=my_gen)
    if aborted():
        return aborted_result()
    if not ok:
        msg = f"Voice failed ({fail_reason}) and no offline voice is available."
        trigger_notification(
            "⚠ Speech failed",
            "Check your internet connection, or install Windows offline voices.",
            force=True,
            important=True,
        )
        _emit(on_status, "error", message=msg)
        return {"status": "error", "mode": "failed", "message": msg}
    _emit(on_status, "done", mode="offline")
    return {"status": "fallback", "mode": "offline", "message": f"Voice failed ({fail_reason}), fell back to offline."}


def _speak_neural(text, plan, *, my_gen, start_ts=None, on_status=None, aborted, interrupt,
                  live_volume, snippet, lang, local=False):
    """Chunked streaming. Several chunks are synthesized in parallel ahead of the one playing,
    so long texts read without gaps. local=True: an offline HD voice (Piper / Kokoro) computes
    the audio on this PC, one chunk at a time (each already uses several CPU cores).

    Returns ("done",) | ("aborted",) | ("changed", text_still_to_read)
          | ("failed", text_still_to_read, reason, chunk_index, chunk_count)
    """
    voice = plan["voice"]
    chunks = (split_for_streaming(text, first=LOCAL_FIRST_CHUNK_CHARS) if local else split_for_streaming(text)) or [text]
    parts = len(chunks)
    _emit(on_status, "synthesizing", voice=voice, parts=parts,
          routed_from=plan["chosen"] if plan["routed"] else "", lang=lang)

    tag = uuid.uuid4().hex[:8]
    cancel = threading.Event()

    def stop_synth() -> bool:
        return cancel.is_set() or aborted()

    def synth(idx):
        if stop_synth():
            return None, "aborted"
        out = str(CACHE_DIR / f"speech_{_PID}_{my_gen}_{tag}_{idx}.{'wav' if local else 'mp3'}")
        # Synthesized at full level: volume is applied once, at playback (and can change live).
        if local:
            from . import localtts
            ok, err = localtts.synthesize_to_wav(chunks[idx], voice, out, rate_mult=plan["rate_mult"],
                                                 abort_check=stop_synth)
        else:
            ok, err = _synthesize_to_file(chunks[idx], voice, out, rate=plan["rate"], pitch=plan["pitch"],
                                          volume=100, abort_check=stop_synth)
        return (out if ok else None), err

    pool = ThreadPoolExecutor(max_workers=1 if local else PREFETCH_WORKERS, thread_name_prefix="fv-synth")
    futures = {}

    def submit_from(i):
        for j in range(i, min(parts, i + PREFETCH_AHEAD)):
            if j not in futures:
                futures[j] = pool.submit(synth, j)

    def cleanup():
        cancel.set()
        pending = list(futures.values())
        for f in pending:
            f.cancel()
        pool.shutdown(wait=False, cancel_futures=True)

        def remove_outputs():
            for f in pending:
                if f.cancelled():
                    continue
                try:
                    path, _ = f.result(timeout=SYNTH_IDLE_TIMEOUT_SEC + 5)
                except Exception:
                    continue
                _safe_remove(path)
        threading.Thread(target=remove_outputs, name="fv-cleanup", daemon=True).start()

    played_any = False
    try:
        for i in range(parts):
            submit_from(i)
            fut = futures[i]
            while True:
                if aborted():
                    return ("aborted",)
                if interrupt():  # settings changed while this chunk was still being prepared
                    return ("changed", " ".join(chunks[i:]))
                try:
                    path, err = fut.result(timeout=0.2)
                    break
                except FutureTimeout:
                    _heartbeat()
            if path is None:
                if aborted():
                    return ("aborted",)
                return ("failed", " ".join(chunks[i:]), err or "synthesis failed", i, parts)
            if not played_any:
                trigger_notification("🔊 Speaking (offline HD voice)" if local else "🔊 Speaking", f"\"{snippet}\"")
                played_any = True

            pos = {"ms": 0, "len": 0}

            def progress(pos_ms, len_ms, _idx=i):
                pos["ms"], pos["len"] = pos_ms, len_ms
                _emit(on_status, "speaking", voice=voice, mode="offline_hd" if local else "neural",
                      part=_idx + 1, parts=parts,
                      pos_ms=pos_ms, len_ms=len_ms)

            changed = {"flag": False}

            def intr():
                if interrupt():
                    changed["flag"] = True
                    return True
                return False

            progress(0, 0)
            ok = play_audio_file(path, my_gen, volume=live_volume(), start_ts=start_ts, on_progress=progress,
                                 interrupt=intr, live_volume=live_volume)
            _safe_remove(path)
            if aborted():
                return ("aborted",)
            if changed["flag"]:
                frac = pos["ms"] / pos["len"] if pos["len"] else 0.0
                cur = chunks[i]
                off = sentence_start_before(cur, int(len(cur) * frac))
                return ("changed", (cur[off:] + " " + " ".join(chunks[i + 1:])).strip())
            if not ok:
                return ("failed", " ".join(chunks[i:]), "Audio playback failed or stalled (see speech.log)", i, parts)
        return ("done",)
    finally:
        cleanup()


def toggle_speak_or_stop(blocking: bool = False):
    """1-Click Toggle: if any FluentVoice process is speaking, stop everything.
    Otherwise read the clipboard. blocking=True is used by the CLI / Start Menu
    shortcuts, whose short-lived process would otherwise exit and cut the speech."""
    if is_any_speaking():
        stop_all_playback(notify=True)
        return {"status": "stopped"}
    text, private = clipboard_text_or_private()
    if private:
        _log.info("clipboard skipped: private or password-like content (%d chars, not logged)", len(text))
        trigger_notification("🔒 Skipped private text", PRIVATE_SKIP_MESSAGE, force=True, important=True)
        return {"status": "skipped", "reason": "private"}
    if blocking:
        return speak_text(text)
    threading.Thread(target=lambda: speak_text(text), daemon=True).start()
    return {"status": "started"}
