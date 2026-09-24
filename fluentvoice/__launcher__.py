"""Frozen / packaged entry.

The tray (and lifecycle helpers) re-launch the app as
``<exe> -m fluentvoice.cli --gui`` / ``--reader`` / ``--about``. In the portable EXE
``sys.executable`` is FluentVoicePro.exe itself, so those ``-m`` arguments must be
dispatched here — previously every such launch just started a second tray, hit the
single-instance mutex and exited, so Settings / Reader / About never opened.
"""

import sys


def _dispatch(argv):
    if len(argv) >= 3 and argv[1] == "-m":
        module, rest = argv[2], argv[3:]
        if module == "fluentvoice.cli":
            sys.argv = ["fluentvoice"] + rest
            from fluentvoice.cli import main as cli_main
            return cli_main()
        if module == "fluentvoice.installer":
            from fluentvoice.installer import install_all
            return install_all()
    elif len(argv) >= 2 and argv[1].startswith("--"):
        # Allow `FluentVoicePro.exe --gui` etc. directly
        sys.argv = ["fluentvoice"] + argv[1:]
        from fluentvoice.cli import main as cli_main
        return cli_main()
    from fluentvoice.tray import main as tray_main
    return tray_main()


if __name__ == "__main__":
    _dispatch(sys.argv)
