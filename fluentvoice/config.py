"""Configuration management for FluentVoice Pro."""

import json
from pathlib import Path

APP_DIR = Path.home() / ".fluentvoice"
APP_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = APP_DIR / "config.json"
CACHE_DIR = APP_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_PREFERRED_VOICES = {
    "english": "en-US-AndrewMultilingualNeural",
    "hebrew": "he-IL-AvriNeural",
    "arabic": "ar-SA-HamedNeural",
    "cjk": "ja-JP-KeitaNeural",
    "spanish": "es-ES-AlvaroNeural",
    "french": "fr-FR-HenriNeural",
    "german": "de-DE-ConradNeural",
    "italian": "it-IT-DiegoNeural",
}

DEFAULT_CONFIG = {
    "engine": "neural",  # 'neural' or 'offline'
    "voice": "en-US-AndrewMultilingualNeural",
    "auto_read_copy": False,
    "clean_markdown": True,
    "show_notifications": True,
    "auto_route_language": True,
    "debounce_sec": 0.6,
    "rate_mult": 1.0,
    "pitch_hz": 0,
    "volume": 100,
    "rate": "+0%",
    # Win+Shift+S is reserved by Windows Snipping Tool — use Ctrl+Shift+Space by default.
    "hotkey_enabled": True,
    "hotkey": "ctrl+shift+space",
    "preferred_voices": DEFAULT_PREFERRED_VOICES.copy(),
}

def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    cfg["preferred_voices"] = DEFAULT_PREFERRED_VOICES.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                prefs = saved.pop("preferred_voices", None)
                cfg.update(saved)
                if isinstance(prefs, dict):
                    merged = DEFAULT_PREFERRED_VOICES.copy()
                    merged.update(prefs)
                    cfg["preferred_voices"] = merged
        except Exception:
            pass
    return cfg

def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
