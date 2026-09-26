"""Voice catalog + auto-route decisions."""
from collections import Counter

from fluentvoice import voices
from fluentvoice.config import DEFAULT_CONFIG, DEFAULT_PREFERRED_VOICES, load_config
from fluentvoice.core import choose_voice, detect_language, detect_script

LONG_EN = "The quick brown fox jumps over the lazy dog while the sun sets slowly."
LONG_ES = "¿Cómo estás? El libro está sobre la mesa y los niños también están aquí hoy."


def cfg():
    c = DEFAULT_CONFIG.copy()
    c["preferred_voices"] = DEFAULT_PREFERRED_VOICES.copy()
    return c


def test_catalog_is_consistent():
    ids = [v for v, _, _ in voices.CATALOG]
    assert len(ids) == len(set(ids)), "duplicate voice ids"
    assert all(fam in voices.LANGUAGES for _, _, fam in voices.CATALOG)
    assert set(voices.DEFAULT_PREFERRED) == set(voices.LANGUAGES)
    assert set(voices.SAMPLE_TEXT) == set(voices.LANGUAGES)
    for fam in voices.LANGUAGES:  # every language offers a male and a female voice
        labels = [label for _, label in voices.voices_for(fam)]
        assert any(" Male" in l for l in labels) and any("Female" in l for l in labels), fam
    for target in list(voices.DEFAULT_PREFERRED.values()) + list(voices.RETIRED.values()):
        assert target in ids


def test_retired_voices_migrate(tmp_path, monkeypatch):
    from fluentvoice import config
    f = tmp_path / "config.json"
    f.write_text('{"voice": "en-US-DavisNeural", "preferred_voices": {"english": "en-AU-WilliamNeural"}}')
    monkeypatch.setattr(config, "CONFIG_FILE", f)
    c = load_config()
    assert c["voice"] == "en-US-ChristopherNeural"
    assert c["preferred_voices"]["english"] == "en-AU-WilliamMultilingualNeural"
    assert c["preferred_voices"]["korean"] == "ko-KR-InJoonNeural"  # new languages get defaults


def test_script_detection_splits_east_asian():
    assert detect_script("こんにちは世界") == "cjk"          # kana → Japanese
    assert detect_language("你好，欢迎使用这个程序") == "chinese"
    assert detect_language("안녕하세요 반갑습니다") == "korean"   # used to be read as "latin"
    assert detect_language("Привет, как дела?") == "cyrillic"


def test_same_language_keeps_chosen_voice():
    assert choose_voice("english", "en-GB-SoniaNeural", cfg(), LONG_EN) == ("en-GB-SoniaNeural", False)


def test_non_english_voice_with_english_text_routes_to_english_pick():
    # Nick's report: Avri selected + English text → Andrew. That's auto-route doing its job.
    assert choose_voice("english", "he-IL-AvriNeural", cfg(), LONG_EN) == ("en-US-AndrewMultilingualNeural", True)


def test_multilingual_voice_keeps_latin_languages():
    assert choose_voice("spanish", "en-US-AvaMultilingualNeural", cfg(), LONG_ES) == ("en-US-AvaMultilingualNeural", False)
    assert choose_voice("english", "fr-FR-VivienneMultilingualNeural", cfg(), LONG_EN)[1] is False


def test_multilingual_voice_still_routes_other_scripts():
    voice, routed = choose_voice("hebrew", "en-US-AvaMultilingualNeural", cfg(), "שלום עולם, מה שלומך היום?")
    assert routed and voice == "he-IL-AvriNeural"


def test_short_latin_snippet_is_not_rerouted():
    # "Hola amigos" is too short to trust a Spanish guess → keep the English voice.
    assert choose_voice("spanish", "en-US-JennyNeural", cfg(), "Hola amigos") == ("en-US-JennyNeural", False)
    assert choose_voice("spanish", "en-US-JennyNeural", cfg(), LONG_ES) == ("es-ES-AlvaroNeural", True)


def test_preferred_voice_is_used_for_routing():
    c = cfg()
    c["preferred_voices"]["hebrew"] = "he-IL-HilaNeural"
    assert choose_voice("hebrew", "en-US-JennyNeural", c, "זה טקסט בעברית ארוך מספיק") == ("he-IL-HilaNeural", True)


def test_sample_text_matches_voice_language():
    assert voices.sample_text("he-IL-HilaNeural") == voices.SAMPLE_TEXT["hebrew"]
    assert voices.sample_text("ko-KR-SunHiNeural") == voices.SAMPLE_TEXT["korean"]
    assert voices.sample_text("some-offline-sapi-voice") == voices.SAMPLE_TEXT["english"]
    assert Counter(detect_language(t) for t in (voices.SAMPLE_TEXT["hebrew"], voices.SAMPLE_TEXT["arabic"])) == \
        Counter({"hebrew": 1, "arabic": 1})
