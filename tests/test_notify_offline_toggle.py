"""v1.4.22: notification levels, offline (OneCore) voices, click/toggle behaviour."""
import json
import threading
import time

import pytest

from fluentvoice import config, core, voices


@pytest.fixture
def cfgfile(tmp_path, monkeypatch):
    f = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", f)
    return f


# ---- notification levels ---------------------------------------------------------------------

def test_old_off_switch_migrates_to_off(cfgfile):
    cfgfile.write_text(json.dumps({"show_notifications": False}))
    assert config.load_config()["notification_level"] == "off"


def test_old_on_switch_migrates_to_important(cfgfile):
    cfgfile.write_text(json.dumps({"show_notifications": True}))
    c = config.load_config()
    assert c["notification_level"] == "important" and c["show_notifications"] is True


def test_new_installs_default_to_important(cfgfile):
    assert config.load_config()["notification_level"] == "important"


@pytest.mark.parametrize("level,info_shown,important_shown", [
    ("all", True, True), ("important", False, True), ("off", False, False)])
def test_levels_filter_toasts(cfgfile, monkeypatch, level, info_shown, important_shown):
    cfgfile.write_text(json.dumps({"notification_level": level}))
    shown = []
    monkeypatch.setattr(core, "_notify_callback", lambda t, m: shown.append(t))
    monkeypatch.setattr(core, "_last_notify_ts", 0.0)
    core.trigger_notification("🔊 Speaking", '"hello"', force=True)
    assert ("🔊 Speaking" in shown) is info_shown
    core.trigger_notification("⚠ Speech failed", "check internet", force=True, important=True)
    assert ("⚠ Speech failed" in shown) is important_shown


# ---- offline voices ----------------------------------------------------------------------------

@pytest.mark.parametrize("desc,label", [
    ("Microsoft George - English (United Kingdom)", "Windows George (English UK)"),
    ("Microsoft Zira Desktop - English (United States)", "Windows Zira Desktop (English US)"),
    ("Microsoft Asaf - Hebrew (Israel)", "Windows Asaf (Hebrew IL)"),
    ("Some Vendor Voice", "Some Vendor Voice"),
])
def test_offline_voice_labels(desc, label):
    assert core.offline_voice_label(desc) == label


def test_offline_voice_language_family():
    assert voices.family_of("Microsoft Asaf - Hebrew (Israel)") == "hebrew"
    assert voices.family_of("Microsoft Irina - Russian (Russia)") == "cyrillic"
    assert voices.family_of("Microsoft George - English (United Kingdom)") == "english"
    assert voices.can_read("Microsoft Asaf - Hebrew (Israel)", "hebrew")


def test_offline_voices_listed_on_this_pc():
    listed = core.get_installed_sapi_voices()
    assert listed and all(label.startswith("Windows ") or label for label, _ in listed)


# ---- toggle / click behaviour --------------------------------------------------------------------

def test_request_counts_as_speaking_while_voice_is_prepared(monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(core, "_speak_text_impl", lambda *a, **k: (gate.wait(2), {"status": "success"})[1])
    t = threading.Thread(target=core.speak_text, args=("hello",))
    t.start()
    time.sleep(0.1)
    assert core.is_any_speaking()  # a second click now means "stop", not "start again"
    gate.set()
    t.join(2)
    assert core._active_requests == 0


def test_tray_double_click_counts_once(monkeypatch):
    from fluentvoice import tray
    calls = []
    monkeypatch.setattr(core, "toggle_speak_or_stop", lambda *a, **k: calls.append(1))
    app = tray.FluentVoiceTrayApp.__new__(tray.FluentVoiceTrayApp)
    app.on_toggle_speech()
    app.on_toggle_speech()  # second half of a double-click, 0 ms later
    time.sleep(0.2)
    assert len(calls) == 1
    app._last_toggle -= 1.0  # a deliberate click a second later still works
    app.on_toggle_speech()
    time.sleep(0.2)
    assert len(calls) == 2
