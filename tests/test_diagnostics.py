"""Settings → Components & sources: health checks, verify / repair, the online-server fallback."""

import asyncio
import hashlib
import re
import shutil
import time
from datetime import datetime

import edge_tts.communicate as edge_comm
import pytest

from fluentvoice import core, diagnostics as d, local_catalog as cat, localtts


# ---------------------------------------------------------------------------- components
def test_components_list_versions_licences_and_sources():
    comps = d.components()
    names = {c["name"] for c in comps}
    assert {"FluentVoice Pro", "edge-tts", "piper-tts", "sherpa-onnx", "langdetect"} <= names
    for c in comps:
        assert c["version"] != "missing", c
        assert c["licence"] and c["source"].startswith("https://")
    assert "SHA-256" in d.components_text()


# ---------------------------------------------------------------------------- online voices
def test_403_is_explained_as_a_microsoft_side_change_with_fixes():
    f = d.classify_online_error("WSServerHandshakeError: 403, message='Invalid response status'", internet=True)
    assert f.level == "error" and "403" in f.summary
    text = " ".join(f.fixes)
    assert "clock" in text and "Check for Updates" in text and "Piper" in text


def test_no_internet_is_told_apart_from_a_blocked_server():
    offline = d.classify_online_error("ClientConnectorError: Cannot connect to host", internet=False)
    assert "not connected to the internet" in offline.summary
    blocked = d.classify_online_error("ClientConnectorError: Cannot connect to host", internet=True,
                                      host="api.msedgeservices.com")
    assert "firewall" in blocked.summary
    assert blocked.fixes[0] == ("Allow api.msedgeservices.com in the firewall or proxy, or try another network "
                                "(or turn the VPN off / on).")


def test_certificate_and_no_audio_errors():
    assert "antivirus" in d.classify_online_error("SSLCertVerificationError", internet=True).summary
    no_audio = d.classify_online_error("TTS service returned no audio", internet=True)
    assert no_audio.level == "warn" and "another voice" in no_audio.fixes[0]


def test_online_check_reports_the_server_that_answered():
    f = d.check_online({"voice": "en-US-AriaNeural"}, synth=lambda *a, **k: (True, ""),
                       internet=lambda: True, host=lambda: "api.msedgeservices.com")
    assert f.level == "ok"
    assert re.fullmatch(r"Working: Aria\b.* answered in \d+\.\d s \(server: api\.msedgeservices\.com\)\.", f.summary)


def test_online_check_never_sends_text_in_privacy_mode():
    def synth(*a, **k):
        raise AssertionError("must not go online")
    f = d.check_online({"offline_only": True}, synth=synth, internet=lambda: True, host=lambda: "")
    assert f.level == "info" and "Offline only" in f.summary


def test_online_check_failure_is_classified():
    f = d.check_online({"voice": "en-US-AriaNeural"}, synth=lambda *a, **k: (False, "403, message='Invalid'"),
                       internet=lambda: True, host=lambda: "api.msedgeservices.com")
    assert f.level == "error" and "403" in f.summary


# ---------------------------------------------------------------------------- other checks
def test_hotkey_checks():
    assert d.check_hotkeys({}, False, {}).level == "warn"
    assert d.check_hotkeys({"hotkey_enabled": False}, True, {}).level == "info"
    clash = d.check_hotkeys({}, True, {"read": {"chord": "ctrl+shift+space", "ok": False, "error": "in use"}})
    assert clash.level == "error" and "ctrl+shift+space" in clash.summary
    ok = d.check_hotkeys({}, True, {"read": {"chord": "ctrl+shift+space", "ok": True}})
    assert ok.level == "ok"


def test_audio_and_windows_voice_checks():
    assert d.check_audio(0).level == "error"
    assert d.check_audio(2).level == "ok"
    assert d.check_windows_voices({}, tokens=[]).level == "error"
    hebrew = d.check_windows_voices({"voice": "he-IL-HilaNeural"},
                                    tokens=["Microsoft Zira Desktop - English (United States)"])
    assert hebrew.level == "info" and "Hebrew" in hebrew.summary
    assert d.check_windows_voices({"voice": "en-US-AriaNeural"},
                                  tokens=["Microsoft Zira Desktop - English (United States)"]).level == "ok"


def _log(ts, level, msg):
    return f"{datetime.fromtimestamp(ts):%Y-%m-%d %H:%M:%S},123 [{level}] (MainThread) {msg}"


def test_recent_errors_from_the_tray_log():
    now = time.time()
    lines = [_log(now - 3 * 86400, "ERROR", "old problem"),
             _log(now - 600, "WARNING", "online voices paused"),
             _log(now - 60, "ERROR", "neural synthesis failed: 403, message='Invalid', url=wss://x")]
    f = d.check_recent_errors(lines, now)
    assert f.level == "warn" and "1 error" in f.summary and "old problem" not in f.summary
    assert "url=" not in f.summary and any("403" in x for x in f.fixes)
    assert d.check_recent_errors(lines[:2], now).level == "ok"


def test_report_headline_follows_the_worst_finding():
    ok = d.report_lines([d.Finding("A", "ok", "fine")])
    assert ok[0][0].startswith("All voice providers work")
    bad = d.report_lines([d.Finding("A", "ok", "fine"), d.Finding("B", "error", "broken", ["do this"])])
    assert bad[0][1] == "error" and ("     → do this", "fix") in bad


def test_a_failing_check_does_not_stop_the_others(monkeypatch):
    monkeypatch.setattr(d, "check_online", lambda cfg: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(d, "check_audio", lambda: d.Finding("Audio output", "ok", "1 device"))
    findings = d.run_checks({}, tray_running=True, hotkey_status={})
    assert findings[0].level == "error" and "boom" in findings[0].summary
    assert any(f.area == "Audio output" for f in findings)


# ---------------------------------------------------------------------------- verify / repair
MODEL = "en_US-joe-medium"


@pytest.fixture
def fake_piper_model(monkeypatch):
    onnx, conf = b"onnx-model-bytes", b'{"config": 1}'
    entry = (cat.PIPER_MODELS[MODEL][0], hashlib.sha256(onnx).hexdigest(), len(onnx),
             hashlib.sha256(conf).hexdigest(), len(conf))
    monkeypatch.setitem(cat.PIPER_MODELS, MODEL, entry)
    folder = localtts.PIPER_DIR / MODEL

    def write(model_bytes=onnx):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{MODEL}.onnx").write_bytes(model_bytes)
        (folder / f"{MODEL}.onnx.json").write_bytes(conf)

    write()
    yield write
    shutil.rmtree(folder, ignore_errors=True)


def test_verify_accepts_intact_files(fake_piper_model):
    res = d.verify_offline_voices()
    joe = next(r for r in res if r["key"] == MODEL)
    assert joe["ok"] and "Joe" in joe["name"]


def test_verify_flags_a_damaged_file_and_repair_downloads_it_again(fake_piper_model, monkeypatch):
    fake_piper_model(b"onnx-model-BYTES")  # same size, different content
    res = d.verify_offline_voices()
    bad = [r for r in res if not r["ok"]]
    assert [r["key"] for r in bad] == [MODEL] and "checksum" in bad[0]["problem"]

    installed = []
    monkeypatch.setattr(localtts, "install", lambda voice, progress=None, cancel=None: (
        installed.append(voice), fake_piper_model()))
    out = d.repair_offline_voices(bad)
    assert installed == [bad[0]["voice"]] and out[0][1] is True
    assert all(r["ok"] for r in d.verify_offline_voices())


def test_repair_reports_files_still_in_use(fake_piper_model, monkeypatch):
    monkeypatch.setattr(localtts, "remove", lambda voice: None)  # e.g. locked by the running tray
    out = d.repair_offline_voices([{"voice": f"piper:{MODEL}", "name": "Joe"}])
    assert out[0][1] is False and "in use" in out[0][2]


# ---------------------------------------------------------------------------- server fallback
class _Refused(Exception):
    def __init__(self, status):
        super().__init__(f"{status}, message='Invalid response status'")
        self.status = status


@pytest.fixture
def classic_server(monkeypatch):
    from edge_tts.constants import WSS_URL
    monkeypatch.setattr(edge_comm, "WSS_URL", WSS_URL)
    return WSS_URL


def _run():
    return asyncio.run(core._synthesize_edge("Hi.", "en-US-AriaNeural", "unused.mp3"))


def test_403_switches_to_the_newer_server_and_stays_there(classic_server, monkeypatch):
    calls = []

    async def stream(text, voice, out, **kw):
        calls.append(edge_comm.WSS_URL)
        if edge_comm.WSS_URL == classic_server:
            raise _Refused(403)
        return True

    monkeypatch.setattr(core, "_stream_edge", stream)
    assert _run() is True
    assert core.edge_server_host() == "api.msedgeservices.com"
    assert _run() is True
    assert calls == [classic_server, core._alt_edge_url(), core._alt_edge_url()]


def test_other_errors_and_a_refusing_newer_server_are_not_retried(classic_server, monkeypatch):
    async def timeout(text, voice, out, **kw):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(core, "_stream_edge", timeout)
    with pytest.raises(asyncio.TimeoutError):
        _run()
    assert edge_comm.WSS_URL == classic_server

    calls = []

    async def refused(text, voice, out, **kw):
        calls.append(edge_comm.WSS_URL)
        raise _Refused(403)

    monkeypatch.setattr(core, "_stream_edge", refused)
    with pytest.raises(_Refused):
        _run()
    assert calls == [classic_server, core._alt_edge_url()]
