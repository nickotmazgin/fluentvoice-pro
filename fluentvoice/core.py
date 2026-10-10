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
SYNTH_IDLE_TIMEOUT_SEC = 15.0     # max silence from the TTS service between messages
SYNTH_FIRST_RESPONSE_SEC = 7.0    # a service that hasn't answered by then counts as unreachable
FIRST_CHUNK_CHARS = 200           # small first chunk => speech starts as soon as possible
SECOND_CHUNK_CHARS = 450
CHUNK_CHARS = 700                 # later chunks; several are prepared in parallel ahead of playback
PREFETCH_WORKERS = 3              # chunks synthesized at the same time
PREFETCH_AHEAD = 4                # never prepare more than this many chunks ahead of the one playing
MAX_SPEAK_CHARS = 100_000         # ~1.5 h of speech; longer texts are read up to here (flood guard)
LOCAL_FIRST_CHUNK_CHARS = 120     # offline HD voices compute on this PC: a shorter first chunk starts sooner
LOCAL_SECOND_CHUNK_CHARS = 220    # …and the second must be ready before that short first chunk ends
PLAYBACK_STALL_SEC = 8.0          # MCI "playing" but position frozen => treat as stalled
CACHE_MAX_AGE_SEC = 15 * 60
ONLINE_PAUSE_STEPS_SEC = (60, 300, 900)  # after the online service fails, offline voices are used this long
ONLINE_PROBE_EVERY_SEC = 30       # while a reading continues offline, how often the online voice is retried

# Errors that concern one voice, not the service: another online voice may still work.
_VOICE_ERRORS = ("NoAudioReceived", "No audio was received", "returned no audio")
_online = {"down_until": 0.0, "strikes": 0, "reason": "", "notified": False}

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
        # Poll finely near the end so the next part starts without an extra pause.
        time.sleep(0.02 if length_ms and length_ms - pos < 300 else 0.08)

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
    first_timeout = min(SYNTH_FIRST_RESPONSE_SEC, idle_timeout)
    vol_pct = max(0, min(100, int(volume)))
    edge_vol = f"{vol_pct - 100:+d}%"
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=edge_vol)
    tmp = out_file + ".part"
    got_audio = got_any = False
    try:
        stream = comm.stream().__aiter__()
        with open(tmp, "wb") as f:
            while True:
                if abort_check and abort_check():
                    raise asyncio.CancelledError("aborted")
                try:
                    chunk = await asyncio.wait_for(stream.__anext__(), idle_timeout if got_any else first_timeout)
                except StopAsyncIteration:
                    break
                got_any = True
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
        msg = "The online voice service did not respond in time"
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


def _fallback_voice(family: str, cfg: dict, text: str = "", *, skip_local: bool = False):
    """An offline voice that can read `text` (language `family`): an offline HD voice of that
    language, a Windows voice of that language, else an English Windows voice for Latin-script
    text. None when nothing on this PC can read it: an English voice says nothing at all for
    Hebrew, Thai, Japanese… text, while FluentVoice used to report that it had read it."""
    if not skip_local:
        hd = _local_hd_for(family, cfg)
        if hd:
            return hd
    win = _windows_voice_for(family)
    if win:
        return win
    if (detect_script(text) == "latin") if text.strip() else family == "english":
        return _windows_voice_for("english") or "Zira"
    return None


def offline_voice_for(family: str, cfg: dict, text: str = ""):
    """The best voice for `family` that keeps the text on this PC: the Preferred Voice when it is
    offline, else see _fallback_voice (None when no offline voice can read `text`)."""
    pref = (cfg.get("preferred_voices") or {}).get(family)
    if pref and voices.is_offline(pref):
        return pref
    return _fallback_voice(family, cfg, text)


def voice_display_name(voice: str) -> str:
    """'Ava Multilingual', 'Joe', 'Windows Zira Desktop (English US)'."""
    if voices.is_offline(voice):
        return offline_voice_label(voice) if " - " in voice else f"Windows {voice}"
    return voices.short_name(voice)


def missing_voice_help(family: str) -> str:
    """What to install so that text in `family` can be read without the online voices."""
    name = voices.LANGUAGES.get(family, family.title())
    windows = f"install the Windows {name} voice (Windows Settings → Time & language → Speech → Add voices)"
    try:
        from . import localtts
        has_hd = bool(localtts.voices_for(family))
    except Exception:
        has_hd = False
    if has_hd:
        return f"Download a {name} offline HD voice in Settings → Voice Providers, or {windows}."
    return f"To read {name} offline, {windows}."


def _hd_tip(family: str, voice: str) -> str:
    """A hint to download an offline HD voice when a Windows voice had to stand in."""
    if not voices.is_offline(voice):
        return ""
    try:
        from . import localtts
        if not localtts.voices_for(family):
            return ""
    except Exception:
        return ""
    name = voices.LANGUAGES.get(family, family.title())
    return f" Tip: an offline HD voice for {name} (Settings → Voice Providers) sounds far more natural."


# ---- Online service health ---------------------------------------------------------------
def online_unavailable() -> bool:
    """True while the online voices are paused after the service failed (offline voices are used)."""
    return time.time() < _online["down_until"]


def _mark_online_down(reason: str) -> int:
    """Pause the online voices; each failure in a row pauses them longer. Returns the pause (s)."""
    _online["strikes"] += 1
    pause = ONLINE_PAUSE_STEPS_SEC[min(_online["strikes"], len(ONLINE_PAUSE_STEPS_SEC)) - 1]
    reason = (reason or "").split(", url=")[0]  # aiohttp appends the whole service URL
    _online.update(down_until=time.time() + pause, reason=reason)
    _log.warning("online voices paused for %ds after: %s", pause, reason)
    return pause


def _mark_online_up():
    if _online["strikes"]:
        _log.info("the online voice service responds again")
    _online.update(down_until=0.0, strikes=0, reason="", notified=False)


def _voice_specific(err: str) -> bool:
    return any(s in (err or "") for s in _VOICE_ERRORS)


def _alternative_online_voice(failed: str, family: str, tried: set):
    """Another Microsoft online voice for `family` (Multilingual first), for when one voice
    returns no audio while the service itself works."""
    options = [v for v, _ in voices.voices_for(family) if v != failed and v not in tried]
    options.sort(key=lambda v: not voices.is_multilingual(v))
    return options[0] if options else None


class _OnlineProbe:
    """While a reading continues offline after the online service failed, checks now and then
    (once the pause is over) whether the online voice works again; .back is set when it does."""

    def __init__(self, voice: str):
        self.voice = voice
        self.back = threading.Event()
        self._stop = threading.Event()
        threading.Thread(target=self._run, name="fv-online-probe", daemon=True).start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(max(ONLINE_PROBE_EVERY_SEC, _online["down_until"] - time.time())):
            out = str(CACHE_DIR / f"speech_probe_{_PID}_{uuid.uuid4().hex[:8]}.mp3")
            ok, err = _synthesize_to_file("OK.", self.voice, out, rate="+0%", pitch="+0Hz", volume=100,
                                          abort_check=self._stop.is_set)
            _safe_remove(out)
            if self._stop.is_set():
                return
            if ok:
                _mark_online_up()
                self.back.set()
                return
            _mark_online_down(err)


def preload_offline_voice(cfg: dict | None = None):
    """Load the offline HD voice the next reading would use (the selected voice, or its offline
    replacement in privacy mode / during an outage) in the background. Returns its id or None."""
    cfg = cfg or load_config()
    voice = cfg.get("voice", voices.DEFAULT_VOICE)
    if voices.is_online(voice) and (cfg.get("offline_only") or online_unavailable()):
        voice = _local_hd_for(voices.family_of(voice), cfg)
    if not voice or not voices.is_local_hd(voice):
        return None
    try:
        from . import localtts
        return voice if localtts.preload(voice) else None
    except Exception:
        return None


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
    private = outage = False
    # An offline stand-in must be able to read the text itself (auto-route off: the voice's language may differ).
    text_family = detected_lang if detected_lang in voices.LANGUAGES else family
    if voices.is_local_hd(voice) and not _local_hd_usable(voice):
        # Offline HD voice picked but its files were removed (or its engine is missing).
        voice = offline_voice_for(text_family, cfg, text) if cfg.get("offline_only") else voices.DEFAULT_PREFERRED.get(
            family, voices.DEFAULT_VOICE)
    fallback_from = ""
    if voices.is_online(voice) and (cfg.get("offline_only") or online_unavailable()):
        # Privacy mode: the text must not leave this PC. Outage: the online service just failed.
        private, outage = bool(cfg.get("offline_only")), not cfg.get("offline_only")
        fallback_from = voice if outage else ""
        voice = offline_voice_for(text_family, cfg, text)  # None: no offline voice can read this text
    rate_mult = float(cfg.get("rate_mult", 1.0))
    pct = int(round((rate_mult - 1.0) * 100))
    pitch_hz = int(cfg.get("pitch_hz", 0))
    return {
        "voice": voice, "chosen": chosen, "routed": routed, "auto_route": auto_route, "private": private,
        "outage": outage, "fallback_from": fallback_from, "family": text_family,
        "rate_mult": rate_mult, "rate": f"{pct:+d}%", "pitch": f"{pitch_hz:+d}Hz",
        "volume": int(cfg.get("volume", 100)),
    }


def _no_voice_result(family: str, on_status, reason: str = "") -> dict:
    """Nothing on this PC can read the text: say exactly what to install instead of playing silence."""
    name = voices.LANGUAGES.get(family, family.title())
    help_ = missing_voice_help(family)
    why = "the online voices are unavailable and " if reason else ""
    msg = f"Can't read {name} text: {why}no offline {name} voice is installed. {help_}"
    _log.warning("no voice can read %s text (%s)", family, reason or "offline only")
    trigger_notification(f"⚠ No {name} voice available", help_, force=True, important=True)
    _emit(on_status, "error", message=msg)
    return {"status": "error", "mode": "no_voice", "message": msg}


def _speak_text_impl(raw_text: str, on_status=None, auto_route_override: bool | None = None,
                     voice_override: str | None = None) -> dict:
    """Speech pipeline.

    on_status(phase, info) is called (from this worker thread) as speech progresses:
      "synthesizing" {voice, parts, routed_from, lang} – contacting the neural engine
                                               (routed_from = the chosen voice when auto-route switched it)
      "speaking"     {voice, mode, part, parts, pos_ms, len_ms}
      "fallback"     {reason, voice}          – a voice failed; the reading continues with `voice`
      "done" / "aborted" / "error" {message}  – terminal states

    Changing the voice, speed or pitch while a text is being read takes effect at once: the
    reading continues from the current sentence with the new settings. Volume changes apply
    to the audio that is playing.

    When a voice fails, the rest is read by the next voice that can read it: another online
    voice (that one voice returned no audio), else an offline HD voice, else a Windows voice of
    the text's language. When none can, the reading stops and says what to install. After the
    online service fails it is paused for a while; the reading returns to it once it responds.
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
    if plan["voice"] is None:
        return _no_voice_result(plan["family"], on_status, _online["reason"] if plan["outage"] else "")
    if plan["outage"] and not _online["notified"]:
        _online["notified"] = True
        mins = max(1, round((_online["down_until"] - time.time()) / 60))
        trigger_notification(
            "🌐 Online voices paused",
            f"The online voice service failed just now, so FluentVoice reads offline with "
            f"{voice_display_name(plan['voice'])} and tries online again in about {mins} min."
            + _hd_tip(plan["family"], plan["voice"]),
            important=True,
        )
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

    state = {"plan": plan, "base": plan}  # base: the plan from Settings, before any fallback
    watch = _SettingsWatch()
    probe = {"p": _OnlineProbe(plan["fallback_from"]) if plan["outage"] else None}
    tried = set()
    family = plan["family"]

    def settings_changed() -> bool:
        """True when the voice / speed / pitch changed; volume is applied live instead."""
        fresh = watch.poll()
        if fresh is None:
            return False
        if voice_override:
            fresh = dict(fresh, voice=voice_override)
        new = _speech_plan(fresh, cleaned, detected_lang, auto_route_override)
        state["plan"]["volume"] = new["volume"]
        # During an outage the fresh plan names the offline stand-in, so compare it with what is playing.
        ref = state["plan"] if new["outage"] else state["base"]
        if (new["voice"], new["rate"], new["pitch"]) != (ref["voice"], ref["rate"], ref["pitch"]):
            state["next"] = new
            return True
        return False

    def online_back() -> bool:
        return probe["p"] is not None and probe["p"].back.is_set()

    def interrupt() -> bool:
        return online_back() or settings_changed()

    def adopt_change() -> bool:
        """Switch to the new plan after an interrupt: new settings, or the online voice is back."""
        if "next" in state:
            new = state.pop("next")
        elif online_back():
            probe["p"].stop()
            probe["p"] = None
            fresh = load_config()
            if voice_override:
                fresh = dict(fresh, voice=voice_override)
            new = _speech_plan(fresh, cleaned, detected_lang, auto_route_override)
            if voices.is_online(new["voice"]):
                _log.info("online voice works again; switching back to %s", new["voice"])
                trigger_notification("🌐 Online voice is back",
                                     f"Continuing with {voice_display_name(new['voice'])}.", important=True)
        else:
            return False
        state["plan"] = state["base"] = new
        tried.clear()
        return True

    def live_volume() -> int:
        return state["plan"]["volume"]

    def finish(mode: str, voice: str) -> dict:
        _emit(on_status, "done", mode=mode, voice=voice)
        fb = state["plan"].get("fallback_from")
        if fb:
            return {"status": "fallback", "mode": mode, "voice": voice,
                    "message": f"{voice_display_name(fb)} was unavailable; read with {voice_display_name(voice)}."}
        return {"status": "success", "mode": mode, "voice": voice}

    snippet = (cleaned[:45] + "...") if len(cleaned) > 45 else cleaned
    text_left = cleaned
    first_round = True
    try:
        while True:
            plan = state["plan"]
            voice = plan["voice"]
            if voice is None:
                return _no_voice_result(family, on_status, _online["reason"])
            offline = voices.is_offline(voice)
            local = voices.is_local_hd(voice)
            _log.info("speak request gen=%d voice=%s engine=%s lang=%s chars=%d%s%s", my_gen, voice,
                      "offline" if offline else ("offline-hd" if local else "neural"), detected_lang, len(text_left),
                      f" routed_from={plan['chosen']}" if plan["routed"] else "",
                      "" if first_round else " (continuing)")
            first_round = False

            if offline:
                trigger_notification("🔊 Speaking (offline voice)", f"\"{snippet}\"")
                _emit(on_status, "speaking", voice=voice, mode="offline", part=1, parts=1, pos_ms=0, len_ms=0)
                prog = {}
                ok = speak_offline_sapi(text_left, voice_pref=voice, rate_mult=plan["rate_mult"],
                                        volume=plan["volume"], start_ts=start_ts, my_gen=my_gen,
                                        interrupt=interrupt, progress=prog)
                if aborted():
                    return aborted_result()
                if prog.get("interrupted") and adopt_change():
                    text_left = text_left[prog.get("pos", 0):].strip()
                    if text_left:
                        continue
                    ok = True
                if ok:
                    return finish("offline", voice)
                if plan.get("fallback_from"):
                    msg = f"{voice_display_name(plan['fallback_from'])} failed and the Windows voice could not speak either."
                else:
                    msg = "The Windows voice could not speak (no working Windows voice found)."
                _log.error("%s", msg)
                trigger_notification("⚠ Speech failed", missing_voice_help(family), force=True, important=True)
                _emit(on_status, "error", message=f"{msg} {missing_voice_help(family)}")
                return {"status": "error", "mode": "offline", "message": msg}

            result = _speak_neural(text_left, plan, my_gen=my_gen, start_ts=start_ts, on_status=on_status,
                                   aborted=aborted, interrupt=interrupt, live_volume=live_volume,
                                   snippet=snippet, lang=detected_lang, local=local)
            kind = result[0]
            if kind == "aborted" or aborted():
                return aborted_result()
            if kind == "changed":
                text_left = result[1]
                adopt_change()
                if text_left:
                    continue
                kind = "done"
            if kind == "done":
                return finish("offline_hd" if local else "neural", voice)

            # ---- This voice failed: continue the rest with the next voice that can read it ----------
            _, text_left, err, failed_at, parts, why = result
            err = (err or "").split(", url=")[0]
            _log.warning("%s failed at part %d/%d (%s): %s", voice, failed_at + 1, parts, why, err)
            if why == "voice":
                tried.add(voice)
                alt = _alternative_online_voice(voice, family, tried)
                if alt:
                    trigger_notification(
                        "🗣 Voice switched",
                        f"{voice_display_name(voice)} returned no audio, so FluentVoice continues with "
                        f"{voice_display_name(alt)}.",
                        force=True, important=True)
                    _emit(on_status, "fallback", reason=err, voice=alt)
                    state["plan"] = dict(plan, voice=alt, fallback_from=plan.get("fallback_from") or voice)
                    continue
            if why == "service":
                _mark_online_down(err)
                _online["notified"] = True
                if probe["p"] is None:
                    probe["p"] = _OnlineProbe(voice)
            nxt = _fallback_voice(family, load_config(), text_left, skip_local=local or why == "playback")
            if nxt is None or nxt == voice:
                return _no_voice_result(family, on_status, err)
            name = voice_display_name(nxt)
            if why == "service":
                title, body = ("🌐 Online voice unavailable",
                               f"The online voice service is not responding, so FluentVoice continues offline with "
                               f"{name}. It switches back when the service responds again.")
            elif why == "voice":
                title, body = ("🌐 Online voice unavailable",
                               f"{voice_display_name(voice)} returned no audio and no other online voice is left, "
                               f"so FluentVoice continues offline with {name}.")
            elif why == "playback":
                title, body = ("🔈 Audio problem",
                               f"Audio playback failed or stalled, so FluentVoice continues with {name}. If this "
                               f"repeats, check the output device in Windows sound settings.")
            else:
                title, body = ("⚠ Offline HD voice failed",
                               f"{voice_display_name(voice)} could not speak, so FluentVoice continues with {name}.")
            trigger_notification(title, body + _hd_tip(family, nxt), force=True, important=True)
            _emit(on_status, "fallback", reason=err, voice=nxt)
            state["plan"] = dict(plan, voice=nxt, fallback_from=plan.get("fallback_from") or voice)
    finally:
        if probe["p"] is not None:
            probe["p"].stop()


def _speak_neural(text, plan, *, my_gen, start_ts=None, on_status=None, aborted, interrupt,
                  live_volume, snippet, lang, local=False):
    """Chunked streaming. Several chunks are synthesized in parallel ahead of the one playing,
    so long texts read without gaps. local=True: an offline HD voice (Piper / Kokoro) computes
    the audio on this PC, one chunk at a time (each already uses several CPU cores).

    Returns ("done",) | ("aborted",) | ("changed", text_still_to_read)
          | ("failed", text_still_to_read, reason, chunk_index, chunk_count, why)
    why: "local" (offline HD engine), "voice" (this online voice returned no audio),
         "service" (the online service failed), "playback" (the audio could not be played).
    """
    voice = plan["voice"]
    chunks = (split_for_streaming(text, first=LOCAL_FIRST_CHUNK_CHARS, second=LOCAL_SECOND_CHUNK_CHARS)
              if local else split_for_streaming(text)) or [text]
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
            retried = False
            while True:
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
                if path is not None or local or retried or aborted() or online_unavailable():
                    break
                # A single dropped request is common online: try this part once more before switching voice.
                retried = True
                _log.info("part %d/%d failed (%s); trying it once more", i + 1, parts, err)
                futures[i] = pool.submit(synth, i)
            if path is None:
                if aborted():
                    return ("aborted",)
                why = "local" if local else ("voice" if _voice_specific(err) else "service")
                return ("failed", " ".join(chunks[i:]), err or "synthesis failed", i, parts, why)
            if not local:
                _mark_online_up()
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
                return ("failed", " ".join(chunks[i:]), "Audio playback failed or stalled (see speech.log)", i, parts,
                        "playback")
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
