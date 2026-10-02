"""v1.4.24: crisp tray icon at the real tray size; show-next-to-clock only once, only our entry."""
import types

import pytest

from fluentvoice import tray


def test_tray_icon_px_is_a_real_small_icon_size():
    assert 16 <= tray.tray_icon_px() <= 64


@pytest.mark.parametrize("size", [16, 20, 24, 32])
def test_tray_image_is_exact_size_and_fills_the_slot(size):
    img = tray.load_tray_image(size)
    assert img.size == (size, size) and img.mode == "RGBA"
    alpha = img.getchannel("A")
    # the tile reaches the edges (no transparent margin shrinking it)
    assert alpha.getpixel((size // 2, 0)) > 0 and alpha.getpixel((0, size // 2)) > 0


@pytest.mark.parametrize("size", [16, 20, 24])
def test_icon_handle_is_loaded_at_exact_size(size):
    win32gui = pytest.importorskip("win32gui")
    stub = types.SimpleNamespace(_icon_handle=None, icon=tray.load_tray_image(size))
    tray.CrispTrayIcon._assert_icon_handle(stub)
    assert stub._icon_handle
    info = win32gui.GetIconInfo(stub._icon_handle)
    try:
        assert win32gui.GetObject(info[4]).bmWidth == size  # colour bitmap
    finally:
        for bmp in info[3:5]:
            if bmp:
                win32gui.DeleteObject(bmp)
        win32gui.DestroyIcon(stub._icon_handle)


@pytest.mark.parametrize("exe,tip,ours", [
    (r"C:\Python\pythonw.exe", "FluentVoice Pro (Click to Speak / Stop)", True),
    (r"C:\Python\pythonw.exe", "Some other Python tray app", False),
    (r"C:\Python\python.exe", "", False),
    (r"D:\Tools\FluentVoicePro.exe", "", True),
])
def test_only_our_notify_entry_is_touched(exe, tip, ours):
    assert tray._is_our_notify_entry(exe, tip) is ours


def test_promote_runs_once_then_respects_the_user(tmp_path, monkeypatch):
    marker = tmp_path / "tray_icon_promoted"
    marker.write_text("1")
    monkeypatch.setattr(tray, "PROMOTED_MARKER", marker)
    import winreg
    monkeypatch.setattr(winreg, "OpenKey", lambda *a, **k: pytest.fail("registry touched after first run"))
    assert tray.promote_notify_icons() == 0


def test_tray_becomes_dpi_aware_before_anything_else(monkeypatch):
    """v1.5.1: a DPI-unaware tray had its menu stretched as a bitmap (blurry at 125% / 150%)."""
    from fluentvoice import shortcuts, tray
    calls = []
    monkeypatch.setattr(tray, "enable_crisp_menus", lambda: calls.append("dpi"))
    monkeypatch.setattr(shortcuts, "apply_app_identity", lambda: calls.append("identity"))

    class App:
        def __init__(self):
            calls.append("app")

        def run(self):
            calls.append("run")

    monkeypatch.setattr(tray, "FluentVoiceTrayApp", App)
    tray.main()
    assert calls == ["dpi", "identity", "app", "run"]
