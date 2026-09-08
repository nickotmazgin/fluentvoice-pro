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
from .config import CACHE_DIR, load_config, save_config

# Global synchronization
_current_generation = 0
_engine_lock = threading.Lock()
_is_speaking = False

MCI_DEVICE_ALIAS = "FluentVoiceDevice"

def stop_all_playback():
    """Instantly halts any active audio playback across MCI and SAPI."""
    global _is_speaking
    _is_speaking = False

    winmm = ctypes.windll.winmm
    # Hard stop our dedicated device
    winmm.mciSendStringW(f"stop {MCI_DEVICE_ALIAS}", None, 0, None)
    winmm.mciSendStringW(f"close {MCI_DEVICE_ALIAS}", None, 0, None)
    # Stop all generic MCI devices as safety net
    winmm.mciSendStringW("stop all", None, 0, None)
    winmm.mciSendStringW("close all", None, 0, None)

    # Purge SAPI speech queue
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
    # Remove code blocks ```...```
    text = re.sub(r'```[\w]*\n[\s\S]*?\n```', ' [Code block omitted] ', text)
    # Remove inline code `...`
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove markdown links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove markdown headers #, ##, ###
    text = re.sub(r'#+\s*', '', text)
    # Remove asterisks and underscores
    text = text.replace('*', '').replace('_', '')
    # Remove markdown blockquotes
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
    # Collapse multiple whitespaces
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

def speak_offline_sapi(text: str, voice_pref: str = "Zira"):
    """Zero-latency offline speech using Windows OneCore / SAPI5."""
    global _is_speaking
    _is_speaking = True
    try:
        import win32com.client
        sp = win32com.client.Dispatch("SAPI.SpVoice")
        for i in range(sp.GetVoices().Count):
            v = sp.GetVoices().Item(i)
            desc = v.GetDescription()
            if voice_pref.lower() in desc.lower():
                sp.Voice = v
                break
        sp.Rate = 1
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
            # Newer speech superseded this one - abort instantly!
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
    
    # Calculate speech speed / rate
    rate_mult = cfg.get("rate_mult", 1.0)
    pct = int(round((rate_mult - 1.0) * 100))
    rate_str = f"{pct:+d}%" if pct != 0 else "+0%"

    with _engine_lock:
        _current_generation += 1
        my_gen = _current_generation
        stop_all_playback()

    # Offline Mode
    if engine == "offline" or "sapi" in voice.lower():
        speak_offline_sapi(cleaned)
        return

    # Neural Mode
    out_file = str(CACHE_DIR / f"speech_gen_{my_gen}.mp3")
    try:
        success = asyncio.run(_synthesize_edge(cleaned, voice, out_file, rate=rate_str))
    except Exception:
        success = False

    # Check if obsolete
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
        speak_offline_sapi(cleaned)

def toggle_speak_or_stop():
    """1-Click Toggle: If speaking, stops immediately. Otherwise, reads clipboard."""
    global _is_speaking
    if _is_speaking:
        stop_all_playback()
    else:
        text = get_clipboard_text()
        threading.Thread(target=lambda: speak_text(text), daemon=True).start()
