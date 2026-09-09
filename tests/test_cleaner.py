"""Unit tests for FluentVoice text cleaner."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fluentvoice.core import clean_text_for_speech


def test_empty():
    assert clean_text_for_speech("") == ""
    assert clean_text_for_speech(None) == ""


def test_strips_markdown_code_and_links():
    text = "See [docs](https://example.com/path) and `inline` plus ```\ncode\n``` end."
    out = clean_text_for_speech(text)
    assert "https://" not in out
    assert "```" not in out
    assert "docs" in out
    assert "inline" in out
    assert "Code block omitted" in out


def test_pdf_hyphen_linebreak():
    text = "inter-\nnational cooperation"
    out = clean_text_for_speech(text)
    assert "international" in out


def test_preserves_hebrew():
    text = "שלום עולם"
    assert "שלום" in clean_text_for_speech(text)


def test_collapses_whitespace_and_bullets():
    text = "Hello\n\n• world\n****\nnext"
    out = clean_text_for_speech(text)
    assert "  " not in out
    assert "Hello" in out and "world" in out
