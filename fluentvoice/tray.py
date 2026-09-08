"""FluentVoice Pro - Modern Windows 11 Fluent System Tray Suite
Author: Nick Otmazgin
"""

import sys
import os
import time
import json
import threading
import ctypes
import webbrowser
from pathlib import Path
from PIL import Image
import pystray
from pystray import MenuItem as item

from .config import load_config, save_config
from . import core

# Windows Single-Instance Mutex
ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\NickOtmazgin_FluentVoicePro_SingleInstance_Mutex"

PAYPAL_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=4HM44VH47LSMW"
GITHUB_REPO_URL = "https://github.com/nickotmazgin/fluentvoice-pro"

def enforce_single_instance():
    kernel32 = ctypes.windll.kernel32
    mutex_handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        print("[FluentVoice Pro] Another instance is already running. Exiting cleanly.")
        if mutex_handle:
            kernel32.CloseHandle(mutex_handle)
        sys.exit(0)
    return mutex_handle

def get_tray_icon_path() -> Path:
    # Look for dedicated high-contrast crisp tray icon first
    pkg_assets = Path(__file__).parent.parent / "assets" / "tray_icon.png"
    if pkg_assets.exists():
        return pkg_assets
    # Fallback to general icon
    app_icon = Path(__file__).parent.parent / "assets" / "icon.png"
    if app_icon.exists():
        return app_icon
    # Fallback to antigravity speaker icon
    alt = Path.home() / ".antigravity" / "tts_speaker.png"
    if alt.exists():
        return alt
    fallback_path = Path.home() / ".fluentvoice" / "tray_icon.png"
    img = Image.new("RGBA", (32, 32), (0, 220, 255, 255))
    img.save(fallback_path)
    return fallback_path

class FluentVoiceTrayApp:
    def __init__(self):
        self.mutex_handle = enforce_single_instance()
        self.cfg = load_config()
        self.auto_read_enabled = self.cfg.get("auto_read_copy", False)
        self.last_clipboard_hash = hash(core.get_clipboard_text())
        self.tray_icon = None

    def save_settings(self):
        self.cfg["auto_read_copy"] = self.auto_read_enabled
        save_config(self.cfg)

    def on_toggle_speech(self, icon=None, item=None):
        threading.Thread(target=core.toggle_speak_or_stop, daemon=True).start()

    def on_stop(self, icon=None, item=None):
        core.stop_all_playback()

    def on_open_settings(self, icon=None, item=None):
        def _launch():
            from .gui import open_settings_window
            open_settings_window(tab="Voice & Speech")
        threading.Thread(target=_launch, daemon=True).start()

    def on_open_about(self, icon=None, item=None):
        def _launch():
            from .gui import open_settings_window
            open_settings_window(tab="About & Developer")
        threading.Thread(target=_launch, daemon=True).start()

    def on_open_paypal(self, icon=None, item=None):
        webbrowser.open(PAYPAL_DONATE_URL)

    def on_open_github(self, icon=None, item=None):
        webbrowser.open(GITHUB_REPO_URL)

    def set_voice(self, voice_name):
        def _inner(icon, item):
            self.cfg["voice"] = voice_name
            if "sapi" in voice_name.lower():
                self.cfg["engine"] = "offline"
            else:
                self.cfg["engine"] = "neural"
            self.save_settings()
        return _inner

    def is_voice_checked(self, voice_name):
        def _inner(item):
            return self.cfg.get("voice") == voice_name
        return _inner

    def toggle_auto_read(self, icon=None, item=None):
        self.auto_read_enabled = not self.auto_read_enabled
        self.save_settings()

    def is_auto_read_checked(self, item):
        return self.auto_read_enabled

    def clipboard_monitor_loop(self):
        while True:
            try:
                if self.auto_read_enabled:
                    current = core.get_clipboard_text()
                    current_h = hash(current)
                    if current_h != self.last_clipboard_hash and len(current.strip()) > 4:
                        self.last_clipboard_hash = current_h
                        time.sleep(0.4)
                        fresh = core.get_clipboard_text()
                        if fresh == current:
                            threading.Thread(target=lambda: core.speak_text(fresh), daemon=True).start()
            except Exception:
                pass
            time.sleep(0.6)

    def on_exit(self, icon, item):
        core.stop_all_playback()
        if icon:
            icon.stop()
        if self.mutex_handle:
            ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
        os._exit(0)

    def run(self):
        icon_path = get_tray_icon_path()
        img = Image.open(icon_path)

        menu = pystray.Menu(
            item("🔊 FluentVoice (Toggle Speak / Stop)", self.on_toggle_speech, default=True),
            item("⚙️ Settings & Control Center...", self.on_open_settings),
            item("⏹ Stop Speech Immediately", self.on_stop),
            pystray.Menu.SEPARATOR,
            item("⚡ Auto-Read on Copy", self.toggle_auto_read, checked=self.is_auto_read_checked),
            pystray.Menu.SEPARATOR,
            item("🗣 Neural Voices (Ultra HD)", pystray.Menu(
                item("Andrew Multilingual (Natural Male)", self.set_voice("en-US-AndrewMultilingualNeural"), checked=self.is_voice_checked("en-US-AndrewMultilingualNeural")),
                item("Ava Multilingual (Natural Female)", self.set_voice("en-US-AvaMultilingualNeural"), checked=self.is_voice_checked("en-US-AvaMultilingualNeural")),
                item("Brian Multilingual (Natural Casual)", self.set_voice("en-US-BrianMultilingualNeural"), checked=self.is_voice_checked("en-US-BrianMultilingualNeural")),
                item("Emma Multilingual (Natural Expressive)", self.set_voice("en-US-EmmaMultilingualNeural"), checked=self.is_voice_checked("en-US-EmmaMultilingualNeural")),
            )),
            item("💻 Local Windows Voices (Offline)", pystray.Menu(
                item("Windows Zira (English US)", self.set_voice("sapi-zira"), checked=self.is_voice_checked("sapi-zira")),
                item("Windows Hazel (English UK)", self.set_voice("sapi-hazel"), checked=self.is_voice_checked("sapi-hazel")),
            )),
            pystray.Menu.SEPARATOR,
            item("ℹ️ About & Credits (Nick Otmazgin)...", self.on_open_about),
            item("💖 Donate & Support (PayPal)...", self.on_open_paypal),
            item("🌐 GitHub Repository & Docs...", self.on_open_github),
            pystray.Menu.SEPARATOR,
            item("❌ Exit FluentVoice Pro", self.on_exit)
        )

        self.tray_icon = pystray.Icon("FluentVoice_Pro", img, "FluentVoice Pro (Click to Speak / Stop)", menu)
        threading.Thread(target=self.clipboard_monitor_loop, daemon=True).start()
        self.tray_icon.run()

def main():
    app = FluentVoiceTrayApp()
    app.run()

if __name__ == "__main__":
    main()
