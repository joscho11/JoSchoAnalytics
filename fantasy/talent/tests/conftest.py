"""Talent test-package config.

Only registers markers. It must NOT create fixtures that mask a missing
REQUIRED input -- see tests/ckpt.py: absence of a required checkpoint is a hard
failure, never a skip.
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_inputs: PROTECTED manual rebuild from the real (licensed, "
        "out-of-repo) inputs. Skipped unless TALENT_REAL_REBUILD=1.")
