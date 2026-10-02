"""Offline HD voices: Piper and Kokoro, downloaded on request and run on this PC.

- Text never leaves the computer: speech is computed locally (ONNX models on the CPU).
- Downloads come only from the official Piper voice library (Hugging Face) and the official
  sherpa-onnx model releases (GitHub), over HTTPS, and every file must match the SHA-256 and
  size pinned in local_catalog.py. Anything else is deleted and never loaded.
- The Kokoro archive is unpacked with strict checks: regular files and folders only, nothing
  outside its own folder (no absolute paths, "..", links or devices).
- Engines are optional at runtime: if piper-tts / sherpa-onnx are missing, these voices are
  simply unavailable and FluentVoice falls back to the online or Windows voices.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tarfile
import threading
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path

from . import local_catalog as cat
from .config import APP_DIR

_log = logging.getLogger("fluentvoice.localtts")

VOICES_DIR = APP_DIR / "voices"
PIPER_DIR = VOICES_DIR / "piper"
KOKORO_DIR = VOICES_DIR / "kokoro"

# Redirect targets the downloads may end up on (Hugging Face CDN, GitHub release storage).
ALLOWED_HOSTS = ("huggingface.co", ".hf.co", "github.com", ".githubusercontent.com")
DOWNLOAD_TIMEOUT_SEC = 30
IDLE_UNLOAD_SEC = 300  # free the models' memory after 5 minutes without speech

PROVIDER_NAMES = {"piper": "Piper", "kokoro": "Kokoro"}


class DownloadError(Exception):
    pass


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------------------------- catalogue
def _gender_initial(name: str) -> str:
    return {"f": "Female", "m": "Male"}.get(name[1:2], "")


def _kokoro_entry(speaker: str, sid: int) -> dict:
    fam, region, lang = cat.KOKORO_LANGS[speaker[0]]
    return {
        "id": f"kokoro:{speaker}", "provider": "kokoro", "name": speaker.split("_", 1)[1].title(),
        "family": fam, "gender": _gender_initial(speaker), "region": region, "kind": "free",
        "licence": "Apache-2.0", "source": cat.KOKORO_HOME, "sid": sid, "lang": lang,
    }


def _piper_entry(row) -> dict:
    vid, name, fam, gender, region, kind, licence, source = row
    model, _, speaker = vid.split(":", 1)[1].partition("#")
    return {
        "id": vid, "provider": "piper", "name": name, "family": fam, "gender": gender, "region": region,
        "kind": kind, "licence": licence, "source": source, "model": model, "speaker": speaker or None,
    }


VOICES = [_piper_entry(r) for r in cat.PIPER_VOICES] + [_kokoro_entry(s, i) for s, i in cat.KOKORO_VOICES]
_BY_ID = {v["id"]: v for v in VOICES}


def is_local(voice: str) -> bool:
    return (voice or "").startswith(("piper:", "kokoro:"))


def info(voice: str) -> dict | None:
    return _BY_ID.get(voice)


def label(voice: str, language_name: str = "") -> str:
    """'Joe (US English Male · Piper Offline)'."""
    v = _BY_ID.get(voice)
    if not v:
        return voice
    lang = language_name or v["family"].title()
    if v["family"] == "english" and v["region"] in ("US", "UK"):
        desc = f"{v['region']} English {v['gender']}".strip()
    else:
        desc = " ".join(x for x in (lang, v["gender"]) if x)
        if v["region"]:
            desc += f", {v['region']}"
    return f"{v['name']} ({desc} · {PROVIDER_NAMES[v['provider']]} Offline)"


def voices_for(family: str) -> list[dict]:
    return [v for v in VOICES if v["family"] == family]


# ---------------------------------------------------------------------------------- engines
def engine_available(provider: str) -> bool:
    """True when the speech engine for `provider` can be imported."""
    try:
        if provider == "piper":
            import piper  # noqa: F401
        else:
            import sherpa_onnx  # noqa: F401
        return True
    except Exception:
        return False


def _piper_files(model: str) -> list[tuple[str, str, int, Path]]:
    path, sha, size, json_sha, json_size = cat.PIPER_MODELS[model]
    folder = PIPER_DIR / model
    return [
        (cat.PIPER_BASE_URL + path, sha, size, folder / f"{model}.onnx"),
        (cat.PIPER_BASE_URL + path + ".json", json_sha, json_size, folder / f"{model}.onnx.json"),
    ]


def _kokoro_folder() -> Path:
    return KOKORO_DIR / cat.KOKORO_PACK["folder"]


def _kokoro_ready() -> bool:
    d = _kokoro_folder()
    return all((d / f).exists() for f in ("model.onnx", "voices.bin", "tokens.txt")) and (d / "espeak-ng-data").is_dir()


def is_installed(voice: str) -> bool:
    v = _BY_ID.get(voice)
    if not v:
        return False
    if v["provider"] == "kokoro":
        return _kokoro_ready()
    return all(dst.exists() and dst.stat().st_size == size for _, _, size, dst in _piper_files(v["model"]))


def is_usable(voice: str) -> bool:
    v = _BY_ID.get(voice)
    return bool(v) and is_installed(voice) and engine_available(v["provider"])


def installed_voices() -> list[dict]:
    return [v for v in VOICES if is_installed(v["id"])]


def installed_signature() -> tuple:
    """Changes whenever a voice is added or removed (the tray rebuilds its menu then)."""
    sig = []
    try:
        for p in sorted(PIPER_DIR.glob("*/*.onnx")):
            sig.append(p.name)
    except Exception:
        pass
    sig.append("kokoro" if _kokoro_ready() else "")
    return tuple(sig)


def download_size(voice: str) -> int:
    v = _BY_ID[voice]
    if v["provider"] == "kokoro":
        return cat.KOKORO_PACK["size"]
    return sum(size for _, _, size, _ in _piper_files(v["model"]))


# ---------------------------------------------------------------------------------- download
def _host_allowed(url: str) -> bool:
    p = urllib.parse.urlsplit(url)
    host = (p.hostname or "").lower()
    return p.scheme == "https" and any(host == h.lstrip(".") or (h.startswith(".") and host.endswith(h))
                                       for h in ALLOWED_HOSTS)


def _download(url: str, sha256: str, size: int, dst: Path, progress=None, cancel=None, done_before: int = 0,
              total: int = 0):
    """Download url → dst, accepting it only if it has exactly `size` bytes and SHA-256 `sha256`."""
    if not _host_allowed(url):
        raise DownloadError(f"refusing to download from {url}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "FluentVoice-Pro"})
    h = hashlib.sha256()
    got = 0
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SEC) as resp, open(tmp, "wb") as f:
            if not _host_allowed(resp.geturl()):
                raise DownloadError(f"redirected to an unexpected host: {urllib.parse.urlsplit(resp.geturl()).hostname}")
            length = resp.headers.get("Content-Length")
            if length and int(length) != size:
                raise DownloadError(f"unexpected size {length} (expected {size})")
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                block = resp.read(1 << 16)
                if not block:
                    break
                got += len(block)
                if got > size:
                    raise DownloadError("download is larger than expected")
                h.update(block)
                f.write(block)
                if progress:
                    progress(done_before + got, total or size)
        if got != size or h.hexdigest() != sha256:
            raise DownloadError("checksum mismatch: the file is not the verified original")
        os.replace(tmp, dst)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _safe_extract(archive: Path, dest: Path, top: str, cancel=None):
    """Unpack a .tar.bz2 into dest/top, refusing anything that is not a plain file or folder
    inside `top` (path traversal, absolute paths, links, devices)."""
    root = dest.resolve()
    with tarfile.open(archive, "r:bz2") as tar:
        members = tar.getmembers()
        for m in members:
            name = m.name.replace("\\", "/")
            parts = [x for x in name.split("/") if x not in ("", ".")]
            if (not parts or parts[0] != top or name.startswith("/") or ":" in name or ".." in parts
                    or not (m.isfile() or m.isdir())):
                raise DownloadError(f"unsafe entry in archive: {m.name!r}")
            target = (root / Path(*parts)).resolve()
            if root not in target.parents:
                raise DownloadError(f"unsafe entry in archive: {m.name!r}")
        for m in members:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            parts = [x for x in m.name.replace("\\", "/").split("/") if x not in ("", ".")]
            target = root / Path(*parts)
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(m)
            with src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)


def install(voice: str, progress=None, cancel=None):
    """Download (and verify) everything `voice` needs. Raises DownloadError / Cancelled."""
    v = _BY_ID.get(voice)
    if not v:
        raise DownloadError(f"unknown voice {voice}")
    if is_installed(voice):
        return
    if v["provider"] == "piper":
        files = _piper_files(v["model"])
        total = sum(size for _, _, size, _ in files)
        done = 0
        try:
            for url, sha, size, dst in files:
                _download(url, sha, size, dst, progress, cancel, done_before=done, total=total)
                done += size
        except BaseException:
            shutil.rmtree(PIPER_DIR / v["model"], ignore_errors=True)
            raise
        _log.info("installed Piper voice %s", v["model"])
        return

    pack = cat.KOKORO_PACK
    KOKORO_DIR.mkdir(parents=True, exist_ok=True)
    archive = KOKORO_DIR / (pack["folder"] + ".tar.bz2")
    staging = KOKORO_DIR / ".unpack"
    try:
        _download(pack["url"], pack["sha256"], pack["size"], archive, progress, cancel)
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        _safe_extract(archive, staging, pack["folder"], cancel)
        shutil.rmtree(_kokoro_folder(), ignore_errors=True)
        os.replace(staging / pack["folder"], _kokoro_folder())
        if not _kokoro_ready():
            raise DownloadError("the Kokoro pack is incomplete")
        _verified_models.discard("kokoro")
        _verify_kokoro_files()
        _log.info("installed Kokoro pack %s", pack["folder"])
    except BaseException:
        shutil.rmtree(_kokoro_folder(), ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        try:
            archive.unlink(missing_ok=True)
        except Exception:
            pass


def remove(voice: str):
    """Delete the files of `voice` (for Kokoro: the whole pack, shared by all its voices)."""
    v = _BY_ID.get(voice)
    if not v:
        return
    unload()
    _verified_models.discard(v.get("model") or "kokoro")
    if v["provider"] == "kokoro":
        shutil.rmtree(_kokoro_folder(), ignore_errors=True)
    else:
        shutil.rmtree(PIPER_DIR / v["model"], ignore_errors=True)


# ---------------------------------------------------------------------------------- speech
_lock = threading.Lock()          # one synthesis at a time (models use several CPU threads)
_piper_cache: dict = {}           # model → PiperVoice (at most 2 kept)
_kokoro = {"lang": None, "tts": None}
_last_used = [0.0]
_unload_timer = [None]


def unload():
    """Free the loaded models (they use a few hundred MB of memory)."""
    with _lock:
        _piper_cache.clear()
        _kokoro["lang"], _kokoro["tts"] = None, None


def _schedule_unload():
    _last_used[0] = time.time()
    t = _unload_timer[0]
    if t is not None:
        t.cancel()

    def check():
        if time.time() - _last_used[0] >= IDLE_UNLOAD_SEC - 1:
            unload()

    t = threading.Timer(IDLE_UNLOAD_SEC, check)
    t.daemon = True
    t.start()
    _unload_timer[0] = t


_verified_models: set = set()


def _verify_files(key: str, files):
    """Hash model files again before their first use in this session: a file damaged on disk or
    replaced after the download is never loaded. files: [(path, sha256, size)]."""
    if key in _verified_models:
        return
    for dst, sha, size in files:
        h = hashlib.sha256()
        with open(dst, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        if dst.stat().st_size != size or h.hexdigest() != sha:
            raise DownloadError(f"{dst.name} does not match its verified fingerprint; download the voice again")
    _verified_models.add(key)


def _verify_piper_files(model: str):
    _verify_files(model, [(dst, sha, size) for _url, sha, size, dst in _piper_files(model)])


def _verify_kokoro_files():
    d = _kokoro_folder()
    _verify_files("kokoro", [(d / name, sha, size) for name, (sha, size) in cat.KOKORO_PACK["files"].items()])


def _piper_voice(model: str):
    pv = _piper_cache.get(model)
    if pv is None:
        from piper import PiperVoice
        _verify_piper_files(model)
        folder = PIPER_DIR / model
        pv = PiperVoice.load(str(folder / f"{model}.onnx"), config_path=str(folder / f"{model}.onnx.json"),
                             download_dir=str(folder))
        while len(_piper_cache) >= 2:
            _piper_cache.pop(next(iter(_piper_cache)))
        _piper_cache[model] = pv
    return pv


def _kokoro_tts(lang: str):
    if _kokoro["lang"] != lang or _kokoro["tts"] is None:
        import sherpa_onnx as so
        _verify_kokoro_files()
        d = _kokoro_folder()
        lexicon = {"en-us": "lexicon-us-en.txt", "en-gb-x-rp": "lexicon-gb-en.txt"}.get(lang)
        lexicons = str(d / lexicon) if lexicon and (d / lexicon).exists() else ""
        threads = max(1, min(4, (os.cpu_count() or 2) - 1))
        cfg = so.OfflineTtsConfig(
            model=so.OfflineTtsModelConfig(
                kokoro=so.OfflineTtsKokoroModelConfig(
                    model=str(d / "model.onnx"), voices=str(d / "voices.bin"), tokens=str(d / "tokens.txt"),
                    data_dir=str(d / "espeak-ng-data"), lexicon=lexicons, dict_dir=str(d / "dict"), lang=lang),
                num_threads=threads, provider="cpu"),
            max_num_sentences=1)
        _kokoro["tts"], _kokoro["lang"] = None, None  # drop the old model before loading the next
        _kokoro["tts"], _kokoro["lang"] = so.OfflineTts(cfg), lang
    return _kokoro["tts"]


def _write_wav(path: str, samples_int16: bytes, rate: int):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples_int16)


def synthesize_to_wav(text: str, voice: str, out_file: str, *, rate_mult: float = 1.0, abort_check=None):
    """Speak `text` with an offline HD voice into a WAV file. Returns (ok, error)."""
    v = _BY_ID.get(voice)
    if not v:
        return False, f"unknown offline voice {voice}"
    if not is_installed(voice):
        return False, "voice not downloaded"
    rate_mult = max(0.5, min(2.0, float(rate_mult or 1.0)))
    tmp = out_file + ".part"
    try:
        with _lock:
            if abort_check and abort_check():
                return False, "aborted"
            if v["provider"] == "piper":
                from piper import SynthesisConfig
                pv = _piper_voice(v["model"])
                sid = None
                if v["speaker"]:
                    sid = pv.config.speaker_id_map.get(v["speaker"])
                syn = SynthesisConfig(speaker_id=sid, length_scale=pv.config.length_scale / rate_mult)
                pcm = bytearray()
                rate = pv.config.sample_rate
                for chunk in pv.synthesize(text, syn_config=syn):
                    if abort_check and abort_check():
                        return False, "aborted"
                    pcm += chunk.audio_int16_bytes
                    rate = chunk.sample_rate
            else:
                import numpy as np
                tts = _kokoro_tts(v["lang"])

                def keep_going(_samples, _progress):
                    return 0 if (abort_check and abort_check()) else 1

                audio = tts.generate(text, sid=v["sid"], speed=rate_mult, callback=keep_going)
                if abort_check and abort_check():
                    return False, "aborted"
                samples = np.clip(np.asarray(audio.samples, dtype=np.float32), -1.0, 1.0)
                pcm = (samples * 32767).astype("<i2").tobytes()
                rate = audio.sample_rate
        if not pcm:
            return False, "the offline voice produced no audio"
        _write_wav(tmp, bytes(pcm), rate)
        os.replace(tmp, out_file)
        return True, ""
    except Exception as e:
        _log.error("offline HD synthesis failed (voice=%s, %d chars): %s: %s", voice, len(text), type(e).__name__, e)
        return False, f"{type(e).__name__}: {e}"
    finally:
        _schedule_unload()
        try:
            os.remove(tmp)
        except OSError:
            pass


def describe_installed() -> str:
    n = len(installed_voices())
    return f"{n} offline HD voice{'s' if n != 1 else ''} ready"


def licence_summary(voice: str) -> str:
    v = _BY_ID.get(voice)
    if not v:
        return ""
    use = "Free to use" if v["kind"] == "free" else "Personal use only (not for publishing or selling the audio)"
    return f"{use} • Licence: {v['licence']} • Source: {v['source']}"


def as_json() -> str:  # for docs / diagnostics
    return json.dumps(VOICES, ensure_ascii=False, indent=1)
