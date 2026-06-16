"""Hermetic tests for betting/calibration.py.

No network / no CSV I/O — every test runs on small synthetic frames in well under a
second, so this runs in CI (.github/workflows/test.yml) alongside test_features.py.

Run:  pytest betting/test_calibration.py    (or: python betting/test_calibration.py)
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so `import calibration` works from any CWD
from calibration import (
    BREAKEVEN,
    MIN_BUCKET_N,
    Estimate,
    build_calibration,
    card_line,
    cover_probability,
    wilson_interval,
)


# ============================================================================
# Synthetic fixtures
# ============================================================================
def _tracker(rows):
    """Build a minimal tracker frame; rows = list of (tier, edge, correct-or-None)."""
    return pd.DataFrame(
        [
            {"consensus_tier": t, "ens_model_edge": e, "ens_model_correct": c, "season": 2025}
            for (t, e, c) in rows
        ]
    )


def _balanced_tracker():
    """A graded set with a clear tier ordering and enough n per tier to be trusted."""
    rows = []
    rows += [("HIGH", 4.0, 1)] * 11 + [("HIGH", 4.0, 0)] * 6     # 11/17 = 64.7%
    rows += [("MEDIUM", 1.5, 1)] * 25 + [("MEDIUM", 1.5, 0)] * 17  # 25/42 = 59.5%
    rows += [("PASS", 0.5, 1)] * 30 + [("PASS", 0.5, 0)] * 28      # 30/58 = 51.7%
    return _tracker(rows)


# ============================================================================
# wilson_interval
# ============================================================================
def test_wilson_empty_sample_is_full_range():
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_brackets_point_estimate():
    lo, hi = wilson_interval(11, 17)
    assert lo < 11 / 17 < hi
    assert 0.0 <= lo <= hi <= 1.0


def test_wilson_tightens_with_n():
    # same rate, 10x the sample → narrower interval
    lo_small, hi_small = wilson_interval(6, 10)
    lo_big, hi_big = wilson_interval(60, 100)
    assert (hi_big - lo_big) < (hi_small - lo_small)


def test_wilson_never_exceeds_unit_interval():
    lo, hi = wilson_interval(10, 10)  # 100% observed
    assert hi <= 1.0 and lo >= 0.0


# ============================================================================
# build_calibration
# ============================================================================
def test_build_calibration_overall_and_tiers():
    calib = build_calibration(_balanced_tracker())
    assert calib["n_graded"] == 117
    assert calib["overall"].n == 117
    assert calib["overall"].wins == 66
    assert calib["by_tier"]["HIGH"].rate == pytest.approx(11 / 17)
    assert calib["by_tier"]["MEDIUM"].rate == pytest.approx(25 / 42)
    assert calib["by_tier"]["PASS"].rate == pytest.approx(30 / 58)


def test_build_calibration_ignores_ungraded_rows():
    df = _tracker([("HIGH", 4.0, 1), ("HIGH", 4.0, 0), ("HIGH", 4.0, None)])
    calib = build_calibration(df)
    assert calib["n_graded"] == 2  # the None row is dropped


def test_build_calibration_edge_buckets_are_diagnostic():
    calib = build_calibration(_balanced_tracker())
    # buckets exist and partition the graded rows
    total = sum(e.n for e in calib["by_edge_bucket"].values())
    assert total == 117


def test_build_calibration_missing_column_raises():
    df = _balanced_tracker().drop(columns=["consensus_tier"])
    with pytest.raises(KeyError):
        build_calibration(df)


def test_build_calibration_empty_frame():
    df = _tracker([("HIGH", 4.0, None)])  # nothing graded
    calib = build_calibration(df)
    assert calib["n_graded"] == 0
    assert calib["overall"].n == 0


# ============================================================================
# cover_probability  (the fallback logic is the load-bearing part)
# ============================================================================
def test_cover_probability_uses_tier_when_well_sampled():
    calib = build_calibration(_balanced_tracker())
    est = cover_probability("HIGH", calib)
    assert est.basis == "tier:HIGH"
    assert est.rate == pytest.approx(11 / 17)


def test_cover_probability_falls_back_when_tier_too_thin():
    # HIGH has only 3 games (< MIN_BUCKET_N) → must fall back to overall
    rows = [("HIGH", 4.0, 1)] * 3 + [("PASS", 0.5, 1)] * 20 + [("PASS", 0.5, 0)] * 20
    calib = build_calibration(_tracker(rows))
    assert calib["by_tier"]["HIGH"].n < MIN_BUCKET_N
    est = cover_probability("HIGH", calib)
    assert est.basis == "overall"


def test_cover_probability_unknown_tier_falls_back():
    calib = build_calibration(_balanced_tracker())
    assert cover_probability("DOES_NOT_EXIST", calib).basis == "overall"
    assert cover_probability(None, calib).basis == "overall"


# ============================================================================
# Estimate semantics
# ============================================================================
def test_beats_breakeven_requires_lower_bound_above_bar():
    # 64.7% on 17 games: point estimate clears 52.4% but the CI lower bound does not
    calib = build_calibration(_balanced_tracker())
    high = calib["by_tier"]["HIGH"]
    assert high.rate > BREAKEVEN
    assert not high.beats_breakeven  # honest: small sample, lower bound below bar

    # a large, strong sample should clear the bar on the lower bound
    strong = Estimate(*_strong())
    assert strong.beats_breakeven


def _strong():
    lo, hi = wilson_interval(600, 1000)
    return (0.60, lo, hi, 1000, 600, "tier:HIGH")


def test_edge_pp_sign():
    calib = build_calibration(_balanced_tracker())
    assert calib["by_tier"]["HIGH"].edge_pp > 0
    assert calib["by_tier"]["PASS"].edge_pp < 0  # 51.7% < 52.4%


# ============================================================================
# card_line  (user-facing string)
# ============================================================================
def test_card_line_mentions_tier_ci_and_n():
    calib = build_calibration(_balanced_tracker())
    line = card_line("HIGH", calib)
    assert "HIGH-confidence bets" in line
    assert "64.7%" in line
    assert "95% CI" in line
    assert "n=17" in line


def test_card_line_falls_back_to_generic_label_when_thin():
    rows = [("HIGH", 4.0, 1)] * 3 + [("PASS", 0.5, 1)] * 20 + [("PASS", 0.5, 0)] * 20
    calib = build_calibration(_tracker(rows))
    line = card_line("HIGH", calib)
    assert "HIGH-confidence" not in line  # fell back to overall basis
    assert "Bets at this model" in line


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
