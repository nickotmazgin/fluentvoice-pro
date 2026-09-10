"""Unit tests for FluentVoice clipboard safety and unlock guarantees."""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fluentvoice.core import get_clipboard_text
import win32clipboard
import win32con


def test_clipboard_reads_unicode_text():
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText("FluentVoice Pro Clipboard Test")
    win32clipboard.CloseClipboard()

    text = get_clipboard_text()
    assert text == "FluentVoice Pro Clipboard Test"


def test_clipboard_empty_returns_empty_string():
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.CloseClipboard()

    text = get_clipboard_text()
    assert text == ""


def test_clipboard_non_text_does_not_lock():
    # Set non-text format
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32con.CF_LOCALE, b"\x09\x04\x00\x00")
    win32clipboard.CloseClipboard()

    # Must return empty string and NOT throw or leave clipboard locked
    text = get_clipboard_text()
    assert text == ""

    # Verify clipboard is immediately openable by another caller
    opened = False
    try:
        win32clipboard.OpenClipboard()
        opened = True
    finally:
        if opened:
            win32clipboard.CloseClipboard()
