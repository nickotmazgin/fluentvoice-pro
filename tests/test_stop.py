"""Stop / generation abort smoke tests."""
import time
import threading

from fluentvoice import core


def test_stop_bumps_generation():
    before = core._current_generation
    core.stop_all_playback(notify=False)
    assert core._current_generation == before + 1
    assert core._is_speaking is False


def test_stop_aborts_play_loop_flag():
    """play_audio_file must exit when generation advances mid-wait."""
    with core._engine_lock:
        core._current_generation += 1
        my_gen = core._current_generation
        core._is_speaking = False
    core._halt_audio_engines()

    # Simulate a waiter that watches generation like play_audio_file
    done = {"ok": False}

    def waiter():
        while True:
            if my_gen != core._current_generation:
                done["ok"] = True
                return
            time.sleep(0.02)

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    time.sleep(0.05)
    core.stop_all_playback(notify=False)
    t.join(timeout=1.0)
    assert done["ok"] is True
