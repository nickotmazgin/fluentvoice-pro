"""Unit tests for FluentVoice language / script detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fluentvoice.core import detect_language, detect_script, resolve_route_voice
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
    assert "Hebrew" in label
