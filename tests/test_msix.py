"""Microsoft Store (MSIX) build: detection and the behaviour it switches."""
import ctypes

import pytest

from fluentvoice import msix, shortcuts, updater


@pytest.fixture(autouse=True)
def _fresh_cache():
    msix.is_packaged.cache_clear()
    yield
    msix.is_packaged.cache_clear()


def test_not_packaged_when_running_from_source():
    assert msix.is_packaged() is False  # tests never run inside an MSIX package


@pytest.mark.parametrize("rc, packaged", [(15700, False), (122, True), (0, True)])
def test_is_packaged_reads_get_current_package_full_name(monkeypatch, rc, packaged):
    class K32:
        @staticmethod
        def GetCurrentPackageFullName(length, buf):
            return rc
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": K32})(), raising=False)
    assert msix.is_packaged() is packaged


def test_store_build_skips_github_updater(monkeypatch):
    monkeypatch.setattr(msix, "is_packaged", lambda: True)

    def no_network(*a, **k):
        raise AssertionError("the Store build must not call GitHub")
    res = updater.check_for_update(force=True, fetch=no_network)
    assert res["status"] == "store"
    assert res["url"] == msix.STORE_PAGE
    assert res["current"] == updater.CURRENT_VERSION


def test_store_build_keeps_package_identity_and_shortcuts(monkeypatch):
    monkeypatch.setattr(msix, "is_packaged", lambda: True)
    monkeypatch.setattr(shortcuts, "is_frozen", lambda: True)
    assert shortcuts.apply_app_identity() is False
    assert shortcuts.repair_moved_portable() == 0


def test_store_build_check_for_updates_never_mentions_github(monkeypatch):
    from fluentvoice import gui
    monkeypatch.setattr(gui, "_is_store_build", lambda: True)
    monkeypatch.setattr(updater, "check_for_update", lambda force=False: {"status": "store"})
    opened = []
    monkeypatch.setattr(msix, "open_store_page", lambda: opened.append(True))
    win = gui.FluentVoiceSettingsWindow.__new__(gui.FluentVoiceSettingsWindow)
    statuses = []
    win._set_update_status = lambda text, color: statuses.append(text)
    win.after = lambda ms, fn: None
    win._check_updates_async(force=True)
    win._apply_update_result({"status": "store"}, force=True, popup=True)
    assert statuses == ["Updates for this copy come from the Microsoft Store."]
    assert opened == [True]


def test_store_links_are_fixed():
    assert msix.STORE_ID == "9N293MJ0MD9F"
    assert msix.STORE_PAGE == "https://apps.microsoft.com/detail/9N293MJ0MD9F"
    assert msix.STARTUP_SETTINGS == "ms-settings:startupapps"
