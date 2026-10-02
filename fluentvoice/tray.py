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
from fluentvoice import config, core, voices
from fluentvoice.config import load_config

LOG_DIR = Path.home() / ".fluentvoice"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "tray.log"

logger = logging.getLogger("fluentvoice.tray")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    from logging.handlers import RotatingFileHandler
    _fh = RotatingFileHandler(str(LOG_FILE), maxBytes=256_000, backupCount=1, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s"))
    logger.addHandler(_fh)

# Per Windows session: with Global\ a second user signed in on the same PC could not start the tray.
MUTEX_NAME = "Local\\FluentVoice_Pro_SingleInstance_Mutex"
LEGACY_MUTEX_NAME = "Global\\FluentVoice_Pro_SingleInstance_Mutex"  # v1.4.x trays (same user only)
PAYPAL_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=4HM44VH47LSMW"
GITHUB_REPO_URL = "https://github.com/nickotmazgin/fluentvoice-pro"
GITHUB_ISSUES_URL = "https://github.com/nickotmazgin/fluentvoice-pro/issues"
TRAY_TOOLTIP = "FluentVoice Pro (Click to Speak / Stop)"

def check_single_instance():
    # use_last_error=True: plain ctypes.windll does not reliably preserve GetLastError(),
    # which could let a second tray instance start.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE
    kernel32.OpenMutexW.restype = ctypes.wintypes.HANDLE
    legacy = kernel32.OpenMutexW(0x00100000, False, LEGACY_MUTEX_NAME)  # SYNCHRONIZE
    if legacy:  # an older FluentVoice tray of this user is still running
        kernel32.CloseHandle(legacy)
        return None
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        if handle:
            kernel32.CloseHandle(handle)
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

def tray_icon_px() -> int:
    """Real notification-area icon size in pixels (16 at 100%, 20 at 125%, 24 at 150%...).

    The tray process is not DPI-aware, so a plain GetSystemMetrics answers 16 on every
    display; ask as a DPI-aware thread instead."""
    try:
        u = ctypes.windll.user32
        u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        old = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
        try:
            return int(u.GetSystemMetricsForDpi(49, u.GetDpiForSystem())) or 16  # SM_CXSMICON
        finally:
            if old:
                u.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))
    except Exception:
        return 16


def load_tray_image(size: int | None = None):
    """The app tile, edge to edge, resampled from the 512 px master to the exact tray size.

    Windows draws tray icons at 16/20/24 px. Handing it a 32 px image made it squeeze the
    icon (blurry at 125%), and the tile's transparent margin made it look smaller than
    the Wi-Fi / volume icons beside it."""
    size = size or tray_icon_px()
    master = Path(__file__).parent.parent / "assets" / "icon.png"
    try:
        img = Image.open(master).convert("RGBA")
        img = img.crop(img.getchannel("A").getbbox())
        return img.resize((size, size), Image.LANCZOS)
    except Exception:
        ico = Path(get_tray_icon_path())
        return Image.open(ico if ico.exists() else ico.with_suffix(".png")).convert("RGBA").resize(
            (size, size), Image.LANCZOS)


class CrispTrayIcon(pystray.Icon):
    """pystray icon that keeps the image at its own size.

    pystray saves the image as an .ico with Pillow's default size list and loads it at the
    *large* icon size (32 px), so Windows scales it twice. Load it at its exact size."""

    def _assert_icon_handle(self):
        if self._icon_handle or not sys.platform.startswith("win"):
            return super()._assert_icon_handle()
        import tempfile
        from pystray._util import win32
        n = self.icon.width
        fd, path = tempfile.mkstemp(suffix=".ico")
        os.close(fd)
        try:
            self.icon.save(path, format="ICO", sizes=[(n, n)])
            self._icon_handle = win32.LoadImage(None, path, win32.IMAGE_ICON, n, n, win32.LR_LOADFROMFILE)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


PROMOTED_MARKER = config.APP_DIR / "tray_icon_promoted"


def _is_our_notify_entry(exe: str, tip: str) -> bool:
    """Only FluentVoice's own entry: other Python apps also run as python(w).exe."""
    return "fluentvoice" in tip.lower() or exe.lower().endswith("fluentvoicepro.exe")


def promote_notify_icons():
    """Show the FluentVoice icon next to the clock (not in the ^ overflow) on first run only.

    Windows lets the user choose which icons stay visible. Earlier versions re-forced this on
    every start (and for every Python tray app); now it happens once, then the user decides
    (drag it into ^ or Settings > Personalization > Taskbar > Other system tray icons)."""
    if PROMOTED_MARKER.exists():
        return 0
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
                if not _is_our_notify_entry(exe, tip):
                    winreg.CloseKey(sk)
                    continue
                winreg.SetValueEx(sk, "IsPromoted", 0, winreg.REG_DWORD, 1)
                promoted += 1
                winreg.CloseKey(sk)
            except Exception:
                try:
                    winreg.CloseKey(sk)
                except Exception:
                    pass
        winreg.CloseKey(root)
        if promoted:
            logger.info("Tray icon set to show next to the clock (first run; the user decides from now on)")
            try:
                PROMOTED_MARKER.parent.mkdir(parents=True, exist_ok=True)
                PROMOTED_MARKER.write_text("1", encoding="utf-8")
            except OSError:
                pass
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
        self._last_autoread_ts = 0.0
        self.tray_icon = None
        self._hotkey_id = 1
        self._hotkey_registered = None  # (mods, vk) currently registered
        self._dark_refresh_ticks = 0
        self.update_info = None  # set when a newer GitHub release is found

        # Register notification bridge to core engine
        core.set_notify_callback(self.notify_user)

    def notify_user(self, title: str, message: str, important: bool = True):
        """Tray toasts are user-requested (voice / setting changes, updates) → important by default."""
        level = load_config().get("notification_level", "important")
        if level == "off" or (level == "important" and not important):
            return
        if self.tray_icon:
            try:
                self.tray_icon.notify(message, title)
            except Exception:
                pass

    def save_settings(self):
        self.cfg = config.update_config({"auto_read_copy": self.auto_read_enabled})

    TOGGLE_DEBOUNCE_SEC = 0.6

    def on_toggle_speech(self, icon=None, item=None):
        """Left-click / hotkey: speak the clipboard, or stop if already speaking.

        A double-click delivers two clicks (and a held hotkey repeats), so presses closer
        than TOGGLE_DEBOUNCE_SEC count once instead of starting and instantly stopping."""
        now = time.monotonic()
        if now - getattr(self, "_last_toggle", -10.0) < self.TOGGLE_DEBOUNCE_SEC:
            return
        self._last_toggle = now
        threading.Thread(target=core.toggle_speak_or_stop, daemon=True).start()

    def on_stop(self, icon=None, item=None):
        core.stop_all_playback()

    def _launch_cli(self, flag: str, tab: str, *extra: str):
        try:
            from .gui import focus_existing_settings_window
            if focus_existing_settings_window(preferred_tab=tab):
                return
        except Exception:
            pass
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = Path(sys.executable)
        base_dir = Path(__file__).parent.parent.resolve()
        subprocess.Popen([str(pythonw), "-m", "fluentvoice.cli", flag, *extra], cwd=str(base_dir))

    def on_open_reader(self, icon=None, item=None):
        self._launch_cli("--reader", "Direct Text Reader")

    def on_open_settings(self, icon=None, item=None):
        self._launch_cli("--gui", "Voice & Speech")

    def on_open_providers(self, icon=None, item=None):
        self._launch_cli("--gui", "Voice Providers", "Voice", "Providers")

    def on_open_about(self, icon=None, item=None):
        self._launch_cli("--about", "About & Developer")

    # ------------------------------------------------------------------ updates
    def _update_menu_text(self, item=None):
        if self.update_info:
            return f"⬆️ Update Available: v{self.update_info.get('latest')}…"
        return "🔄 Check for Updates…"

    def on_check_updates(self, icon=None, item=None):
        if self.update_info:
            self._open_update_popup()
            return

        def _run():
            from . import updater
            res = updater.check_for_update(force=True)
            st = res.get("status")
            if st == "update":
                self._set_update(res)
                self._open_update_popup()
            elif st == "current":
                self.notify_user("✅ Up to date", f"You have the latest version (v{res.get('current')}).")
            else:
                self.notify_user("⚠ Update check failed", "Couldn't reach GitHub (offline?). Try again later.")
        threading.Thread(target=_run, daemon=True, name="UpdateCheck").start()

    def _open_update_popup(self):
        try:
            (config.APP_DIR / "pending_update_popup.txt").write_text("1", encoding="utf-8")
        except Exception:
            pass
        self._launch_cli("--about", "About & Developer")

    def _set_update(self, info):
        self.update_info = info
        try:
            if self.tray_icon:
                self.tray_icon.update_menu()
        except Exception:
            pass

    def portable_setup(self):
        """Portable EXE only: keep our shortcuts pointing at this folder, and offer
        Start-with-Windows + Desktop/Start Menu shortcuts once on first launch
        (the portable ZIP has no installer, so otherwise it vanishes after a reboot)."""
        from fluentvoice import shortcuts
        if not shortcuts.is_frozen():
            return
        try:
            fixed = shortcuts.repair_moved_portable()
            if fixed:
                logger.info(f"Re-pointed {fixed} shortcut(s) at {shortcuts.app_dir()}")
        except Exception as e:
            logger.warning(f"Shortcut repair failed: {e}")

        marker = config.APP_DIR / "portable_setup_offered"
        if marker.exists():
            return
        try:
            if shortcuts.startup_enabled() and shortcuts.shortcuts_installed():
                marker.touch()
                return
            time.sleep(1.5)
            # MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND | MB_TOPMOST
            answer = ctypes.windll.user32.MessageBoxW(
                None,
                "FluentVoice Pro is running in the tray (near the clock).\n\n"
                "Start it automatically with Windows and add Desktop + Start Menu shortcuts?\n\n"
                "You can change this any time in Settings → Automation & System → Startup & Shortcuts.",
                "FluentVoice Pro — Portable setup",
                0x04 | 0x20 | 0x10000 | 0x40000,
            )
            marker.touch()
            if answer == 6:  # IDYES
                shortcuts.set_startup(True)
                shortcuts.create_shortcuts()
                self.notify_user("✓ Portable setup done", "Starts with Windows • Desktop & Start Menu shortcuts added")
                logger.info("Portable setup: startup + shortcuts created")
        except Exception as e:
            logger.warning(f"Portable setup failed: {e}")

    def update_check_loop(self):
        """Quiet background check: shortly after start, then every few hours (updater self-throttles to 1/day)."""
        time.sleep(25)
        from . import updater
        announced = None
        while True:
            try:
                res = updater.check_for_update(force=False)
                if res.get("status") == "update":
                    self._set_update(res)
                    if announced != res.get("latest"):
                        announced = res.get("latest")
                        self.notify_user(
                            "⬆ Update available",
                            f"v{res.get('latest')} is out (you have v{res.get('current')}). "
                            "Right-click the tray icon → Update Available.",
                        )
                        logger.info("Update available: %s", res.get("latest"))
            except Exception as e:
                logger.warning("update check failed: %s", e)
            time.sleep(6 * 3600)

    def on_open_paypal(self, icon=None, item=None):
        webbrowser.open(PAYPAL_DONATE_URL)

    def on_open_github(self, icon=None, item=None):
        webbrowser.open(GITHUB_REPO_URL)

    def on_open_feedback(self, icon=None, item=None):
        webbrowser.open(GITHUB_ISSUES_URL)

    def set_voice(self, voice_name, display_label=None):
        def _inner(icon, item):
            # Only the voice changes; a reading in progress switches to it at once (core).
            self.cfg = config.update_config({
                "voice": voice_name,
                "engine": ("offline" if voices.is_offline(voice_name) else
                           "local" if voices.is_local_hd(voice_name) else "neural"),
            })
            label = display_label or voice_name
            self.notify_user("🗣 Voice selected", label)
        return _inner

    def _voice_items(self, family):
        """Tray menu items for one language, from the shared catalog (fluentvoice/voices.py)."""
        return [
            item(label, self.set_voice(vid, label), checked=self.is_voice_checked(vid))
            for vid, label in voices.voices_for(family)
        ]

    def _local_hd_items(self):
        """Downloaded offline HD voices (Piper / Kokoro), by language. Rebuilt when one is added."""
        from . import localtts
        installed = localtts.installed_voices()
        if not installed:
            yield item("Download offline HD voices… (Settings → Voice Providers)", self.on_open_providers)
            return
        for fam, name in voices.LANGUAGES.items():
            mine = [v for v in installed if v["family"] == fam]
            if mine:
                yield item(name, pystray.Menu(*[
                    item(voices.label_for(v["id"]), self.set_voice(v["id"], voices.label_for(v["id"])),
                         checked=self.is_voice_checked(v["id"]))
                    for v in mine
                ]))
        yield pystray.Menu.SEPARATOR
        yield item("Manage offline HD voices…", self.on_open_providers)

    def toggle_offline_only(self, icon=None, item=None):
        on = not load_config().get("offline_only", False)
        self.cfg = config.update_config({"offline_only": on})
        self.notify_user("🛡 Privacy", "Offline only: text stays on this PC" if on else "Online HD voices allowed again")

    def is_offline_only_checked(self, item):
        return load_config().get("offline_only", False)

    def is_voice_checked(self, voice_name):
        def _inner(item):
            return load_config().get("voice", "") == voice_name
        return _inner

    def toggle_auto_read(self, icon=None, item=None):
        self.cfg = load_config()
        self.auto_read_enabled = not self.cfg.get("auto_read_copy", False)
        self.save_settings()
        state = "On — copied text is read aloud" if self.auto_read_enabled else "Off"
        self.notify_user("⚡ Auto-Read on Copy", state)

    def is_auto_read_checked(self, item):
        return load_config().get("auto_read_copy", False)

    NOTIFY_CHOICES = (("important", "Important only (recommended)"), ("all", "All — including every read"), ("off", "Off"))

    def set_notification_level(self, level):
        def _inner(icon=None, item=None):
            self.cfg = config.update_config({"notification_level": level, "show_notifications": level != "off"})
            if level != "off":
                self.notify_user("🔔 Notifications", dict(self.NOTIFY_CHOICES)[level])
        return _inner

    def is_notification_level(self, level):
        def _inner(item):
            return load_config().get("notification_level", "important") == level
        return _inner

    def clipboard_monitor_loop(self):
        user32 = ctypes.windll.user32
        last_seq = user32.GetClipboardSequenceNumber()
        last_cfg_check = 0.0
        cfg_cached = load_config()
        from . import localtts
        voices_sig = localtts.installed_signature()

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
                    sig = localtts.installed_signature()
                    if sig != voices_sig:  # an offline HD voice was downloaded or removed in Settings
                        voices_sig = sig
                        if self.tray_icon:
                            self.tray_icon.update_menu()

                curr_seq = user32.GetClipboardSequenceNumber()
                if not cfg_cached.get("auto_read_copy", False):
                    # Keep tracking while disabled so re-enabling does not read stale clipboard.
                    last_seq = curr_seq
                elif curr_seq != last_seq:
                    last_seq = curr_seq
                    current = core.get_clipboard_text()
                    if self.autoread_should_read(current):
                        time.sleep(float(cfg_cached.get("debounce_sec", 0.6)))
                        fresh = core.get_clipboard_text()
                        if fresh == current:  # unchanged after the stability buffer
                            last_seq = user32.GetClipboardSequenceNumber()
                            self.autoread_start(fresh)

                # Re-apply dark menus occasionally (hover theme can regress)
                self._dark_refresh_ticks += 1
                if self._dark_refresh_ticks % 20 == 0:
                    apply_win32_dark_menus()
            except Exception:
                pass
            time.sleep(0.5)

    AUTOREAD_DUPLICATE_SEC = 1.5  # apps that put the same text on the clipboard twice in a row

    def autoread_should_read(self, text: str) -> bool:
        """Auto-Read on Copy filter.

        - Skips copies marked private by the copying app (e.g. KeePass, KeePassXC) and copies that
          look like a password, API key or token: they are never read aloud nor sent to the cloud
          voice service.
        - Skips copies shorter than 2 characters and copies with no letters or digits.
        - The same text copied again is read again once the previous reading has finished
          (earlier versions ignored it for good, so after changing the voice, copying the
          same text stayed silent until FluentVoice was restarted).
        - While that same text is still being read, copying it again does not restart it.
        - Duplicate clipboard updates within AUTOREAD_DUPLICATE_SEC are ignored.
        """
        if len((text or "").strip()) < 2 or not any(ch.isalnum() for ch in text):
            return False
        if core.looks_like_secret(text) or core.clipboard_is_private():
            return False
        h = hash(text)
        if h == self.last_clipboard_hash:
            if time.time() - self._last_autoread_ts < self.AUTOREAD_DUPLICATE_SEC:
                return False
            if core.is_any_speaking():
                return False
        return True

    def autoread_start(self, text: str):
        self.last_clipboard_hash = hash(text)
        self._last_autoread_ts = time.time()
        threading.Thread(target=core.speak_text, args=(text,), daemon=True, name="fv-autoread").start()

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
        else:
            logger.warning("Global hotkey %r could not be registered (in use by another app?)", cfg.get("hotkey"))

    def hotkey_message_loop(self):
        """Dedicated thread: GetMessage pump for WM_HOTKEY."""
        self.sync_hotkey_from_config()
        user32 = ctypes.windll.user32
        msg = ctypes.wintypes.MSG()
        last_chord = None
        last_cfg_check = 0.0
        while True:
            # Reload hotkey if Settings changed the chord (throttled: was reading config 20x/sec)
            try:
                if time.time() - last_cfg_check < 2.0:
                    raise StopIteration
                last_cfg_check = time.time()
                cfg = load_config()
                chord = (cfg.get("hotkey"), cfg.get("hotkey_enabled", True))
                if chord != last_chord:
                    last_chord = chord
                    self.sync_hotkey_from_config()
            except StopIteration:
                pass
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
            threading.Thread(target=self.update_check_loop, daemon=True, name="UpdateWatcher").start()
            threading.Thread(target=self.portable_setup, daemon=True, name="PortableSetup").start()
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
            item("🛡 Offline Only (Privacy Mode)", self.toggle_offline_only, checked=self.is_offline_only_checked),
            item("🔔 Notifications", pystray.Menu(*[
                item(text, self.set_notification_level(lvl), checked=self.is_notification_level(lvl), radio=True)
                for lvl, text in self.NOTIFY_CHOICES
            ])),
            pystray.Menu.SEPARATOR,
            item("☁ Online HD Voices: English (Microsoft)", pystray.Menu(*self._voice_items("english"))),
            item("☁ Online HD Voices: Hebrew (Microsoft)", pystray.Menu(*self._voice_items("hebrew"))),
            item("☁ Online HD Voices: World (Microsoft)", pystray.Menu(*[
                item(name, pystray.Menu(*self._voice_items(fam)))
                for fam, name in voices.LANGUAGES.items() if fam not in ("english", "hebrew")
            ])),
            item("🖥 Offline HD Voices (Piper / Kokoro)", pystray.Menu(lambda: tuple(self._local_hd_items()))),
            item("💻 Local Windows Voices (Offline)", pystray.Menu(*offline_items)),
            pystray.Menu.SEPARATOR,
            item("ℹ️ About && Credits (Nick Otmazgin)...", self.on_open_about),
            item("💖 Donate && Support (PayPal)...", self.on_open_paypal),
            item("🌐 GitHub Repository && Docs...", self.on_open_github),
            item("🐛 Report an Issue / Feedback...", self.on_open_feedback),
            item(self._update_menu_text, self.on_check_updates),
            pystray.Menu.SEPARATOR,
            item("❌ Exit FluentVoice Pro", self.on_exit)
        )

        self.tray_icon = CrispTrayIcon("FluentVoice_Pro", img, TRAY_TOOLTIP, menu)
        logger.info("Running pystray tray_icon event loop...")
        self.tray_icon.run(setup=self._on_icon_ready)

def main():
    try:
        from fluentvoice import shortcuts
        shortcuts.apply_app_identity()  # toasts titled "FluentVoice Pro" with its icon, not "Python"
        app = FluentVoiceTrayApp()
        app.run()
    except Exception as e:
        logger.critical(f"Fatal crash in FluentVoiceTrayApp: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
