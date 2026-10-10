"""Test isolation: never touch the real ~/.fluentvoice (config, speech.log, stop signals).

fluentvoice.config computes APP_DIR from Path.home() at import time, so the home
directory is redirected here, before any test module imports fluentvoice.
"""
import atexit
import os
import shutil
import tempfile

import pytest

_TEST_HOME = tempfile.mkdtemp(prefix="fluentvoice-tests-")
os.environ["HOME"] = _TEST_HOME
os.environ["USERPROFILE"] = _TEST_HOME  # Path.home() on Windows


def _cleanup():
    # Don't leave one folder per run in %TEMP%. Close log files first: the rotating
    # speech.log handler keeps its file open and Windows can't delete open files.
    import logging
    logging.shutdown()
    shutil.rmtree(_TEST_HOME, ignore_errors=True)


atexit.register(_cleanup)


@pytest.fixture(autouse=True)
def _online_voices_healthy():
    """Each test starts with the online voices available (a simulated outage pauses them)."""
    from fluentvoice import core
    core._online.update(down_until=0.0, strikes=0, reason="", notified=False)
    yield
    core._online.update(down_until=0.0, strikes=0, reason="", notified=False)
