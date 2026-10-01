"""v1.4.28: passwords / keys on the clipboard are never read aloud (nor sent to the cloud voice);
Icelandic voices and detection."""
import sys

import pytest

from fluentvoice import core, voices

SECRETS = [
    "S3cret-pass", "Tr0ub4dor&3", "P@ssw0rd123",
    "ghp_" + "a1B2" * 9,                                   # GitHub token
    "sk-proj-" + "Ab1" * 10,                               # OpenAI-style key
    "AKIA" + "ABCDEFGHIJKLMNOP",                           # AWS access key id
    "xoxb-1234567890-abcdefghij",                          # Slack token
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",  # JWT
    "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",   # hash / hex token
]
NORMAL = [
    "Hello world, this is a sentence.", "Mississippi's", "getElementById", "snake_case_name",
    "https://github.com/nickotmazgin/fluentvoice-pro", "nickotmazgin@example.com",
    r"C:\Users\Public\Documents\file.txt", "/usr/local/bin/python3", "Antidisestablishmentarianism",
    "ברוכים הבאים", "Hi", "12345678", "2026-10-01", "3.14159265",
]


@pytest.mark.parametrize("text", SECRETS)
def test_secrets_are_recognised(text):
    assert core.looks_like_secret(text)


@pytest.mark.parametrize("text", NORMAL)
def test_normal_text_is_not_a_secret(text):
    assert not core.looks_like_secret(text)


@pytest.fixture
def clip(monkeypatch):
    state = {"text": "", "private": False, "spoken": [], "toasts": []}
    monkeypatch.setattr(core, "get_clipboard_text", lambda: state["text"])
    monkeypatch.setattr(core, "clipboard_is_private", lambda: state["private"])
    monkeypatch.setattr(core, "is_any_speaking", lambda: False)
    monkeypatch.setattr(core, "speak_text", lambda text, *a, **k: state["spoken"].append(text))
    monkeypatch.setattr(core, "trigger_notification", lambda title, msg, **k: state["toasts"].append(title))
    return state


def test_hotkey_and_tray_click_skip_a_password(clip):
    clip["text"] = "Tr0ub4dor&3"
    assert core.toggle_speak_or_stop(blocking=True)["status"] == "skipped"
    assert clip["spoken"] == [] and clip["toasts"] == ["🔒 Skipped private text"]


def test_hotkey_and_tray_click_skip_text_marked_private(clip):
    clip["text"], clip["private"] = "an ordinary looking phrase", True
    assert core.toggle_speak_or_stop(blocking=True)["status"] == "skipped"
    assert clip["spoken"] == []


def test_hotkey_and_tray_click_still_read_normal_text(clip):
    clip["text"] = "Please read this paragraph aloud."
    core.toggle_speak_or_stop(blocking=True)
    assert clip["spoken"] == ["Please read this paragraph aloud."]


def test_command_line_clip_skips_a_password(clip, monkeypatch, capsys):
    from fluentvoice import cli
    clip["text"] = "ghp_" + "a1B2" * 9
    monkeypatch.setattr(sys, "argv", ["fluentvoice", "--clip"])
    cli.main()
    assert clip["spoken"] == [] and "password or key" in capsys.readouterr().out


def test_auto_read_skips_a_password(monkeypatch):
    from fluentvoice import tray
    app = tray.FluentVoiceTrayApp.__new__(tray.FluentVoiceTrayApp)
    app.last_clipboard_hash, app._last_autoread_ts = None, 0.0
    monkeypatch.setattr(core, "clipboard_is_private", lambda: False)
    monkeypatch.setattr(core, "is_any_speaking", lambda: False)
    assert not app.autoread_should_read("P@ssw0rd123")
    assert app.autoread_should_read("A normal sentence to read.")


def test_icelandic_voices_and_detection():
    assert [v for v, _ in voices.voices_for("icelandic")] == ["is-IS-GunnarNeural", "is-IS-GudrunNeural"]
    assert voices.DEFAULT_PREFERRED["icelandic"] == "is-IS-GunnarNeural"
    assert core.detect_language(voices.SAMPLE_TEXT["icelandic"]) == "icelandic"
    assert core.detect_language("Það er gott veður í dag og við förum út að ganga.") == "icelandic"
    # an English sentence that mentions a name with þ stays English
    assert core.detect_language("The Norse god Þór appears in many old stories and modern films alike.") == "english"
