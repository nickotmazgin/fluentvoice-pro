"""FluentVoice Pro - Command Line & GUI Dispatcher Interface
Author: Nick Otmazgin
"""

import sys
import argparse
from . import core

def main():
    parser = argparse.ArgumentParser(
        prog="fluentvoice",
        description="FluentVoice Pro: Modern Text-to-Speech & Voice Reader for Windows 11/10"
    )
    parser.add_argument("text", nargs="*", help="Text to speak aloud")
    parser.add_argument("--clip", "-c", action="store_true", help="Read current clipboard text")
    parser.add_argument("--stop", "-s", action="store_true", help="Stop any active speech immediately")
    parser.add_argument("--toggle", "-t", action="store_true", help="Toggle speak or stop (Default)")
    parser.add_argument("--gui", "-g", action="store_true", help="Open FluentVoice Pro Settings & Control Center")
    parser.add_argument("--about", "-a", action="store_true", help="Open About & Developer Credits window")

    args = parser.parse_args()

    if args.gui:
        from .gui import open_settings_window
        open_settings_window(tab="Voice & Speech")
        return

    if args.about:
        from .gui import open_settings_window
        open_settings_window(tab="About & Developer")
        return

    if args.stop:
        core.stop_all_playback()
        return

    if args.text:
        text = " ".join(args.text)
        core.speak_text(text)
        return

    if args.clip:
        text = core.get_clipboard_text()
        core.speak_text(text)
        return

    # Default: Toggle speak or stop
    core.toggle_speak_or_stop()

if __name__ == "__main__":
    main()
