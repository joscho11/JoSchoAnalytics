"""Shared rookie-model feature engineering (single source of truth).

The rookie PPG model uses information available at draft time that the veteran
Model A never sees: draft capital, combine athletic measurables, and landing-spot
/ team-context features. Combine measurables come from nflreadpy's `load_combine`,
bridged to our gsis `player_id` via `load_draft_picks`' pfr id (~93% coverage on
drafted rookies). College production is NOT in nflreadpy, so it is not included.

Used by: train_rookie_model.py (production trainer), build_draft_board.py (uses the
rookie model for rookies inside the blend), and the experiment scripts. Keep the
feature list here so all four stay in sync.
"""
import numpy as np
import pandas as pd
import nflreadpy as nfl

COMBINE_COLS = ["forty", "bench", "vertical", "broad_jump", "cone", "shuttle", "ht_in", "wt"]
ROOKIE_FEATS = (["draft_round", "draft_pick", "age"] + COMBINE_COLS +
                ["prior_team_pass_rate", "prior_team_plays",
                 "vacated_target_share", "vacated_rush_share",
                 "coach_changed", "qb_changed", "position"])
CAT = ["position"]

_COMBINE_CACHE = None


def _pdf(x):
    try:
        return x.to_pandas()
    except AttributeError:
        return x


def parse_ht(s):
    """Combine height like '6-4' -> inches (76). NaN if unparseable."""
    if not isinstance(s, str) or "-" not in s:
        return np.nan
    ft, inch = s.split("-")
    try:
        return int(ft) * 12 + int(inch)
    except ValueError:
        return np.nan


def load_combine_features():
    """Per-gsis_id combine measurables (cached). Bridged via draft_picks' pfr id."""
    global _COMBINE_CACHE
    if _COMBINE_CACHE is not None:
        return _COMBINE_CACHE
    draft = _pdf(nfl.load_draft_picks()).dropna(subset=["gsis_id"])
    draft = draft[["gsis_id", "pfr_player_id"]].drop_duplicates("gsis_id")
    comb = _pdf(nfl.load_combine()).dropna(subset=["pfr_id"]).drop_duplicates("pfr_id").copy()
    comb["ht_in"] = comb["ht"].map(parse_ht)
    comb = comb[["pfr_id", "forty", "bench", "vertical", "broad_jump", "cone", "shuttle", "ht_in", "wt"]]
    m = draft.merge(comb, left_on="pfr_player_id", right_on="pfr_id", how="left")
    _COMBINE_CACHE = m.set_index("gsis_id")[COMBINE_COLS]
    return _COMBINE_CACHE


def add_rookie_features(df):
    """Return a copy of df with combine columns joined and the casts ROOKIE_FEATS needs.

    `position` -> str (CatBoost categorical); `coach_changed`/`qb_changed` -> float.
    Combine columns are joined on `player_id` (gsis). Missing measurables stay NaN
    (CatBoost routes them natively -- never zero-filled).
    """
    d = df.copy()
    d["position"] = d["position"].astype(str)
    for c in ("coach_changed", "qb_changed"):
        if c in d.columns:
            d[c] = d[c].astype(float)
    comb = load_combine_features()
    for c in COMBINE_COLS:
        d[c] = d["player_id"].map(comb[c])
    return d
