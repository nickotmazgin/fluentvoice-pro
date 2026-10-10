"""Global hotkeys: chord parsing and validation, the registration status the tray reports to
Settings, and copying the selected text before the hotkey reads it."""

import ctypes
import json
import logging
import time

from .config import APP_DIR

_log = logging.getLogger("fluentvoice.hotkeys")

STATUS_FILE = APP_DIR / "hotkey_status.json"

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
MOD_NOREPEAT = 0x4000

# Virtual-key codes for RegisterHotKey
VK_MAP = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22, "pause": 0x13, "backspace": 0x08,
}
for _i in range(24):
    VK_MAP[f"f{_i + 1}"] = 0x70 + _i
for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    VK_MAP[_ch] = 0x41 + _i
for _i in range(10):
    VK_MAP[str(_i)] = 0x30 + _i

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT, "alt": MOD_ALT,
         "win": MOD_WIN, "windows": MOD_WIN, "super": MOD_WIN, "meta": MOD_WIN}


def _split(chord: str) -> list:
    return [p for p in (chord or "").lower().replace(" ", "").split("+") if p]


def parse_hotkey(chord: str):
    """'ctrl+shift+space' → (modifiers, vk) for RegisterHotKey; None when it is not a valid hotkey.

    A key without Ctrl / Alt / Shift / Win would be taken from every app (a lone "space" or "r"
    could no longer be typed anywhere), so only the function keys may be used alone."""
    mods, key = 0, None
    for p in _split(chord):
        if p in _MODS:
            mods |= _MODS[p]
        elif key is None:
            key = p
        else:
            return None  # two non-modifier keys
    if key not in VK_MAP:
        return None
    if not mods and not (key.startswith("f") and key[1:].isdigit()):
        return None
    if mods == MOD_SHIFT and not (key.startswith("f") and key[1:].isdigit()):
        return None  # Shift+letter is just a capital letter
    return mods, VK_MAP[key]


def hotkey_problem(chord: str) -> str:
    """Why `chord` can't be a hotkey ('' when it can), in words for Settings."""
    parts = _split(chord)
    keys = [p for p in parts if p not in _MODS]
    if not keys:
        return "Add a key after the modifiers, e.g. ctrl+shift+space."
    if len(keys) > 1:
        return f"Use one key plus modifiers ({' + '.join(keys)} are {len(keys)} keys)."
    if keys[0] not in VK_MAP:
        return f"'{keys[0]}' is not a supported key. Use a letter, digit, F1–F24, space, insert, home, end…"
    if parse_hotkey(chord) is None:
        return (f"'{keys[0]}' alone would stop it from working in every other app. "
                "Add Ctrl, Alt or Win, e.g. ctrl+shift+" + keys[0] + ".")
    return ""


def write_status(**entries):
    """Tray → Settings: whether each hotkey was registered, e.g. read={"chord":..., "ok":..., "error":...}."""
    try:
        STATUS_FILE.write_text(json.dumps(dict(entries, ts=time.time())), encoding="utf-8")
    except OSError:
        pass


def read_status() -> dict:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---- Copy the selection ---------------------------------------------------------------------
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, VK_INSERT, VK_C = 0x10, 0x11, 0x12, 0x5B, 0x5C, 0x2D, 0x43
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
# Ctrl+C in a console stops the running program; Ctrl+Insert copies there instead.
CONSOLE_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "VirtualConsoleClass",
                   "PuTTY", "KiTTYClass"}

_ignore_until = 0.0


def recently_copied() -> bool:
    """True right after copy_selection(): the clipboard change came from the hotkey itself,
    so Auto-Read on Copy must not read it a second time."""
    return time.monotonic() < _ignore_until


def _modifiers_down(user32) -> bool:
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN))


def _foreground_class(user32) -> str:
    buf = ctypes.create_unicode_buffer(256)
    try:
        user32.GetClassNameW(user32.GetForegroundWindow(), buf, 256)
    except Exception:
        return ""
    return buf.value


def _press(user32, vk_mod, vk, extended=False):
    ext = KEYEVENTF_EXTENDEDKEY if extended else 0
    user32.keybd_event(vk_mod, 0, 0, 0)
    user32.keybd_event(vk, 0, ext, 0)
    user32.keybd_event(vk, 0, ext | KEYEVENTF_KEYUP, 0)
    user32.keybd_event(vk_mod, 0, KEYEVENTF_KEYUP, 0)


def _wait_change(user32, seq, timeout) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if user32.GetClipboardSequenceNumber() != seq:
            return True
        time.sleep(0.02)
    return False


def copy_selection(*, release_timeout=0.8, copy_timeout=0.3) -> bool:
    """Copy the text selected in the active app, as if the user pressed Ctrl+C, so the hotkey
    reads the selection. True when the clipboard changed; with nothing selected the clipboard
    keeps what was copied before and that is read instead."""
    global _ignore_until
    try:
        user32 = ctypes.windll.user32
    except AttributeError:  # not Windows
        return False
    end = time.monotonic() + release_timeout
    while _modifiers_down(user32):  # Ctrl+Insert with the hotkey's Shift still held would paste
        if time.monotonic() > end:
            _log.info("hotkey keys still held; reading the clipboard without copying the selection")
            return False
        time.sleep(0.02)
    _ignore_until = time.monotonic() + release_timeout + 2 * copy_timeout + 1.0
    seq = user32.GetClipboardSequenceNumber()
    _press(user32, VK_CONTROL, VK_INSERT, extended=True)
    changed = _wait_change(user32, seq, copy_timeout)
    if not changed and _foreground_class(user32) not in CONSOLE_CLASSES:
        _press(user32, VK_CONTROL, VK_C)  # some apps only know Ctrl+C
        changed = _wait_change(user32, seq, copy_timeout)
    if changed:
        time.sleep(0.05)  # let the app finish writing every clipboard format
    _ignore_until = time.monotonic() + 1.0
    return changed
