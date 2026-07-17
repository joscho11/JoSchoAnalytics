"""Hermetic tests for historical line analysis + CLV math — no file/network."""
import math
import os
import tempfile

import numpy as np
import pandas as pd

import historical_lines as hl
import clv_backtest as cb


def test_run_join_franchise_and_pushes():
    """run(): relocated abbrevs must join (OAK->LV), and exact pushes must be
    excluded (NaN), not scored as losses."""
    preds = pd.DataFrame({
        "predicted_margin": [5.0, 6.0, -5.0],
        "xgb_margin": [5.0, 6.0, -5.0], "ridge_margin": [5.0, 6.0, -5.0],
        "lgbm_margin": [5.0, 6.0, -5.0],
        "home_team": ["OAK", "KC", "NE"], "away_team": ["DEN", "BUF", "MIA"],
        "gameday": ["2019-09-08"] * 3, "season": [2019, 2019, 2019],
    })
    fake_lines = pd.DataFrame({
        "date": pd.to_datetime(["2019-09-08"] * 3),
        "home": ["LV", "KC", "NE"], "away": ["DEN", "BUF", "MIA"],
        "spread_open": [-1.0, 2.0, -2.5], "spread_close": [-1.0, 3.0, -3.0],
        "home_score": [20, 30, 10], "away_score": [17, 20, 13],  # margins +3, +10, -3
    })
    tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    preds.to_csv(tmp.name, index=False); tmp.close()
    orig = cb.hl.load_lines
    cb.hl.load_lines = lambda: fake_lines
    try:
        df = cb.run(1.0, tmp.name)
    finally:
        cb.hl.load_lines = orig
        os.unlink(tmp.name)

    assert len(df) == 3                                   # OAK joined via franchise norm
    assert "voter" in df.attrs["tier_method"]             # voter cols present -> reconstructed
    ne = df[df["home_team"] == "NE"].iloc[0]
    assert ne["side"] == "AWAY"                           # pred -5 vs open -2.5
    assert math.isnan(ne["won_close"])                    # margin -3 == close -3 -> push
    assert ne["won_open"] == 1.0                          # MIA +2.5 covered (NE lost by 3)


def test_clv_home_and_away():
    # nflverse sign (positive = home favored). HOME pick beats close when the
    # home side gets MORE favored (close > open).
    assert cb.clv_points(3.0, 4.0, "HOME") == 1.0     # home 3 -> 4, moved toward home
    assert cb.clv_points(3.0, 2.0, "HOME") == -1.0
    assert cb.clv_points(3.0, 2.0, "AWAY") == 1.0     # home less favored -> good for away
    assert cb.clv_points(3.0, 4.0, "AWAY") == -1.0
    assert math.isnan(cb.clv_points(3.0, 4.0, "PASS"))


def test_movement_summary():
    df = pd.DataFrame({
        "season": [2020, 2020, 2020, 2020],
        "spread_open": [3.0, -2.0, 7.0, 1.0],
        "spread_close": [3.0, -0.5, 9.5, 1.5],   # moves: 0, 1.5, 2.5, 0.5
        "total_open": [44, 50, 41, 47],
        "total_close": [45, 50, 44, 47],
    })
    m = hl.movement_summary(df)
    assert m["games"] == 4
    assert abs(m["spread"]["mean_abs_move"] - (0 + 1.5 + 2.5 + 0.5) / 4) < 1e-9
    assert m["spread"]["pct_moved_1+"] == 50.0      # 2 of 4 moved >= 1
    assert m["spread"]["pct_moved_2+"] == 25.0      # 1 of 4 moved >= 2


def test_closing_sharper():
    # close lands exactly on the margin, open is off -> close strictly better
    df = pd.DataFrame({
        "home_score": [24, 20], "away_score": [17, 17],   # margins 7, 3
        "spread_open": [3.0, 7.0], "spread_close": [7.0, 3.0],
    })
    s = hl.closing_is_sharper(df)
    assert s["mae_close"] < s["mae_open"]
    assert s["close_better_pct"] == 100.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


# ---- review 2026-07-17 U4A-4: totals pcts on ONE denominator (dropna) ----------
def test_totals_movement_single_denominator():
    import pandas as pd
    df = pd.DataFrame({
        "season": [2025, 2025, 2025],
        "spread_open": [3.0, -2.0, 1.0], "spread_close": [3.0, -2.0, 1.0],
        "total_open": [44.0, 47.0, float("nan")],
        "total_close": [45.5, 47.0, float("nan")],
    })
    s = hl.movement_summary(df)["total"]
    assert s["n_totals"] == 2
    assert s["pct_moved_1+"] == 50.0   # 1 of the 2 NON-NULL rows moved 1+ (was 33.3)


# ---- review 2026-07-17 U4A-11: duplicate-key merge guard ------------------------
def test_backtest_merge_rejects_duplicate_keys(monkeypatch, tmp_path):
    import pytest
    import pandas as pd
    dup_lines = pd.DataFrame({
        "date": ["2025-12-28", "2025-12-28"], "home": ["ATL", "ATL"],
        "away": ["LA", "LA"], "spread_open": [2.5, 2.0], "spread_close": [3.0, 2.5],
        "home_score": [24, 24], "away_score": [20, 20]})
    monkeypatch.setattr(cb.hl, "load_lines", lambda: dup_lines)
    preds = tmp_path / "preds.csv"
    pd.DataFrame({"date": ["2025-12-28"], "home_team": ["ATL"], "away_team": ["LA"],
                  "spread_line": [2.5], "recommendation": ["HOME (ATL)"],
                  "ridge_margin": [3.0], "lgbm_margin": [3.0], "xgb_margin": [3.0],
                  "actual_margin": [4.0]}).to_csv(preds, index=False)
    with pytest.raises(Exception):        # pandas MergeError on validate="one_to_one"
        cb.run(str(preds))
