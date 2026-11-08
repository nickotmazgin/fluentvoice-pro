"""v1.6.7: limits that keep long or rapid text from overloading anything, Auto-Read in the Reader, disk space."""
import collections
import types

import pytest

from fluentvoice import config, core, gui, local_catalog as cat, localtts, tray
from test_autoread_voices import LONG, engine  # noqa: F401  (engine is a pytest fixture)


# ---- online requests -----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_request_window():
    core._online_request_times.clear()
    yield
    core._online_request_times.clear()


def test_online_requests_are_limited_across_readings(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(core.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(core.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    for _ in range(core.ONLINE_REQUESTS_PER_WINDOW):
        assert core._wait_for_online_slot() is True
    assert clock["t"] == 1000.0  # the allowance itself never waits
    assert core._wait_for_online_slot() is True
    assert clock["t"] >= 1000.0 + core.ONLINE_REQUEST_WINDOW_SEC  # the next one waited for the window


def test_waiting_for_an_online_slot_stops_when_the_reading_is_stopped():
    for _ in range(core.ONLINE_REQUESTS_PER_WINDOW):
        core._wait_for_online_slot()
    assert core._wait_for_online_slot(abort_check=lambda: True) is False
    assert core._synthesize_to_file("x", "v", "out", rate="+0%", pitch="+0Hz", volume=100,
                                    abort_check=lambda: True) == (False, "aborted")


# ---- how much text is read -----------------------------------------------------------------------

def test_auto_read_has_its_own_smaller_limit(monkeypatch):
    started = {}

    class FakeThread:
        def __init__(self, target, args=(), kwargs=None, **_):
            started.update(target=target, kwargs=kwargs or {})

        def start(self):
            started["started"] = True

    monkeypatch.setattr(tray.threading, "Thread", FakeThread)
    app = tray.FluentVoiceTrayApp.__new__(tray.FluentVoiceTrayApp)
    app.autoread_start("Some copied text.")
    assert started["started"] and started["target"] is core.speak_text
    assert started["kwargs"] == {"max_chars": core.AUTOREAD_MAX_CHARS}
    assert core.AUTOREAD_MAX_CHARS < core.MAX_SPEAK_CHARS


def test_max_chars_limits_the_reading(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(core, "split_for_streaming", lambda text, *a, **k: [text])
    core.speak_text(LONG, max_chars=300)
    assert len(engine["synth"][0][1]) <= 300


def test_huge_text_is_trimmed_before_the_costly_cleaning(engine, monkeypatch):  # noqa: F811
    seen = {}
    real = core.clean_text_for_speech
    monkeypatch.setattr(core, "clean_text_for_speech", lambda t: (seen.__setitem__("n", len(t)), real(t))[1])
    monkeypatch.setattr(core, "split_for_streaming", lambda text, *a, **k: [text])
    core.speak_text("A short sentence here. " * 20_000, max_chars=1_000)
    assert seen["n"] <= 1_000 * core.RAW_TEXT_FACTOR
    assert len(engine["synth"][0][1]) <= 1_000


def test_limit_text_cuts_at_a_sentence_start():
    text = "First sentence here. Second sentence here. Third sentence here."
    assert core.limit_text(text, 1000) == text
    cut = core.limit_text(text, 30)
    assert len(cut) <= 30 and cut.startswith("First sentence here.") and "Second" not in cut


# ---- Auto-Read text in the Direct Text Reader ----------------------------------------------------

class FakeTextbox:
    def __init__(self, text=""):
        self.text = text

    def get(self, *_):
        return self.text

    def delete(self, *_):
        self.text = ""

    def insert(self, _index, text):
        self.text += text

    def tag_config(self, *a, **k):
        pass

    tag_add = tag_remove = tag_config


def _reader(text):
    win = types.SimpleNamespace(reader_textbox=FakeTextbox(text), _update_reader_meta=lambda: None)
    win._reader_accepts_autofill = lambda: gui.FluentVoiceSettingsWindow._reader_accepts_autofill(win)
    return win, gui.FluentVoiceSettingsWindow._fill_reader_from_autoread


@pytest.fixture
def clipboard_not_private(monkeypatch):
    monkeypatch.setattr(core, "clipboard_is_private", lambda: False)


@pytest.mark.parametrize("start", ["", gui.READER_SAMPLE_TEXT])
def test_reader_autofill_replaces_the_sample_or_an_empty_box(clipboard_not_private, start):
    win, fill = _reader(start)
    assert fill(win, "A copied sentence.") is True
    assert win.reader_textbox.text == "A copied sentence."


def test_reader_autofill_replaces_its_own_text_but_never_what_the_user_typed(clipboard_not_private):
    win, fill = _reader("")
    fill(win, "The first copy.")
    assert fill(win, "The second copy.") is True and win.reader_textbox.text == "The second copy."
    typed = "The second copy, and now I am typing my own words."
    win.reader_textbox.text = typed
    assert fill(win, "The third copy.") is False
    assert win.reader_textbox.text == typed


def test_reader_autofill_skips_private_and_password_like_text(monkeypatch):
    monkeypatch.setattr(core, "clipboard_is_private", lambda: True)
    win, fill = _reader("")
    assert fill(win, "A normal sentence from a password manager.") is False
    monkeypatch.setattr(core, "clipboard_is_private", lambda: False)
    assert fill(win, "Pa55word-from-a-manager") is False
    assert win.reader_textbox.text == ""


def test_reader_autofill_shows_only_what_auto_read_reads(clipboard_not_private):
    win, fill = _reader("")
    assert fill(win, "A sentence to read. " * 2_000) is True
    assert len(win.reader_textbox.text) <= core.AUTOREAD_MAX_CHARS


def test_reader_autofill_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    assert config.load_config()["autoread_show_in_reader"] is False


def test_reader_language_label_samples_long_text_and_shows_the_limit(monkeypatch):
    seen, labels = {}, {}
    monkeypatch.setattr(core, "detect_language", lambda t: (seen.__setitem__("n", len(t)), "english")[1])
    win = types.SimpleNamespace(
        reader_textbox=FakeTextbox("word " * 30_000), _apply_bidi=lambda *a: None,
        reader_meta_lbl=types.SimpleNamespace(configure=lambda text: labels.__setitem__("text", text)),
        _refresh_reader_voice_label=lambda: None)
    gui.FluentVoiceSettingsWindow._update_reader_meta(win)
    assert seen["n"] <= gui.READER_SAMPLE_CHARS
    assert f"reads first {core.MAX_SPEAK_CHARS:,}" in labels["text"]
    win.reader_textbox.text = "A short text."
    gui.FluentVoiceSettingsWindow._update_reader_meta(win)
    assert "reads first" not in labels["text"]


# ---- disk space before a voice download ----------------------------------------------------------

def _usage(free):
    return collections.namedtuple("usage", "total used free")(10**12, 10**12 - free, free)


def test_download_stops_before_starting_when_the_disk_is_too_full(monkeypatch, tmp_path):
    monkeypatch.setattr(localtts, "VOICES_DIR", tmp_path)
    monkeypatch.setattr(localtts.shutil, "disk_usage", lambda _p: _usage(10_000_000))
    monkeypatch.setattr(localtts, "_download", lambda *a, **k: pytest.fail("download started without enough space"))
    monkeypatch.setattr(localtts, "is_installed", lambda _v: False)
    with pytest.raises(localtts.DownloadError, match="Not enough disk space"):
        localtts.install("kokoro:af_heart")


def test_download_goes_ahead_with_enough_disk_space(monkeypatch, tmp_path):
    monkeypatch.setattr(localtts, "VOICES_DIR", tmp_path)
    monkeypatch.setattr(localtts.shutil, "disk_usage", lambda _p: _usage(10**11))
    localtts._check_disk_space("kokoro:af_heart")  # no exception


def test_kokoro_needs_room_for_the_pack_and_its_unpacked_copy():
    needed = localtts.disk_space_needed("kokoro:af_heart")
    assert needed >= cat.KOKORO_PACK["size"] + sum(size for _, size in cat.KOKORO_PACK["files"].values())
