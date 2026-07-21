"""Part A — panel + HIT target assembly (BLIND build; structural asserts only, NO metrics).

Reproduces the frozen Session-7 panel exactly:
  HIT panel = drafted skill rookies, entry 2015-2023 (9 classes), n=712 (QB101/RB189/WR290/TE132)
  hits at QB top-12 / RB top-24 / WR top-24 / TE top-12 = 15/54/47/19 (base 14.9/28.6/16.2/14.4%)
  SCORING set = entry 2024-2026 (not trainable).

Target: best positional finish over first 3 NFL seasons, by season-total half-PPR (REG),
half_ppr = fantasy_points + 0.5*receptions (repo formula, build_season_dataset.py:90).
This is OBSERVED OUTCOME only. No feature is touched here; no feature-vs-target computed.

Outputs (scratchpad only, never committed): panel_hit.parquet, panel_scoring.parquet.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import nflreadpy as nfl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SKILL = ["QB", "RB", "WR", "TE"]
THRESH = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}   # LOCKED football thresholds (prereg §2)
HIT_CLASSES = list(range(2015, 2024))               # entry 2015-2023 (9 classes)
SCORE_CLASSES = list(range(2024, 2027))             # entry 2024-2026
MAXOBS = 2025                                        # last fully-observed NFL season

# --- frozen expected structural counts (prereg §2/§3; Session-7 measurement) ---
EXP_N = {"QB": 101, "RB": 189, "WR": 290, "TE": 132}
EXP_HIT = {"QB": 15, "RB": 54, "WR": 47, "TE": 19}


def pdf(x):
    try:
        return x.to_pandas()
    except AttributeError:
        return x


def build_season_finish():
    """Per (player_id, season) season-total half-PPR + positional finish rank (REG)."""
    seasons = list(range(2014, MAXOBS + 1))
    try:
        ps = pdf(nfl.load_player_stats(seasons=seasons))
    except TypeError:
        ps = pdf(nfl.load_player_stats())
        ps = ps[ps["season"].isin(seasons)]
    if "season_type" in ps.columns:
        ps = ps[ps["season_type"] == "REG"]
    pos_col = "position" if "position" in ps.columns else "position_group"
    ps["half_ppr"] = ps["fantasy_points"].fillna(0) + 0.5 * ps["receptions"].fillna(0)
    seas = (ps.groupby(["player_id", "season"])
              .agg(half_ppr=("half_ppr", "sum"),
                   g=("week", "nunique"),
                   position=(pos_col, "last"))
              .reset_index())
    seas["position"] = seas["position"].replace({"HB": "RB", "FB": "RB"})
    seas = seas[seas["position"].isin(SKILL)].copy()
    seas["pos_finish"] = (seas.groupby(["season", "position"])["half_ppr"]
                              .rank(ascending=False, method="min").astype(int))
    return seas


def build_panel():
    seas = build_season_finish()
    finish_by_player = seas.groupby("player_id")

    draft = pdf(nfl.load_draft_picks())
    draft = draft[draft["position"].isin(SKILL)].dropna(subset=["gsis_id"]).copy()
    draft = (draft.rename(columns={"season": "entry_year"})
                  [["gsis_id", "entry_year", "position", "round", "pick"]]
                  .drop_duplicates("gsis_id"))

    def best_of_first3(gsis, entry):
        yrs = {entry, entry + 1, entry + 2}
        try:
            sub = finish_by_player.get_group(gsis)
        except KeyError:
            return np.nan
        sub = sub[sub["season"].isin(yrs)]
        return float(sub["pos_finish"].min()) if len(sub) else np.nan

    draft["best_finish"] = [best_of_first3(g, e)
                            for g, e in zip(draft.gsis_id, draft.entry_year)]

    hit = draft[draft.entry_year.isin(HIT_CLASSES)].copy()
    hit["hit"] = [int((not np.isnan(bf)) and bf <= THRESH[p])
                  for bf, p in zip(hit.best_finish, hit.position)]
    scoring = draft[draft.entry_year.isin(SCORE_CLASSES)].copy()
    return hit, scoring


def main():
    hit, scoring = build_panel()

    print("=" * 64)
    print("PART A STRUCTURAL ASSERTS (no metrics)")
    print("=" * 64)
    ok = True
    for pos in SKILL:
        sub = hit[hit.position == pos]
        n, nhit = len(sub), int(sub.hit.sum())
        n_ok = (n == EXP_N[pos]); h_ok = (nhit == EXP_HIT[pos])
        ok &= n_ok and h_ok
        print(f"  {pos}: n={n:3d} (exp {EXP_N[pos]}, {'OK' if n_ok else 'FAIL'}) | "
              f"hits={nhit:2d} (exp {EXP_HIT[pos]}, {'OK' if h_ok else 'FAIL'}) | "
              f"base={nhit/n:.3f}")
    tot, tothit = len(hit), int(hit.hit.sum())
    print(f"  ALL: n={tot} (exp 712, {'OK' if tot==712 else 'FAIL'}) | "
          f"hits={tothit} (exp 135, {'OK' if tothit==135 else 'FAIL'})")
    assert ok and tot == 712 and tothit == 135, "PANEL COUNTS DIVERGE FROM FROZEN — STOP"

    # leakage / scope structural asserts
    assert hit.entry_year.between(2015, 2023).all(), "hit panel class out of range"
    assert scoring.entry_year.between(2024, 2026).all(), "scoring class out of range"
    assert hit.gsis_id.is_unique, "duplicate gsis in hit panel"
    assert set(hit.hit.unique()) <= {0, 1}, "hit not binary"
    print("  scope/leakage asserts: OK (classes in range, gsis unique, hit binary)")

    print("\nSCORING set counts (entry 2024-2026):")
    print(scoring.groupby(["entry_year", "position"]).size()
                 .unstack(fill_value=0).reindex(columns=SKILL, fill_value=0).to_string())

    hit.to_parquet(HERE / "panel_hit.parquet", index=False)
    scoring.to_parquet(HERE / "panel_scoring.parquet", index=False)
    print(f"\nwrote panel_hit.parquet ({len(hit)}) + panel_scoring.parquet ({len(scoring)})")
    print("PART A: PASS — panel reproduces frozen counts, blindness intact (no feature touched).")


if __name__ == "__main__":
    main()
