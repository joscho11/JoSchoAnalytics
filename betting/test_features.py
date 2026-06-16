"""Hermetic synthetic-data tests for betting/features.py (the feature source of truth).

Ported verbatim from the former inline ``if RUN_TESTS:`` cells of features.ipynb.
No network / nflreadpy calls — every test runs on small synthetic frames in well
under a second, so this runs in CI (.github/workflows/test.yml). Includes the
order-hash check that locks PROD_FEATURES_35 / FEATURE_COLS_85 to the trained-pkl
contract.

Run:  pytest betting/test_features.py    (or: python betting/test_features.py)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import nflreadpy as nfl

sys.path.insert(0, str(Path(__file__).resolve().parent))   # so `import features` works from any CWD
from features import (
    norm_name, canonicalize_ngs_team, TEAM_MAP, FEATURE_COLS_85, PROD_FEATURES_35,
    build_features, build_numeric_features,
    _build_schedule_context, _build_rolling_pbp, _build_sos_and_performance,
    _build_allpro, _build_situational_pbp, _build_qb_switch, _build_passer_rating,
    _build_injuries, _build_coach_win_pct,
)

# ============================================================================
# Synthetic fixtures
# ============================================================================
def _synth_schedule():
    """4 played weeks + 1 unplayed target week, KC vs BUF (KC wins by 7)."""
    played = [
        {"season": 2025, "week": w, "game_id": f"2025_W{w}_1", "game_type": "REG",
         "home_team": "KC", "away_team": "BUF",
         "spread_line": -3.0, "total_line": 47.0,
         "result": 7.0, "home_score": 24, "away_score": 17,
         "roof": "dome", "surface": "turf",
         "home_rest": 7, "away_rest": 7, "div_game": 0,
         "home_coach": "Andy Reid", "away_coach": "Sean McDermott",
         "home_qb_name": "P.Mahomes", "away_qb_name": "J.Allen",
         "gameday": "2025-10-05"}
        for w in range(1, 5)
    ]
    upcoming = {**played[0], "week": 5, "game_id": "2025_W5_1",
                "result": None, "home_score": None, "away_score": None}
    return pd.DataFrame(played + [upcoming])


def _synth_pbp():
    """Pass plays across 2024 (full season) and 2025 W1-4."""
    rows = [
        {"season": s, "week": w, "game_id": f"{s}_W{w}_1",
         "posteam": t, "defteam": o, "play_id": p,
         "play_type": "pass", "epa": 0.1, "yards_gained": 6,
         "sack": 0, "interception": 0, "fumble_lost": 0,
         "down": 1, "first_down": 1,
         "pass_attempt": 1, "complete_pass": 1, "passing_yards": 7, "pass_touchdown": 0,
         "passer_player_name": "P.Mahomes" if t == "KC" else "J.Allen"}
        for s in [2024, 2025]
        for w in (range(1, 19) if s == 2024 else range(1, 5))
        for t, o in [("KC", "BUF"), ("BUF", "KC")]
        for p in range(25)
    ]
    return pd.DataFrame(rows)


def _synth_allpro():
    return pd.DataFrame({
        "Year":   [2024, 2023],
        "Team":   ["KC",  "BUF"],
        "Player": ["P1",  "P2"],
        "Side":   ["offense", "defense"],
    })

def test_imports():
    assert callable(getattr(nfl, "load_nextgen_stats", None)), "nflreadpy.load_nextgen_stats missing"
    assert callable(getattr(nfl, "load_injuries", None)),       "nflreadpy.load_injuries missing"
    assert callable(getattr(nfl, "load_schedules", None)),      "nflreadpy.load_schedules missing"

def test_constants_and_order_hashes():
    import hashlib as _hashlib
    assert len(FEATURE_COLS_85) == 85, f"FEATURE_COLS_85 has {len(FEATURE_COLS_85)} entries"
    assert len(set(FEATURE_COLS_85)) == 85, "FEATURE_COLS_85 has duplicates"
    assert len(PROD_FEATURES_35) == 35, f"PROD_FEATURES_35 has {len(PROD_FEATURES_35)} entries"
    assert len(set(PROD_FEATURES_35)) == 35, "PROD_FEATURES_35 has duplicates"
    _missing = [f for f in PROD_FEATURES_35 if f not in FEATURE_COLS_85]
    assert not _missing, f"PROD_FEATURES_35 not a subset of FEATURE_COLS_85: {_missing}"
    assert "allpro_diff_home_def_away_off_3_years " in FEATURE_COLS_85, \
        "Trailing-space feature name was stripped — would break production pkl"

    # Order-preservation hash check. List order is contract: PROD_FEATURES_35 order
    # determines X_tr column order which determines pkl bytes. A reorder bug was hit
    # during Phase 2a (see memory [[feature-list-order-is-contract]]). These hashes
    # lock the canonical ablation-study order. If you intentionally change a list,
    # recompute the hash and update it here in the same commit as the retrain.
    _EXPECTED_FC85_HASH = "c1822ba82502f1963f6bde5b34270c54"
    _EXPECTED_PF35_HASH = "ac8801072e32165daadeaf83eba758e4"
    _fc85_hash = _hashlib.md5("\n".join(FEATURE_COLS_85).encode("utf-8")).hexdigest()
    _pf35_hash = _hashlib.md5("\n".join(PROD_FEATURES_35).encode("utf-8")).hexdigest()
    assert _fc85_hash == _EXPECTED_FC85_HASH, (
        f"FEATURE_COLS_85 order changed (got {_fc85_hash}, expected {_EXPECTED_FC85_HASH}). "
        "If intentional, retrain pkls and update the expected hash."
    )
    assert _pf35_hash == _EXPECTED_PF35_HASH, (
        f"PROD_FEATURES_35 order changed (got {_pf35_hash}, expected {_EXPECTED_PF35_HASH}). "
        "If intentional, retrain pkls and update the expected hash."
    )
    print(f"✓ Constants: 85 features, 35-subset, trailing-space, order-hashes — all locked.")

def test_norm_name():
    assert norm_name("Patrick Mahomes Jr.")    == "patrick mahomes", "Jr. not stripped"
    assert norm_name("J.J. Watt")               == "jj watt",         "Punctuation not stripped"
    assert norm_name("Ja'Marr Chase")           == "jamarr chase",    "Apostrophe not stripped"
    assert norm_name("Odell Beckham III")       == "odell beckham",   "Roman numeral not stripped"
    assert norm_name("D'Andre Swift")           == "dandre swift",    "Leading apostrophe not stripped"
    assert norm_name(None)                       == "",                "None should yield empty string"
    assert norm_name(123)                        == "",                "Non-string should yield empty string"
    assert norm_name("  Tom  Brady  ")          == "tom brady",       "Whitespace not collapsed"
    print("✓ norm_name: 7 cases pass.")

def test_canonicalize_ngs_team():
    # Rams relocated 2016 → "LA" everywhere in schedule
    assert canonicalize_ngs_team("LAR", 2019) == "LA"
    assert canonicalize_ngs_team("LAR", 2024) == "LA"
    # Raiders moved 2020; pre-2020 schedule uses "OAK"
    assert canonicalize_ngs_team("LV",  2018) == "OAK"
    assert canonicalize_ngs_team("LV",  2022) == "LV"
    # Chargers moved 2017; pre-2017 schedule uses "SD"
    assert canonicalize_ngs_team("LAC", 2016) == "SD"
    assert canonicalize_ngs_team("LAC", 2018) == "LAC"
    # Passthrough for unaffected teams
    assert canonicalize_ngs_team("KC",  2020) == "KC"
    print("✓ canonicalize_ngs_team: 7 cases pass.")

def test_build_schedule_context():
    _fs = _synth_schedule()
    _up = _fs[_fs["week"] == 5].copy()
    _out = _build_schedule_context(_up, _fs, target_week=5)
    assert "is_playoff" in _out.columns and "is_final_week" in _out.columns
    assert bool(_out["is_playoff"].iloc[0]) is False, "REG game flagged as playoff"
    # synth has REG weeks 1-5, so max REG week = 5 → final
    assert bool(_out["is_final_week"].iloc[0]) is True, "Last REG week not flagged"
    print("✓ Group 1 — schedule_context: playoff + final-week flags correct.")

def test_build_rolling_pbp():
    _fs = _synth_schedule()
    _pbp = _synth_pbp()
    _up = _fs[_fs["week"] == 5].copy()
    _wk = _pbp[["game_id", "week", "season"]].drop_duplicates()
    _out = _build_rolling_pbp(_up, _pbp, _wk)
    _expected = [
        "home_rolling_avg_epa", "home_rolling_avg_yards", "home_rolling_play_count",
        "away_rolling_avg_epa", "away_rolling_avg_yards", "away_rolling_play_count",
        "home_rolling_allowed_avg_epa", "home_rolling_allowed_avg_yards", "home_rolling_allowed_play_count",
        "away_rolling_allowed_avg_epa", "away_rolling_allowed_avg_yards", "away_rolling_allowed_play_count",
        "epa_home_off_away_def_rolling_diff", "epa_home_def_away_off_rolling_diff",
        "avg_yards_home_off_away_def_rolling_diff", "avg_yards_home_def_away_off_rolling_diff",
        "play_count_home_off_away_def_rolling_diff", "play_count_home_def_away_off_rolling_diff",
    ]
    for c in _expected:
        assert c in _out.columns, f"Missing column {c}"
    # Diff math sanity: epa_home_off_away_def_rolling_diff == home_rolling_avg_epa - away_rolling_allowed_avg_epa
    r = _out.iloc[0]
    assert np.isclose(r["epa_home_off_away_def_rolling_diff"],
                      r["home_rolling_avg_epa"] - r["away_rolling_allowed_avg_epa"]), \
        "epa diff math is wrong"
    print(f"✓ Group 2 — rolling_pbp: {len(_expected)} cols present, diff math correct.")

def test_build_sos_and_performance():
    _fs = _synth_schedule()
    _up = _fs[_fs["week"] == 5].copy()
    _history = _fs[(_fs["week"] < 5) & _fs["result"].notna()].copy()
    _hist_rolling = _history[["season","week","home_team","away_team","home_score","away_score","result","spread_line"]].copy()
    _out = _build_sos_and_performance(_up, _hist_rolling, _history, week_margin_lkp=None)
    for c in ["sos_diff", "season_sos_diff", "home_rolling_win_pct", "away_rolling_win_pct",
              "scoring_diff", "cover_rate_diff", "league_rolling_avg_abs_margin_by_week"]:
        assert c in _out.columns, f"Missing column {c}"
        assert not pd.isna(_out[c].iloc[0]), f"Column {c} is NaN"
    # KC won every game in synth → home_rolling_win_pct should be 1.0
    assert _out["home_rolling_win_pct"].iloc[0] == 1.0, \
        f"KC won 4/4 synth games — expected 1.0, got {_out['home_rolling_win_pct'].iloc[0]}"
    assert _out["away_rolling_win_pct"].iloc[0] == 0.0, "BUF lost 4/4 synth games — expected 0.0"
    print("✓ Groups 3+5 — sos_and_performance: KC win%=1.0, BUF win%=0.0, all cols present.")

def test_build_allpro():
    _fs = _synth_schedule()
    _up = _fs[_fs["week"] == 5].copy()
    _allpro = _synth_allpro()
    _out = _build_allpro(_up, _allpro, target_season=2025)
    for c in ["home_allpro_last_3_years_weighted", "away_allpro_last_3_years_weighted",
              "home_offense_allpro_3_years", "away_offense_allpro_3_years",
              "home_defense_allpro_3_years", "away_defense_allpro_3_years",
              "diff_allpro_last_3_years_weighted",
              "allpro_diff_home_def_away_off_3_years "]:  # trailing space!
        assert c in _out.columns, f"Missing column {c}"
    # KC has an offense AllPro in 2024 (weight 4 for target_season 2025) → home_offense_allpro_3_years = 4
    assert _out["home_offense_allpro_3_years"].iloc[0] == 4.0, \
        f"Expected KC offense_3yr=4, got {_out['home_offense_allpro_3_years'].iloc[0]}"
    print("✓ Group 4 — allpro: trailing-space col preserved, weighted math correct.")

def test_build_situational_pbp():
    _fs = _synth_schedule()
    _pbp = _synth_pbp()
    _up = _fs[_fs["week"] == 5].copy()
    _wk = _pbp[["game_id", "week", "season"]].drop_duplicates()
    _out = _build_situational_pbp(_up, _pbp, _wk)
    for c in ["turnover_diff", "turnover_diff_reverse",
              "third_down_diff", "third_down_diff_reverse"]:
        assert c in _out.columns, f"Missing column {c}"
    # sack_diff may be NaN since synth pbp has no sacks for either team (sack=0 everywhere)
    # — but the columns must exist.
    assert "sack_diff" in _out.columns and "sack_diff_reverse" in _out.columns
    # reverse should equal -forward
    r = _out.iloc[0]
    assert np.isclose(r["turnover_diff_reverse"], -r["turnover_diff"]), "turnover_diff_reverse != -turnover_diff"
    assert np.isclose(r["third_down_diff_reverse"], -r["third_down_diff"]), "third_down_diff_reverse != -third_down_diff"
    print("✓ Group 6 — situational_pbp: diffs + reverse-diff invariant hold.")

def test_build_qb_switch():
    _fs = _synth_schedule()
    _hist = _fs[(_fs["week"] < 5) & _fs["result"].notna()].copy()
    _up = _fs[_fs["week"] == 5].copy()
    _coach_hist = _fs[_fs["result"].notna()].copy()
    _out = _build_qb_switch(_up, _hist, _coach_hist, target_season=2025)
    for c in ["home_qb_switch", "away_qb_switch", "is_home_qb_new", "is_away_qb_new"]:
        assert c in _out.columns, f"Missing column {c}"
    # Synth has P.Mahomes / J.Allen every week → no switch
    assert bool(_out["home_qb_switch"].iloc[0]) is False, "False switch detected for P.Mahomes"
    assert bool(_out["away_qb_switch"].iloc[0]) is False, "False switch detected for J.Allen"
    print("✓ Group 7 — qb_switch: 4 flag cols present, no false switches.")

def test_build_passer_rating():
    _fs = _synth_schedule()
    _pbp = _synth_pbp()
    _up = _fs[_fs["week"] == 5].copy()

    # Hermetic test: pre-fab the NGS aggregate that ``_build_passer_rating`` would
    # otherwise fetch via ``nfl.load_nextgen_stats``. Mirrors NGS schema (week==0 row
    # per team with attempts >= 100, plus the three columns we read).
    _ngs_stub = pd.DataFrame([
        {"team_abbr": "KC",  "season": 2024, "week": 0, "attempts": 500,
         "passer_rating": 102.5, "completion_percentage_above_expectation": 4.5, "avg_time_to_throw": 2.7},
        {"team_abbr": "BUF", "season": 2024, "week": 0, "attempts": 480,
         "passer_rating":  88.3, "completion_percentage_above_expectation": -1.2, "avg_time_to_throw": 2.9},
    ])
    _out = _build_passer_rating(_up, _pbp, target_season=2025, ngs_data=_ngs_stub)
    for c in ["home_pr_prev_year", "away_pr_prev_year", "diff_pr_prev_year",
              "home_cpae_prev_year", "away_cpae_prev_year", "diff_cpae_prev_year",
              "home_time_to_throw_prev_year", "away_time_to_throw_prev_year", "diff_time_to_throw_prev_year"]:
        assert c in _out.columns, f"Missing column {c}"
        assert not pd.isna(_out[c].iloc[0]), f"Column {c} is NaN after median imputation"
    # KC (home) has the higher passer rating in the stub, BUF (away) is lower — diff should be positive.
    assert _out["diff_pr_prev_year"].iloc[0] > 0, "Expected positive diff (KC > BUF)"
    print(f"✓ Group 8 — passer_rating: 9 cols populated, hermetic (no network), home_pr={_out['home_pr_prev_year'].iloc[0]:.1f}")

def test_build_injuries():
    _fs = _synth_schedule()
    _allpro = _synth_allpro()
    _up = _fs[_fs["week"] == 5].copy()
    # Inject the Group 4 cols this helper depends on (we test Group 4 separately).
    _up = _build_allpro(_up, _allpro, target_season=2025)
    _out = _build_injuries(_up, _allpro, target_season=2025, target_week=5)
    for c in ["home_injured_count", "away_injured_count", "diff_injured_count",
              "diff_active_allpro_weighted", "diff_active_allpro_prev_year"]:
        assert c in _out.columns, f"Missing column {c}"
    print("✓ Group 9 — injuries: 5 cols present (offline fallback path).")

def test_build_coach_win_pct():
    _fs = _synth_schedule()
    _up = _fs[_fs["week"] == 5].copy()
    _coach_hist = _fs[_fs["result"].notna()].copy()
    _out = _build_coach_win_pct(_up, _coach_hist, target_season=2025, target_week=5)
    for c in ["home_coach_win_pct_prior", "away_coach_win_pct_prior",
              "home_coach_win_pct_roll3", "away_coach_win_pct_roll3"]:
        assert c in _out.columns, f"Missing column {c}"
    # Andy Reid (home_coach) won 4/4 synth games → 1.0
    assert _out["home_coach_win_pct_roll3"].iloc[0] == 1.0, \
        f"Andy Reid won 4/4 — expected 1.0, got {_out['home_coach_win_pct_roll3'].iloc[0]}"
    assert _out["away_coach_win_pct_roll3"].iloc[0] == 0.0, "Sean McDermott lost 4/4 → expected 0.0"
    print("✓ Group 10 — coach_win_pct: 4 cols present, win%s match synth ground truth.")

def test_build_features_integration():
    _res = build_features(
        target_week=5,
        target_season=2025,
        full_schedule=_synth_schedule(),
        pbp_rp=_synth_pbp(),
        allpro_df=_synth_allpro(),
        week_margin_lkp=None,
        coach_hist_df=_synth_schedule()[_synth_schedule()["result"].notna()].copy(),
    )
    assert _res is not None, "build_features returned None on non-empty synth input"
    assert isinstance(_res, pd.DataFrame), "build_features did not return a DataFrame"
    assert len(_res) == 1, f"Expected 1 upcoming row, got {len(_res)}"
    _missing = [c for c in FEATURE_COLS_85 if c not in _res.columns]
    assert not _missing, f"FEATURE_COLS_85 not all present after build_features: {_missing}"
    for _c in ["home_rolling_win_pct", "home_coach_win_pct_prior", "home_coach_win_pct_roll3",
               "sos_diff", "cover_rate_diff",
               "home_pr_prev_year", "home_cpae_prev_year", "home_time_to_throw_prev_year",
               "diff_pr_prev_year", "diff_cpae_prev_year", "diff_time_to_throw_prev_year"]:
        assert not pd.isna(_res[_c].iloc[0]), f"Column {_c} is NaN"
    print(f"✓ build_features integration: 1 row, {len(_res.columns)} cols, all 85 features present.")

def test_build_numeric_features():
    from sklearn.preprocessing import OrdinalEncoder
    _enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    _enc.fit([["dome", "turf"], ["outdoors", "grass"], ["retractable", "turf"]])
    _feats = ["roof", "surface", "is_playoff", "spread_line"]

    # Known categories → correct shape + dtype
    _df_ok = pd.DataFrame({"roof": ["dome"], "surface": ["turf"], "is_playoff": [0], "spread_line": [-3.0]})
    _X = build_numeric_features(_df_ok, _feats, _enc)
    assert isinstance(_X, np.ndarray), "Expected numpy array"
    assert _X.shape == (1, 4),          f"Expected shape (1,4), got {_X.shape}"
    assert np.issubdtype(_X.dtype, np.floating), "Expected float dtype"

    # Unknown category → must not raise
    _df_unk = pd.DataFrame({"roof": ["open_air_xyz"], "surface": ["sod"], "is_playoff": [0], "spread_line": [2.5]})
    build_numeric_features(_df_unk, _feats, _enc)

    # NaN input → must not raise
    _df_nan = pd.DataFrame({"roof": [None], "surface": [None], "is_playoff": [0], "spread_line": [-1.0]})
    build_numeric_features(_df_nan, _feats, _enc)
    print("✓ build_numeric_features: known + unknown + NaN inputs all pass.")

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); passed += 1; print(f"  ok  {fn.__name__}")
        except Exception:
            print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} tests passed")
