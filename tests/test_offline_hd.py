"""v1.5.0: offline HD voices (Piper / Kokoro) — catalogue, safe downloads, privacy mode, fallback."""
import hashlib
import io
import re
import tarfile

import pytest

from fluentvoice import core, local_catalog as cat, localtts, voices

HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------------- catalogue
def test_every_piper_voice_has_pinned_files():
    for vid, name, fam, gender, region, kind, licence, source in cat.PIPER_VOICES:
        model = vid.split(":", 1)[1].split("#")[0]
        path, sha, size, json_sha, json_size = cat.PIPER_MODELS[model]
        assert path.endswith(f"{model}.onnx") and HEX64.match(sha) and HEX64.match(json_sha)
        assert size > 10_000_000 and 1_000 < json_size < 100_000
        assert fam in voices.LANGUAGES and kind in ("free", "personal") and licence and name
        assert source.startswith(("https://", "http://hdl.handle.net/"))


def test_kokoro_pack_is_pinned_and_voices_are_curated():
    assert cat.KOKORO_PACK["url"].startswith("https://github.com/k2-fsa/sherpa-onnx/releases/download/")
    assert HEX64.match(cat.KOKORO_PACK["sha256"]) and cat.KOKORO_PACK["size"] > 300_000_000
    names = {n.split("_", 1)[1] for n, _ in cat.KOKORO_VOICES}
    # voices named after other companies' voices are left out
    assert not names & {"alloy", "echo", "fable", "nova", "onyx", "sky", "puck", "kore", "fenrir", "aoede"}
    assert not any(n.startswith(("xiao", "yun")) for n in names)
    assert all(n[0] in cat.KOKORO_LANGS for n, _ in cat.KOKORO_VOICES)


def test_local_voice_ids_are_recognised_everywhere():
    joe, heart, shaul = "piper:en_US-joe-medium", "kokoro:af_heart", "piper:he_IL-saspeech-medium"
    assert voices.family_of(joe) == "english" and voices.family_of(shaul) == "hebrew"
    assert voices.family_of("kokoro:hm_psi") == "hindi" and voices.family_of("kokoro:bm_george") == "english"
    assert localtts.info("kokoro:bm_george")["lang"] == "en-gb-x-rp"  # "en-gb" is not an eSpeak NG voice name
    assert not any(v["id"].startswith("kokoro:j") for v in localtts.VOICES)  # Japanese skipped kanji
    for v in (joe, heart, shaul):
        assert voices.is_local_hd(v) and not voices.is_online(v) and not voices.is_offline(v)
    assert voices.is_online("en-US-JennyNeural") and not voices.is_offline("en-US-JennyNeural")
    assert voices.is_offline("Microsoft George - English (United Kingdom)")
    assert voices.label_for(joe) == "Joe (US English Male · Piper Offline)"
    assert voices.label_for(heart) == "Heart (US English Female · Kokoro Offline)"
    assert voices.short_name(shaul) == "Shaul"
    assert localtts.info(shaul)["kind"] == "personal"


# ---------------------------------------------------------------------------------- downloads
def test_only_https_to_known_hosts():
    ok = ["https://huggingface.co/rhasspy/x", "https://us.aws.cdn.hf.co/x", "https://github.com/k2-fsa/x",
          "https://release-assets.githubusercontent.com/x"]
    bad = ["http://huggingface.co/x", "https://huggingface.co.evil.com/x", "https://evilhf.co/x",
           "https://example.com/x", "file:///C:/x", "ftp://github.com/x"]
    assert all(localtts._host_allowed(u) for u in ok)
    assert not any(localtts._host_allowed(u) for u in bad)


class _Resp:
    def __init__(self, data, url="https://huggingface.co/x"):
        self.data, self.url, self.pos = data, url, 0
        self.headers = {"Content-Length": str(len(data))}

    def geturl(self):
        return self.url

    def read(self, n=-1):
        chunk = self.data[self.pos:self.pos + (n if n >= 0 else len(self.data))]
        self.pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_accepts_only_the_pinned_bytes(monkeypatch, tmp_path):
    data = b"onnx-model-bytes"
    monkeypatch.setattr(localtts.urllib.request, "urlopen", lambda req, timeout=0: _Resp(data))
    dst = tmp_path / "v" / "m.onnx"
    localtts._download("https://huggingface.co/x", hashlib.sha256(data).hexdigest(), len(data), dst)
    assert dst.read_bytes() == data
    for sha, size in (("0" * 64, len(data)), (hashlib.sha256(data).hexdigest(), len(data) + 1)):
        bad = tmp_path / "w" / "m.onnx"
        with pytest.raises(localtts.DownloadError):
            localtts._download("https://huggingface.co/x", sha, size, bad)
        assert not bad.exists() and not bad.with_name("m.onnx.part").exists()


def test_download_refuses_redirect_to_unknown_host(monkeypatch, tmp_path):
    data = b"x"
    monkeypatch.setattr(localtts.urllib.request, "urlopen",
                        lambda req, timeout=0: _Resp(data, url="https://evil.example.com/x"))
    with pytest.raises(localtts.DownloadError):
        localtts._download("https://huggingface.co/x", hashlib.sha256(data).hexdigest(), 1, tmp_path / "a")
    assert list(tmp_path.iterdir()) == []


def _tar(path, entries):
    with tarfile.open(path, "w:bz2") as tar:
        for name, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "link":
                info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                tar.addfile(info)
            else:
                info.size = 2
                tar.addfile(info, io.BytesIO(b"ok"))
    return path


def test_archive_extraction_is_contained(tmp_path):
    good = _tar(tmp_path / "good.tar.bz2", [("pack", "dir"), ("pack/model.onnx", "file"), ("pack/d/x.txt", "file")])
    out = tmp_path / "out"
    out.mkdir()
    localtts._safe_extract(good, out, "pack")
    assert (out / "pack" / "d" / "x.txt").read_bytes() == b"ok"
    for entries in ([("pack/../../escape.txt", "file")], [("/abs.txt", "file")], [("other/x.txt", "file")],
                    [("pack/link", "link")], [("pack/C:/x.txt", "file")]):
        evil = _tar(tmp_path / "evil.tar.bz2", entries)
        dest = tmp_path / "dest"
        dest.mkdir(exist_ok=True)
        with pytest.raises(localtts.DownloadError):
            localtts._safe_extract(evil, dest, "pack")
        assert list(dest.rglob("*")) == []
    assert not (tmp_path.parent / "escape.txt").exists()


def test_unknown_voice_ids_never_touch_the_disk(tmp_path):
    with pytest.raises(localtts.DownloadError):
        localtts.install("piper:../../evil")
    assert localtts.synthesize_to_wav("hi", "piper:../../evil", str(tmp_path / "a.wav"))[0] is False
    localtts.remove("piper:../../evil")  # no-op


# ---------------------------------------------------------------------------------- privacy mode
def _cfg(**kw):
    cfg = {"voice": "en-US-JennyNeural", "auto_route_language": True, "preferred_voices": dict(voices.DEFAULT_PREFERRED)}
    cfg.update(kw)
    return cfg


def test_offline_only_never_uses_an_online_voice(monkeypatch):
    monkeypatch.setattr(core, "_local_hd_for", lambda fam, cfg: "piper:en_US-joe-medium" if fam == "english" else None)
    monkeypatch.setattr(core, "_windows_voice_for", lambda fam: "Microsoft Asaf - Hebrew (Israel)" if fam == "hebrew" else None)
    plan = core._speech_plan(_cfg(offline_only=True), "A sentence in English to read aloud.", "english", None)
    assert plan["voice"] == "piper:en_US-joe-medium" and plan["private"]
    plan = core._speech_plan(_cfg(offline_only=True), "שלום עולם, זה טקסט בעברית לקריאה", "hebrew", None)
    assert plan["voice"] == "Microsoft Asaf - Hebrew (Israel)" and not voices.is_online(plan["voice"])
    plan = core._speech_plan(_cfg(offline_only=True), "Bonjour à tous, voici un texte en français.", "french", None)
    assert not voices.is_online(plan["voice"])  # nothing offline for French → Zira, never online
    plan = core._speech_plan(_cfg(), "A sentence in English to read aloud.", "english", None)
    assert plan["voice"] == "en-US-JennyNeural" and not plan["private"]


def test_removed_offline_voice_falls_back_to_a_working_voice(monkeypatch):
    monkeypatch.setattr(core, "_local_hd_usable", lambda v: False)
    plan = core._speech_plan(_cfg(voice="piper:en_US-joe-medium"), "Some English text to read now.", "english", None)
    assert plan["voice"] == voices.DEFAULT_PREFERRED["english"]


# ---------------------------------------------------------------------------------- pipeline
def _patch(monkeypatch, cfg, online_ok=True, local_ok=True):
    calls = {"online": [], "local": [], "play": [], "sapi": []}
    monkeypatch.setattr(core, "_halt_audio_engines", lambda: None)
    monkeypatch.setattr(core, "trigger_notification", lambda *a, **k: None)
    monkeypatch.setattr(core, "load_config", lambda: cfg)
    monkeypatch.setattr(core, "_local_hd_usable", lambda v: True)
    monkeypatch.setattr(core, "_local_hd_for", lambda fam, c: "piper:en_US-joe-medium" if fam == "english" else None)
    monkeypatch.setattr(core, "_windows_voice_for", lambda fam: None)

    def online(text, voice, out, **kw):
        calls["online"].append(text)
        if online_ok:
            open(out, "wb").write(b"ID3")
        return (True, "") if online_ok else (False, "offline network")

    def local(text, voice, out, **kw):
        calls["local"].append(voice)
        if local_ok:
            open(out, "wb").write(b"RIFF")
        return (True, "") if local_ok else (False, "engine error")

    monkeypatch.setattr(core, "_synthesize_to_file", online)
    monkeypatch.setattr(localtts, "synthesize_to_wav", local)
    monkeypatch.setattr(core, "play_audio_file", lambda path, *a, **k: calls["play"].append(path) or True)
    monkeypatch.setattr(core, "speak_offline_sapi", lambda text, **kw: calls["sapi"].append(kw.get("voice_pref")) or True)
    return calls


TEXT = "This is a test sentence for the offline voices. It has a second sentence as well."


def test_offline_hd_voice_reads_with_the_local_engine(monkeypatch):
    calls = _patch(monkeypatch, _cfg(voice="piper:en_US-joe-medium"))
    res = core.speak_text(TEXT)
    assert res["status"] == "success" and res["mode"] == "offline_hd"
    assert calls["online"] == [] and calls["local"] and all(p.endswith(".wav") for p in calls["play"])


def test_online_failure_continues_with_offline_hd_voice(monkeypatch):
    calls = _patch(monkeypatch, _cfg(), online_ok=False)
    res = core.speak_text(TEXT)
    assert res["status"] == "fallback" and res["mode"] == "offline_hd"
    assert calls["local"] and calls["sapi"] == []


def test_offline_hd_failure_continues_with_windows_voice(monkeypatch):
    calls = _patch(monkeypatch, _cfg(voice="piper:en_US-joe-medium"), local_ok=False)
    res = core.speak_text(TEXT)
    assert res["status"] == "fallback" and res["mode"] == "offline" and calls["sapi"] == ["Zira"]
    assert calls["online"] == []  # a failed offline voice never sends the text online


def test_privacy_mode_never_calls_the_online_service(monkeypatch):
    calls = _patch(monkeypatch, _cfg(offline_only=True), online_ok=True)
    core.speak_text(TEXT)
    assert calls["online"] == [] and calls["local"]


def test_try_voice_override_uses_exactly_that_voice(monkeypatch):
    calls = _patch(monkeypatch, _cfg())
    res = core.speak_text(TEXT, voice="kokoro:af_heart")
    assert res["mode"] == "offline_hd" and calls["local"][0] == "kokoro:af_heart"


def test_secret_guard_applies_with_offline_voices(monkeypatch):
    spoken = []
    monkeypatch.setattr(core, "get_clipboard_text", lambda: "Tr0ub4dor&3")
    monkeypatch.setattr(core, "clipboard_is_private", lambda: False)
    monkeypatch.setattr(core, "is_any_speaking", lambda: False)
    monkeypatch.setattr(core, "speak_text", lambda *a, **k: spoken.append(a))
    monkeypatch.setattr(core, "trigger_notification", lambda *a, **k: None)
    assert core.toggle_speak_or_stop(blocking=True)["status"] == "skipped" and spoken == []


def test_tray_offers_download_when_no_offline_hd_voice(monkeypatch):
    from fluentvoice import tray
    monkeypatch.setattr(localtts, "installed_voices", lambda: [])
    app = tray.FluentVoiceTrayApp.__new__(tray.FluentVoiceTrayApp)
    items = list(app._local_hd_items())
    assert len(items) == 1 and "Download offline HD voices" in items[0].text
    monkeypatch.setattr(localtts, "installed_voices", lambda: [localtts.info("piper:en_US-joe-medium")])
    names = [i.text for i in app._local_hd_items() if hasattr(i, "text")]
    assert "English" in names and "Manage offline HD voices…" in names


def test_voice_licence_doc_is_up_to_date():
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("gen", root / "scripts" / "gen_voice_licenses.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    assert (root / "docs" / "VOICE_LICENSES.md").read_text(encoding="utf-8") == gen.render(), \
        "run: python scripts/gen_voice_licenses.py"


def test_tampered_model_on_disk_is_never_loaded(monkeypatch, tmp_path):
    monkeypatch.setattr(localtts, "PIPER_DIR", tmp_path)
    model = "en_US-joe-medium"
    for _url, _sha, size, dst in localtts._piper_files(model):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"\0" * size)  # right size, wrong content
    localtts._verified_models.discard(model)
    assert localtts.is_installed("piper:" + model)
    ok, err = localtts.synthesize_to_wav("Hello", "piper:" + model, str(tmp_path / "o.wav"))
    assert not ok and "fingerprint" in err and model not in localtts._verified_models


def test_every_voice_label_is_unique():
    labels = [voices.label_for(v["id"]) for v in localtts.VOICES] + [label for _, label, _ in voices.CATALOG]
    assert len(labels) == len(set(labels))


def test_privacy_mode_follows_the_language_of_the_text(monkeypatch):
    monkeypatch.setattr(core, "_local_hd_for", lambda fam, cfg: {"spanish": "piper:es_ES-davefx-medium",
                                                                 "english": "piper:en_US-joe-medium"}.get(fam))
    monkeypatch.setattr(core, "_windows_voice_for", lambda fam: None)
    text = "Hoy hace buen tiempo y la reunión empieza a las diez de la mañana en la oficina."
    cfg = _cfg(offline_only=True, voice="en-US-AvaMultilingualNeural")  # Multilingual keeps Spanish itself
    assert core._speech_plan(cfg, text, "spanish", None)["voice"] == "piper:es_ES-davefx-medium"
    assert core._speech_plan(cfg, "Plain English words for the reader today.", "english", None)["voice"] == \
        "piper:en_US-joe-medium"
