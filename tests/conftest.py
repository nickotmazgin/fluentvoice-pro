"""Test isolation: never touch the real ~/.fluentvoice (config, speech.log, stop signals).

fluentvoice.config computes APP_DIR from Path.home() at import time, so the home
directory is redirected here, before any test module imports fluentvoice.
"""
import os
import tempfile

_TEST_HOME = tempfile.mkdtemp(prefix="fluentvoice-tests-")
os.environ["HOME"] = _TEST_HOME
os.environ["USERPROFILE"] = _TEST_HOME  # Path.home() on Windows
