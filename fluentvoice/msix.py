"""Microsoft Store (MSIX) build: detection and the few places it behaves differently.

The Store package runs the same portable EXE inside an MSIX container. There, the Store
delivers updates, Windows manages Start with Windows (Settings → Apps → Startup, through
the package's startup task) and the package itself carries the app identity, so the
GitHub updater, the Startup shortcut and the Start Menu identity shortcut are not used.
"""

import functools
import os

STORE_ID = "9N293MJ0MD9F"
STORE_PAGE = f"https://apps.microsoft.com/detail/{STORE_ID}"
STORE_PROTOCOL = f"ms-windows-store://pdp/?productid={STORE_ID}"
STARTUP_SETTINGS = "ms-settings:startupapps"

_APPMODEL_ERROR_NO_PACKAGE = 15700


@functools.lru_cache(maxsize=1)
def is_packaged() -> bool:
    """True when running inside an MSIX package (the Microsoft Store build)."""
    try:
        import ctypes
        from ctypes import wintypes

        length = wintypes.UINT(0)
        rc = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        return rc != _APPMODEL_ERROR_NO_PACKAGE
    except Exception:  # not Windows, or Windows older than 8
        return False


def open_uri(uri: str) -> bool:
    try:
        os.startfile(uri)  # noqa: S606 - fixed ms-settings / Store URIs only
        return True
    except Exception:
        return False


def open_store_page() -> bool:
    return open_uri(STORE_PROTOCOL) or open_uri(STORE_PAGE)


def open_startup_settings() -> bool:
    return open_uri(STARTUP_SETTINGS)
