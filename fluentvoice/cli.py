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
    parser.add_argument("text", nargs="*", help="Text to speak aloud or tab name for GUI")
    parser.add_argument("--clip", "-c", action="store_true", help="Read current clipboard text")
    parser.add_argument("--stop", "-s", action="store_true", help="Stop any active speech immediately")
    parser.add_argument("--toggle", "-t", action="store_true", help="Toggle speak or stop (Default)")
    parser.add_argument("--gui", "-g", action="store_true", help="Open FluentVoice Pro Settings & Control Center")
    parser.add_argument("--reader", "-r", action="store_true", help="Open Direct Text Reader scratchpad window")
    parser.add_argument("--about", "-a", action="store_true", help="Open About & Developer Credits window")

    args = parser.parse_args()

    if args.reader or args.gui or args.about:
        # Desktop / Settings must resurrect the tray if user previously Exit'ed it.
        try:
            from .lifecycle import ensure_tray_running
            ensure_tray_running()
        except Exception:
            pass

    if args.reader:
        from .gui import open_settings_window
        open_settings_window(tab="Direct Text Reader")
        return

    if args.gui:
        tab_name = " ".join(args.text) if args.text else "Voice & Speech"
        from .gui import open_settings_window
        open_settings_window(tab=tab_name)
        return

    if args.about:
        from .gui import open_settings_window
        open_settings_window(tab="About & Developer")
        return

    if args.stop:
        core.stop_all_playback()
        return

    if args.clip:
        text = core.get_clipboard_text()
        core.speak_text(text)
        return

    if args.text:
        text = " ".join(args.text)
        core.speak_text(text)
        return

    # Default: Toggle speak or stop
    core.toggle_speak_or_stop()

if __name__ == "__main__":
    main()
