"""v1.6.2: what happens when a voice fails — retry, another voice, pause the online service, come
back to it, and never report silence (an English voice reading Thai) as success."""
import sys
import threading
import time
import types

from fluentvoice import core, localtts

LONG = ("First sentence of the text is here. " * 6 + "Second paragraph follows with more words. " * 6).strip()


def _patch(monkeypatch, *, cfg=None, online=lambda text, voice, attempt: True, local_hd=None, windows=None,
           play_ok=True):
    calls = {"online": [], "local": [], "play": [], "sapi": [], "toasts": []}
    attempts = {}
    monkeypatch.setattr(core, "_halt_audio_engines", lambda: None)
    monkeypatch.setattr(core, "trigger_notification",
                        lambda title, msg="", **k: calls["toasts"].append((title, msg)))
    cfg = cfg or {"voice": "en-US-AvaMultilingualNeural", "auto_route_language": True, "clean_markdown": True}
    monkeypatch.setattr(core, "load_config", lambda: cfg)
    monkeypatch.setattr(core, "_local_hd_usable", lambda v: True)
    monkeypatch.setattr(core, "_local_hd_for", lambda fam, c: (local_hd or {}).get(fam))
    monkeypatch.setattr(core, "_windows_voice_for", lambda fam: (windows or {}).get(fam))

    def fake_online(text, voice, out, **kw):
        key = (text, voice)
        attempts[key] = attempts.get(key, 0) + 1
        calls["online"].append((text, voice))
        res = online(text, voice, attempts[key])
        if res is True:
            open(out, "wb").write(b"ID3")
            return True, ""
        return False, res or "boom"

    def fake_local(text, voice, out, **kw):
        calls["local"].append(voice)
        open(out, "wb").write(b"RIFF")
        return True, ""

    def fake_play(path, gen, volume=100, start_ts=None, on_progress=None, **kw):
        calls["play"].append(path)
        return play_ok(kw) if callable(play_ok) else play_ok

    monkeypatch.setattr(core, "_synthesize_to_file", fake_online)
    monkeypatch.setattr(localtts, "synthesize_to_wav", fake_local)
    monkeypatch.setattr(core, "play_audio_file", fake_play)
    monkeypatch.setattr(core, "speak_offline_sapi",
                        lambda text, **kw: calls["sapi"].append(kw.get("voice_pref")) or True)
    return calls


def test_no_voice_for_the_language_says_what_to_install_instead_of_silence(monkeypatch):
    calls = _patch(monkeypatch, online=lambda *a: "403 Forbidden")
    res = core.speak_text("สวัสดีครับ นี่คือข้อความภาษาไทยสำหรับการทดสอบ")
    assert res["status"] == "error" and res["mode"] == "no_voice"
    assert calls["sapi"] == []  # Zira would "read" Thai as silence
    title, msg = calls["toasts"][-1]
    assert "Thai" in title and "Add voices" in msg


def test_english_text_still_falls_back_to_the_english_windows_voice(monkeypatch):
    calls = _patch(monkeypatch, online=lambda *a: "403 Forbidden")
    res = core.speak_text("A short English sentence to read.")
    assert res["status"] == "fallback" and calls["sapi"] == ["Zira"]


def test_privacy_mode_without_an_offline_voice_for_the_language(monkeypatch):
    cfg = {"voice": "he-IL-HilaNeural", "offline_only": True, "auto_route_language": True}
    calls = _patch(monkeypatch, cfg=cfg)
    res = core.speak_text("שלום עולם, זה טקסט בעברית לקריאה")
    assert res["mode"] == "no_voice" and calls["online"] == [] and calls["sapi"] == []


def test_a_dropped_part_is_retried_once_before_switching_voice(monkeypatch):
    calls = _patch(monkeypatch, online=lambda text, voice, attempt: attempt > 1 or "connection reset")
    res = core.speak_text("One short sentence to read.")
    assert res["status"] == "success" and calls["sapi"] == [] and len(calls["online"]) == 2


def test_voice_that_returns_no_audio_switches_to_another_online_voice(monkeypatch):
    bad = "en-US-AvaMultilingualNeural"
    calls = _patch(monkeypatch, online=lambda text, voice, attempt: voice != bad or "NoAudioReceived")
    res = core.speak_text("One short sentence to read.")
    assert res["status"] == "fallback" and res["mode"] == "neural" and res["voice"] != bad
    assert calls["sapi"] == [] and not core.online_unavailable()  # the service itself works
    assert any(t == "🗣 Voice switched" for t, _ in calls["toasts"])


def test_service_failure_pauses_the_online_voices(monkeypatch):
    calls = _patch(monkeypatch, online=lambda *a: "403 Forbidden",
                   local_hd={"english": "piper:en_US-joe-medium"})
    first = core.speak_text("One short sentence to read.")
    assert first["status"] == "fallback" and first["mode"] == "offline_hd"
    assert core.online_unavailable()
    sent = len(calls["online"])
    second = core.speak_text("Another sentence to read now.")
    assert len(calls["online"]) == sent  # no waiting on a service that just failed
    assert second["status"] == "fallback" and second["mode"] == "offline_hd"


def test_pause_grows_with_each_failure_and_resets_on_success():
    assert core._mark_online_down("x") == core.ONLINE_PAUSE_STEPS_SEC[0]
    assert core._mark_online_down("x") == core.ONLINE_PAUSE_STEPS_SEC[1]
    core._mark_online_up()
    assert not core.online_unavailable() and core._online["strikes"] == 0


def test_reading_switches_back_to_online_when_the_service_recovers(monkeypatch):
    monkeypatch.setattr(core, "ONLINE_PROBE_EVERY_SEC", 0.05)
    core._online.update(down_until=time.time() + 0.2, strikes=1, reason="403")

    interrupted = []

    def play(kw):  # the first (offline) part keeps playing until FluentVoice interrupts it
        t0 = time.time()
        while not interrupted and time.time() - t0 < 5:
            if kw["interrupt"]():
                interrupted.append(1)
            time.sleep(0.02)
        return True

    calls = _patch(monkeypatch, local_hd={"english": "piper:en_US-joe-medium"}, play_ok=play)
    res = core.speak_text(LONG)
    assert calls["local"]  # began offline during the outage
    assert any(text != "OK." for text, _ in calls["online"])  # then continued online
    assert any(t == "🌐 Online voice is back" for t, _ in calls["toasts"])
    assert res["status"] == "success" and res["mode"] == "neural"


def test_playback_failure_explains_the_audio_problem(monkeypatch):
    calls = _patch(monkeypatch, play_ok=False, local_hd={"english": "piper:en_US-joe-medium"})
    res = core.speak_text("One short sentence to read.")
    assert res["status"] == "fallback" and calls["sapi"] == ["Zira"]  # same player: skip the HD voice
    assert any(t == "🔈 Audio problem" for t, _ in calls["toasts"])
    assert not core.online_unavailable()


def test_fallback_message_names_the_voices(monkeypatch):
    _patch(monkeypatch, online=lambda *a: "403 Forbidden", windows={"english": "Microsoft David Desktop"})
    res = core.speak_text("A short English sentence to read.")
    assert "Ava" in res["message"] and "David" in res["message"]


def test_missing_voice_help_points_to_the_right_place():
    assert "Voice Providers" in core.missing_voice_help("spanish")  # offline HD voices exist
    assert "Add voices" in core.missing_voice_help("thai")


# ---------------------------------------------------------------------------------- speed
class _SilentComm:
    def __init__(self, *a, **k):
        pass

    async def stream(self):
        import asyncio
        await asyncio.sleep(3600)
        yield {"type": "audio", "data": b"x"}


def test_a_silent_connection_fails_fast(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=_SilentComm))
    monkeypatch.setattr(core, "SYNTH_FIRST_RESPONSE_SEC", 0.3)
    t0 = time.time()
    ok, _ = core._synthesize_to_file("hi", "v", str(tmp_path / "a.mp3"), rate="+0%", pitch="+0Hz", volume=100)
    assert not ok and time.time() - t0 < 3


def test_preload_warms_the_offline_voice_once(monkeypatch):
    done = threading.Event()
    seen = []
    monkeypatch.setattr(localtts, "is_usable", lambda v: True)

    def synth(text, voice, out, **kw):
        seen.append(voice)
        done.set()
        return True, ""

    monkeypatch.setattr(localtts, "synthesize_to_wav", synth)
    cfg = {"voice": "piper:en_US-joe-medium"}
    assert core.preload_offline_voice(cfg) == "piper:en_US-joe-medium"
    assert done.wait(5) and seen == ["piper:en_US-joe-medium"]
    assert core.preload_offline_voice({"voice": "en-US-AvaMultilingualNeural"}) is None


def test_offline_hd_parts_start_small_and_grow_gradually():
    text = "Short first one. A second sentence that is a bit longer. " + LONG * 3
    parts = core.split_for_streaming(text, first=core.LOCAL_FIRST_CHUNK_CHARS, second=core.LOCAL_SECOND_CHUNK_CHARS,
                                     grow=core.LOCAL_CHUNK_GROWTH)
    assert len(parts[1]) <= core.LOCAL_SECOND_CHUNK_CHARS
    for prev, nxt in zip(parts, parts[1:]):  # each part is ready before the previous one has played
        assert len(nxt) <= max(core.LOCAL_FIRST_CHUNK_CHARS, len(prev) * core.LOCAL_CHUNK_GROWTH)
    assert max(len(p) for p in parts) > 400  # still grows to long parts (fewer boundaries)
    assert core.split_for_streaming(text) == core.split_for_streaming(text, grow=None)  # online unchanged
