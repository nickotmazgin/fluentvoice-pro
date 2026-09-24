"""Chunked streaming + cross-process single-stream signal tests (no audio device needed)."""
import time

from fluentvoice import core


LONG = ("The Proof of Hidden Gods: a critical review. Despite claims to the contrary, "
        "there is zero verifiable physical evidence. Non-avian dinosaurs went extinct "
        "approximately 66 million years ago! Anatomically modern humans emerged only "
        "300,000 years ago? ") * 25


def test_split_short_text_is_single_chunk():
    assert core.split_for_streaming("Hello world.") == ["Hello world."]
    assert core.split_for_streaming("   ") == []


def test_split_long_text_preserves_content_and_limits():
    chunks = core.split_for_streaming(LONG)
    assert len(chunks) > 2
    assert len(chunks[0]) <= core.FIRST_CHUNK_CHARS
    assert all(len(c) <= core.CHUNK_CHARS for c in chunks[1:])
    # No words lost or duplicated
    assert " ".join(chunks).split() == LONG.split()


def test_split_prefers_sentence_boundaries():
    chunks = core.split_for_streaming(LONG)
    for c in chunks[:-1]:
        assert c.rstrip()[-1] in ".!?:;…", c[-40:]


def test_split_hebrew_and_no_spaces_fallback():
    heb = ("שלום עולם, זהו מבחן קריאה ארוך. " * 40).strip()
    chunks = core.split_for_streaming(heb)
    assert " ".join(chunks).split() == heb.split()
    blob = "x" * 5000
    chunks = core.split_for_streaming(blob)
    assert "".join(chunks) == blob


def test_claim_from_other_process_aborts_but_not_self(monkeypatch):
    start = time.time() - 1
    gen = core._current_generation
    # Our own claim must not abort ourselves
    core._broadcast_signal("claim")
    assert core._should_abort(gen, start) is False
    # A claim written by another PID aborts us
    core.STOP_SIGNAL_FILE.write_text(f"{core._PID + 1} {time.time():.6f} claim", encoding="utf-8")
    assert core._should_abort(gen, start) is True


def test_stop_all_signal_aborts_every_process():
    start = time.time() - 1
    gen = core._current_generation
    core.STOP_SIGNAL_FILE.write_text(f"{core._PID} {time.time():.6f} all", encoding="utf-8")
    assert core._should_abort(gen, start) is True
    # Speech that starts after the stop is unaffected
    assert core._should_abort(gen, time.time() + 1) is False


def _patch_engine(monkeypatch, synth_ok=lambda idx: True, play_ok=True):
    calls = {"synth": [], "play": [], "sapi": []}
    monkeypatch.setattr(core, "_halt_audio_engines", lambda: None)
    monkeypatch.setattr(core, "trigger_notification", lambda *a, **k: None)
    monkeypatch.setattr(core, "load_config", lambda: {
        "voice": "en-US-AvaMultilingualNeural", "engine": "neural", "auto_route_language": True,
        "clean_markdown": True, "preferred_voices": {"english": "en-US-AndrewMultilingualNeural"}})

    def fake_synth(text, voice, out, **kw):
        idx = len(calls["synth"])
        calls["synth"].append(text)
        if synth_ok(idx):
            open(out, "wb").write(b"ID3")
            return True, ""
        return False, "boom"

    def fake_play(path, gen, volume=100, start_ts=None, on_progress=None):
        calls["play"].append(path)
        if on_progress:
            on_progress(500, 1000)
        return play_ok

    def fake_sapi(text, **kw):
        calls["sapi"].append(text)
        return True

    monkeypatch.setattr(core, "_synthesize_to_file", fake_synth)
    monkeypatch.setattr(core, "play_audio_file", fake_play)
    monkeypatch.setattr(core, "speak_offline_sapi", fake_sapi)
    return calls


def test_speak_text_streams_all_chunks_and_reports_phases(monkeypatch):
    calls = _patch_engine(monkeypatch)
    phases = []
    res = core.speak_text(LONG, on_status=lambda p, i: phases.append(p))
    assert res["status"] == "success"
    assert len(calls["play"]) == len(calls["synth"]) == len(core.split_for_streaming(core.clean_text_for_speech(LONG)))
    assert phases[0] == "synthesizing" and "speaking" in phases and phases[-1] == "done"
    assert calls["sapi"] == []


def test_speak_text_falls_back_for_remaining_text(monkeypatch):
    calls = _patch_engine(monkeypatch, synth_ok=lambda idx: idx == 0)
    phases = []
    res = core.speak_text(LONG, on_status=lambda p, i: phases.append(p))
    assert res["status"] == "fallback"
    assert len(calls["play"]) == 1           # first chunk played on neural
    assert len(calls["sapi"]) == 1           # rest handed to offline voice
    assert "fallback" in phases and phases[-1] == "done"


def test_speak_text_never_hangs_when_first_chunk_fails(monkeypatch):
    calls = _patch_engine(monkeypatch, synth_ok=lambda idx: False)
    t0 = time.time()
    res = core.speak_text("Short sentence to read.", on_status=None)
    assert res["status"] == "fallback"
    assert time.time() - t0 < 3
    assert calls["play"] == []


class _FakeComm:
    def __init__(self, text, voice, hang=False, **kw):
        self.hang = hang

    async def stream(self):
        import asyncio
        yield {"type": "audio", "data": b"abc"}
        if self.hang:
            await asyncio.sleep(3600)
        yield {"type": "WordBoundary"}
        yield {"type": "audio", "data": b"def"}


def _fake_edge(monkeypatch, hang):
    import sys, types
    mod = types.SimpleNamespace(Communicate=lambda *a, **k: _FakeComm(*a, hang=hang, **k))
    monkeypatch.setitem(sys.modules, "edge_tts", mod)


def test_synthesize_writes_file_atomically(monkeypatch, tmp_path):
    _fake_edge(monkeypatch, hang=False)
    out = str(tmp_path / "a.mp3")
    ok, err = core._synthesize_to_file("hi", "v", out, rate="+0%", pitch="+0Hz", volume=100)
    assert ok and err == ""
    assert open(out, "rb").read() == b"abcdef"
    assert not (tmp_path / "a.mp3.part").exists()


def test_synthesize_times_out_instead_of_hanging(monkeypatch, tmp_path):
    _fake_edge(monkeypatch, hang=True)
    monkeypatch.setattr(core, "SYNTH_IDLE_TIMEOUT_SEC", 0.3)
    out = str(tmp_path / "b.mp3")
    t0 = time.time()
    ok, err = core._synthesize_to_file("hi", "v", out, rate="+0%", pitch="+0Hz", volume=100)
    assert not ok
    assert time.time() - t0 < 5
    assert not (tmp_path / "b.mp3").exists() and not (tmp_path / "b.mp3.part").exists()


def test_heartbeat_marks_cross_process_speaking():
    core._clear_heartbeat()
    core.SPEAKING_FILE.unlink(missing_ok=True)
    assert core.is_any_speaking() is False
    # Another process heartbeat (fresh) => speaking
    core.SPEAKING_FILE.write_text(f"{core._PID + 1} {time.time():.3f}", encoding="utf-8")
    assert core.is_any_speaking() is True
    # Stale heartbeat => not speaking
    core.SPEAKING_FILE.write_text(f"{core._PID + 1} {time.time() - 10:.3f}", encoding="utf-8")
    assert core.is_any_speaking() is False
    core.SPEAKING_FILE.unlink(missing_ok=True)


def test_toggle_blocking_speaks_in_this_process(monkeypatch):
    core.SPEAKING_FILE.unlink(missing_ok=True)
    spoken = []
    monkeypatch.setattr(core, "get_clipboard_text", lambda: "clipboard words")
    monkeypatch.setattr(core, "speak_text", lambda t, on_status=None: spoken.append(t) or {"status": "success"})
    res = core.toggle_speak_or_stop(blocking=True)
    assert res["status"] == "success" and spoken == ["clipboard words"]


def test_toggle_stops_when_other_process_speaks(monkeypatch):
    stopped = []
    monkeypatch.setattr(core, "stop_all_playback", lambda notify=True: stopped.append(1))
    core.SPEAKING_FILE.write_text(f"{core._PID + 1} {time.time():.3f}", encoding="utf-8")
    assert core.toggle_speak_or_stop(blocking=True)["status"] == "stopped" and stopped
    core.SPEAKING_FILE.unlink(missing_ok=True)
