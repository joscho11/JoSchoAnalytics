"""Checkpoint / artifact loaders for the talent suites.

Contract (2026-08-03): a REQUIRED input that is missing is a FAILURE, never a
skip. The previous `_ck()` helpers called `pytest.skip()`, and because the
checkpoint dir was the hardcoded machine-local `C:/tmp/talent_build`, a fresh
Linux CI runner skipped 14 of 26 tests and reported success. A skipped
regression is not a regression.

The checkpoints resolve to `config.TEST_WORK` -- the committed fixture set under
`tests/fixtures/work/` by default, or a live build dir via `TALENT_TEST_WORK`.
"""
import pickle
import sys
from pathlib import Path

import pandas as pd
import pytest

PKG = Path(__file__).resolve().parents[1]
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from config import TEST_WORK  # noqa: E402

W = Path(TEST_WORK)

# Every checkpoint the two suites read. Absence of any of these is a FAILURE.
REQUIRED_CHECKPOINTS = (
    "FACETS.pkl",
    "MODEL_reproduce.pkl", "BOARD_reproduce.pkl",
    "MODEL_ruled.pkl", "BOARD_ruled.pkl",
    "MODEL_ruled2.pkl", "BOARD_ruled2.pkl",
)

# Shipped repo artifacts (git-tracked) the suites cross-check against.
REQUIRED_ARTIFACTS = ("talent_score_2026.csv", "rookie_score_2026.csv")


def _missing_msg(kind, name, where):
    return (f"REQUIRED {kind} {name!r} is missing from {where}. This is a hard "
            f"failure, not a skip: the regression it guards would otherwise pass "
            f"vacuously. Regenerate with tests/fixtures/make_fixtures.py, or point "
            f"TALENT_TEST_WORK at a build dir that contains it.")


def ck(name):
    """Load a REQUIRED build checkpoint. Fails loudly if absent."""
    if name not in REQUIRED_CHECKPOINTS:
        raise AssertionError(f"{name} is not declared in REQUIRED_CHECKPOINTS")
    p = W / name
    if not p.exists():
        pytest.fail(_missing_msg("checkpoint", name, W))
    with open(p, "rb") as fh:
        return pickle.load(fh)


def art(name):
    """Load a REQUIRED shipped artifact CSV. Fails loudly if absent."""
    if name not in REQUIRED_ARTIFACTS:
        raise AssertionError(f"{name} is not declared in REQUIRED_ARTIFACTS")
    p = PKG / name
    if not p.exists():
        pytest.fail(_missing_msg("artifact", name, PKG))
    return pd.read_csv(p)


def golden(name):
    """Load a REQUIRED golden file. Fails loudly if absent."""
    import json
    p = PKG / "tests" / "golden" / name
    if not p.exists():
        pytest.fail(_missing_msg("golden", name, p.parent))
    return json.loads(p.read_text())
