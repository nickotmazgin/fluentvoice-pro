"""Unit tests for FluentVoice language / script detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from fluentvoice import voices
from fluentvoice.core import choose_voice, detect_language, detect_script, resolve_route_voice
from fluentvoice.config import DEFAULT_PREFERRED_VOICES, DEFAULT_CONFIG


def test_hebrew_script():
    assert detect_script("זה טקסט בעברית") == "hebrew"
    assert detect_language("זה טקסט בעברית") == "hebrew"


def test_arabic_script():
    assert detect_script("هذا نص عربي") == "arabic"
    assert detect_language("هذا نص عربي") == "arabic"


def test_cjk_script():
    assert detect_script("こんにちは世界") == "cjk"
    assert detect_language("こんにちは世界") == "cjk"


def test_english_latin():
    text = "The quick brown fox jumps over the lazy dog and that is the way it is."
    assert detect_script(text) == "latin"
    assert detect_language(text) == "english"


def test_spanish_heuristic_or_langdetect():
    text = (
        "El niño está en la casa y también quiere más comida para la familia "
        "porque es importante que los niños coman bien todos los días."
    )
    lang = detect_language(text)
    assert lang in ("spanish", "english")  # langdetect can vary on short text
    # Stronger Spanish sample
    strong = "¿Cómo estás? El libro está sobre la mesa y los niños también están aquí."
    assert detect_language(strong) == "spanish"


def test_french_detection():
    text = (
        "Bonjour, je suis très heureux d'être ici avec vous aujourd'hui "
        "pour parler de la culture française et des traditions."
    )
    assert detect_language(text) == "french"


def test_resolve_route_voice_uses_preferences():
    cfg = DEFAULT_CONFIG.copy()
    cfg["preferred_voices"] = DEFAULT_PREFERRED_VOICES.copy()
    cfg["preferred_voices"]["hebrew"] = "he-IL-HilaNeural"
    voice, label = resolve_route_voice("hebrew", cfg)
    assert voice == "he-IL-HilaNeural"
    assert label == "Hila"  # route label is the voice name now


@pytest.mark.parametrize("family", sorted(voices.SAMPLE_TEXT))
def test_every_sample_sentence_detects_as_its_own_language(family):
    assert detect_language(voices.SAMPLE_TEXT[family]) == family


@pytest.mark.parametrize("text, expected", [
    ("欢迎使用 FluentVoice Pro", "chinese"),
    ("这是 Windows 上的 FluentVoice Pro 语音朗读工具。", "chinese"),
    ("FluentVoice Pro へようこそ", "cjk"),
    ("삼성 Galaxy S24 Ultra 리뷰", "korean"),
    ("Yesterday I met my friend 李明 at the train station near the office.", "english"),
])
def test_cjk_characters_outweigh_latin_brand_names(text, expected):
    assert detect_language(text) == expected


@pytest.mark.parametrize("text, code, name", [
    ("Dit is een korte zin in het Nederlands om de taaldetectie te testen vandaag.", "nl", "Dutch"),
    ("To jest krótkie zdanie po polsku, które sprawdza wykrywanie języka w programie.", "pl", "Polish"),
    ("Bu, programdaki dil algılamasını test etmek için yazılmış kısa bir Türkçe cümledir.", "tr", "Turkish"),
    ("Đây là một câu ngắn bằng tiếng Việt để kiểm tra tính năng nhận diện ngôn ngữ.", "vi", "Vietnamese"),
    ("Det här är en kort mening på svenska för att testa språkigenkänningen i programmet.", "sv", "Swedish"),
    ("Tämä on lyhyt suomenkielinen lause, jolla testataan ohjelman kielentunnistusta.", "fi", "Finnish"),
])
def test_unlisted_language_is_named(text, code, name):
    lang = detect_language(text)
    assert lang == f"other:{code}"
    assert voices.language_name(lang) == name


@pytest.mark.parametrize("text", [
    "The meeting is at 3pm in room B, bring the slides and the budget numbers.",
    "run the build on windows then push the feature branch and open a pull request",
    "Hi Tom, see you tomorrow",
    "OK thanks",
])
def test_plain_english_is_not_reported_as_another_language(text):
    assert detect_language(text) == "english"


def test_language_name():
    assert voices.language_name("hebrew") == "Hebrew"
    assert voices.language_name("other:nl") == "Dutch"
    assert voices.language_name("other:xx") == "another language"


def _cfg():
    cfg = DEFAULT_CONFIG.copy()
    cfg["preferred_voices"] = DEFAULT_PREFERRED_VOICES.copy()
    return cfg


DUTCH = "Dit is een korte zin in het Nederlands om de taaldetectie te testen vandaag."


def test_unlisted_language_routes_to_a_multilingual_voice():
    cfg = _cfg()
    cfg["preferred_voices"]["english"] = "en-US-AriaNeural"
    assert choose_voice("other:nl", "en-US-AriaNeural", cfg, DUTCH) == (voices.DEFAULT_VOICE, True)
    assert choose_voice("other:nl", "he-IL-HilaNeural", cfg, DUTCH) == (voices.DEFAULT_VOICE, True)


def test_unlisted_language_prefers_a_multilingual_english_choice():
    cfg = _cfg()
    cfg["preferred_voices"]["english"] = "en-US-EmmaMultilingualNeural"
    assert choose_voice("other:nl", "en-US-AriaNeural", cfg, DUTCH) == ("en-US-EmmaMultilingualNeural", True)


def test_unlisted_language_keeps_a_multilingual_voice_and_short_text():
    cfg = _cfg()
    assert choose_voice("other:nl", "en-US-EmmaMultilingualNeural", cfg, DUTCH) == (
        "en-US-EmmaMultilingualNeural", False)
    assert choose_voice("other:nl", "en-US-AriaNeural", cfg, "Goedemorgen allemaal") == ("en-US-AriaNeural", False)


def test_short_greek_still_routes_to_a_multilingual_voice():
    cfg = _cfg()
    cfg["preferred_voices"]["english"] = "en-US-AriaNeural"
    assert choose_voice("other:el", "en-US-AriaNeural", cfg, "Καλημέρα σας") == (voices.DEFAULT_VOICE, True)


def test_greek_is_named():
    text = "Αυτή είναι μια σύντομη πρόταση στα ελληνικά για να δοκιμάσουμε την αναγνώριση γλώσσας."
    assert detect_language(text) == "other:el"
    assert voices.language_name("other:el") == "Greek"
