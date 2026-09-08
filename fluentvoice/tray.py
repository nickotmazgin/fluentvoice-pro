"""FluentVoice Pro - Modern Windows 11 System Tray Daemon & Clipboard Watcher
Author: Nick Otmazgin
"""

import sys
import os
import time
import ctypes
import threading
import subprocess
import webbrowser
from pathlib import Path
from PIL import Image
import pystray
from pystray import MenuItem as item

# Ensure package imports work
sys.path.insert(0, str(Path(__file__).parent.parent))
from fluentvoice import config, core
from fluentvoice.config import load_config, save_config

MUTEX_NAME = "Global\\FluentVoice_Pro_SingleInstance_Mutex"
PAYPAL_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=4HM44VH47LSMW"
GITHUB_REPO_URL = "https://github.com/nickotmazgin/fluentvoice-pro"
GITHUB_ISSUES_URL = "https://github.com/nickotmazgin/fluentvoice-pro/issues"

def check_single_instance():
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle

def get_tray_icon_path():
    p = Path(__file__).parent.parent / "assets" / "tray_icon.ico"
    if p.exists():
        return str(p)
    return str(Path.home() / ".antigravity" / "tray_icon.ico")

def apply_win32_dark_menus():
    try:
        uxtheme = ctypes.windll.uxtheme
        uxtheme.SetPreferredAppMode(2)  # ForceDark
    except Exception:
        pass

class FluentVoiceTrayApp:
    def __init__(self):
        self.mutex_handle = check_single_instance()
        if not self.mutex_handle:
            sys.exit(0)

        apply_win32_dark_menus()

        self.cfg = load_config()
        self.auto_read_enabled = self.cfg.get("auto_read_copy", False)
        self.last_clipboard_hash = None
        self.tray_icon = None

        # Register notification bridge to core engine
        core.set_notify_callback(self.notify_user)

    def notify_user(self, title: str, message: str):
        if not self.cfg.get("show_notifications", True):
            return
        if self.tray_icon:
            try:
                self.tray_icon.notify(message, title)
            except Exception:
                pass

    def save_settings(self):
        self.cfg["auto_read_copy"] = self.auto_read_enabled
        save_config(self.cfg)

    def on_toggle_speech(self, icon=None, item=None):
        threading.Thread(target=core.toggle_speak_or_stop, daemon=True).start()

    def on_stop(self, icon=None, item=None):
        core.stop_all_playback()

    def on_open_reader(self, icon=None, item=None):
        try:
            from .gui import focus_existing_settings_window
            if focus_existing_settings_window():
                return
        except Exception:
            pass
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = Path(sys.executable)
        base_dir = Path(__file__).parent.parent.resolve()
        subprocess.Popen([str(pythonw), "-m", "fluentvoice.cli", "--reader"], cwd=str(base_dir))

    def on_open_settings(self, icon=None, item=None):
        try:
            from .gui import focus_existing_settings_window
            if focus_existing_settings_window():
                return
        except Exception:
            pass
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = Path(sys.executable)
        base_dir = Path(__file__).parent.parent.resolve()
        subprocess.Popen([str(pythonw), "-m", "fluentvoice.cli", "--gui"], cwd=str(base_dir))

    def on_open_about(self, icon=None, item=None):
        try:
            from .gui import focus_existing_settings_window
            if focus_existing_settings_window():
                return
        except Exception:
            pass
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = Path(sys.executable)
        base_dir = Path(__file__).parent.parent.resolve()
        subprocess.Popen([str(pythonw), "-m", "fluentvoice.cli", "--about"], cwd=str(base_dir))

    def on_open_paypal(self, icon=None, item=None):
        webbrowser.open(PAYPAL_DONATE_URL)

    def on_open_github(self, icon=None, item=None):
        webbrowser.open(GITHUB_REPO_URL)

    def on_open_feedback(self, icon=None, item=None):
        webbrowser.open(GITHUB_ISSUES_URL)

    def set_voice(self, voice_name, display_label=None):
        def _inner(icon, item):
            self.cfg["voice"] = voice_name
            if "sapi" in voice_name.lower() or "desktop" in voice_name.lower():
                self.cfg["engine"] = "offline"
            else:
                self.cfg["engine"] = "neural"
            save_config(self.cfg)
            label = display_label or voice_name
            self.notify_user("FluentVoice Pro", f"🗣️ Voice selected: {label}")
        return _inner

    def is_voice_checked(self, voice_name):
        def _inner(item):
            curr = load_config().get("voice", "")
            return curr == voice_name or voice_name in curr or curr in voice_name
        return _inner

    def toggle_auto_read(self, icon=None, item=None):
        self.cfg = load_config()
        self.auto_read_enabled = not self.cfg.get("auto_read_copy", False)
        self.save_settings()
        state = "Enabled" if self.auto_read_enabled else "Disabled"
        self.notify_user("FluentVoice Pro", f"⚡ Auto-Read on Copy: {state}")

    def is_auto_read_checked(self, item):
        return load_config().get("auto_read_copy", False)

    def toggle_notifications(self, icon=None, item=None):
        self.cfg = load_config()
        curr = self.cfg.get("show_notifications", True)
        self.cfg["show_notifications"] = not curr
        save_config(self.cfg)
        state = "Enabled" if not curr else "Disabled"
        if self.tray_icon:
            try:
                self.tray_icon.notify(f"Windows Notifications: {state}", "FluentVoice Pro")
            except Exception:
                pass

    def is_notifications_checked(self, item):
        return load_config().get("show_notifications", True)

    def clipboard_monitor_loop(self):
        while True:
            try:
                fresh_cfg = load_config()
                if fresh_cfg.get("auto_read_copy", False):
                    current = core.get_clipboard_text()
                    current_h = hash(current)
                    if current_h != self.last_clipboard_hash and len(current.strip()) > 4:
                        self.last_clipboard_hash = current_h
                        debounce = float(fresh_cfg.get("debounce_sec", 0.6))
                        time.sleep(debounce)
                        fresh = core.get_clipboard_text()
                        if fresh == current:
                            threading.Thread(target=lambda: core.speak_text(fresh), daemon=True).start()
            except Exception:
                pass
            time.sleep(0.5)

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

        # Build dynamic offline SAPI menu items
        offline_items = []
        for label, desc in core.get_installed_sapi_voices():
            offline_items.append(
                item(label, self.set_voice(desc, label), checked=self.is_voice_checked(desc))
            )

        menu = pystray.Menu(
            item("🔊 FluentVoice (Toggle Speak / Stop)", self.on_toggle_speech, default=True),
            item("📋 Direct Text Reader...", self.on_open_reader),
            item("⚙️ Settings && Control Center...", self.on_open_settings),
            item("⏹ Stop Speech Immediately", self.on_stop),
            pystray.Menu.SEPARATOR,
            item("⚡ Auto-Read on Copy", self.toggle_auto_read, checked=self.is_auto_read_checked),
            item("🔔 Windows Notifications", self.toggle_notifications, checked=self.is_notifications_checked),
            pystray.Menu.SEPARATOR,
            item("🗣 Neural Voices (English HD)", pystray.Menu(
                item("Andrew Multilingual (US HD Male)", self.set_voice("en-US-AndrewMultilingualNeural", "Andrew Multilingual (US)"), checked=self.is_voice_checked("en-US-AndrewMultilingualNeural")),
                item("Ava Multilingual (US HD Female)", self.set_voice("en-US-AvaMultilingualNeural", "Ava Multilingual (US)"), checked=self.is_voice_checked("en-US-AvaMultilingualNeural")),
                item("Brian Multilingual (US HD Casual)", self.set_voice("en-US-BrianMultilingualNeural", "Brian Multilingual (US)"), checked=self.is_voice_checked("en-US-BrianMultilingualNeural")),
                item("Emma Multilingual (US HD Expressive)", self.set_voice("en-US-EmmaMultilingualNeural", "Emma Multilingual (US)"), checked=self.is_voice_checked("en-US-EmmaMultilingualNeural")),
                item("Jenny (US Studio Professional Female)", self.set_voice("en-US-JennyNeural", "Jenny (US Studio)"), checked=self.is_voice_checked("en-US-JennyNeural")),
                item("Guy (US Studio Professional Male)", self.set_voice("en-US-GuyNeural", "Guy (US Studio)"), checked=self.is_voice_checked("en-US-GuyNeural")),
                item("Ryan (UK British Natural Male)", self.set_voice("en-GB-RyanNeural", "Ryan (UK)"), checked=self.is_voice_checked("en-GB-RyanNeural")),
                item("Sonia (UK British Natural Female)", self.set_voice("en-GB-SoniaNeural", "Sonia (UK)"), checked=self.is_voice_checked("en-GB-SoniaNeural")),
            )),
            item("🇮🇱 Neural Voices (Hebrew HD)", pystray.Menu(
                item("Avri (Hebrew Natural Male)", self.set_voice("he-IL-AvriNeural", "Avri (Hebrew)"), checked=self.is_voice_checked("he-IL-AvriNeural")),
                item("Hila (Hebrew Natural Female)", self.set_voice("he-IL-HilaNeural", "Hila (Hebrew)"), checked=self.is_voice_checked("he-IL-HilaNeural")),
            )),
            item("🌍 Neural Voices (World HD)", pystray.Menu(
                item("Alvaro (Spanish Spain)", self.set_voice("es-ES-AlvaroNeural", "Alvaro (Spanish)"), checked=self.is_voice_checked("es-ES-AlvaroNeural")),
                item("Dalia (Spanish Mexico)", self.set_voice("es-MX-DaliaNeural", "Dalia (Spanish Mexico)"), checked=self.is_voice_checked("es-MX-DaliaNeural")),
                item("Henri (French France)", self.set_voice("fr-FR-HenriNeural", "Henri (French)"), checked=self.is_voice_checked("fr-FR-HenriNeural")),
                item("Conrad (German Germany)", self.set_voice("de-DE-ConradNeural", "Conrad (German)"), checked=self.is_voice_checked("de-DE-ConradNeural")),
                item("Diego (Italian Italy)", self.set_voice("it-IT-DiegoNeural", "Diego (Italian)"), checked=self.is_voice_checked("it-IT-DiegoNeural")),
                item("Hamed (Arabic Saudi Arabia)", self.set_voice("ar-SA-HamedNeural", "Hamed (Arabic)"), checked=self.is_voice_checked("ar-SA-HamedNeural")),
                item("Keita (Japanese Japan)", self.set_voice("ja-JP-KeitaNeural", "Keita (Japanese)"), checked=self.is_voice_checked("ja-JP-KeitaNeural")),
            )),
            item("💻 Local Windows Voices (Offline 0ms)", pystray.Menu(*offline_items)),
            pystray.Menu.SEPARATOR,
            item("ℹ️ About && Credits (Nick Otmazgin)...", self.on_open_about),
            item("💖 Donate && Support (PayPal)...", self.on_open_paypal),
            item("🌐 GitHub Repository && Docs...", self.on_open_github),
            item("🐛 Report an Issue / Feedback...", self.on_open_feedback),
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
