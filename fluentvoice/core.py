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

def clean_text_for_speech(text: str) -> str:
    """Strips Markdown syntax, URLs, and code blocks for fluid, natural reading."""
    if not text:
        return ""
    text = re.sub(r'```[\w]*\n[\s\S]*?\n```', ' [Code block omitted] ', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'#+\s*', '', text)
    text = text.replace('*', '').replace('_', '')
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text).strip()
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
            # Clean label e.g. "Microsoft Zira Desktop - English (United States)" -> "Windows Zira (English US)"
            label = desc.replace("Microsoft ", "Windows ").replace(" Desktop", "")
            label = label.replace(" - English (United States)", " (English US)")
            label = label.replace(" - English (Great Britain)", " (English UK)")
            voices.append((label, desc))
    except Exception:
        pass
    if not voices:
        voices = [("Windows Zira (English US)", "Zira"), ("Windows Hazel (English UK)", "Hazel")]
    return voices

def speak_offline_sapi(text: str, voice_pref: str = "Zira", rate_mult: float = 1.0):
    """Zero-latency offline speech using Windows OneCore / SAPI5."""
    global _is_speaking
    _is_speaking = True
    try:
        import win32com.client
        sp = win32com.client.Dispatch("SAPI.SpVoice")
        # Match preferred voice
        for i in range(sp.GetVoices().Count):
            v = sp.GetVoices().Item(i)
            desc = v.GetDescription()
            clean_pref = voice_pref.lower().replace("sapi-", "").replace("windows ", "")
            if clean_pref in desc.lower():
                sp.Voice = v
                break

        # SAPI Rate ranges from -10 to +10 (0 is normal)
        sapi_rate = int(round((rate_mult - 1.0) * 8))
        sapi_rate = max(-10, min(10, sapi_rate))
        sp.Rate = sapi_rate
        sp.Speak(text, 1)  # 1 for async execution
    except Exception as e:
        print(f"[Offline SAPI] Error: {e}")
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

async def _synthesize_edge(text: str, voice: str, out_file: str, rate: str = "+0%") -> bool:
    try:
        import edge_tts
        comm = edge_tts.Communicate(text, voice, rate=rate)
        await comm.save(out_file)
        return True
    except Exception:
        return False

def speak_text(raw_text: str):
    """Main thread-safe speech dispatcher."""
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

    with _engine_lock:
        _current_generation += 1
        my_gen = _current_generation
        stop_all_playback()

    snippet = (cleaned[:45] + "...") if len(cleaned) > 45 else cleaned
    trigger_notification("FluentVoice Pro", f"🔊 Speaking: \"{snippet}\"")

    # Offline SAPI Mode
    if engine == "offline" or "sapi" in voice.lower():
        speak_offline_sapi(cleaned, voice_pref=voice, rate_mult=rate_mult)
        return

    # Neural Cloud Mode
    out_file = str(CACHE_DIR / f"speech_gen_{my_gen}.mp3")
    try:
        success = asyncio.run(_synthesize_edge(cleaned, voice, out_file, rate=rate_str))
    except Exception:
        success = False

    # Check if superseded
    if my_gen != _current_generation:
        try:
            if os.path.exists(out_file):
                os.remove(out_file)
        except Exception:
            pass
        return

    if success and os.path.exists(out_file):
        play_audio_file(out_file, my_gen)
        try:
            os.remove(out_file)
        except Exception:
            pass
    else:
        # Fallback to local SAPI
        speak_offline_sapi(cleaned, voice_pref="Zira", rate_mult=rate_mult)

def toggle_speak_or_stop():
    """1-Click Toggle: If speaking, stops immediately. Otherwise, reads clipboard."""
    global _is_speaking
    if _is_speaking:
        stop_all_playback()
        trigger_notification("FluentVoice Pro", "⏹️ Speech stopped.")
    else:
        text = get_clipboard_text()
        threading.Thread(target=lambda: speak_text(text), daemon=True).start()
