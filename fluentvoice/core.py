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

MCI_DEVICE_ALIAS = "FluentVoiceDevice"

def set_notify_callback(cb):
    """Registers a notification handler (e.g. from the system tray daemon)."""
    global _notify_callback
    _notify_callback = cb

def trigger_notification(title: str, message: str):
    """Sends a notification if enabled in config."""
    cfg = load_config()
    if not cfg.get("show_notifications", True):
        return
    if _notify_callback:
        try:
            _notify_callback(title, message)
        except Exception:
            pass

def stop_all_playback():
    """Instantly halts any active audio playback across MCI and SAPI."""
    global _is_speaking
    _is_speaking = False

    winmm = ctypes.windll.winmm
    winmm.mciSendStringW(f"stop {MCI_DEVICE_ALIAS}", None, 0, None)
    winmm.mciSendStringW(f"close {MCI_DEVICE_ALIAS}", None, 0, None)
    winmm.mciSendStringW("stop all", None, 0, None)
    winmm.mciSendStringW("close all", None, 0, None)

    try:
        import win32com.client
        sp = win32com.client.Dispatch("SAPI.SpVoice")
        sp.Speak("", 2)  # SVSFPurgeBeforeSpeak
    except Exception:
        pass

def detect_language(text: str) -> str:
    """Detects predominant language from text using character script distribution.
    Returns: 'hebrew', 'arabic', 'cjk', 'cyrillic', or 'latin'.
    """
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
    text = re.sub(r"```[\w]*\n[\s\S]*?\n```", " [Code block omitted] ", text)
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
    """Safely retrieves text from the Windows clipboard."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return text if text else ""
    except Exception:
        return ""

def get_installed_sapi_voices() -> list:
    """Dynamically enumerates all Windows SAPI/OneCore voices installed on this PC."""
    voices = []
    try:
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

def speak_offline_sapi(text: str, voice_pref: str = "Zira", rate_mult: float = 1.0) -> bool:
    """Zero-latency offline speech using Windows OneCore / SAPI5. Returns True on success."""
    global _is_speaking
    _is_speaking = True
    try:
        import win32com.client
        sp = win32com.client.Dispatch("SAPI.SpVoice")
        if sp.GetVoices().Count == 0:
            _is_speaking = False
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
        sp.Speak(text, 1)  # 1 for async execution
        return True
    except Exception as e:
        print(f"[Offline SAPI] Error: {e}")
        return False
    finally:
        _is_speaking = False

def play_audio_file(file_path: str, generation_id: int) -> bool:
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

async def _synthesize_edge(text: str, voice: str, out_file: str, rate: str = "+0%", pitch: str = "+0Hz") -> bool:
    try:
        import edge_tts
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await comm.save(out_file)
        return True
    except Exception:
        return False

def speak_text(raw_text: str) -> dict:
    """Main thread-safe speech dispatcher. Returns status dictionary."""
    global _current_generation, _is_speaking

    cleaned = clean_text_for_speech(raw_text)
    if not cleaned:
        cleaned = "Nothing to read. Copy text or click to speak."

    cfg = load_config()
    voice = cfg.get("voice", "en-US-AndrewMultilingualNeural")
    engine = cfg.get("engine", "neural")
    
    rate_mult = cfg.get("rate_mult", 1.0)
    pct = int(round((rate_mult - 1.0) * 100))
    rate_str = f"{pct:+d}%" if pct != 0 else "+0%"

    pitch_hz = int(cfg.get("pitch_hz", 0))
    pitch_str = f"{pitch_hz:+d}Hz" if pitch_hz != 0 else "+0Hz"

    # Smart Language Detection & Voice Routing
    detected_lang = detect_language(cleaned)
    auto_route = cfg.get("auto_route_language", True)
    
    if auto_route:
        if detected_lang == "hebrew" and not voice.startswith("he-"):
            voice = "he-IL-AvriNeural"
            trigger_notification("FluentVoice Pro", "🇮🇱 Hebrew detected: Auto-routed to Avri (Hebrew HD)")
        elif detected_lang == "arabic" and not voice.startswith("ar-"):
            voice = "ar-SA-HamedNeural"
            trigger_notification("FluentVoice Pro", "🇸🇦 Arabic detected: Auto-routed to Hamed (Arabic HD)")
        elif detected_lang == "cjk" and not voice.startswith("ja-"):
            voice = "ja-JP-KeitaNeural"
            trigger_notification("FluentVoice Pro", "🇯🇵 Japanese/CJK detected: Auto-routed to Keita (Japanese HD)")
    else:
        if detected_lang == "hebrew" and not voice.startswith("he-"):
            trigger_notification("FluentVoice Pro - Voice Notice", "ℹ️ Hebrew text detected with an English voice active.")

    with _engine_lock:
        _current_generation += 1
        my_gen = _current_generation
        stop_all_playback()

    snippet = (cleaned[:45] + "...") if len(cleaned) > 45 else cleaned

    # Offline SAPI Mode
    if engine == "offline" or "sapi" in voice.lower() or "desktop" in voice.lower():
        trigger_notification("FluentVoice Pro", f"🔊 Speaking (Offline): \"{snippet}\"")
        ok = speak_offline_sapi(cleaned, voice_pref=voice, rate_mult=rate_mult)
        if not ok:
            trigger_notification(
                "FluentVoice Pro - Voice Alert",
                "⚠️ No local Windows offline voices found. Open Settings -> 'Add More Offline Voices' to install one."
            )
            return {"status": "error", "mode": "offline", "message": "No local Windows voices found."}
        return {"status": "success", "mode": "offline", "message": "Played via Windows offline SAPI"}

    # Neural Cloud Mode: Notify user immediately that synthesis has commenced
    trigger_notification("FluentVoice Pro", f"⏳ Synthesizing speech: \"{snippet}\"")

    out_file = str(CACHE_DIR / f"speech_gen_{my_gen}.mp3")
    try:
        success = asyncio.run(_synthesize_edge(cleaned, voice, out_file, rate=rate_str, pitch=pitch_str))
    except Exception:
        success = False

    # Check if superseded
    if my_gen != _current_generation:
        try:
            if os.path.exists(out_file):
                os.remove(out_file)
        except Exception:
            pass
        return {"status": "aborted", "mode": "superseded"}

    if success and os.path.exists(out_file):
        trigger_notification("FluentVoice Pro", f"🔊 Speaking: \"{snippet}\"")
        play_audio_file(out_file, my_gen)
        try:
            os.remove(out_file)
        except Exception:
            pass
        return {"status": "success", "mode": "neural", "voice": voice}
    else:
        # Fallback to local SAPI
        trigger_notification(
            "FluentVoice Pro - Network Notice",
            "🌐 Cloud voice unreachable. Automatically switching to offline Windows speech."
        )
        ok = speak_offline_sapi(cleaned, voice_pref="Zira", rate_mult=rate_mult)
        if not ok:
            trigger_notification(
                "FluentVoice Pro - Speech Alert",
                "⚠️ Speech synthesis failed. Check your internet connection or install local Windows voices."
            )
            return {"status": "error", "mode": "failed", "message": "Cloud unreachable and no offline voice."}
        return {"status": "fallback", "mode": "offline", "message": "Cloud failed, fell back to offline."}

def toggle_speak_or_stop():
    """1-Click Toggle: If speaking, stops immediately. Otherwise, reads clipboard."""
    global _is_speaking
    if _is_speaking:
        stop_all_playback()
        trigger_notification("FluentVoice Pro", "⏹️ Speech stopped.")
    else:
        text = get_clipboard_text()
        threading.Thread(target=lambda: speak_text(text), daemon=True).start()
