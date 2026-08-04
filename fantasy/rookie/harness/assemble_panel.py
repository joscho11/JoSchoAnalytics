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


def _norm(name):
    """Lowercase, strip punctuation and generational suffixes — join key for the backfill only."""
    s = str(name).lower().replace(".", "").replace("'", "").replace("-", " ")
    s = " ".join(w for w in s.split() if w not in {"jr", "sr", "ii", "iii", "iv", "v"})
    return s


def backfill_scoring_gsis(draft):
    """Fill a MISSING gsis_id on SCORING-class rows only, from nflverse's players table.

    `load_draft_picks()` leaves gsis_id null for some recent picks even though the player has a
    real, active id in `load_players()` — as of the 2026 class, 7 drafted skill players (Stribling
    2.33, Beck 3.65, Delp 3.73, Young 4.140, Singleton 5.165, Royer 5.170, Burks 7.254). The
    `dropna` below then silently removed them from the board, so a second-round pick was simply
    absent from a page listing his draft class.

    SCOPED TO SCORING CLASSES ON PURPOSE. The dropna is CORRECT for the hit panel: no gsis_id
    means the outcome join in `best_of_first3` cannot run, so there is no label. Scoring rows
    carry no outcome and need only features, so the id is pure identity there. Backfilling the
    hit panel would also add rows to the frozen 712/135 panel and silently change the fitted
    models — hence the assert that the hit classes are untouched.

    Guarded name+position join; anything ambiguous on either side is refused, never guessed.
    """
    target = draft["season"].isin(SCORE_CLASSES) & draft["gsis_id"].isna()
    if not target.any():
        return draft
    players = pdf(nfl.load_players())
    players = players.dropna(subset=["gsis_id", "display_name", "position"]).copy()
    players["_k"] = players["display_name"].map(_norm) + "|" + players["position"].astype(str)
    players = players.drop_duplicates("_k", keep=False)          # ambiguous on the players side
    key = draft.loc[target, "pfr_player_name"].map(_norm) + "|" + draft.loc[target, "position"].astype(str)
    key = key.where(~key.duplicated(keep=False))                 # ambiguous on the draft side
    found = key.map(players.set_index("_k")["gsis_id"])
    # never collide with an id the table already carries — drop_duplicates("gsis_id") below
    # would otherwise silently discard one of the two rows
    existing = set(draft["gsis_id"].dropna())
    found = found.where(~found.isin(existing))
    draft = draft.copy()
    draft.loc[target, "gsis_id"] = found
    filled = draft.loc[target, "gsis_id"].notna()
    print(f"  gsis_id backfill (scoring classes only): {int(filled.sum())}/{int(target.sum())} filled")
    return draft


def build_panel():
    seas = build_season_finish()
    finish_by_player = seas.groupby("player_id")

    draft = pdf(nfl.load_draft_picks())
    draft = draft[draft["position"].isin(SKILL)].copy()
    before_hit = set(draft.loc[draft["season"].isin(HIT_CLASSES) & draft["gsis_id"].notna(), "gsis_id"])
    draft = backfill_scoring_gsis(draft)
    after_hit = set(draft.loc[draft["season"].isin(HIT_CLASSES) & draft["gsis_id"].notna(), "gsis_id"])
    assert before_hit == after_hit, "backfill touched the HIT panel — frozen 712/135 at risk"
    draft = draft.dropna(subset=["gsis_id"]).copy()
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
