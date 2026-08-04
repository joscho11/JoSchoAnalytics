"""As-of feature lookups for the totals model — safe for games that have not kicked off.

STATUS 2026-08-03: **WIRED IN.** `build_totals_features` (cell 10 of
`betting/totals_features.ipynb`) now takes its team-scoring, pace and league-environment
features from the as-of lookups below, keyed on (team, season, week), instead of joining a
rolling table on the target game's `game_id`. `predict_totals.ipynb` passes the COMPLETE
target-week schedule, calls the builder with `impute_missing=False`, and runs
`totals_live_preflight` (also in this module) before inference; its blanket `.fillna(0)` over
the totals block is gone. `test_totals_live.py` proves the historical values did not move by
executing the vendored pre-fix builder side by side with the new one.


Why this module exists (2026-08-03)
-----------------------------------
`build_totals_features` attached every rolling feature by joining the ROLLING TABLE ON
`game_id`. That works only for a game that already sits in the historical table. The live
path (`predict_totals.ipynb`) passes completed games only as `sched`, so the upcoming
week's `game_id` was absent from every one of those tables, each merge produced NaN, the
`fillna(column.mean())` guards were no-ops over all-NaN columns, and a downstream blanket
`fillna(0)` turned 10 of the 14 totals-specific features into 0.0 — including `is_dome`,
which the function's own assert claims to protect. Those features carry ~21% of the
shipped XGBoost's importance.

The functions here take the value from a team's own strictly-prior completed games instead
of from a row keyed by the target game, so a future game is a first-class input rather than
a lookup miss. For a historical row the result is IDENTICAL to
`shift(1).rolling(n, min_periods=1).mean()` — `tests/../test_totals_asof.py` proves the
equivalence on real schedule data rather than asserting it.

Nothing here silently substitutes a value. A team with no prior games gets NaN, and the
caller's preflight decides whether that is fatal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "team_asof_rolling", "league_asof_rolling", "MISSING",
    "TotalsPreflightError", "totals_live_preflight",
    "TOTALS_FEATURE_COLS_EXPECTED", "MUST_VARY_COLS", "MUST_BE_POSITIVE_COLS",
    "BINARY_COLS", "SANE_RANGES", "TEMP_FALLBACK_F", "WIND_FALLBACK_MPH",
    "DOME_TEMP_F", "DOME_WIND_MPH", "WEATHER_SOURCE_COLS", "WEATHER_SOURCES",
]

MISSING = np.nan

# ── documented weather fallbacks (see `build_totals_features`) ──────────────────────────
TEMP_FALLBACK_F = 60.0   # outdoor league-average stand-in when no source supplies a temp
WIND_FALLBACK_MPH = 8.0  # outdoor league-average stand-in when no source supplies a wind
DOME_TEMP_F = 70.0       # dome/closed-roof neutralisation (NOT a fallback — a real value)
DOME_WIND_MPH = 0.0
WEATHER_SOURCE_COLS = ["temp_f_source", "wind_mph_source"]
WEATHER_SOURCES = ("weather_file", "dome_neutralized", "default_outdoor", "slate_mean")


def _order_key(df, season_col="season", week_col="week"):
    """Sortable integer for (season, week). Weeks are < 100 in every NFL season."""
    return df[season_col].astype("int64") * 100 + df[week_col].astype("int64")


def team_asof_rolling(history, targets, value_col, window=5,
                      team_col="team", out_col=None):
    """Mean of each target's team's most recent `window` STRICTLY PRIOR completed games.

    `history` needs team/season/week/`value_col` and must already be restricted to games
    whose value is known (i.e. played). `targets` needs team/season/week. Returns a Series
    aligned to `targets.index`; NaN where the team has no prior completed game.

    Crosses season boundaries, matching the original `groupby(team).shift(1).rolling(n)`
    which sorted by (team, season, week) without resetting per season.
    """
    out_col = out_col or f"asof_{value_col}"
    hist = history.dropna(subset=[value_col]).copy()
    if hist.empty:
        return pd.Series(MISSING, index=targets.index, name=out_col)
    hist["_k"] = _order_key(hist)
    hist = hist.sort_values([team_col, "_k"], kind="stable")

    tgt = targets.copy()
    tgt["_k"] = _order_key(tgt)

    by_team = {t: (g["_k"].to_numpy(), g[value_col].to_numpy(dtype="float64"))
               for t, g in hist.groupby(team_col, sort=False)}

    vals = np.full(len(tgt), MISSING, dtype="float64")
    for i, (team, k) in enumerate(zip(tgt[team_col].to_numpy(), tgt["_k"].to_numpy())):
        pair = by_team.get(team)
        if pair is None:
            continue
        keys, values = pair
        # STRICTLY prior: a game in the same (season, week) slot is not usable pregame.
        j = int(np.searchsorted(keys, k, side="left"))
        if j == 0:
            continue
        vals[i] = values[max(0, j - window):j].mean()
    return pd.Series(vals, index=targets.index, name=out_col)


def league_asof_rolling(history, targets, value_col, window=4):
    """League-wide weekly mean over the `window` weeks strictly before each target week.

    Mirrors the original `groupby(season).shift(1).rolling(4)` on the per-week mean, but
    resolved by (season, week) ordering rather than by the target's own row existing.
    Confined to the target's own season, as the original was.
    """
    hist = history.dropna(subset=[value_col]).copy()
    if hist.empty:
        return pd.Series(MISSING, index=targets.index, name="league_asof")
    weekly = (hist.groupby(["season", "week"])[value_col].mean()
              .reset_index().rename(columns={value_col: "_wk_mean"}))
    weekly["_k"] = _order_key(weekly)
    weekly = weekly.sort_values(["season", "_k"], kind="stable")

    tgt = targets.copy()
    tgt["_k"] = _order_key(tgt)
    by_season = {s: (g["_k"].to_numpy(), g["_wk_mean"].to_numpy(dtype="float64"))
                 for s, g in weekly.groupby("season", sort=False)}

    vals = np.full(len(tgt), MISSING, dtype="float64")
    for i, (season, k) in enumerate(zip(tgt["season"].to_numpy(), tgt["_k"].to_numpy())):
        pair = by_season.get(season)
        if pair is None:
            continue
        keys, values = pair
        j = int(np.searchsorted(keys, k, side="left"))
        if j == 0:
            continue
        vals[i] = values[max(0, j - window):j].mean()
    return pd.Series(vals, index=tgt.index, name="league_asof")


# ══════════════════════════════════════════════════════════════════════════════════════
# Fail-closed live preflight
# ══════════════════════════════════════════════════════════════════════════════════════
#
# The defect this exists to catch: every rolling totals feature used to be attached by
# merging a history table on the target game's `game_id`. A game that has not been played
# has no row in those tables, so the merges produced all-NaN columns, the
# `fillna(column.mean())` guards were no-ops over an all-NaN column, and a blanket
# `.fillna(0)` at the call site wrote 0.0 into 10 of the 14 totals features — including
# `is_dome`. Nothing raised. The model was handed a zero vector for ~21% of its importance
# and printed a confident tier.
#
# So the preflight refuses to be a printer. It RETURNS a report when the slate is usable and
# RAISES `TotalsPreflightError` when it is not. There is no "warn and continue" path for a
# fatal condition, and no caller-supplied vocabulary: the required column list, the ranges
# and the rules below are module literals, so a caller cannot authorise a slate by narrowing
# what gets checked.

TOTALS_FEATURE_COLS_EXPECTED = [
    "total_line", "home_implied_pts", "away_implied_pts",
    "temp_f", "wind_mph", "is_dome",
    "home_pts_scored_5g", "home_pts_allowed_5g",
    "away_pts_scored_5g", "away_pts_allowed_5g", "combined_pts_5g",
    "league_avg_total_4wk", "pace_5g", "div_game",
]

# Columns that CANNOT legitimately be identical across a multi-game slate. Deliberately
# excludes:
#   * league_avg_total_4wk -- constant within a (season, week) BY CONSTRUCTION;
#   * temp_f / wind_mph    -- legitimately constant under the documented outdoor fallback;
#   * is_dome / div_game   -- binary; an all-outdoor or all-divisional slate is normal;
#   * total_line and the implied totals -- two games can genuinely share a line.
# What remains is the set whose constancy is only explicable as imputation.
MUST_VARY_COLS = [
    "home_pts_scored_5g", "home_pts_allowed_5g",
    "away_pts_scored_5g", "away_pts_allowed_5g", "combined_pts_5g", "pace_5g",
]

# Zero is semantically impossible for all of these: an NFL team does not average 0 points
# over its last five games, a week's league average total is not 0, and a team does not run
# 0 plays. This is the check that would have caught the original defect on its first run.
MUST_BE_POSITIVE_COLS = [
    "total_line", "home_implied_pts", "away_implied_pts",
    "home_pts_scored_5g", "home_pts_allowed_5g",
    "away_pts_scored_5g", "away_pts_allowed_5g", "combined_pts_5g",
    "league_avg_total_4wk", "pace_5g",
]

BINARY_COLS = ["is_dome", "div_game"]

SANE_RANGES = {
    "total_line": (20.0, 80.0),
    "home_implied_pts": (3.0, 60.0),
    "away_implied_pts": (3.0, 60.0),
    "home_pts_scored_5g": (3.0, 60.0),
    "home_pts_allowed_5g": (3.0, 60.0),
    "away_pts_scored_5g": (3.0, 60.0),
    "away_pts_allowed_5g": (3.0, 60.0),
    "combined_pts_5g": (3.0, 60.0),
    "league_avg_total_4wk": (20.0, 80.0),
    "pace_5g": (30.0, 90.0),
    "temp_f": (-20.0, 120.0),
    "wind_mph": (0.0, 50.0),
}

# Below this many games a modal-value share means nothing (2 of 3 games sharing a value is
# ordinary), so the default-domination rule only fires on a slate big enough to interpret.
MIN_ROWS_FOR_DOMINANCE = 4
MAX_MODAL_SHARE = 0.5


class TotalsPreflightError(RuntimeError):
    """Raised when a live totals slate is not safe to predict on."""


def _fail(checks, name, detail):
    checks.append({"check": name, "ok": False, "detail": detail})


def _ok(checks, name, detail=""):
    checks.append({"check": name, "ok": True, "detail": detail})


def totals_live_preflight(features_df, strict_weather=False):
    """Fail-closed gate between feature building and totals inference.

    Returns a report dict when the slate passes. Raises `TotalsPreflightError` when it does
    not -- it never merely prints, and there is no flag that downgrades a failure to a
    warning. `strict_weather=True` only ADDS a requirement (that the slate is not dominated
    by defaulted weather); it can never remove one.

    Weather note: on the live path the retained weather CSV has no row for a game that has
    not been played, so `default_outdoor` provenance is the EXPECTED steady state and is
    reported as a non-fatal note. What IS fatal is provenance that was never recorded -- a
    value whose origin is unknown is exactly the condition that hid the original defect.
    """
    checks = []
    notes = []

    if not isinstance(features_df, pd.DataFrame):
        raise TotalsPreflightError(
            f"totals_live_preflight: expected a DataFrame, got {type(features_df)!r}")

    n = len(features_df)
    if n == 0:
        _fail(checks, "non_empty", "feature frame has 0 rows")
        return _finish(checks, notes, n)
    _ok(checks, "non_empty", f"{n} games")

    missing = [c for c in TOTALS_FEATURE_COLS_EXPECTED if c not in features_df.columns]
    if missing:
        _fail(checks, "required_columns_present", f"missing: {missing}")
        # Nothing downstream can be evaluated without the columns.
        return _finish(checks, notes, n)
    _ok(checks, "required_columns_present",
        f"all {len(TOTALS_FEATURE_COLS_EXPECTED)} totals features present")

    num = {}
    non_numeric = []
    for c in TOTALS_FEATURE_COLS_EXPECTED:
        s = pd.to_numeric(features_df[c], errors="coerce")
        if s.isna().sum() > features_df[c].isna().sum():
            non_numeric.append(c)
        num[c] = s
    if non_numeric:
        _fail(checks, "numeric_dtypes", f"non-numeric values in: {non_numeric}")
    else:
        _ok(checks, "numeric_dtypes")

    nan_cols = {c: int(num[c].isna().sum()) for c in TOTALS_FEATURE_COLS_EXPECTED
                if num[c].isna().any()}
    if nan_cols:
        _fail(checks, "no_missing_values",
              "NaN present (imputation was deliberately removed; a missing live feature is "
              f"fatal, not fillable): {nan_cols}")
    else:
        _ok(checks, "no_missing_values")

    bad_binary = {c: sorted(set(num[c].dropna().unique()) - {0.0, 1.0}) for c in BINARY_COLS}
    bad_binary = {c: v for c, v in bad_binary.items() if v}
    if bad_binary:
        _fail(checks, "binary_flags_are_binary", f"{bad_binary}")
    else:
        _ok(checks, "binary_flags_are_binary")

    nonpos = {c: int((num[c] <= 0).sum()) for c in MUST_BE_POSITIVE_COLS
              if (num[c] <= 0).any()}
    if nonpos:
        _fail(checks, "no_zero_or_negative_scoring_features",
              "zero is semantically impossible for these columns -- this is the signature of "
              f"the blanket fillna(0) defect: {nonpos}")
    else:
        _ok(checks, "no_zero_or_negative_scoring_features")

    out_of_range = {}
    for c, (lo, hi) in SANE_RANGES.items():
        s = num[c].dropna()
        if len(s) and (s.min() < lo or s.max() > hi):
            out_of_range[c] = (float(s.min()), float(s.max()), lo, hi)
    if out_of_range:
        _fail(checks, "values_in_sane_range", f"{out_of_range}")
    else:
        _ok(checks, "values_in_sane_range")

    if n >= 2:
        constant = [c for c in MUST_VARY_COLS if num[c].dropna().nunique() <= 1]
        if constant:
            _fail(checks, "rolling_features_vary_across_slate",
                  "identical across every game on the slate -- only imputation does that: "
                  f"{constant}")
        else:
            _ok(checks, "rolling_features_vary_across_slate")
    else:
        _ok(checks, "rolling_features_vary_across_slate",
            f"skipped: {n} game(s), variance is not interpretable")

    if n >= MIN_ROWS_FOR_DOMINANCE:
        dominated = {}
        for c in MUST_VARY_COLS:
            s = num[c].dropna()
            if not len(s):
                continue
            share = float(s.value_counts(normalize=True).iloc[0])
            if share > MAX_MODAL_SHARE:
                dominated[c] = round(share, 3)
        if dominated:
            _fail(checks, "no_default_dominated_feature",
                  f"one value covers more than {MAX_MODAL_SHARE:.0%} of the slate: {dominated}")
        else:
            _ok(checks, "no_default_dominated_feature")
    else:
        _ok(checks, "no_default_dominated_feature",
            f"skipped: {n} game(s) < {MIN_ROWS_FOR_DOMINANCE}")

    have_prov = [c for c in WEATHER_SOURCE_COLS if c in features_df.columns]
    if len(have_prov) < len(WEATHER_SOURCE_COLS):
        _fail(checks, "weather_provenance_recorded",
              "missing provenance column(s): "
              f"{[c for c in WEATHER_SOURCE_COLS if c not in have_prov]}")
    else:
        unrecorded = {}
        for c in WEATHER_SOURCE_COLS:
            s = features_df[c]
            bad = int((~s.fillna("").isin(WEATHER_SOURCES)).sum())
            if bad:
                unrecorded[c] = bad
        if unrecorded:
            _fail(checks, "weather_provenance_recorded",
                  f"rows whose weather origin is unrecorded or unrecognised: {unrecorded}")
        else:
            _ok(checks, "weather_provenance_recorded")
            shares = {c: float((features_df[c] == "default_outdoor").mean())
                      for c in WEATHER_SOURCE_COLS}
            notes.append("defaulted-weather share: "
                         + ", ".join(f"{c}={v:.0%}" for c, v in shares.items()))
            if strict_weather:
                hot = {c: round(v, 3) for c, v in shares.items() if v > MAX_MODAL_SHARE}
                if hot:
                    _fail(checks, "weather_not_default_dominated",
                          f"strict_weather=True and the slate is mostly defaulted: {hot}")
                else:
                    _ok(checks, "weather_not_default_dominated")

    return _finish(checks, notes, n)


def _finish(checks, notes, n_games):
    failures = [c for c in checks if not c["ok"]]
    report = {
        "ok": len(failures) == 0,
        "n_games": int(n_games),
        "n_checks": len(checks),
        "n_failed": len(failures),
        "checks": checks,
        "failures": failures,
        "notes": notes,
    }
    if failures:
        lines = "\n".join(f"  - {f['check']}: {f['detail']}" for f in failures)
        raise TotalsPreflightError(
            f"totals_live_preflight ABORTED -- {len(failures)} of {len(checks)} checks failed "
            f"on a {n_games}-game slate. Prediction must not run.\n{lines}")
    return report
