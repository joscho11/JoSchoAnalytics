"""Shared fixtures for the v3.9 coaching tests.

v3.9w: `_PIPELINE_ASSERTIONS` is PROCESS-GLOBAL module state. Any test that runs the pipeline leaves
the counters positive for every test that follows, and the `pre_run` preflight phase requires them to
be EXACTLY zero. Without isolation, `pre_run` assertions would pass or fail on test ORDER rather than
on the behaviour under test.

The fixture resets BEFORE each test only. It never resets after, so a test may still inspect the
counters its own pipeline produced, and it can never make a `post_pipeline` assertion pass — that
phase requires POSITIVE counters, which only a real pipeline run inside the test can produce.
"""
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))


@pytest.fixture(autouse=True)
def _isolate_pipeline_assertion_counters():
    import run_coach_projection_experiment_v39 as EX
    EX.reset_pipeline_assertions()
    yield
