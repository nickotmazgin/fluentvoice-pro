"""v1.4.25: Auto-Read pipeline, mid-read voice changes, offline voices, Indian languages + Thai."""
import json
import time

import pytest

from fluentvoice import config, core, voices

# ---- voices / languages ------------------------------------------------------------------------

NEW = ("hindi", "marathi", "bengali", "tamil", "telugu", "gujarati", "kannada", "malayalam", "thai")


def test_indian_languages_and_thai_have_male_and_female_voices():
    for fam in NEW:
        assert fam in voices.LANGUAGES and fam in voices.SAMPLE_TEXT and fam in voices.DEFAULT_PREFERRED
        assert len(voices.voices_for(fam)) == 2, fam


@pytest.mark.parametrize("voice,offline", [
    ("en-US-AndrewMultilingualNeural", False),
    ("th-TH-PremwadeeNeural", False),
    ("en-US-DavisNeural", False),                                  # retired id, still a neural id
    ("Microsoft George - English (United Kingdom)", True),         # OneCore (was sent to the cloud before)
    ("Microsoft Zira Desktop - English (United States)", True),
    ("Zira", True),
])
def test_offline_voices_are_recognised(voice, offline):
    assert voices.is_offline(voice) is offline


def test_english_accent_labels_say_english():
    assert voices.label_for("en-IN-PrabhatNeural") == "Prabhat (Indian English HD Male)"
    assert voices.label_for("en-IE-EmilyNeural") == "Emily (Irish English HD Female)"
    assert voices.family_of("en-IN-NeerjaNeural") == "english"


@pytest.mark.parametrize("fam", NEW)
def test_sample_text_is_detected_as_its_language(fam):
    assert core.detect_language(voices.SAMPLE_TEXT[fam]) == fam


def test_marathi_voice_keeps_devanagari_text():
    assert voices.can_read("mr-IN-AarohiNeural", "hindi")
    assert voices.can_read("hi-IN-SwaraNeural", "marathi")
    assert not voices.can_read("en-US-GuyNeural", "hindi")

# ---- text cleaner ---------------------------------------------------------------------------------


def test_cleaner_keeps_code_and_maths_symbols():
    out = core.clean_text_for_speech("Use my_var and snake_case in C#: 2*3 = 6, see #OpenSource")
    assert "my_var" in out and "snake_case" in out and "C#" in out and "2*3" in out
    assert "#OpenSource" not in out and "OpenSource" in out


def test_cleaner_still_strips_markdown():
    out = core.clean_text_for_speech("## Title\n* item one\n**bold** *it* _em_ __strong__")
    assert out == "Title item one bold it em strong"

# ---- chunking -------------------------------------------------------------------------------------


def test_chunks_grow_and_stay_small_enough_to_prepare_in_time():
    sizes = [len(c) for c in core.split_for_streaming("A sentence that is read aloud. " * 300)]
    assert sizes[0] <= core.FIRST_CHUNK_CHARS and sizes[1] <= core.SECOND_CHUNK_CHARS
    assert max(sizes) <= core.CHUNK_CHARS < 1000


def test_danda_ends_a_sentence():
    text = "पहला वाक्य यहाँ है। " * 40
    assert all(c.endswith("।") for c in core.split_for_streaming(text)[:-1])


def test_sentence_start_before():
    t = "One two. Three four. Five six."
    assert core.sentence_start_before(t, t.index("four")) == t.index("Three")
    assert core.sentence_start_before(t, 3) == 0

# ---- pipeline: parallel prefetch, mid-read changes, offline routing, length guard -----------------


@pytest.fixture
def engine(tmp_path, monkeypatch):
    cfgfile = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", cfgfile)
    config.save_config({**config.load_config(), "voice": "en-US-BrianMultilingualNeural"})
    calls = {"synth": [], "play": [], "sapi": []}
    monkeypatch.setattr(core, "_halt_audio_engines", lambda: None)
    monkeypatch.setattr(core, "trigger_notification", lambda *a, **k: None)
    monkeypatch.setattr(core, "CACHE_DIR", tmp_path)

    def fake_synth(text, voice, out, **kw):
        calls["synth"].append((voice, text, kw.get("volume")))
        open(out, "wb").write(b"ID3")
        return True, ""

    def fake_play(path, gen, volume=100, start_ts=None, on_progress=None, interrupt=None, live_volume=None):
        calls["play"].append(path)
        hook = calls.get("during_play")
        if hook:
            hook(len(calls["play"]))
        for _ in range(3):
            if on_progress:
                on_progress(500, 1000)
            if interrupt and interrupt():
                return False
            time.sleep(0.3)  # > the settings poll interval
        return True

    def fake_sapi(text, **kw):
        calls["sapi"].append((kw.get("voice_pref"), text))
        return True

    monkeypatch.setattr(core, "_synthesize_to_file", fake_synth)
    monkeypatch.setattr(core, "play_audio_file", fake_play)
    monkeypatch.setattr(core, "speak_offline_sapi", fake_sapi)
    return calls


LONG = " ".join(f"Sentence number {i} is read aloud by the voice." for i in range(60))


def test_volume_is_applied_once_at_playback_not_baked_into_audio(engine):
    config.update_config({"volume": 40})
    core.speak_text("Hello there, this is a short test.")
    assert {v for _, _, v in engine["synth"]} == {100}


def test_voice_change_mid_read_continues_with_the_new_voice(engine):
    engine["during_play"] = lambda n: n == 1 and config.update_config({"voice": "en-US-AvaMultilingualNeural"})
    res = core.speak_text(LONG)
    assert res["status"] == "success"
    used = [v for v, _, _ in engine["synth"]]
    assert used[0] == "en-US-BrianMultilingualNeural" and used[-1] == "en-US-AvaMultilingualNeural"
    first_ava = next(t for v, t, _ in engine["synth"] if v == "en-US-AvaMultilingualNeural")
    assert first_ava.startswith("Sentence number")  # resumes at a sentence start


def test_switch_to_offline_voice_mid_read(engine):
    george = "Microsoft George - English (United Kingdom)"
    engine["during_play"] = lambda n: n == 1 and config.update_config({"voice": george, "engine": "offline"})
    res = core.speak_text(LONG)
    assert res["mode"] == "offline"
    assert engine["sapi"] and engine["sapi"][0][0] == george


def test_onecore_voice_speaks_offline_not_via_the_cloud(engine):
    george = "Microsoft George - English (United Kingdom)"
    config.update_config({"voice": george, "engine": "neural"})  # engine left stale on purpose
    res = core.speak_text("A sentence for the offline voice.")
    assert res["mode"] == "offline" and engine["synth"] == []
    assert engine["sapi"][0][0] == george


def test_very_long_text_is_trimmed(engine, monkeypatch):
    monkeypatch.setattr(core, "MAX_SPEAK_CHARS", 300)
    monkeypatch.setattr(core, "split_for_streaming", lambda text, *a, **k: [text])
    core.speak_text(LONG)
    assert len(engine["synth"][0][1]) <= 300

# ---- settings saves never overwrite the other process's changes ----------------------------------


@pytest.fixture
def cfgfile(tmp_path, monkeypatch):
    f = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", f)
    return f


def test_tray_voice_pick_keeps_auto_read_set_in_settings(cfgfile):
    from fluentvoice import tray
    app = tray.FluentVoiceTrayApp.__new__(tray.FluentVoiceTrayApp)
    app.cfg = config.load_config()                      # tray's cached copy: Auto-Read off
    config.update_config({"auto_read_copy": True})      # turned on in Settings afterwards
    app.notify_user = lambda *a, **k: None
    app.set_voice("Microsoft George - English (United Kingdom)", "George")(None, None)
    saved = json.loads(cfgfile.read_text())
    assert saved["auto_read_copy"] is True
    assert saved["engine"] == "offline"


def test_settings_window_saves_only_its_own_changes(cfgfile):
    from fluentvoice.gui import FluentVoiceSettingsWindow
    import copy
    win = FluentVoiceSettingsWindow.__new__(FluentVoiceSettingsWindow)
    win.cfg = config.load_config()
    win._cfg_base = copy.deepcopy(win.cfg)
    config.update_config({"voice": "he-IL-AvriNeural"})  # changed in the tray meanwhile
    win.cfg["rate_mult"] = 1.3
    win._persist_cfg()
    saved = json.loads(cfgfile.read_text())
    assert saved["voice"] == "he-IL-AvriNeural" and saved["rate_mult"] == 1.3

# ---- Auto-Read on Copy filter ----------------------------------------------------------------------


@pytest.fixture
def watcher(monkeypatch):
    from fluentvoice import tray
    app = tray.FluentVoiceTrayApp.__new__(tray.FluentVoiceTrayApp)
    app.last_clipboard_hash = None
    app._last_autoread_ts = 0.0
    speaking = {"on": False}
    monkeypatch.setattr(core, "is_any_speaking", lambda: speaking["on"])
    monkeypatch.setattr(core, "speak_text", lambda *a, **k: None)
    monkeypatch.setattr(core, "clipboard_is_private", lambda: False)  # never read the real clipboard
    return app, speaking


def test_same_text_copied_again_is_read_again_after_it_finished(watcher):
    app, speaking = watcher
    assert app.autoread_should_read("Read this paragraph please.")
    app.autoread_start("Read this paragraph please.")
    app._last_autoread_ts -= 5                     # a few seconds later
    speaking["on"] = True
    assert not app.autoread_should_read("Read this paragraph please.")  # still reading it: no restart
    speaking["on"] = False
    assert app.autoread_should_read("Read this paragraph please.")      # finished: read again (new voice)


def test_duplicate_clipboard_burst_and_symbols_are_ignored(watcher):
    app, _ = watcher
    app.autoread_start("Some copied sentence.")
    assert not app.autoread_should_read("Some copied sentence.")   # same text within 1.5 s
    assert not app.autoread_should_read("  --- *** ...  ")         # no letters or digits
    assert app.autoread_should_read("A different sentence.")


# ---- private clipboard (password managers) -------------------------------------------------------

class _FakeClipboard:
    """Stands in for win32clipboard so the real clipboard is never touched."""

    def __init__(self, formats, history_flag=None):
        self.formats, self.history_flag, self.ids = set(formats), history_flag, {}

    def RegisterClipboardFormat(self, name):
        return self.ids.setdefault(name, 0xC000 + len(self.ids))

    def IsClipboardFormatAvailable(self, fmt):
        names = {v: k for k, v in self.ids.items()}
        return names.get(fmt) in self.formats

    def OpenClipboard(self):
        pass

    def CloseClipboard(self):
        pass

    def GetClipboardData(self, fmt):
        return self.history_flag


@pytest.mark.parametrize("formats,flag,private", [
    (set(), None, False),
    ({"ExcludeClipboardContentFromMonitorProcessing"}, None, True),   # Bitwarden, 1Password, KeePass…
    ({"Clipboard Viewer Ignore"}, None, True),
    ({"CanIncludeInClipboardHistory"}, (0).to_bytes(4, "little"), True),
    ({"CanIncludeInClipboardHistory"}, (1).to_bytes(4, "little"), False),
])
def test_private_clipboard_is_never_read(monkeypatch, formats, flag, private):
    import sys
    monkeypatch.setitem(sys.modules, "win32clipboard", _FakeClipboard(formats, flag))
    assert core.clipboard_is_private() is private


def test_autoread_skips_private_and_tiny_copies(watcher, monkeypatch):
    app, _ = watcher
    monkeypatch.setattr(core, "clipboard_is_private", lambda: True)
    assert not app.autoread_should_read("Pa55word-from-a-manager")
    monkeypatch.setattr(core, "clipboard_is_private", lambda: False)
    assert not app.autoread_should_read("a")
    assert app.autoread_should_read("Hi")
