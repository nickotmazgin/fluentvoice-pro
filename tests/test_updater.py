"""Update checker tests (network mocked)."""
import hashlib
import json

from fluentvoice import updater


def _release(tag="v9.9.9", digest=None):
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/nickotmazgin/fluentvoice-pro/releases/tag/{tag}",
        "name": f"FluentVoice Pro {tag}",
        "published_at": "2026-10-01T10:00:00Z",
        "body": "## notes\n### Changelog\n## [9.9.9]\n### Fixed\n- **Thing** fixed",
        "assets": [
            {"name": f"fluentvoice-pro-{tag[1:]}-windows.zip", "browser_download_url": "https://x/src.zip",
             "size": 10, "digest": digest or ""},
            {"name": f"FluentVoicePro-{tag[1:]}-portable-win64.zip", "browser_download_url": "https://x/port.zip",
             "size": 20, "digest": ""},
        ],
    }


def _isolate(monkeypatch, tmp_path, cfg=None):
    store = {"cfg": dict(cfg or {})}
    monkeypatch.setattr(updater, "STATE_FILE", tmp_path / "update_state.json")
    monkeypatch.setattr(updater, "load_config", lambda: dict(store["cfg"]))
    monkeypatch.setattr(updater, "save_config", lambda c: store.__setitem__("cfg", dict(c)))
    return store


def test_version_ordering():
    assert updater.is_newer("1.4.18", "1.4.17")
    assert updater.is_newer("v1.10.0", "1.9.9")
    assert updater.is_newer("2.0", "1.99.99")
    assert not updater.is_newer("1.4.17", "1.4.17")
    assert not updater.is_newer("v1.4.16", "1.4.17")
    assert updater.is_newer("1.5.0", "1.5.0-beta.2")
    assert not updater.is_newer("1.5.0-rc.1", "1.5.0")
    assert not updater.is_newer("garbage", "1.0.0")


def test_update_detected_and_cached(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        return _release("v9.9.9")

    res = updater.check_for_update(force=True, fetch=fetch)
    assert res["status"] == "update" and res["latest"] == "9.9.9"
    assert res["assets"][0]["name"].endswith("-windows.zip")
    # Non-forced check within 24h uses the cache (no second network call)
    res2 = updater.check_for_update(force=False, fetch=fetch)
    assert res2["status"] == "update" and len(calls) == 1


def test_current_version_reports_up_to_date(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    res = updater.check_for_update(force=True, fetch=lambda u, t: _release("v" + updater.CURRENT_VERSION))
    assert res["status"] == "current"


def test_skip_and_disable(monkeypatch, tmp_path):
    store = _isolate(monkeypatch, tmp_path)
    updater.skip_version("9.9.9")
    assert store["cfg"]["skipped_update_version"] == "9.9.9"
    res = updater.check_for_update(force=False, fetch=lambda u, t: _release("v9.9.9"))
    assert res["status"] == "skipped"
    # Manual check ignores the skip
    assert updater.check_for_update(force=True, fetch=lambda u, t: _release("v9.9.9"))["status"] == "update"
    store["cfg"]["check_updates"] = False
    assert updater.check_for_update(force=False)["status"] == "disabled"


def test_network_error_is_graceful(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    def boom(url, timeout):
        raise OSError("offline")

    res = updater.check_for_update(force=True, fetch=boom)
    assert res["status"] == "error" and "offline" in res["message"]


def test_digest_parsed_and_asset_choice(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    res = updater.check_for_update(force=True, fetch=lambda u, t: _release("v9.9.9", digest="sha256:ABCDEF"))
    assert res["assets"][0]["sha256"] == "abcdef"
    assert "portable" in updater.preferred_asset(res, portable=True)["name"]
    assert updater.preferred_asset(res, portable=False)["name"].endswith("-windows.zip")


class _Resp:
    def __init__(self, data):
        self.data = data
        self.headers = {"Content-Length": str(len(data))}
        self.pos = 0

    def read(self, n=-1):
        if n < 0:
            n = len(self.data)
        chunk = self.data[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_verifies_sha256(monkeypatch, tmp_path):
    payload = b"PK-fake-zip-bytes"
    good = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda req, timeout=0: _Resp(payload))
    info = updater._summarize(_release("v9.9.9", digest="sha256:" + good))
    res = updater.download_update(info, dest_dir=tmp_path)
    assert res["ok"] and res["verified"] and res["sha256"] == good
    assert (tmp_path / "fluentvoice-pro-9.9.9-windows.zip").read_bytes() == payload


def test_download_rejects_tampered_file(monkeypatch, tmp_path):
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda req, timeout=0: _Resp(b"tampered"))
    info = updater._summarize(_release("v9.9.9", digest="sha256:" + "0" * 64))
    res = updater.download_update(info, dest_dir=tmp_path)
    assert not res["ok"] and "mismatch" in res["message"].lower()
    assert list(tmp_path.iterdir()) == []


def test_short_notes_strips_markdown():
    txt = updater.short_notes(_release()["body"])
    assert "Thing fixed" in txt and "**" not in txt


def _zip(path, files):
    import zipfile
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def test_prepare_install_source_zip(tmp_path):
    root = tmp_path / "fluentvoice-pro-1.4.17"
    root.mkdir()
    z = _zip(tmp_path / "fluentvoice-pro-9.9.9-windows.zip", {"install.ps1": "Write-Host hi", "fluentvoice/__init__.py": ""})
    plan = updater.prepare_install(str(z), {"latest": "9.9.9"}, root=root)
    assert plan["ok"] and not plan["portable"]
    assert plan["command"][-1].endswith("install.ps1")
    assert (tmp_path / "fluentvoice-pro-9.9.9" / "install.ps1").exists()


def test_prepare_install_portable_zip(tmp_path):
    root = tmp_path / "FluentVoicePro"
    root.mkdir()
    z = _zip(tmp_path / "FluentVoicePro-9.9.9-portable-win64.zip", {"FluentVoicePro.exe": "MZ"})
    plan = updater.prepare_install(str(z), {"latest": "9.9.9"}, root=root)
    assert plan["ok"] and plan["portable"]
    assert "Start-Process" in plan["command"][-1] and "FluentVoicePro.exe" in plan["command"][-1]


def test_prepare_install_refuses_git_checkout_and_zip_slip(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    z = _zip(tmp_path / "fluentvoice-pro-9.9.9-windows.zip", {"install.ps1": ""})
    plan = updater.prepare_install(str(z), {"latest": "9.9.9"}, root=root)
    assert not plan["ok"] and "git" in plan["message"]
    root2 = tmp_path / "plain"
    root2.mkdir()
    evil = _zip(tmp_path / "evil-windows.zip", {"../../escape.txt": "x"})
    plan = updater.prepare_install(str(evil), {"latest": "9.9.10"}, root=root2)
    assert not plan["ok"] and "Unsafe" in plan["message"]
    assert not (tmp_path.parent / "escape.txt").exists()
