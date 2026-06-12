"""Build the upcoming-season (2026) feature rows so a pre-draft board can be built.

The normal dataset is driven by `load_player_stats`, which is empty for a season
that hasn't been played -- so there are no 2026 rows. But a *pre-draft* board does
not need 2026 stats; it needs each 2026-relevant player's 2025-derived priors. All
of that exists today:
  - 2026 player population + teams : load_rosters([2026])
  - 2026 rookies' draft capital     : load_draft_picks (2026 draft was April 2026)
  - 2025 priors                     : the existing aggregates (load_player_stats <=2025)
  - 2026 ADP + Sleeper projection   : Sleeper (early best-ball drafts already run)

So we seed a games=0 row for every 2026 rostered skill player, attach bio / draft /
team-context / vacated-opportunity, append to the standard `full` frame, and reuse
`build_season_dataset.build_feature_rows` (with 2026 added to TARGET_SEASONS) so the
2026 priors come from the exact same prior-join the training data uses -- no
reimplementation, no drift. Targets are NaN (season unplayed). qb_changed is left NaN
(can't know the 2026 primary passer from stats pre-season).

Output: season_dataset_2014_2026.csv (the existing rows, byte-for-byte, PLUS 2026).
build_draft_board.py globs the newest season_dataset_*.csv, so `BOARD_SEASON=2026
python build_draft_board.py` then produces the 2026 board.

Run:  python fantasy/seasonal_projections/build_2026_board.py
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import nflreadpy as nfl

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_season_dataset as bsd
from _utils import norm_name, SKILL_POSITIONS

HERE     = Path(__file__).resolve().parent
UPCOMING = 2026
BASE_CSV = HERE / "season_dataset_2014_2025.csv"      # the trained dataset -- kept intact
OUT_CSV  = HERE / "season_dataset_2014_2026.csv"
ADP_CSV  = bsd.ADP_CSV
SKILL    = set(SKILL_POSITIONS)
# draft-picks use pfr-style abbreviations; rosters/Sleeper use these -- normalize so a drafted
# rookie groups with their actual team (e.g. Jeremiyah Love ARI -> AZ, with Conner/Benson).
DRAFT_TEAM_MAP = {"ARI": "AZ", "GNB": "GB", "KAN": "KC", "LAR": "LA", "LVR": "LV",
                  "NOR": "NO", "NWE": "NE", "SFO": "SF", "TAM": "TB"}


def _pdf(x):
    try:
        return x.to_pandas()
    except AttributeError:
        return x


def seed_upcoming_rows(full):
    """One games=0 row per 2026 rostered skill player, with bio/draft/team/vacated set."""
    ros = _pdf(nfl.load_rosters([UPCOMING]))
    ros = ros[ros["position"].isin(SKILL)].dropna(subset=["gsis_id"]).copy()
    ros = ros.rename(columns={"gsis_id": "player_id"})
    name_col = next((c for c in ["full_name", "player_name", "football_name"] if c in ros.columns), None)
    ros["player"] = ros[name_col] if name_col else ros["player_id"]
    ros = ros.drop_duplicates("player_id")[["player_id", "player", "position", "team"]]
    print(f"2026 roster skill players: {len(ros)}")

    # The roster FEED lags the draft -- drafted rookies (even the #3 overall) may not be on a
    # team's roster yet, so they'd be silently dropped. Add every drafted UPCOMING skill rookie
    # straight from the draft, using the draft team (normalized to the roster convention).
    dpk = _pdf(nfl.load_draft_picks())
    dpk = dpk[(dpk["season"] == UPCOMING) & (dpk["position"].isin(SKILL))].copy()
    nmc = next((c for c in ["pfr_player_name", "player_name", "full_name"] if c in dpk.columns), None)
    if nmc and len(dpk):
        dpk["team"] = dpk["team"].map(lambda t: DRAFT_TEAM_MAP.get(t, t))
        dpk["player"] = dpk[nmc]
        # stable id: gsis when present, else a pfr-derived id (so brand-new rookies still get a row)
        dpk["player_id"] = np.where(dpk["gsis_id"].notna(), dpk["gsis_id"],
                                    "pfr_" + dpk.get("pfr_player_id", dpk[nmc]).astype(str))
        dpk["norm_name"] = dpk["player"].map(norm_name)
        have_id = set(ros["player_id"]); have_nm = set(ros["player"].map(norm_name))
        miss = dpk[(~dpk["player_id"].isin(have_id)) & (~dpk["norm_name"].isin(have_nm))]
        miss = miss.drop_duplicates("player_id")[["player_id", "player", "position", "team"]]
        if len(miss):
            ros = pd.concat([ros, miss], ignore_index=True)
            print(f"  + {len(miss)} drafted rookies not yet on the roster feed "
                  f"(e.g. {', '.join(miss['player'].head(3))})")

    # veteran vs rookie from prior NFL activity (any games>0 before 2026)
    active = full[full["games"] > 0]
    rookie_season = active.groupby("player_id")["season"].min()
    ros["rookie_season"] = ros["player_id"].map(rookie_season)
    ros["is_rookie"]  = ros["rookie_season"].isna().astype(int)
    ros["rookie_season"] = ros["rookie_season"].fillna(UPCOMING)
    ros["years_exp"]  = UPCOMING - ros["rookie_season"]
    ros["norm_name"]  = ros["player"].map(norm_name)
    print(f"  veterans: {(ros.is_rookie==0).sum()}  rookies: {(ros.is_rookie==1).sum()}")

    # age from player birthdates
    players = _pdf(nfl.load_players())
    bd = players[["gsis_id", "birth_date"]].dropna(subset=["birth_date"]).copy()
    bd["birth_date"] = pd.to_datetime(bd["birth_date"], errors="coerce")
    ros = ros.merge(bd.rename(columns={"gsis_id": "player_id"}), on="player_id", how="left")
    ros["age"] = (pd.to_datetime(f"{UPCOMING}-09-01") - ros["birth_date"]).dt.days / 365.25
    ros.drop(columns=["birth_date"], inplace=True)

    # draft capital (gsis join, name fallback) -- covers 2026 rookies
    ros["draft_round"] = np.nan
    ros["draft_pick"]  = np.nan
    dp = _pdf(nfl.load_draft_picks())
    if "gsis_id" in dp.columns:
        by_id = (dp[dp["gsis_id"].notna()].sort_values("season")
                 .groupby("gsis_id").agg(dr=("round", "first"), dp_=("pick", "first")).reset_index()
                 .rename(columns={"gsis_id": "player_id"}))
        ros = ros.merge(by_id, on="player_id", how="left")
        ros["draft_round"] = ros["dr"]; ros["draft_pick"] = ros["dp_"]
        ros.drop(columns=["dr", "dp_"], inplace=True)
    nmcol = next((c for c in ["pfr_player_name", "full_name", "player_name"] if c in dp.columns), None)
    if nmcol:
        dp["norm_name"] = dp[nmcol].map(norm_name)
        by_nm = (dp.sort_values("season").groupby("norm_name")
                 .agg(dr=("round", "first"), dp_=("pick", "first")).reset_index())
        ros = ros.merge(by_nm, on="norm_name", how="left")
        ros["draft_round"] = ros["draft_round"].fillna(ros["dr"])
        ros["draft_pick"]  = ros["draft_pick"].fillna(ros["dp_"])
        ros.drop(columns=["dr", "dp_"], inplace=True)
    print(f"  draft capital matched: {ros['draft_pick'].notna().sum()}")

    # coach change (2026 vs 2025), if the 2026 schedule is out
    ros["coach_changed"] = np.nan
    try:
        sched = _pdf(nfl.load_schedules([2025, UPCOMING]))
        h = sched[["season", "home_team", "home_coach"]].rename(columns={"home_team": "team", "home_coach": "coach"})
        a = sched[["season", "away_team", "away_coach"]].rename(columns={"away_team": "team", "away_coach": "coach"})
        co = pd.concat([h, a]).dropna().groupby(["team", "season"])["coach"].agg(lambda s: s.mode().iat[0]).reset_index()
        c25 = co[co.season == 2025].set_index("team")["coach"]
        c26 = co[co.season == UPCOMING].set_index("team")["coach"]
        if len(c26):
            chg = {t: (c26[t] != c25.get(t)) for t in c26.index if pd.notna(c25.get(t, np.nan))}
            ros["coach_changed"] = ros["team"].map(chg)
            print(f"  coach_changed computed for {ros['coach_changed'].notna().sum()} players (2026 schedule available)")
        else:
            print("  2026 schedule not posted yet -> coach_changed left NaN")
    except Exception as e:
        print(f"  coach_changed left NaN ({type(e).__name__})")

    # vacated opportunity: 2025 target/rush share held by players NOT on the 2026 roster
    roster26 = set(ros["player_id"])
    a25 = full[(full.season == 2025) & (full.games > 0)][["player_id", "team", "target_share", "carries"]].copy()
    tcar = a25.groupby("team")["carries"].sum().rename("tot")
    a25 = a25.merge(tcar, on="team", how="left")
    a25["rush_share"] = a25["carries"] / a25["tot"].replace(0, np.nan)
    a25["gone"] = ~a25["player_id"].isin(roster26)
    vac = a25[a25.gone].groupby("team").agg(
        vacated_target_share=("target_share", lambda s: s.fillna(0).sum()),
        vacated_rush_share=("rush_share", lambda s: s.fillna(0).sum())).reset_index()
    ros = ros.merge(vac, on="team", how="left")

    # assemble rows with full's columns (unplayed stats stay NaN; flags/bio set)
    seed = pd.DataFrame(index=ros.index)
    for c in full.columns:
        seed[c] = np.nan
    seed["player_id"] = ros["player_id"]; seed["player"] = ros["player"]
    seed["norm_name"] = ros["norm_name"]; seed["position"] = ros["position"]
    seed["team"] = ros["team"];           seed["season"] = UPCOMING
    seed["games"] = 0.0;                  seed["reconstructed"] = 0
    seed["half_ppr"] = 0.0
    for c in ["is_rookie", "years_exp", "rookie_season", "age", "draft_round", "draft_pick",
              "coach_changed", "vacated_target_share", "vacated_rush_share"]:
        seed[c] = ros[c].values
    seed["qb_changed"] = np.nan            # unknowable pre-season from stats
    return seed


def main():
    # standard 2014-2025 pipeline (unchanged)
    agg, primary_qb = bsd.build_season_aggregates()
    full = bsd.reconstruct_missed(agg)
    full = bsd.add_snaps(full)
    full = bsd.add_rates(full)
    full = bsd.add_bio(full)
    full = bsd.add_team_context(full, primary_qb)
    full = bsd.add_vacated(full)

    seed = seed_upcoming_rows(full)
    full = pd.concat([full, seed[full.columns]], ignore_index=True)

    # Emit ONLY the upcoming-season rows. The 2014-2025 training rows are NOT rebuilt
    # here (nflreadpy data drifts over time, and the models were trained on the existing
    # dataset) -- we take those verbatim from BASE_CSV and append fresh 2026 rows. The
    # 2026 priors still come from the same prior-join (fresh 2025 aggregates), which is
    # correct: a 2026 prior SHOULD reflect actual 2025 production.
    bsd.TARGET_SEASONS = [UPCOMING]
    rows = bsd.build_feature_rows(full)

    if ADP_CSV.exists():
        adp = pd.read_csv(ADP_CSV)
        keep = ["season", "norm_name", "position", "adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "sleeper_pts_half_ppr"]
        rows = rows.merge(adp[[c for c in keep if c in adp.columns]], on=["season", "norm_name", "position"], how="left")
        print(f"\nADP joined: {int(rows.adp_half_ppr.notna().sum())} of the {len(rows)} {UPCOMING} rows have ADP")
    else:
        print(f"  WARNING: {ADP_CSV.name} not found -- run fetch_adp.py first")

    base = pd.read_csv(BASE_CSV)
    cols = list(base.columns)
    new26 = rows.reindex(columns=cols)            # align to the trained dataset's schema
    final = pd.concat([base, new26], ignore_index=True)
    final.to_csv(OUT_CSV, index=False)

    n26 = (final.season == UPCOMING).sum()
    print(f"\nWrote {OUT_CSV.name}  ({len(final):,} rows = {len(base):,} base + {n26} {UPCOMING}); "
          f"2014-2025 rows taken verbatim from {BASE_CSV.name}")
    u = final[final.season == UPCOMING]
    print(f"  {UPCOMING}: rookies {int(u.is_rookie.sum())}  | with ADP {int(u.adp_half_ppr.notna().sum())}  "
          f"| with prior_ppg {int(u.prior_ppg.notna().sum())}")
    print(f"\nNext: BOARD_SEASON={UPCOMING} python fantasy/seasonal_projections/build_draft_board.py")


if __name__ == "__main__":
    main()
