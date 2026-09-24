"""2026 live Tuesday-model display rules and slate merge.

2025 predictions_tracker.csv stays byte-identical. 2026 matchups live in slate_2026.csv.
"""
import hashlib
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "betting"))

from live_2026 import (  # noqa: E402
    LIVE_HIGH_N,
    LIVE_HIGH_WILSON_LOWER,
    LIVE_HIGH_WILSON_Z,
    LIVE_HIGH_WINS,
    TRACKER_2025_MD5,
    attach_slate,
    display_high,
    high_dropped,
    is_finale_week,
    is_live_season,
    leftover_to_home_margin,
    row_display_high,
    row_qualifying_edge,
    row_qualifying_spread,
    row_high_dropped,
    season_high_record,
    sportsbook_to_nflverse,
    tracker_2025_payload,
    tuesday_high,
)

_TRACKER = _HERE / "betting" / "predictions_tracker.csv"
_SLATE = _HERE / "betting" / "slate_2026.csv"


def _wilson_one_sided_lower(wins: int, n: int, z: float) -> float:
    p = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * ((p * (1 - p) + z2 / (4 * n)) / n) ** 0.5) / denom
    return center - margin


def test_2025_tracker_byte_identical():
    digest = hashlib.md5(tracker_2025_payload(_TRACKER)).hexdigest()
    assert digest == TRACKER_2025_MD5, digest
    if b",2026," not in _TRACKER.read_bytes():
        assert hashlib.md5(_TRACKER.read_bytes()).hexdigest() == TRACKER_2025_MD5


def test_slate_is_matchups_only():
    df = pd.read_csv(_SLATE)
    assert len(df) == 272
    assert set(df["week"].astype(int)) == set(range(1, 19))
    assert df["predicted_margin"].isna().all()
    assert df["ens_predicted_margin"].isna().all()
    assert df["spread_line"].isna().all()
    assert df["tuesday_spread_line"].isna().all()
    assert (df["mode"] == "matchup").all()
    w1 = df[df["week"] == 1]
    assert (w1["away_team"] == "NE").any()
    assert (w1["home_team"] == "SEA").any()
    assert "2026-09-09" in set(w1["gameday"].astype(str))


def test_attach_slate_does_not_duplicate_tracker_ids():
    tracker = pd.read_csv(_TRACKER)
    out = attach_slate(tracker, _HERE)
    assert out["game_id"].is_unique
    assert len(out) == len(tracker) + 272
    assert set(tracker["game_id"]).issubset(set(out["game_id"]))
    assert (out["season"] == 2025).sum() == len(tracker)
    assert (out["season"] == 2026).sum() == 272


def test_attach_slate_skips_already_logged_2026_row(tmp_path):
    tracker = pd.DataFrame(
        {"game_id": ["2026_01_NE_SEA"], "season": [2026], "week": [1]}
    )
    out = attach_slate(tracker, _HERE)
    assert (out["game_id"] == "2026_01_NE_SEA").sum() == 1
    assert len(out) == 272


def test_display_high_demote_only():
    # HIGH_GAP is 3.0 (bumped from 2.5, see betting/live_2026.py history).
    assert tuesday_high(10, 6.9)
    assert not tuesday_high(10, 7.1)
    assert tuesday_high(10, 7)
    assert display_high(10, 7, None)
    assert display_high(10, 7, 6.5)
    assert not display_high(10, 7, 8)
    assert high_dropped(10, 7, 8)
    assert not high_dropped(10, 7, None)
    assert not display_high(10, 8, 6)
    assert not high_dropped(10, 8, 6)


def test_finale_week_never_high():
    assert is_finale_week(2026, 18, "REG")
    assert not display_high(12, 7, None, season=2026, week=18)
    assert not is_finale_week(2026, 18, "POST")


def test_row_helpers_and_live_season():
    assert is_live_season(2026)
    assert not is_live_season(2025)
    row = pd.Series(
        {
            "ens_predicted_margin": 10.0,
            "tuesday_spread_line": 7.0,
            "live_spread_line": 8.5,
            "season": 2026,
            "week": 1,
            "game_type": "REG",
        }
    )
    assert not row_display_high(row)
    assert row_high_dropped(row)


def test_2026_high_qualifies_off_median_and_shop_cannot_promote():
    """The best captured quote is execution only, never a looser trigger."""
    row = pd.Series(
        {
            "ens_predicted_margin": 2.89,
            "tuesday_median_spread_line": 5.0,   # consensus: gap 2.11, under the cut
            "tuesday_spread_line": 5.5,          # best quote: gap 2.61, over the cut
            "tuesday_spread_book": "DraftKings",
            "season": 2026,
            "week": 1,
            "game_type": "REG",
        }
    )
    assert row_qualifying_spread(row) == 5.0
    assert round(row_qualifying_edge(row), 2) == -2.11
    assert not row_display_high(row)

    # A median-qualified game remains HIGH while its shopped execution improves.
    # HIGH_GAP is 3.0: median gap 3.5 qualifies, shopped gap 4.0 keeps it HIGH.
    row["ens_predicted_margin"] = 0.0
    row["tuesday_median_spread_line"] = 3.5
    row["tuesday_spread_line"] = 4.0
    assert row_display_high(row)


def test_one_sided_wilson_claim_matches_locked_book():
    # Values load from the versioned promoted-model benchmark artifact.
    assert LIVE_HIGH_WINS == 256
    assert LIVE_HIGH_N == 432
    lo = _wilson_one_sided_lower(LIVE_HIGH_WINS, LIVE_HIGH_N, LIVE_HIGH_WILSON_Z)
    assert round(lo, 4) == round(LIVE_HIGH_WILSON_LOWER, 4)
    assert round(lo, 4) == 0.5532


def test_leftover_converts_to_site_home_margin():
    leftover = 4.0
    sportsbook = -7.0
    home = leftover_to_home_margin(leftover, sportsbook)
    nflverse = sportsbook_to_nflverse(sportsbook)
    assert home == 11.0
    assert nflverse == 7.0
    assert abs(home - nflverse) == abs(leftover)
    assert tuesday_high(home, nflverse)


def _mk_high_fixture(rows):
    cols = ["season", "week", "ens_predicted_margin", "tuesday_spread_line",
            "live_spread_line", "actual_margin", "ens_model_correct"]
    return pd.DataFrame(rows, columns=cols)


def _track_record_high_ref(df, season):
    """Independent replication of the Track Record page's live HIGH filter, so
    season_high_record can never silently diverge from what Track Record shows."""
    sdf = df[(df["season"] == season) & (df["actual_margin"].notna())].copy()
    if sdf.empty:
        return 0, 0
    col = ("ens_model_correct"
           if ("ens_model_correct" in sdf.columns and sdf["ens_model_correct"].notna().any())
           else "model_correct")
    hdf = sdf[sdf.apply(row_display_high, axis=1)]
    return int(hdf[col].sum()), int(hdf[col].notna().sum())


def test_season_high_record_counts_graded_high_only():
    df = _mk_high_fixture([
        (2026, 1, 6.0, -2.0, -2.0, 7, 1),                     # HIGH, graded, correct
        (2026, 1, 1.0, -1.0, -1.0, -3, 0),                    # gap 2.0 -> not HIGH
        (2026, 2, -5.0, 1.0, 1.0, 2, 0),                      # HIGH, graded, wrong
        (2026, 2, 9.0, 3.0, 3.0, float("nan"), float("nan")),  # HIGH but UNGRADED
        (2026, 3, 8.0, 3.0, 3.0, 10, 1),                      # HIGH, graded, correct
        (2025, 10, 9.0, 0.0, 0.0, 5, 1),                      # other season
    ])
    assert season_high_record(df, 2026) == (2, 3, round(2 / 3 * 100, 1))


def test_season_high_record_matches_track_record_filter():
    df = _mk_high_fixture([
        (2026, 1, 6.0, -2.0, -2.0, 7, 1),
        (2026, 2, -5.0, 1.0, 1.0, 2, 0),
        (2026, 3, 8.0, 3.0, 3.0, 10, 1),
        (2026, 4, 0.5, 0.0, 0.0, 3, 1),                       # not HIGH
        (2026, 5, 9.0, 3.0, 3.0, float("nan"), float("nan")),  # ungraded
    ])
    wins, n, _ = season_high_record(df, 2026)
    assert (wins, n) == _track_record_high_ref(df, 2026)


def test_season_high_record_empty_preseason_and_other_season():
    assert season_high_record(pd.DataFrame(), 2026) == (0, 0, None)
    only_ungraded = _mk_high_fixture([(2026, 5, 9.0, 3.0, 3.0, float("nan"), float("nan"))])
    assert season_high_record(only_ungraded, 2026) == (0, 0, None)
    only_2025 = _mk_high_fixture([(2025, 10, 9.0, 0.0, 0.0, 5, 1)])
    assert season_high_record(only_2025, 2026) == (0, 0, None)


def test_season_high_record_falls_back_to_model_correct():
    df = _mk_high_fixture([
        (2026, 1, 6.0, -2.0, -2.0, 7, 1),
        (2026, 2, -5.0, 1.0, 1.0, 2, 0),
        (2026, 3, 8.0, 3.0, 3.0, 10, 1),
    ]).drop(columns=["ens_model_correct"])
    df["model_correct"] = [1, 0, 1]
    assert season_high_record(df, 2026)[:2] == (2, 3)
