"""FluentVoice Pro - Direct Text Reader TTS diagnostic.

Run from the repo root with the console Python (not pythonw) so output is visible:
    python scripts\\diag_reader_tts.py

Checks, step by step:
  1. edge-tts import + version
  2. neural synthesis latency (short + ~3k char text), written to a unique temp file
  3. MCI playback from a worker thread (exactly how the Settings window plays audio),
     printing MCI mode/position every second so "playing but silent" is visible
  4. offline SAPI fallback voice count
"""

import os
import sys
import time
import asyncio
import threading
import ctypes
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SHORT = "FluentVoice diagnostic. If you can hear this sentence, neural playback works."
LONG = ("The Proof of Hidden Gods. This is a comprehensive check of the available research "
        "and historical records. ") * 30


def step(msg):
    print(f"\n=== {msg}", flush=True)


async def synth(text, voice, out):
    import edge_tts
    comm = edge_tts.Communicate(text, voice)
    t0 = time.time()
    first = None
    n = 0
    with open(out, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                if first is None:
                    first = time.time() - t0
                f.write(chunk["data"])
                n += len(chunk["data"])
    return first, time.time() - t0, n


def mci_play(path, seconds_max=12):
    winmm = ctypes.windll.winmm
    alias = "FVDiag"
    err = ctypes.create_unicode_buffer(256)
    rc = winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
    if rc:
        winmm.mciGetErrorStringW(rc, err, 256)
        print(f"  MCI open FAILED rc={rc}: {err.value}")
        return
    winmm.mciSendStringW(f"set {alias} time format milliseconds", None, 0, None)
    buf = ctypes.create_unicode_buffer(128)
    winmm.mciSendStringW(f"status {alias} length", buf, 128, None)
    print(f"  MCI open OK, length={buf.value} ms")
    rc = winmm.mciSendStringW(f"play {alias}", None, 0, None)
    print(f"  MCI play rc={rc}")
    t0 = time.time()
    while time.time() - t0 < seconds_max:
        winmm.mciSendStringW(f"status {alias} mode", buf, 128, None)
        mode = buf.value
        winmm.mciSendStringW(f"status {alias} position", buf, 128, None)
        print(f"  t={time.time()-t0:4.1f}s mode={mode!r} position={buf.value} ms", flush=True)
        if mode not in ("playing", "seeking"):
            break
        time.sleep(1.0)
    winmm.mciSendStringW(f"close {alias}", None, 0, None)


def main():
    from fluentvoice import config, __version__
    cfg = config.load_config()
    voice = cfg.get("voice", "en-US-AndrewMultilingualNeural")
    print(f"FluentVoice {__version__} | Python {sys.version.split()[0]} | exe={sys.executable}")
    print(f"voice={voice} engine={cfg.get('engine')} auto_read_copy={cfg.get('auto_read_copy')}")

    step("1. edge-tts import")
    try:
        import edge_tts
        print("  edge-tts", getattr(edge_tts, "__version__", "?"))
    except Exception as e:
        print("  IMPORT FAILED:", e)
        return

    tmp = Path(tempfile.gettempdir())
    for label, text in (("short", SHORT), ("long ~3k chars", LONG)):
        step(f"2. neural synthesis ({label}, {len(text)} chars)")
        out = tmp / f"fv_diag_{label.split()[0]}.mp3"
        try:
            first, total, n = asyncio.run(asyncio.wait_for(synth(text, voice, str(out)), 90))
            print(f"  first audio after {first:.2f}s, done in {total:.2f}s, {n:,} bytes")
        except Exception as e:
            print(f"  SYNTH FAILED: {type(e).__name__}: {e}")

    step("3. MCI playback from worker thread (listen now!)")
    short_mp3 = tmp / "fv_diag_short.mp3"
    if short_mp3.exists() and short_mp3.stat().st_size > 0:
        th = threading.Thread(target=mci_play, args=(str(short_mp3),), daemon=True)
        th.start()
        th.join(20)
    else:
        print("  skipped (no audio file)")

    step("4. offline SAPI voices")
    try:
        from fluentvoice import core
        for label, desc in core.get_installed_sapi_voices():
            print("  -", desc)
    except Exception as e:
        print("  SAPI check failed:", e)

    print("\nDone. Copy everything above and share it if anything says FAILED.")


if __name__ == "__main__":
    main()
