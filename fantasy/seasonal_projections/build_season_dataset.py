"""Build the season-projection training dataset (v2).

One row per (player, season). Features are strictly prior-to-season, so there
is no leakage from the season being projected (with two documented exceptions
below). Two targets support the two-model design:
  - target_ppg    : half-PPR points per game (Model A, production). NaN when the
                    player played < MIN_GAMES_TARGET or 0 games (noisy label).
  - target_games  : games played (Model B, availability). Present for every row,
                    including reconstructed 0-game (full-miss) seasons.
  - sample_weight : games played, so short seasons are trusted less by Model A.

v2 additions over the first build:
  1. Full-miss seasons RECONSTRUCTED: a season a player skipped entirely leaves
     no stats row, so we synthesize a games=0 row for every gap BETWEEN a
     player's first and last active season. This gives Model B the full-miss
     tail it otherwise never sees. (Gaps between active seasons imply the player
     was retained/returned, so this leans toward injury/IR rather than left-league.)
  2. Snap counts: games_played and snap_share now come from snap data
     (offense_snaps), not just "weeks with a stat line". snap_share_pg is a
     feature (catches the 15%-snap, every-game role player).
  3. Per-game opportunity: targets_pg, carries_pg, receptions_pg, touches_pg.
  4. coach_changed (clean — coaches known at season start) and qb_changed
     (mild hindsight — uses season-N primary passer) flags.
  5. vacated_target_share / vacated_rush_share: opportunity left behind by
     players who were on the team in N-1 but not rostered in N (mild hindsight —
     uses season-N rosters, which at real draft time are ~known by late August).

Edge cases (unchanged design): 0-game seasons dropped from Model A / kept for B,
soft floor on Model A labels, prior_games_played as a feature, NaN never 0 for
missing priors, is_rookie + missed_prior_season flags.

Output: fantasy/seasonal_projections/season_dataset_2014_2025.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import nflreadpy as nfl

sys.path.insert(0, str(Path(__file__).resolve().parent))   # so _utils imports regardless of CWD
from _utils import norm_name, SKILL_POSITIONS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE             = Path(__file__).resolve().parent
OUT_CSV          = HERE / "season_dataset_2014_2025.csv"
ADP_CSV          = HERE / "sleeper_adp_2020_2025.csv"
SKILL            = set(SKILL_POSITIONS)
TARGET_SEASONS   = list(range(2014, 2026))
LOAD_FROM        = 2011
SNAP_FROM        = 2013                       # snap_counts reliable from 2013
MIN_GAMES_TARGET = 3


# ── 1. Season aggregates from weekly player stats ────────────────────────────
def build_season_aggregates():
    """Aggregate weekly player stats to season level.

    Returns:
        (agg, primary_qb): `agg` is one row per active (player_id, season) with
        season totals/usage; `primary_qb` is one row per (team, season) giving
        the player_id of that team's leading passer (used for the qb_changed flag).
    """
    print(f"Loading player stats {LOAD_FROM}-2025 ...")
    ps = nfl.load_player_stats(list(range(LOAD_FROM, 2026))).to_pandas()
    ps = ps[(ps["season_type"] == "REG") & (ps["position"].isin(SKILL))].copy()
    ps["half_ppr"] = ps["fantasy_points"].fillna(0) + 0.5 * ps["receptions"].fillna(0)
    ps["touches"]  = ps["carries"].fillna(0) + ps["receptions"].fillna(0)
    ps["total_td"] = ps["rushing_tds"].fillna(0) + ps["receiving_tds"].fillna(0) + ps["passing_tds"].fillna(0)

    g = ps.groupby(["player_id", "season"])
    agg = g.agg(
        player=("player_display_name", "last"),
        position=("position", lambda s: s.mode().iat[0] if not s.mode().empty else s.iat[0]),
        team=("team", "last"),
        games=("week", "nunique"),
        half_ppr=("half_ppr", "sum"),
        targets=("targets", "sum"),
        receptions=("receptions", "sum"),
        rec_yards=("receiving_yards", "sum"),
        rec_air_yards=("receiving_air_yards", "sum"),
        carries=("carries", "sum"),
        rush_yards=("rushing_yards", "sum"),
        pass_att=("attempts", "sum"),
        total_td=("total_td", "sum"),
        touches=("touches", "sum"),
        target_share=("target_share", "mean"),
        air_yards_share=("air_yards_share", "mean"),
        rec_epa=("receiving_epa", "sum"),
        rush_epa=("rushing_epa", "sum"),
    ).reset_index()
    agg["norm_name"] = agg["player"].map(norm_name)
    # primary passer per team-season (for qb_changed): the QB with most attempts.
    # Tiebreak on player_id so the choice is deterministic when attempts tie.
    qb = ps[ps["position"] == "QB"].groupby(["team", "season", "player_id"])["attempts"].sum().reset_index()
    primary_qb = (qb.sort_values(["attempts", "player_id"], ascending=[False, True])
                    .groupby(["team", "season"]).head(1)[["team", "season", "player_id"]])
    primary_qb = primary_qb.rename(columns={"player_id": "primary_qb_id"})
    print(f"  active player-seasons: {len(agg):,}")
    return agg, primary_qb


# ── 2. Reconstruct full-miss (0-game) seasons between first & last active ────
def reconstruct_missed(agg):
    rows = []
    for pid, grp in agg.groupby("player_id"):
        seasons = set(grp["season"])
        lo, hi = min(seasons), max(seasons)
        gap = [s for s in range(lo + 1, hi) if s not in seasons]
        if not gap:
            continue
        modal_pos = grp["position"].mode().iat[0]
        nm        = grp["norm_name"].iat[0]
        nm_player = grp["player"].iat[0]
        for s in gap:
            rows.append({"player_id": pid, "season": s, "player": nm_player,
                         "position": modal_pos, "team": np.nan, "norm_name": nm,
                         "games": 0, "half_ppr": 0.0, "reconstructed": 1})
    miss = pd.DataFrame(rows)
    print(f"  reconstructed full-miss seasons: {len(miss):,}")
    agg["reconstructed"] = 0
    full = pd.concat([agg, miss], ignore_index=True)
    # numeric stat cols on reconstructed rows -> 0 (they truly produced nothing)
    for c in ["targets", "receptions", "rec_yards", "rec_air_yards", "carries", "rush_yards",
              "pass_att", "total_td", "touches", "rec_epa", "rush_epa"]:
        full[c] = full[c].fillna(0)
    # rate stats stay NaN on 0-game rows (undefined), filled later by guards
    return full


# ── 3. Snap counts -> snap_share + snap-based games ─────────────────────────
def add_snaps(full):
    print(f"Loading snap counts {SNAP_FROM}-2025 ...")
    sc = nfl.load_snap_counts(list(range(SNAP_FROM, 2026))).to_pandas()
    _need = {"offense_snaps", "offense_pct", "player", "season", "week"}
    _missing = _need - set(sc.columns)
    assert not _missing, f"snap_counts schema changed; missing {sorted(_missing)}"
    sc = sc[sc["offense_snaps"].fillna(0) > 0].copy()
    sc["norm_name"] = sc["player"].map(norm_name)
    snap = sc.groupby(["norm_name", "season"]).agg(
        snap_games=("week", "nunique"),
        snap_share_pg=("offense_pct", "mean"),
    ).reset_index()
    full = full.merge(snap, on=["norm_name", "season"], how="left")
    # Prefer snap-based games where available (more accurate availability), but
    # NEVER let a name-collision snap match resurrect a reconstructed 0-game
    # season — those must stay games=0. Fall back to stat-line weeks otherwise.
    use_snap = full["snap_games"].notna() & (full["reconstructed"] == 0)
    full["games"] = full["snap_games"].where(use_snap, full["games"]).astype(float)
    full.loc[full["reconstructed"] == 1, ["snap_games", "snap_share_pg"]] = [0.0, np.nan]
    return full


# ── 4. Derived per-game / efficiency columns ─────────────────────────────────
def add_rates(full):
    gz = full["games"].replace(0, np.nan)
    full["ppg"]          = full["half_ppr"] / gz
    full["targets_pg"]   = full["targets"] / gz
    full["carries_pg"]   = full["carries"] / gz
    full["receptions_pg"] = full["receptions"] / gz
    full["touches_pg"]   = full["touches"] / gz
    full["adot"]         = full["rec_air_yards"] / full["targets"].replace(0, np.nan)
    full["td_rate"]      = full["total_td"] / full["touches"].replace(0, np.nan)
    full["yptarget"]     = full["rec_yards"] / full["targets"].replace(0, np.nan)
    full["ypc"]          = full["rush_yards"] / full["carries"].replace(0, np.nan)
    return full


# ── 5. Bio: experience, rookie flag, age, draft capital ─────────────────────
def add_bio(full):
    first_seen = full[full["games"] > 0].groupby("player_id")["season"].min().rename("rookie_season")
    full = full.merge(first_seen, on="player_id", how="left")
    full["years_exp"] = full["season"] - full["rookie_season"]
    full["is_rookie"] = (full["season"] == full["rookie_season"]).astype(int)

    players = nfl.load_players().to_pandas()
    bd = players[["gsis_id", "birth_date"]].dropna(subset=["birth_date"]).copy()
    bd["birth_date"] = pd.to_datetime(bd["birth_date"], errors="coerce")
    full = full.merge(bd.rename(columns={"gsis_id": "player_id"}), on="player_id", how="left")
    full["age"] = (pd.to_datetime(full["season"].astype(str) + "-09-01") - full["birth_date"]).dt.days / 365.25
    full.drop(columns=["birth_date"], inplace=True)

    # Draft capital. Prefer a gsis_id join (matches player_id exactly) so that
    # same-name father/son pairs (e.g. Frank Gore vs Frank Gore Jr.) don't collide;
    # fall back to a normalized-name join only for the ~14% of picks lacking gsis_id.
    full["draft_round"] = np.nan
    full["draft_pick"]  = np.nan
    try:
        dp = nfl.load_draft_picks().to_pandas()
        if "gsis_id" in dp.columns:
            by_id = (dp[dp["gsis_id"].notna()].sort_values("season")
                     .groupby("gsis_id").agg(dr=("round", "first"), dp_=("pick", "first")).reset_index()
                     .rename(columns={"gsis_id": "player_id"}))
            full = full.merge(by_id, on="player_id", how="left")
            full["draft_round"] = full["dr"]; full["draft_pick"] = full["dp_"]
            full.drop(columns=["dr", "dp_"], inplace=True)
        # name fallback for rows still unmatched (picks without gsis_id)
        nmcol = next((c for c in ["pfr_player_name", "full_name", "player_name"] if c in dp.columns), None)
        if nmcol:
            dp["norm_name"] = dp[nmcol].map(norm_name)
            by_nm = (dp.sort_values("season").groupby("norm_name")
                     .agg(dr=("round", "first"), dp_=("pick", "first")).reset_index())
            full = full.merge(by_nm, on="norm_name", how="left")
            full["draft_round"] = full["draft_round"].fillna(full["dr"])
            full["draft_pick"]  = full["draft_pick"].fillna(full["dp_"])
            full.drop(columns=["dr", "dp_"], inplace=True)
        print(f"  draft capital matched: {full['draft_pick'].notna().sum():,} "
              f"({full[['player_id','draft_pick']].dropna()['player_id'].nunique():,} unique players)")
    except KeyError as e:
        print(f"  WARNING: draft picks schema changed (missing {e}); draft_round/pick left NaN")
    except Exception as e:
        print(f"  WARNING: draft picks load failed ({type(e).__name__}: {e}); draft_round/pick left NaN")
    return full


# ── 6. Team context: pass rate, coaching change, QB change, vacated opp ─────
def add_team_context(full, primary_qb):
    # team offensive volume per season
    team = full[full["games"] > 0].groupby(["team", "season"]).agg(
        team_pass_att=("pass_att", "sum"), team_carries=("carries", "sum")).reset_index()
    team["team_pass_rate"] = team["team_pass_att"] / (team["team_pass_att"] + team["team_carries"]).replace(0, np.nan)
    team["team_plays_est"] = team["team_pass_att"] + team["team_carries"]
    full = full.merge(team[["team", "season", "team_pass_rate", "team_plays_est"]], on=["team", "season"], how="left")

    # coaching change (clean: coaches known at season start)
    sched = nfl.load_schedules(list(range(LOAD_FROM, 2026))).to_pandas()
    h = sched[["season", "home_team", "home_coach"]].rename(columns={"home_team": "team", "home_coach": "coach"})
    a = sched[["season", "away_team", "away_coach"]].rename(columns={"away_team": "team", "away_coach": "coach"})
    coaches = pd.concat([h, a]).dropna().groupby(["team", "season"])["coach"].agg(lambda s: s.mode().iat[0]).reset_index()
    coaches = coaches.sort_values(["team", "season"])
    coaches["prev_coach"] = coaches.groupby("team")["coach"].shift(1)
    coaches["coach_changed"] = (coaches["coach"] != coaches["prev_coach"]) & coaches["prev_coach"].notna()
    full = full.merge(coaches[["team", "season", "coach_changed"]], on=["team", "season"], how="left")

    # QB change (mild hindsight: uses season-N primary passer vs N-1)
    pq = primary_qb.sort_values(["team", "season"]).copy()
    pq["prev_qb"] = pq.groupby("team")["primary_qb_id"].shift(1)
    pq["qb_changed"] = (pq["primary_qb_id"] != pq["prev_qb"]) & pq["prev_qb"].notna()
    full = full.merge(pq[["team", "season", "qb_changed"]], on=["team", "season"], how="left")
    return full


def add_vacated(full):
    # vacated opportunity: share of a team's N-1 targets/carries held by players
    # NOT on the team's roster in season N. Mild hindsight (season-N roster).
    print("Loading rosters for vacated-opportunity ...")
    ros = nfl.load_rosters(list(range(LOAD_FROM, 2026))).to_pandas()
    ros = ros[["season", "team", "gsis_id"]].dropna().rename(columns={"gsis_id": "player_id"})
    roster_set = ros.groupby(["team", "season"])["player_id"].apply(set).to_dict()

    active = full[full["games"] > 0][["player_id", "season", "team", "target_share", "carries"]].copy()
    # team-season totals for share denominators
    tcar = active.groupby(["team", "season"])["carries"].sum().rename("team_carries_tot")
    active = active.merge(tcar, on=["team", "season"], how="left")
    active["rush_share"] = active["carries"] / active["team_carries_tot"].replace(0, np.nan)

    vac_rows = []
    for (team, s_prev), grp in active.groupby(["team", "season"]):
        s_next = s_prev + 1
        # Skip if we have no roster for the next season (e.g. a live/incomplete
        # upcoming year): without it every prior player looks "gone" and the
        # vacated shares would be spuriously inflated. Leave those rows NaN.
        if (team, s_next) not in roster_set:
            continue
        next_roster = roster_set[(team, s_next)]
        gone = grp[~grp["player_id"].isin(next_roster)]
        vac_rows.append({"team": team, "season": s_next,
                         "vacated_target_share": gone["target_share"].fillna(0).sum(),
                         "vacated_rush_share":  gone["rush_share"].fillna(0).sum()})
    vac = pd.DataFrame(vac_rows)
    full = full.merge(vac, on=["team", "season"], how="left")
    return full


# ── 7. Prior-season + rolling features, flags, targets ───────────────────────
ROLL_BASE = ["ppg", "targets_pg", "carries_pg", "receptions_pg", "touches_pg",
             "target_share", "air_yards_share", "adot", "td_rate", "yptarget", "ypc",
             "rec_epa", "rush_epa", "half_ppr", "games", "snap_share_pg"]


def build_feature_rows(full):
    full = full.sort_values(["player_id", "season"]).reset_index(drop=True)
    out = full[full["season"].isin(TARGET_SEASONS)].copy()

    prior = full[["player_id", "season"] + ROLL_BASE + ["team_pass_rate", "team_plays_est"]].copy()
    prior["season"] = prior["season"] + 1
    rename = {c: f"prior_{c}" for c in ROLL_BASE}
    rename.update({"team_pass_rate": "prior_team_pass_rate", "team_plays_est": "prior_team_plays"})
    out = out.merge(prior.rename(columns=rename), on=["player_id", "season"], how="left")

    for k in (2, 3):
        lag = full[["player_id", "season", "ppg"]].copy()
        lag["season"] = lag["season"] + k
        out = out.merge(lag.rename(columns={"ppg": f"ppg_lag{k}"}), on=["player_id", "season"], how="left")
    out["ppg_2yr"]   = out[["prior_ppg", "ppg_lag2"]].mean(axis=1)
    out["ppg_3yr"]   = out[["prior_ppg", "ppg_lag2", "ppg_lag3"]].mean(axis=1)
    out["ppg_trend"] = out["prior_ppg"] - out["ppg_lag2"]

    ch = full.groupby("player_id")["ppg"].transform(lambda s: s.shift(1).expanding().max())
    out = out.merge(full[["player_id", "season"]].assign(career_high_ppg=ch),
                    on=["player_id", "season"], how="left")

    out["missed_prior_season"] = ((out["is_rookie"] == 0) & (out["prior_games"].fillna(-1) == 0)).astype(int)
    sched_games = np.where(out["season"] - 1 >= 2021, 17, 16)
    out["prior_games_missed"] = np.clip(sched_games - out["prior_games"], 0, None)

    # flags to clean bool->int (.eq avoids the object-dtype fillna downcast warning)
    for c in ["coach_changed", "qb_changed"]:
        out[c] = out[c].eq(True).astype(int)

    # targets — only on rows that actually happened (reconstructed rows are
    # Model-B examples: games=0, target_ppg NaN, kept for availability)
    out["target_games"]  = out["games"]
    out["sample_weight"] = out["games"]
    out["target_ppg"]    = out["ppg"].where(out["games"] >= MIN_GAMES_TARGET, np.nan)
    return out


def main():
    agg, primary_qb = build_season_aggregates()
    full = reconstruct_missed(agg)
    full = add_snaps(full)
    full = add_rates(full)
    full = add_bio(full)
    full = add_team_context(full, primary_qb)
    full = add_vacated(full)
    rows = build_feature_rows(full)

    if ADP_CSV.exists():
        adp = pd.read_csv(ADP_CSV)
        keep = ["season", "norm_name", "position", "adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "sleeper_pts_half_ppr"]
        rows = rows.merge(adp[[c for c in keep if c in adp.columns]], on=["season", "norm_name", "position"], how="left")
        print(f"  ADP benchmark joined: {rows['adp_half_ppr'].notna().sum():,} rows (2020+ only)")
    else:
        print(f"  WARNING: {ADP_CSV.name} not found — run fetch_adp.py first. "
              f"Dataset will be written WITHOUT ADP benchmark columns.")

    feature_cols = [
        "prior_ppg", "prior_half_ppr", "prior_games", "prior_snap_share_pg",
        "ppg_2yr", "ppg_3yr", "ppg_trend", "career_high_ppg",
        "prior_targets_pg", "prior_carries_pg", "prior_receptions_pg", "prior_touches_pg",
        "prior_target_share", "prior_air_yards_share", "prior_adot",
        "prior_td_rate", "prior_yptarget", "prior_ypc", "prior_rec_epa", "prior_rush_epa",
        "age", "years_exp", "draft_round", "draft_pick",
        "prior_team_pass_rate", "prior_team_plays", "coach_changed", "qb_changed",
        "vacated_target_share", "vacated_rush_share",
        "prior_games_missed", "is_rookie", "missed_prior_season",
    ]
    id_cols     = ["player_id", "player", "norm_name", "position", "team", "season", "reconstructed"]
    target_cols = ["target_ppg", "target_games", "sample_weight"]
    bench_cols  = [c for c in ["adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "sleeper_pts_half_ppr"] if c in rows.columns]

    final = rows[id_cols + feature_cols + target_cols + bench_cols].copy()
    final = final.sort_values(["season", "position", "target_ppg"], ascending=[True, True, False]).reset_index(drop=True)
    final.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV}  ({len(final):,} rows, {final['season'].nunique()} seasons)")

    print("\n=== verification ===")
    print(f"rows: {len(final):,}  | reconstructed (0-game): {int(final['reconstructed'].sum()):,}")
    print(f"Model A usable (target_ppg not NaN): {final['target_ppg'].notna().sum():,}")
    print(f"Model B with target_games==0 (full-miss): {(final['target_games']==0).sum():,}")
    print(f"rookies: {int(final['is_rookie'].sum()):,}  | missed_prior_season: {int(final['missed_prior_season'].sum()):,}")
    print(f"coach_changed: {int(final['coach_changed'].sum()):,}  | qb_changed: {int(final['qb_changed'].sum()):,}")
    print(f"snap_share_pg present: {final['prior_snap_share_pg'].notna().mean()*100:.0f}% | vacated_target_share present: {final['vacated_target_share'].notna().mean()*100:.0f}%")
    return final


if __name__ == "__main__":
    main()
