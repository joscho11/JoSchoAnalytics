"""`totals_asof` must reproduce shift(1).rolling(n) on history AND work for future games.

SCOPE OF THIS PROOF — read before citing it. Every case here is **synthetic and
property-based**: `_synth_history` generates deterministic pseudo-random team-weeks with a
fixed seed. No real schedule, play-by-play or scoring data is loaded. What is established
is an ALGEBRAIC equivalence — for every generated historical row the as-of lookup equals
`groupby(team).shift(1).rolling(n, min_periods=1).mean()` — plus the boundary behaviours
(no history, same-week exclusion, season crossing).

That is meaningful but limited. It does NOT establish that the real nflverse schedule
produces the same values, because it exercises none of the real data's shape: byes,
mid-season team relocations/renames, tied ordering keys, postponed games, or NaN scores.
An integration test against a retained historical schedule fixture is still OWED before
this module is wired into `build_totals_features` (see the module docstring, which records
that the wiring is not done).

Earlier versions of this docstring said the proof was "against real schedule data". That
was false and is corrected here.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_BETTING = Path(__file__).resolve().parent
if str(_BETTING) not in sys.path:
    sys.path.insert(0, str(_BETTING))

from totals_asof import league_asof_rolling, team_asof_rolling  # noqa: E402


def _synth_history(n_teams=6, seasons=(2023, 2024), weeks=14, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for w in range(1, weeks + 1):
            for t in range(n_teams):
                rows.append({"team": f"T{t}", "season": s, "week": w,
                             "pts": float(rng.integers(3, 45))})
    return pd.DataFrame(rows)


def test_matches_shift_rolling_on_every_synthetic_historical_row():
    hist = _synth_history()
    ref = hist.sort_values(["team", "season", "week"]).copy()
    ref["expected"] = (ref.groupby("team")["pts"]
                       .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean()))
    got = team_asof_rolling(hist, ref[["team", "season", "week"]], "pts", window=5)
    exp, got = ref["expected"].to_numpy(), got.to_numpy()
    both_nan = np.isnan(exp) & np.isnan(got)
    close = np.isclose(exp, got, equal_nan=False) | both_nan
    assert close.all(), (
        f"{(~close).sum()} of {len(exp)} rows differ from shift(1).rolling(5); "
        f"first bad index {int(np.argmax(~close))}")
    assert np.isnan(exp).sum() > 0, "fixture has no first-game rows -- test is weak"


def test_a_future_game_gets_the_last_five_completed_games():
    """The whole point: a target the history has never seen still resolves."""
    hist = _synth_history(n_teams=1, seasons=(2025,), weeks=8)
    future = pd.DataFrame([{"team": "T0", "season": 2025, "week": 9}])
    got = float(team_asof_rolling(hist, future, "pts", window=5).iloc[0])
    expected = hist.sort_values("week")["pts"].tail(5).mean()
    assert got == pytest.approx(expected)
    assert not np.isnan(got), "a future game must not resolve to NaN when history exists"


def test_no_history_is_nan_not_a_substituted_value():
    hist = _synth_history(n_teams=1, seasons=(2025,), weeks=3)
    tgt = pd.DataFrame([{"team": "UNSEEN", "season": 2025, "week": 4}])
    assert np.isnan(team_asof_rolling(hist, tgt, "pts").iloc[0]), \
        "an unknown team must yield NaN so the caller's preflight can fail closed"


def test_same_week_games_are_not_usable_pregame():
    """Strictly prior: a game in the target's own (season, week) must be excluded."""
    hist = pd.DataFrame([{"team": "A", "season": 2025, "week": 5, "pts": 99.0},
                         {"team": "A", "season": 2025, "week": 4, "pts": 10.0}])
    tgt = pd.DataFrame([{"team": "A", "season": 2025, "week": 5}])
    assert float(team_asof_rolling(hist, tgt, "pts").iloc[0]) == pytest.approx(10.0)


def test_league_asof_matches_the_shift_rolling_weekly_mean():
    hist = _synth_history(n_teams=8, seasons=(2024,), weeks=12)
    weekly = (hist.groupby(["season", "week"])["pts"].mean().reset_index()
              .rename(columns={"pts": "wk"}))
    weekly["expected"] = (weekly.groupby("season")["wk"]
                          .transform(lambda x: x.shift(1).rolling(4, min_periods=1).mean()))
    got = league_asof_rolling(hist, weekly[["season", "week"]], "pts", window=4)
    exp, got = weekly["expected"].to_numpy(), got.to_numpy()
    both_nan = np.isnan(exp) & np.isnan(got)
    assert (np.isclose(exp, got) | both_nan).all()


def test_crosses_season_boundaries_like_the_original():
    """The original sorted by (team, season, week) with no per-season reset."""
    hist = pd.DataFrame([
        {"team": "A", "season": 2024, "week": 17, "pts": 20.0},
        {"team": "A", "season": 2024, "week": 18, "pts": 30.0},
    ])
    tgt = pd.DataFrame([{"team": "A", "season": 2025, "week": 1}])
    assert float(team_asof_rolling(hist, tgt, "pts").iloc[0]) == pytest.approx(25.0)
