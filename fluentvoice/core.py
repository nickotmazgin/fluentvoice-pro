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
import queue
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from .config import APP_DIR, CACHE_DIR, load_config, save_config
except (ImportError, ValueError):
    from config import APP_DIR, CACHE_DIR, load_config, save_config

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
FIRST_CHUNK_CHARS = 280           # small first chunk => first audio in ~1-2 s even for long texts
CHUNK_CHARS = 1800
PLAYBACK_STALL_SEC = 8.0          # MCI "playing" but position frozen => treat as stalled
CACHE_MAX_AGE_SEC = 15 * 60

# Global synchronization
_current_generation = 0
_engine_lock = threading.Lock()
_is_speaking = False
_notify_callback = None
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

def trigger_notification(title: str, message: str, *, force: bool = False):
    """Sends a notification if enabled — with tact (dedupe / rate-limit)."""
    global _last_notify_key, _last_notify_ts
    cfg = load_config()
    if not cfg.get("show_notifications", True):
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
    """True if this or another FluentVoice process is currently speaking."""
    if _is_speaking:
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
        trigger_notification("FluentVoice Pro", "⏹️ Speech stopped.", force=True)

def detect_script(text: str) -> str:
    """Script family from Unicode ranges: hebrew, arabic, cjk, cyrillic, or latin."""
    if not text:
        return "latin"

    counts = {"hebrew": 0, "arabic": 0, "cjk": 0, "cyrillic": 0, "latin": 0}
    for ch in text:
        code = ord(ch)
        if 0x0590 <= code <= 0x05FF or 0xFB1D <= code <= 0xFB4F:
            counts["hebrew"] += 1
        elif 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
            counts["arabic"] += 1
        elif 0x4E00 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF:
            counts["cjk"] += 1
        elif 0x0400 <= code <= 0x04FF:
            counts["cyrillic"] += 1
        elif (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A) or (0x00C0 <= code <= 0x024F):
            counts["latin"] += 1

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
    Returns: hebrew, arabic, cjk, cyrillic, english, spanish, french, german, italian.
    """
    script = detect_script(text)
    if script != "latin":
        return script

    sample = (text or "")[:4000].strip()
    if not sample:
        return "english"

    try:
        from langdetect import detect
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
            "zh-cn": "cjk",
            "zh-tw": "cjk",
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
    labels = {
        "hebrew": "Hebrew HD",
        "arabic": "Arabic HD",
        "cjk": "Japanese/CJK HD",
        "cyrillic": "Russian HD",
        "spanish": "Spanish HD",
        "french": "French HD",
        "german": "German HD",
        "italian": "Italian HD",
        "portuguese": "Portuguese HD",
        "english": "English HD",
    }
    return voice, labels.get(key, key)

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

    # 10. Markdown syntax symbols
    text = re.sub(r"#+\s*", "", text)
    text = text.replace("*", "").replace("_", "")
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

def get_installed_sapi_voices() -> list:
    """Dynamically enumerates all Windows SAPI/OneCore voices installed on this PC."""
    voices = []
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        import win32com.client
        sp = win32com.client.Dispatch("SAPI.SpVoice")
        for i in range(sp.GetVoices().Count):
            v = sp.GetVoices().Item(i)
            desc = v.GetDescription()
            label = desc.replace("Microsoft ", "Windows ").replace(" Desktop", "")
            label = label.replace(" - English (United States)", " (English US)")
            label = label.replace(" - English (Great Britain)", " (English UK)")
            voices.append((label, desc))
    except Exception:
        pass
    if not voices:
        voices = [("Windows Zira (English US)", "Zira"), ("Windows Hazel (English UK)", "Hazel")]
    return voices

def speak_offline_sapi(
    text: str,
    voice_pref: str = "Zira",
    rate_mult: float = 1.0,
    volume: int = 100,
    *,
    start_ts=None,
    my_gen=None,
) -> bool:
    """Zero-latency offline speech using Windows OneCore / SAPI5. Returns True on success."""
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
        if sp.GetVoices().Count == 0:
            return False

        clean_pref = voice_pref.lower().replace("sapi-", "").replace("windows ", "")
        for i in range(sp.GetVoices().Count):
            v = sp.GetVoices().Item(i)
            if clean_pref in v.GetDescription().lower():
                sp.Voice = v
                break

        sapi_rate = int(round((rate_mult - 1.0) * 8))
        sp.Rate = max(-10, min(10, sapi_rate))
        sp.Volume = max(0, min(100, int(volume)))
        # Async + pump wait so Stop / Emergency Stop can purge mid-utterance.
        sp.Speak(text, 1)  # SVSFlagsAsync
        while sp.Status.RunningState == 2:  # SPRS_IS_SPEAKING
            _heartbeat()
            if _should_abort(my_gen, start_ts):
                try:
                    sp.Speak("", _SVSF_PURGE_ASYNC)
                except Exception:
                    pass
                return False
            time.sleep(0.05)
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
) -> bool:
    """Plays audio through a single dedicated MCI device with instant generation abort.

    Returns True when the file played to the end. Returns False on abort, MCI error,
    or a playback stall (MCI reports 'playing' but the position never advances).
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
    while True:
        if _should_abort(generation_id, start_ts):
            finished = False
            break

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


def split_for_streaming(text: str, first: int = FIRST_CHUNK_CHARS, rest: int = CHUNK_CHARS) -> list:
    """Split text into speakable chunks at sentence boundaries.

    The first chunk is short so audio starts almost immediately; later chunks are
    synthesized in the background while earlier ones play.
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
        for m in re.finditer(r"[.!?…:;׃۔。！？](?:[\"'”’)\]]*)\s", window):
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
        limit = rest
    return chunks


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
    v = (voice or "").lower()
    if v.startswith("he-"):
        return "hebrew"
    if v.startswith("ar-"):
        return "arabic"
    if v.startswith(("ja-", "zh-", "ko-")):
        return "cjk"
    if v.startswith("ru-"):
        return "cyrillic"
    if v.startswith("es-"):
        return "spanish"
    if v.startswith("fr-"):
        return "french"
    if v.startswith("de-"):
        return "german"
    if v.startswith("it-"):
        return "italian"
    if v.startswith("pt-"):
        return "portuguese"
    return "english"

def _emit(on_status, phase: str, **info):
    if on_status is None:
        return
    try:
        on_status(phase, info)
    except Exception:
        pass


def speak_text(raw_text: str, on_status=None) -> dict:
    """Main thread-safe speech dispatcher. Returns status dictionary (see _speak_text_impl)."""
    try:
        return _speak_text_impl(raw_text, on_status)
    except Exception as e:
        _log.exception("speak_text crashed")
        _emit(on_status, "error", message=f"{type(e).__name__}: {e}")
        return {"status": "error", "mode": "failed", "message": f"{type(e).__name__}: {e}"}
    finally:
        _clear_heartbeat()


def _speak_text_impl(raw_text: str, on_status=None) -> dict:
    """Speech pipeline.

    on_status(phase, info) is called (from this worker thread) as speech progresses:
      "synthesizing" {voice, parts}           – contacting the neural engine
      "speaking"     {voice, mode, part, parts, pos_ms, len_ms}
      "fallback"     {reason}                 – cloud failed, switching to offline voice
      "done" / "aborted" / "error" {message}  – terminal states
    """
    global _current_generation, _is_speaking

    cfg = load_config()
    if cfg.get("clean_markdown", True):
        cleaned = clean_text_for_speech(raw_text)
    else:
        cleaned = (raw_text or "").strip()
    if not cleaned:
        cleaned = "Nothing to read. Copy text or click to speak."

    voice = cfg.get("voice", "en-US-AndrewMultilingualNeural")
    engine = cfg.get("engine", "neural")

    rate_mult = cfg.get("rate_mult", 1.0)
    pct = int(round((rate_mult - 1.0) * 100))
    rate_str = f"{pct:+d}%" if pct != 0 else "+0%"

    pitch_hz = int(cfg.get("pitch_hz", 0))
    pitch_str = f"{pitch_hz:+d}Hz" if pitch_hz != 0 else "+0Hz"
    volume = int(cfg.get("volume", 100))

    # Smart Language Detection & Voice Routing
    detected_lang = detect_language(cleaned)
    auto_route = cfg.get("auto_route_language", True)
    routed = False

    if auto_route:
        route_voice, route_label = resolve_route_voice(detected_lang, cfg)
        active_family = _voice_family(voice)
        if route_voice and detected_lang != active_family:
            voice = route_voice
            engine = "neural"
            routed = True
            flags = {
                "hebrew": "🇮🇱",
                "arabic": "🇸🇦",
                "cjk": "🇯🇵",
                "cyrillic": "🇷🇺",
                "spanish": "🇪🇸",
                "french": "🇫🇷",
                "german": "🇩🇪",
                "italian": "🇮🇹",
                "portuguese": "🇧🇷",
                "english": "🇺🇸",
            }
            flag = flags.get(detected_lang, "🌐")
            trigger_notification(
                "FluentVoice Pro",
                f"{flag} {detected_lang.title()} detected: Auto-routed to {route_label}",
            )
    else:
        # Warn on script/voice mismatch when auto-routing is disabled
        voice_lang = _voice_family(voice)
        script = detect_script(cleaned)
        non_latin = script in ("hebrew", "arabic", "cjk")
        if non_latin and script != voice_lang:
            names = {
                "hebrew": "Hebrew",
                "arabic": "Arabic",
                "cjk": "Japanese/CJK",
                "spanish": "Spanish",
                "french": "French",
                "german": "German",
                "italian": "Italian",
                "english": "English",
                "latin": "English/Latin",
            }
            trigger_notification(
                "FluentVoice Pro - Voice Notice",
                f"ℹ️ {names.get(detected_lang, detected_lang)} text detected, but active voice is {names.get(voice_lang, voice_lang)}. Enable Smart Language Auto-Routing or switch voice."
            )

    with _engine_lock:
        _current_generation += 1
        my_gen = _current_generation
        _is_speaking = False
    start_ts = time.time()
    # Single stream across processes: cut the tray / Settings window if it is talking.
    _broadcast_signal("claim")
    # Halt prior audio without a second generation bump / "stopped" toast.
    _halt_audio_engines()
    _cleanup_stale_cache()

    def aborted() -> bool:
        return _should_abort(my_gen, start_ts)

    def aborted_result():
        _emit(on_status, "aborted", message="Stopped")
        return {"status": "aborted", "mode": "superseded"}

    snippet = (cleaned[:45] + "...") if len(cleaned) > 45 else cleaned
    _log.info("speak request gen=%d voice=%s engine=%s lang=%s chars=%d", my_gen, voice, engine, detected_lang, len(cleaned))

    # Offline SAPI Mode (skip when auto-route forced a neural voice)
    if (not routed) and (engine == "offline" or "sapi" in voice.lower() or "desktop" in voice.lower()):
        trigger_notification("FluentVoice Pro", f"🔊 Speaking (Offline): \"{snippet}\"")
        _emit(on_status, "speaking", voice=voice, mode="offline", part=1, parts=1, pos_ms=0, len_ms=0)
        ok = speak_offline_sapi(cleaned, voice_pref=voice, rate_mult=rate_mult, volume=volume,
                                start_ts=start_ts, my_gen=my_gen)
        if aborted():
            return aborted_result()
        if not ok:
            msg = "No local Windows voices found."
            trigger_notification(
                "FluentVoice Pro - Voice Alert",
                "⚠️ No local Windows offline voices found. Open Settings -> 'Install Windows Offline Voices' to add one.",
                force=True,
            )
            _emit(on_status, "error", message=msg)
            return {"status": "error", "mode": "offline", "message": msg}
        _emit(on_status, "done", mode="offline")
        return {"status": "success", "mode": "offline", "message": "Played via Windows offline SAPI"}

    # ---- Neural: chunked streaming pipeline -------------------------------------------
    # Producer synthesizes chunk N+1 while chunk N plays, so a 3,000+ char text starts
    # talking in ~1-2 s instead of waiting for the whole file (which looked "stuck").
    chunks = split_for_streaming(cleaned) or [cleaned]
    parts = len(chunks)
    _emit(on_status, "synthesizing", voice=voice, parts=parts)

    ready = queue.Queue(maxsize=2)
    tag = uuid.uuid4().hex[:8]

    def producer():
        for idx, chunk in enumerate(chunks):
            if aborted():
                break
            out = str(CACHE_DIR / f"speech_{_PID}_{my_gen}_{tag}_{idx}.mp3")
            ok, err = _synthesize_to_file(chunk, voice, out, rate=rate_str, pitch=pitch_str,
                                          volume=volume, abort_check=aborted)
            item = (idx, out if ok else None, err)
            while not aborted():
                try:
                    ready.put(item, timeout=0.2)
                    break
                except queue.Full:
                    continue
            else:
                _safe_remove(out)
                return
            if not ok:
                return
        while not aborted():
            try:
                ready.put(None, timeout=0.2)
                break
            except queue.Full:
                continue

    threading.Thread(target=producer, name="fv-synth", daemon=True).start()

    def drain_and_abort():
        while True:
            try:
                it = ready.get_nowait()
            except queue.Empty:
                break
            if it and it[1]:
                _safe_remove(it[1])
        return aborted_result()

    played_any = False
    failed_at = None
    fail_reason = ""
    while True:
        item = None
        while item is None:
            if aborted():
                return drain_and_abort()
            try:
                item = ready.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:  # end sentinel
                break
        if item is None:
            break
        idx, path, err = item
        if path is None:
            failed_at, fail_reason = idx, err or "synthesis failed"
            break
        if not played_any:
            trigger_notification("FluentVoice Pro", f"🔊 Speaking: \"{snippet}\"")
        played_any = True

        def progress(pos_ms, len_ms, _idx=idx):
            _emit(on_status, "speaking", voice=voice, mode="neural", part=_idx + 1, parts=parts,
                  pos_ms=pos_ms, len_ms=len_ms)

        progress(0, 0)
        ok = play_audio_file(path, my_gen, volume=volume, start_ts=start_ts, on_progress=progress)
        _safe_remove(path)
        if aborted():
            return drain_and_abort()
        if not ok:
            failed_at, fail_reason = idx, "Audio playback failed or stalled (see speech.log)"
            break

    if aborted():
        return drain_and_abort()

    if failed_at is None:
        _emit(on_status, "done", mode="neural", voice=voice)
        return {"status": "success", "mode": "neural", "voice": voice}

    # ---- Fallback to local SAPI for whatever has not been spoken yet -------------------
    remaining = " ".join(chunks[failed_at:])
    _log.warning("falling back to offline SAPI at part %d/%d: %s", failed_at + 1, parts, fail_reason)
    trigger_notification(
        "FluentVoice Pro - Network Notice",
        "🌐 Cloud voice unreachable. Automatically switching to offline Windows speech.",
        force=True,
    )
    _emit(on_status, "fallback", reason=fail_reason)
    ok = speak_offline_sapi(remaining, voice_pref="Zira", rate_mult=rate_mult, volume=volume,
                            start_ts=start_ts, my_gen=my_gen)
    if aborted():
        return aborted_result()
    if not ok:
        msg = f"Cloud voice failed ({fail_reason}) and no offline voice is available."
        trigger_notification(
            "FluentVoice Pro - Speech Alert",
            "⚠️ Speech synthesis failed. Check your internet connection or install local Windows voices.",
            force=True,
        )
        _emit(on_status, "error", message=msg)
        return {"status": "error", "mode": "failed", "message": msg}
    _emit(on_status, "done", mode="offline")
    return {"status": "fallback", "mode": "offline", "message": f"Cloud failed ({fail_reason}), fell back to offline."}


def toggle_speak_or_stop(blocking: bool = False):
    """1-Click Toggle: if any FluentVoice process is speaking, stop everything.
    Otherwise read the clipboard. blocking=True is used by the CLI / Start Menu
    shortcuts, whose short-lived process would otherwise exit and cut the speech."""
    if is_any_speaking():
        stop_all_playback(notify=True)
        return {"status": "stopped"}
    text = get_clipboard_text()
    if blocking:
        return speak_text(text)
    threading.Thread(target=lambda: speak_text(text), daemon=True).start()
    return {"status": "started"}
