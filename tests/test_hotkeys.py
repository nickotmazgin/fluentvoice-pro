"""v1.6.2: hotkey rules, the in-use warning, the Stop hotkey, reading the selection, live tray voices."""
import ctypes
import time
import types

import pytest

from fluentvoice import config, core, hotkeys


@pytest.mark.parametrize("chord", ["ctrl+shift+space", "ctrl+alt+r", "f9", "shift+f5", "ctrl+insert",
                                   "win+shift+pagedown", "f20", "Ctrl + Shift + Space"])
def test_valid_hotkeys(chord):
    assert hotkeys.parse_hotkey(chord) is not None and hotkeys.hotkey_problem(chord) == ""


@pytest.mark.parametrize("chord", ["space", "r", "5", "shift+a", "ctrl+shift", "ctrl+a+b", "ctrl+bogus", ""])
def test_hotkeys_that_would_break_typing_are_refused(chord):
    assert hotkeys.parse_hotkey(chord) is None and hotkeys.hotkey_problem(chord)


def test_single_key_message_suggests_a_modifier():
    assert "ctrl+shift+space" in hotkeys.hotkey_problem("space")


class _User32:
    """Just enough of user32 for hotkey registration and copying."""

    def __init__(self, taken=(), copies_on=(), window_class="Chrome_WidgetWin_1"):
        self.taken, self.copies_on, self.window_class = set(taken), set(copies_on), window_class
        self.registered, self.keys, self.seq = {}, [], 100

    def RegisterHotKey(self, hwnd, hk_id, mods, vk):
        if vk in self.taken:
            return 0
        self.registered[hk_id] = (mods, vk)
        return 1

    def UnregisterHotKey(self, hwnd, hk_id):
        self.registered.pop(hk_id, None)
        return 1

    def GetAsyncKeyState(self, vk):
        return 0

    def GetClipboardSequenceNumber(self):
        return self.seq

    def GetForegroundWindow(self):
        return 1

    def GetClassNameW(self, hwnd, buf, n):
        buf.value = self.window_class
        return len(self.window_class)

    def keybd_event(self, vk, scan, flags, extra):
        if not flags & hotkeys.KEYEVENTF_KEYUP:
            self.keys.append(vk)
            if vk in self.copies_on:
                self.seq += 1


def _tray_app(monkeypatch, user32, cfg):
    from fluentvoice import tray
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False)
    monkeypatch.setattr(tray, "load_config", lambda: dict(config.DEFAULT_CONFIG, **cfg))
    app = tray.FluentVoiceTrayApp.__new__(tray.FluentVoiceTrayApp)
    app._hotkey_id, app._stop_hotkey_id, app._hotkey_registered = 1, 2, {}
    app.toasts = []
    app.notify_user = lambda title, msg, important=True: app.toasts.append((title, msg))
    return app


def test_hotkey_taken_by_another_app_is_reported(monkeypatch):
    user32 = _User32(taken={0x20})
    app = _tray_app(monkeypatch, user32, {"hotkey": "ctrl+shift+space", "stop_hotkey": "ctrl+shift+x"})
    app.sync_hotkey_from_config()
    st = hotkeys.read_status()
    assert not st["read"]["ok"] and "another app" in st["read"]["error"]
    assert st["stop"]["ok"] and user32.registered == {2: (hotkeys.MOD_CONTROL | hotkeys.MOD_SHIFT
                                                          | hotkeys.MOD_NOREPEAT, 0x58)}
    assert app.toasts and "Speak / Stop" in app.toasts[0][0]


def test_stop_hotkey_is_optional_and_never_duplicates_the_main_one(monkeypatch):
    user32 = _User32()
    app = _tray_app(monkeypatch, user32, {"hotkey": "ctrl+shift+space", "stop_hotkey": "Ctrl+Shift+Space"})
    app.sync_hotkey_from_config()
    assert list(user32.registered) == [1] and app.toasts == []


def test_old_single_key_hotkey_is_not_registered_and_explained(monkeypatch):
    user32 = _User32()
    app = _tray_app(monkeypatch, user32, {"hotkey": "space"})
    app.sync_hotkey_from_config()
    assert user32.registered == {} and "alone" in hotkeys.read_status()["read"]["error"]


def test_hotkey_copies_the_selection_before_reading(monkeypatch):
    from fluentvoice import tray
    order = []
    monkeypatch.setattr(core, "is_any_speaking", lambda: False)
    monkeypatch.setattr(hotkeys, "copy_selection", lambda: order.append("copy"))
    monkeypatch.setattr(core, "toggle_speak_or_stop", lambda *a, **k: order.append("read"))
    monkeypatch.setattr(tray, "load_config", lambda: dict(config.DEFAULT_CONFIG))
    app = tray.FluentVoiceTrayApp.__new__(tray.FluentVoiceTrayApp)
    app.on_toggle_speech(from_hotkey=True)
    time.sleep(0.2)
    assert order == ["copy", "read"]
    app._last_toggle -= 1.0
    app.on_toggle_speech()  # a tray click reads the clipboard as before
    time.sleep(0.2)
    assert order == ["copy", "read", "read"]


def test_copy_selection_uses_ctrl_insert_first(monkeypatch):
    user32 = _User32(copies_on={hotkeys.VK_INSERT})
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False)
    assert hotkeys.copy_selection(copy_timeout=0.1) is True
    assert hotkeys.VK_C not in user32.keys and hotkeys.recently_copied()


def test_copy_selection_falls_back_to_ctrl_c_but_never_in_a_console(monkeypatch):
    user32 = _User32(copies_on={hotkeys.VK_C})
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False)
    assert hotkeys.copy_selection(copy_timeout=0.1) is True and hotkeys.VK_C in user32.keys
    console = _User32(copies_on={hotkeys.VK_C}, window_class="CASCADIA_HOSTING_WINDOW_CLASS")
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=console), raising=False)
    assert hotkeys.copy_selection(copy_timeout=0.1) is False and hotkeys.VK_C not in console.keys


def test_windows_voices_menu_refreshes_when_a_voice_is_added(monkeypatch):
    from fluentvoice import tray
    found = [("Windows Zira (English US)", "Microsoft Zira Desktop")]
    monkeypatch.setattr(core, "get_installed_sapi_voices", lambda: list(found))
    app = tray.FluentVoiceTrayApp.__new__(tray.FluentVoiceTrayApp)
    assert app._refresh_windows_voices() is True
    assert app._refresh_windows_voices() is False
    found.append(("Windows Asaf (Hebrew IL)", "Microsoft Asaf - Hebrew (Israel)"))
    assert app._refresh_windows_voices() is True
    labels = [i.text for i in app._windows_voice_items() if hasattr(i, "text")]
    assert "Windows Asaf (Hebrew IL)" in labels and any("Add Windows voices" in t for t in labels)
