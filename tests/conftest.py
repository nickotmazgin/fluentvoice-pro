"""Test isolation: never touch the real ~/.fluentvoice (config, speech.log, stop signals).

fluentvoice.config computes APP_DIR from Path.home() at import time, so the home
directory is redirected here, before any test module imports fluentvoice.
"""
import atexit
import os
import shutil
import tempfile

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
