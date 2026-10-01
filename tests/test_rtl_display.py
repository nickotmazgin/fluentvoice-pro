"""v1.4.26: right-to-left lines (Hebrew / Arabic mixed with English) display in reading order."""
from fluentvoice import core, voices
from fluentvoice.gui import PDF, RLE, _index_after_plain, bidi_strip, bidi_wrap_lines


def test_each_non_empty_line_is_wrapped_once():
    text = "שלום עולם\n\nمرحبا بك"
    wrapped = bidi_wrap_lines(text)
    assert wrapped == f"{RLE}שלום עולם{PDF}\n\n{RLE}مرحبا بك{PDF}"
    assert bidi_wrap_lines(wrapped) == wrapped          # idempotent: re-running adds nothing
    assert bidi_strip(wrapped) == text


def test_cursor_stays_inside_the_marks():
    t = bidi_wrap_lines("אבג\n\nדה")
    assert _index_after_plain(t, 0) == 1                # after the opening mark
    assert _index_after_plain(t, 3) == t.index(PDF)     # before the closing mark
    assert t[_index_after_plain(t, 4)] == "\n"          # empty line
    assert _index_after_plain(t, 6) == len(t) - 2       # between ד and ה


def test_marks_never_reach_the_voice():
    spoken = core.clean_text_for_speech(bidi_wrap_lines(voices.SAMPLE_TEXT["hebrew"]))
    assert RLE not in spoken and PDF not in spoken
    assert spoken == core.clean_text_for_speech(voices.SAMPLE_TEXT["hebrew"])


def test_niqqud_is_passed_to_the_voice():
    pointed = "סֵפֶר שָׁלוֹם"
    assert core.clean_text_for_speech(pointed) == pointed
