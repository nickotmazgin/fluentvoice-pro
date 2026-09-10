"""FluentVoice Pro - Modern Windows 11 System Tray Daemon & Clipboard Watcher
Author: Nick Otmazgin
"""

import sys
import os
import time
import ctypes
import ctypes.wintypes
import threading
import subprocess
import webbrowser
from pathlib import Path
from PIL import Image
import pystray
from pystray import MenuItem as item

import logging

# Ensure package imports work
sys.path.insert(0, str(Path(__file__).parent.parent))
from fluentvoice import config, core
from fluentvoice.config import load_config, save_config

LOG_DIR = Path.home() / ".fluentvoice"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "tray.log"

logger = logging.getLogger("fluentvoice.tray")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s"))
    logger.addHandler(_fh)

MUTEX_NAME = "Global\\FluentVoice_Pro_SingleInstance_Mutex"
PAYPAL_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=4HM44VH47LSMW"
GITHUB_REPO_URL = "https://github.com/nickotmazgin/fluentvoice-pro"
GITHUB_ISSUES_URL = "https://github.com/nickotmazgin/fluentvoice-pro/issues"
TRAY_TOOLTIP = "FluentVoice Pro (Click to Speak / Stop)"

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
    # Prefer packaged assets; last-resort legacy path
    fallback = Path.home() / ".fluentvoice" / "tray_icon.ico"
    if fallback.exists():
        return str(fallback)
    return str(p)

def load_tray_image():
    """Load a crisp RGBA tray image (prefer multi-size ICO, fall back to PNG)."""
    ico = Path(get_tray_icon_path())
    png = ico.with_suffix(".png")
    src = ico if ico.exists() else png
    img = Image.open(src)
    # Use the smallest available frame when multi-frame ICO — Windows picks size,
    # but giving pystray a clean RGBA bitmap avoids blank/transparent draws.
    try:
        if getattr(img, "n_frames", 1) > 1:
            # Prefer ~32px frame for crisp taskbar at 100–150% DPI
            best = None
            best_score = 10**9
            for i in range(img.n_frames):
                img.seek(i)
                w, h = img.size
                score = abs(w - 32) + abs(h - 32)
                if score < best_score:
                    best_score = score
                    best = img.copy().convert("RGBA")
            if best is not None:
                return best
    except Exception:
        pass
    return img.convert("RGBA")

def promote_notify_icons():
    """Force FluentVoice / pythonw notify icons to stay visible (not overflow-only)."""
    try:
        import winreg
        root = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Control Panel\NotifyIconSettings",
            0,
            winreg.KEY_READ,
        )
        promoted = 0
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
                i += 1
            except OSError:
                break
            try:
                sk = winreg.OpenKey(root, name, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
            except OSError:
                continue
            try:
                exe = ""
                tip = ""
                try:
                    exe = winreg.QueryValueEx(sk, "ExecutablePath")[0] or ""
                except OSError:
                    pass
                try:
                    tip = winreg.QueryValueEx(sk, "Tooltip")[0] or ""
                except OSError:
                    pass
                exe_l = exe.lower()
                tip_l = tip.lower()
                match = (
                    "pythonw.exe" in exe_l
                    or "python.exe" in exe_l
                    or "fluentvoice" in tip_l
                    or "fluent voice" in tip_l
                )
                if not match:
                    winreg.CloseKey(sk)
                    continue
                winreg.SetValueEx(sk, "IsPromoted", 0, winreg.REG_DWORD, 1)
                if not tip.strip():
                    winreg.SetValueEx(sk, "Tooltip", 0, winreg.REG_SZ, "FluentVoice Pro")
                promoted += 1
                winreg.CloseKey(sk)
            except Exception:
                try:
                    winreg.CloseKey(sk)
                except Exception:
                    pass
        winreg.CloseKey(root)
        if promoted:
            logger.info("Promoted %s Windows notify-icon entr(y/ies) to always-show", promoted)
        return promoted
    except Exception as e:
        logger.debug("promote_notify_icons: %s", e)
        return 0

def apply_win32_dark_menus():
    """Force Windows 11 dark popup menus (fixes white menus + khaki/beige hover).
    SetPreferredAppMode / FlushMenuThemes are process-wide uxtheme.dll exports.
    Does NOT EnumWindows/SetWindowTheme on pystray HWNDs (that broke the tray).
    """
    try:
        uxtheme = ctypes.WinDLL("uxtheme.dll")
        # PreferredAppMode: 0 Default, 1 AllowDark, 2 ForceDark, 3 ForceLight
        for ordinal in (135, 132):
            try:
                fn = uxtheme[ordinal]
                fn.argtypes = [ctypes.c_int]
                fn.restype = ctypes.c_int
                fn(2)  # ForceDark
                break
            except Exception:
                continue
        try:
            flush_menu_themes = uxtheme[136]  # FlushMenuThemes
            flush_menu_themes.argtypes = []
            flush_menu_themes.restype = None
            flush_menu_themes()
        except Exception:
            pass
        try:
            allow_dark = getattr(uxtheme, "AllowDarkModeForApp", None)
            if allow_dark:
                allow_dark(True)
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"apply_win32_dark_menus error: {e}")


# Virtual-key map for RegisterHotKey
_VK_MAP = {
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _VK_MAP[_ch] = 0x41 + _i
for _i in range(10):
    _VK_MAP[str(_i)] = 0x30 + _i


def parse_hotkey(chord: str):
    """Parse 'ctrl+shift+space' into (modifiers, vk) for RegisterHotKey."""
    MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
    parts = [p.strip().lower() for p in (chord or "").replace(" ", "").split("+") if p.strip()]
    mods = 0
    key = None
    for p in parts:
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p in ("shift",):
            mods |= MOD_SHIFT
        elif p in ("alt",):
            mods |= MOD_ALT
        elif p in ("win", "windows", "super", "meta"):
            mods |= MOD_WIN
        else:
            key = p
    if not key or key not in _VK_MAP:
        return None
    return mods, _VK_MAP[key]

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
        self._hotkey_id = 1
        self._hotkey_registered = None  # (mods, vk) currently registered
        self._dark_refresh_ticks = 0

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
            if focus_existing_settings_window(preferred_tab="Direct Text Reader"):
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
            if focus_existing_settings_window(preferred_tab="Voice & Speech"):
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
            if focus_existing_settings_window(preferred_tab="About & Developer"):
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
        user32 = ctypes.windll.user32
        last_seq = user32.GetClipboardSequenceNumber()
        last_cfg_check = 0.0
        cfg_cached = load_config()

        while True:
            try:
                # Honor Settings → Restart Tray
                restart_flag = config.APP_DIR / "pending_tray_restart.txt"
                if restart_flag.exists():
                    try:
                        restart_flag.unlink(missing_ok=True)
                    except Exception:
                        pass
                    self.on_exit(self.tray_icon, None)
                    return

                # Refresh cached config every 2 seconds instead of every 500ms
                now = time.time()
                if now - last_cfg_check >= 2.0:
                    cfg_cached = load_config()
                    last_cfg_check = now

                if cfg_cached.get("auto_read_copy", False):
                    curr_seq = user32.GetClipboardSequenceNumber()
                    if curr_seq != last_seq:
                        last_seq = curr_seq
                        current = core.get_clipboard_text()
                        current_h = hash(current)
                        if current_h != self.last_clipboard_hash and len(current.strip()) > 4:
                            self.last_clipboard_hash = current_h
                            debounce = float(cfg_cached.get("debounce_sec", 0.6))
                            time.sleep(debounce)
                            fresh = core.get_clipboard_text()
                            if fresh == current:
                                threading.Thread(target=lambda: core.speak_text(fresh), daemon=True).start()

                # Re-apply dark menus occasionally (hover theme can regress)
                self._dark_refresh_ticks += 1
                if self._dark_refresh_ticks % 20 == 0:
                    apply_win32_dark_menus()
            except Exception:
                pass
            time.sleep(0.5)

    def sync_hotkey_from_config(self):
        """Register or update the global Win32 hotkey from config."""
        cfg = load_config()
        user32 = ctypes.windll.user32
        if self._hotkey_registered is not None:
            try:
                user32.UnregisterHotKey(None, self._hotkey_id)
            except Exception:
                pass
            self._hotkey_registered = None

        if not cfg.get("hotkey_enabled", True):
            return
        parsed = parse_hotkey(cfg.get("hotkey", "ctrl+shift+space"))
        if not parsed:
            return
        mods, vk = parsed
        if user32.RegisterHotKey(None, self._hotkey_id, mods, vk):
            self._hotkey_registered = (mods, vk)

    def hotkey_message_loop(self):
        """Dedicated thread: GetMessage pump for WM_HOTKEY."""
        self.sync_hotkey_from_config()
        user32 = ctypes.windll.user32
        msg = ctypes.wintypes.MSG()
        last_chord = None
        while True:
            # Reload hotkey if Settings changed the chord
            try:
                cfg = load_config()
                chord = (cfg.get("hotkey"), cfg.get("hotkey_enabled", True))
                if chord != last_chord:
                    last_chord = chord
                    self.sync_hotkey_from_config()
            except Exception:
                pass

            # Peek/wait with short timeout via MsgWaitForMultipleObjects-style polling
            has_msg = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)  # PM_REMOVE
            if has_msg:
                if msg.message == 0x0312:  # WM_HOTKEY
                    self.on_toggle_speech()
                else:
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.05)

    def on_exit(self, icon=None, item=None):
        logger.info("FluentVoice Pro shutting down...")
        core.stop_all_playback()
        try:
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
        except Exception:
            pass
        if icon:
            try:
                icon.stop()
            except Exception:
                pass
        if self.mutex_handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
            except Exception:
                pass
        logger.info("FluentVoice Pro exited cleanly.")
        os._exit(0)

    def _open_settings_failsafe(self, reason: str):
        """Open Settings when tray visibility cannot be confirmed (emergency back door)."""
        logger.error("Tray failsafe opening Settings: %s", reason)
        try:
            pythonw = Path(sys.executable).parent / "pythonw.exe"
            if not pythonw.exists():
                pythonw = Path(sys.executable)
            base_dir = Path(__file__).parent.parent.resolve()
            subprocess.Popen(
                [str(pythonw), "-m", "fluentvoice.cli", "--gui"],
                cwd=str(base_dir),
            )
        except Exception as e:
            logger.error("Failsafe Settings launch failed: %s", e)

    def _verify_and_promote_icon(self, icon):
        """Honest tray check: HWND + visible flag + promote in Windows notify settings."""
        hwnd = getattr(icon, "_hwnd", None)
        visible = bool(getattr(icon, "visible", False))
        icon_handle = getattr(icon, "_icon_handle", None) or getattr(icon, "icon", None)
        logger.info(
            "Tray status: visible=%s hwnd=%s has_icon=%s",
            visible,
            hwnd,
            bool(icon_handle),
        )
        promote_notify_icons()
        if visible and hwnd:
            logger.info("Tray icon registration OK (HWND present + visible=True)")
            return True
        logger.warning(
            "Tray icon NOT fully confirmed (visible=%s hwnd=%s). "
            "Use Desktop/Start Menu Emergency Stop / Settings if the icon is missing.",
            visible,
            hwnd,
        )
        return False

    def _on_icon_ready(self, icon):
        """Called by pystray once the tray window is live and ready to receive messages."""
        try:
            icon.title = TRAY_TOOLTIP
            icon.visible = True
            # Nudge Windows to redraw the notification area icon
            try:
                icon.icon = icon.icon
            except Exception:
                pass
            ok = self._verify_and_promote_icon(icon)
            threading.Thread(target=self.clipboard_monitor_loop, daemon=True, name="ClipboardWatcher").start()
            threading.Thread(target=self.hotkey_message_loop, daemon=True, name="HotkeyWatcher").start()
            logger.info("Background watcher threads started successfully")
            if not ok:
                # Delayed failsafe: give the shell a moment, then offer Settings UI
                def _delayed_failsafe():
                    time.sleep(2.5)
                    promote_notify_icons()
                    if not getattr(icon, "visible", False) or not getattr(icon, "_hwnd", None):
                        self._open_settings_failsafe("tray HWND/visible still missing after startup")
                threading.Thread(target=_delayed_failsafe, daemon=True, name="TrayFailsafe").start()
            else:
                # Second promote pass after Explorer finishes registering the icon
                threading.Thread(
                    target=lambda: (time.sleep(1.0), promote_notify_icons()),
                    daemon=True,
                    name="PromoteIcons",
                ).start()
        except Exception as e:
            logger.error(f"Error during tray icon setup: {e}", exc_info=True)
            self._open_settings_failsafe(str(e))

    def run(self):
        img = load_tray_image()

        # Build dynamic offline SAPI menu items
        offline_items = []
        try:
            for label, desc in core.get_installed_sapi_voices():
                offline_items.append(
                    item(label, self.set_voice(desc, label), checked=self.is_voice_checked(desc))
                )
        except Exception as e:
            logger.warning(f"Failed to enumerate SAPI voices: {e}")

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

        self.tray_icon = pystray.Icon("FluentVoice_Pro", img, TRAY_TOOLTIP, menu)
        logger.info("Running pystray tray_icon event loop...")
        self.tray_icon.run(setup=self._on_icon_ready)

def main():
    try:
        app = FluentVoiceTrayApp()
        app.run()
    except Exception as e:
        logger.critical(f"Fatal crash in FluentVoiceTrayApp: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
