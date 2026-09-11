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
from pathlib import Path

try:
    from .config import CACHE_DIR, load_config, save_config
except (ImportError, ValueError):
    from config import CACHE_DIR, load_config, save_config

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

def stop_all_playback(*, notify: bool = True):
    """Instantly halts any active audio — bumps generation so play loops abort."""
    global _is_speaking, _current_generation
    with _engine_lock:
        _current_generation += 1
        _is_speaking = False
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

def speak_offline_sapi(text: str, voice_pref: str = "Zira", rate_mult: float = 1.0, volume: int = 100) -> bool:
    """Zero-latency offline speech using Windows OneCore / SAPI5. Returns True on success."""
    global _is_speaking, _sapi_voice, _current_generation
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

        for i in range(sp.GetVoices().Count):
            v = sp.GetVoices().Item(i)
            desc = v.GetDescription()
            clean_pref = voice_pref.lower().replace("sapi-", "").replace("windows ", "")
            if clean_pref in desc.lower():
                sp.Voice = v
                break

        sapi_rate = int(round((rate_mult - 1.0) * 8))
        sapi_rate = max(-10, min(10, sapi_rate))
        sp.Rate = sapi_rate
        sp.Volume = max(0, min(100, int(volume)))
        # Async + pump wait so Stop / Emergency Stop can purge mid-utterance.
        sp.Speak(text, 1)  # SVSFlagsAsync
        while sp.Status.RunningState == 2:  # SPRS_IS_SPEAKING
            if my_gen != _current_generation:
                try:
                    sp.Speak("", _SVSF_PURGE_ASYNC)
                except Exception:
                    pass
                return False
            time.sleep(0.05)
        return my_gen == _current_generation
    except Exception as e:
        print(f"[Offline SAPI] Error: {e}")
        return False
    finally:
        if my_gen == _current_generation:
            _is_speaking = False
        else:
            _is_speaking = False

def play_audio_file(file_path: str, generation_id: int, volume: int = 100) -> bool:
    """Plays audio through a single dedicated MCI device with instant generation abort."""
    global _is_speaking
    if generation_id != _current_generation:
        return False

    file_path = os.path.abspath(file_path)
    winmm = ctypes.windll.winmm

    winmm.mciSendStringW(f"stop {MCI_DEVICE_ALIAS}", None, 0, None)
    winmm.mciSendStringW(f"close {MCI_DEVICE_ALIAS}", None, 0, None)

    res_open = winmm.mciSendStringW(f'open "{file_path}" type mpegvideo alias {MCI_DEVICE_ALIAS}', None, 0, None)
    if res_open != 0:
        return False

    # MCI volume is 0–1000
    mci_vol = max(0, min(1000, int(volume) * 10))
    winmm.mciSendStringW(f"setaudio {MCI_DEVICE_ALIAS} volume to {mci_vol}", None, 0, None)

    _is_speaking = True
    winmm.mciSendStringW(f"play {MCI_DEVICE_ALIAS}", None, 0, None)

    status_buf = ctypes.create_unicode_buffer(128)
    while True:
        if generation_id != _current_generation:
            winmm.mciSendStringW(f"stop {MCI_DEVICE_ALIAS}", None, 0, None)
            winmm.mciSendStringW(f"close {MCI_DEVICE_ALIAS}", None, 0, None)
            _is_speaking = False
            return False

        winmm.mciSendStringW(f"status {MCI_DEVICE_ALIAS} mode", status_buf, 128, None)
        mode = status_buf.value
        if mode not in ("playing", "seeking"):
            break
        time.sleep(0.08)

    winmm.mciSendStringW(f"close {MCI_DEVICE_ALIAS}", None, 0, None)
    _is_speaking = False
    return True

async def _synthesize_edge(
    text: str,
    voice: str,
    out_file: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: int = 100,
) -> bool:
    try:
        import edge_tts
        vol_pct = max(0, min(100, int(volume)))
        edge_vol = f"{vol_pct - 100:+d}%"
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=edge_vol)
        await comm.save(out_file)
        return True
    except Exception:
        return False

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

def speak_text(raw_text: str) -> dict:
    """Main thread-safe speech dispatcher. Returns status dictionary."""
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
    # Halt prior audio without a second generation bump / "stopped" toast.
    _halt_audio_engines()

    snippet = (cleaned[:45] + "...") if len(cleaned) > 45 else cleaned

    # Offline SAPI Mode (skip when auto-route forced a neural voice)
    if (not routed) and (engine == "offline" or "sapi" in voice.lower() or "desktop" in voice.lower()):
        trigger_notification("FluentVoice Pro", f"🔊 Speaking (Offline): \"{snippet}\"")
        ok = speak_offline_sapi(cleaned, voice_pref=voice, rate_mult=rate_mult, volume=volume)
        if my_gen != _current_generation:
            return {"status": "aborted", "mode": "superseded"}
        if not ok:
            trigger_notification(
                "FluentVoice Pro - Voice Alert",
                "⚠️ No local Windows offline voices found. Open Settings -> 'Install Windows Offline Voices' to add one.",
                force=True,
            )
            return {"status": "error", "mode": "offline", "message": "No local Windows voices found."}
        return {"status": "success", "mode": "offline", "message": "Played via Windows offline SAPI"}

    # Neural: synthesize quietly (Settings/tray UI already show status) — toast only when speaking.
    out_file = str(CACHE_DIR / f"speech_gen_{my_gen}.mp3")
    try:
        success = asyncio.run(
            _synthesize_edge(cleaned, voice, out_file, rate=rate_str, pitch=pitch_str, volume=volume)
        )
    except Exception:
        success = False

    # Check if superseded (Stop pressed during synthesis)
    if my_gen != _current_generation:
        try:
            if os.path.exists(out_file):
                os.remove(out_file)
        except Exception:
            pass
        return {"status": "aborted", "mode": "superseded"}

    if success and os.path.exists(out_file):
        trigger_notification("FluentVoice Pro", f"🔊 Speaking: \"{snippet}\"")
        play_audio_file(out_file, my_gen, volume=volume)
        try:
            os.remove(out_file)
        except Exception:
            pass
        if my_gen != _current_generation:
            return {"status": "aborted", "mode": "superseded"}
        return {"status": "success", "mode": "neural", "voice": voice}
    else:
        # Fallback to local SAPI
        trigger_notification(
            "FluentVoice Pro - Network Notice",
            "🌐 Cloud voice unreachable. Automatically switching to offline Windows speech.",
            force=True,
        )
        ok = speak_offline_sapi(cleaned, voice_pref="Zira", rate_mult=rate_mult)
        if my_gen != _current_generation:
            return {"status": "aborted", "mode": "superseded"}
        if not ok:
            trigger_notification(
                "FluentVoice Pro - Speech Alert",
                "⚠️ Speech synthesis failed. Check your internet connection or install local Windows voices.",
                force=True,
            )
            return {"status": "error", "mode": "failed", "message": "Cloud unreachable and no offline voice."}
        return {"status": "fallback", "mode": "offline", "message": "Cloud failed, fell back to offline."}

def toggle_speak_or_stop():
    """1-Click Toggle: If speaking, stops immediately. Otherwise, reads clipboard."""
    global _is_speaking
    if _is_speaking:
        stop_all_playback(notify=True)
    else:
        text = get_clipboard_text()
        threading.Thread(target=lambda: speak_text(text), daemon=True).start()
