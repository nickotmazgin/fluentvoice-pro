"""Configuration management for FluentVoice Pro."""

import os
import json
from pathlib import Path

APP_DIR = Path.home() / ".fluentvoice"
APP_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = APP_DIR / "config.json"
CACHE_DIR = APP_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "engine": "neural",  # 'neural' or 'offline'
    "voice": "en-US-AndrewMultilingualNeural",
    "auto_read_copy": False,
    "clean_markdown": True,
    "show_notifications": True,
    "rate_mult": 1.0,
    "volume": 100,
    "rate": "+0%",
}

def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    return cfg

def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
