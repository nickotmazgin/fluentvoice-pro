"""Configuration management for FluentVoice Pro."""

import json
from pathlib import Path

from . import voices

APP_DIR = Path.home() / ".fluentvoice"
APP_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = APP_DIR / "config.json"
CACHE_DIR = APP_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_PREFERRED_VOICES = dict(voices.DEFAULT_PREFERRED)

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
    # Update checker (Settings → About & Developer → Updates)
    "check_updates": True,
    "skipped_update_version": "",
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
    # Voices Microsoft retired (e.g. Davis, William AU) → closest current voice.
    cfg["voice"] = voices.current_id(cfg.get("voice", voices.DEFAULT_VOICE))
    cfg["preferred_voices"] = {k: voices.current_id(v) for k, v in cfg["preferred_voices"].items()}
    return cfg

def save_config(cfg: dict):
    """Atomic write (temp file + replace) so the tray and Settings never read a
    half-written config.json (which silently fell back to defaults)."""
    import os
    import time
    tmp = CONFIG_FILE.with_name(f"config.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        for attempt in range(10):
            try:
                os.replace(tmp, CONFIG_FILE)
                return
            except PermissionError:  # another process is reading it right now (Windows)
                time.sleep(0.02 * (attempt + 1))
        os.replace(tmp, CONFIG_FILE)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def factory_reset_config() -> dict:
    """Restore all settings to factory defaults and persist to disk."""
    cfg = DEFAULT_CONFIG.copy()
    cfg["preferred_voices"] = DEFAULT_PREFERRED_VOICES.copy()
    save_config(cfg)
    return cfg
