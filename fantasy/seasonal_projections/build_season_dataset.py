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

v3 (2026-07-09) LEAKAGE FIXES — season-N context is now strictly preseason:
  (a) qb_changed: week-1 REG depth-chart QB1 of season N vs the N-1 primary
      passer (was: season-N primary passer = genuine hindsight).
  (b) vacated_*: departures detected against the WEEK-1 roster of season N
      (was: full-season-N rosters, which include in-season signings).
  (c) context_team: the player's week-1 roster team drives every season-N
      context join and the output `team` (was: last stats team of season N,
      wrong after midseason trades). Fallback = stats team (post-week-1
      signees only; residual, documented).
  (d) years_exp/is_rookie from draft year (load_draft_picks, 1980+), UDFA
      fallback = first active season (was: first-seen in 2011+ data, which
      truncates pre-2011 debuts).
Raw pulls are pinned by snapshots.py, so these fixes are measured against the
identical bytes the old logic consumed (no drift confound).

Output: fantasy/seasonal_projections/season_dataset_2014_2025.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import nflreadpy as nfl

sys.path.insert(0, str(Path(__file__).resolve().parent))   # so _utils imports regardless of CWD
from _utils import norm_name, SKILL_POSITIONS, SLEEPER_NAME_ALIASES
from snapshots import snap

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import os

HERE             = Path(__file__).resolve().parent
EXTENDED         = os.environ.get("EXTENDED_BUILD") == "1"   # Step 1b: 2002+ targets
OUT_CSV          = HERE / ("season_dataset_2002_2025.csv" if EXTENDED else "season_dataset_2014_2025.csv")
ADP_CSV          = HERE / "sleeper_adp_2020_2026.csv"
SKILL            = set(SKILL_POSITIONS)
TARGET_SEASONS   = list(range(2002 if EXTENDED else 2014, 2026))
LOAD_FROM        = 1999 if EXTENDED else 2011
W1_FROM          = 2002 if EXTENDED else 2014 # week-1 rosters / depth charts floor
SNAP_FROM        = 2013                       # snap_counts reliable from 2013
AIR_YARDS_FROM   = 2006                       # pre-2006 air-yards values are junk -> NaN
MIN_GAMES_TARGET = 3

# Canonical team codes = the load_player_stats convention, which is modernized in EVERY
# season. Three feeds disagree and every team-keyed join in this file used to mix them:
#   load_player_stats   ARI BAL CLE HOU LA  LAC LV   (canonical)
#   load_rosters_weekly ARZ BLT CLV HST SL  SD  OAK  (legacy GSIS codes, 2014-2019)
#   load_schedules      ARI BAL CLE HOU STL SD  OAK  (era codes)
# Unmapped, context_team carried legacy codes into the coach / QB1 / vacated joins, which
# then silently produced NaN (vacated) or a hard 0 (coach_changed/qb_changed). Folding the
# relocations onto one code additionally lets coaches.shift(1) bridge STL->LA, SD->LAC and
# OAK->LV, which previously broke prev_coach across each move.
TEAM_CANON = {"ARZ": "ARI", "AZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
              "SL": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV"}


def canon_team(s):
    """Map any feed's team codes onto the canonical (player_stats) convention."""
    return s.replace(TEAM_CANON)


# ── 1. Season aggregates from weekly player stats ────────────────────────────
def build_season_aggregates():
    """Aggregate weekly player stats to season level.

    Returns:
        (agg, primary_qb): `agg` is one row per active (player_id, season) with
        season totals/usage; `primary_qb` is one row per (team, season) giving
        the player_id of that team's leading passer (used for the qb_changed flag).
    """
    print(f"Loading player stats {LOAD_FROM}-2025 ...")
    ps = snap(f"player_stats_{LOAD_FROM}_2025", nfl.load_player_stats, list(range(LOAD_FROM, 2026)))
    ps = ps[(ps["season_type"] == "REG") & (ps["position"].isin(SKILL))].copy()
    ps["half_ppr"] = ps["fantasy_points"].fillna(0) + 0.5 * ps["receptions"].fillna(0)
    # pre-2006 air-yards are junk (0-17% nonzero): NaN them so sums/rates can't fake zeros
    ps.loc[ps["season"] < AIR_YARDS_FROM, ["receiving_air_yards", "air_yards_share"]] = np.nan
    # reconstructed weekly target share (fills the 2003-2008 native hole; validated below)
    tt = ps.groupby(["team", "season", "week"])["targets"].transform("sum")
    ps["recon_tgt_share"] = ps["targets"] / tt.replace(0, np.nan)
    # Season-level share denominators. A season share MUST be volume-weighted
    # (sum player targets / sum team targets over the weeks the player was on that team).
    # Averaging weekly shares is not a share: it gives a 2-game 40%-share player the same
    # weight as a 17-game one, and the per-team totals summed to 1.38 on average (max 2.19).
    ps["_team_wk_tgt"] = tt
    ps["_team_wk_ay"]  = ps.groupby(["team", "season", "week"])["receiving_air_yards"].transform("sum")
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
        mean_wk_target_share=("target_share", "mean"),      # legacy (NOT a share) - diagnostic only
        team_tgt_den=("_team_wk_tgt", "sum"),
        team_ay_den=("_team_wk_ay", "sum"),
        rec_epa=("receiving_epa", "sum"),
        rush_epa=("rushing_epa", "sum"),
    ).reset_index()
    agg.loc[agg["season"] < AIR_YARDS_FROM, "rec_air_yards"] = np.nan
    agg["norm_name"] = agg["player"].map(norm_name)
    # TRUE volume-weighted shares, at (player, season, TEAM) grain so the denominator is
    # that team's own season total and the per-team shares sum to exactly 1. The old
    # mean-of-weekly-shares aggregation was not a share (per-team totals averaged 1.38,
    # max 2.19), and a season-last team key additionally credited a traded player's whole
    # season to his final team.
    pt = ps.groupby(["player_id", "season", "team"], as_index=False).agg(
        _tgt=("targets", "sum"), _ay=("receiving_air_yards", "sum"))
    tden = pt.groupby(["team", "season"], as_index=False).agg(
        _tgt_den=("_tgt", "sum"), _ay_den=("_ay", "sum"))
    share_tbl = pt.merge(tden, on=["team", "season"], how="left")
    share_tbl["target_share"]    = share_tbl["_tgt"] / share_tbl["_tgt_den"].replace(0, np.nan)
    share_tbl["air_yards_share"] = share_tbl["_ay"] / share_tbl["_ay_den"].replace(0, np.nan)
    chk = share_tbl.groupby(["team", "season"])["target_share"].sum()
    print(f"  target_share now volume-weighted per team: per-team season totals mean "
          f"{chk.mean():.4f} (max {chk.max():.4f}); legacy mean-of-weekly averaged 1.384")
    assert chk.max() <= 1.0001, f"target_share still not a share (max team total {chk.max():.4f})"
    share_tbl = share_tbl[["player_id", "season", "team", "target_share", "air_yards_share"]]
    # the model feature is the player's share with the team he is listed under (season-last)
    agg = agg.merge(share_tbl, on=["player_id", "season", "team"], how="left")
    agg.drop(columns=["team_tgt_den", "team_ay_den", "mean_wk_target_share"], inplace=True)
    # primary passer per team-season (for qb_changed): the QB with most attempts.
    # Tiebreak on player_id so the choice is deterministic when attempts tie.
    qb = ps[ps["position"] == "QB"].groupby(["team", "season", "player_id"])["attempts"].sum().reset_index()
    primary_qb = (qb.sort_values(["attempts", "player_id"], ascending=[False, True])
                    .groupby(["team", "season"]).head(1)[["team", "season", "player_id"]])
    primary_qb = primary_qb.rename(columns={"player_id": "primary_qb_id"})
    # Team offensive volume, aggregated from the WEEKLY rows so each snap of volume is
    # credited to the team the player was actually on that week. Aggregating from
    # player-season rows keyed on team=("team","last") gave a traded player's entire
    # season to his final team and removed it from his original one.
    team_vol = ps.groupby(["team", "season"]).agg(
        team_pass_att=("attempts", "sum"), team_carries=("carries", "sum")).reset_index()
    team_vol["team"] = canon_team(team_vol["team"])
    team_vol = team_vol.groupby(["team", "season"], as_index=False).sum()
    print(f"  active player-seasons: {len(agg):,}")
    return agg, primary_qb, team_vol, share_tbl


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
    # numeric stat cols on RECONSTRUCTED rows -> 0 (they truly produced nothing).
    # Restricted to reconstructed rows: a blanket fillna(0) would resurrect the
    # pre-2006 air-yards junk-zeros that build_season_aggregates deliberately NaN'd.
    for c in ["targets", "receptions", "rec_yards", "rec_air_yards", "carries", "rush_yards",
              "pass_att", "total_td", "touches", "rec_epa", "rush_epa"]:
        full.loc[full["reconstructed"] == 1, c] = full.loc[full["reconstructed"] == 1, c].fillna(0)
    # rate stats stay NaN on 0-game rows (undefined), filled later by guards
    return full


# ── 3. Snap counts -> snap_share + snap-based games ─────────────────────────
def add_snaps(full):
    print(f"Loading snap counts {SNAP_FROM}-2025 ...")
    sc = snap("snap_counts_2013_2025", nfl.load_snap_counts, list(range(SNAP_FROM, 2026)))
    _need = {"offense_snaps", "offense_pct", "player", "season", "week"}
    _missing = _need - set(sc.columns)
    assert not _missing, f"snap_counts schema changed; missing {sorted(_missing)}"
    if "game_type" in sc.columns:
        sc = sc[sc["game_type"].astype(str).str.upper().eq("REG")].copy()
    sc = sc[sc["offense_snaps"].fillna(0) > 0].copy()
    # Join on a STABLE ID, not the normalized name. Name-keyed, two different players who
    # share a name collapsed into one snap row and both inherited the same wrong games /
    # snap_share_pg. snap_counts carries pfr_player_id; players.parquet crosswalks it to gsis.
    sc["norm_name"] = sc["player"].map(norm_name)
    xw = snap("players", nfl.load_players)
    xw = (xw[["pfr_id", "gsis_id"]].dropna().drop_duplicates("pfr_id")
            .rename(columns={"pfr_id": "pfr_player_id", "gsis_id": "player_id"}))
    if "pfr_player_id" in sc.columns:
        sc = sc.merge(xw, on="pfr_player_id", how="left")
    else:
        sc["player_id"] = np.nan
    by_id = (sc[sc["player_id"].notna()].groupby(["player_id", "season"])
             .agg(snap_games=("week", "nunique"), snap_share_pg=("offense_pct", "mean")).reset_index())
    full = full.merge(by_id, on=["player_id", "season"], how="left")
    # Name fallback ONLY for snap rows with no id crosswalk, and only where the name is
    # unambiguous in that season (a colliding name is left unmatched rather than guessed).
    rest = sc[sc["player_id"].isna()]
    if len(rest):
        amb = (sc.groupby(["norm_name", "season"])["pfr_player_id"].nunique()
                 .rename("n_ids").reset_index())
        by_nm = (rest.groupby(["norm_name", "season"])
                 .agg(sg=("week", "nunique"), ss=("offense_pct", "mean")).reset_index()
                 .merge(amb, on=["norm_name", "season"], how="left"))
        by_nm = by_nm[by_nm["n_ids"] <= 1].drop(columns="n_ids")
        full = full.merge(by_nm, on=["norm_name", "season"], how="left")
        full["snap_games"]    = full["snap_games"].fillna(full["sg"])
        full["snap_share_pg"] = full["snap_share_pg"].fillna(full["ss"])
        full.drop(columns=["sg", "ss"], inplace=True)
    print(f"  snap join: {int(full['snap_games'].notna().sum()):,} rows matched "
          f"({int(by_id['player_id'].nunique()):,} players by id)")
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
    # first active season kept as the UDFA fallback for entry year (fix d);
    # drafted players get their true draft year below.
    first_seen = full[full["games"] > 0].groupby("player_id")["season"].min().rename("first_active")
    full = full.merge(first_seen, on="player_id", how="left")

    players = snap("players", nfl.load_players)
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
    full["draft_year"]  = np.nan
    try:
        dp = snap("draft_picks", nfl.load_draft_picks)
        if "gsis_id" in dp.columns:
            by_id = (dp[dp["gsis_id"].notna()].sort_values("season")
                     .groupby("gsis_id").agg(dr=("round", "first"), dp_=("pick", "first"),
                                             dy=("season", "first")).reset_index()
                     .rename(columns={"gsis_id": "player_id"}))
            full = full.merge(by_id, on="player_id", how="left")
            full["draft_round"] = full["dr"]; full["draft_pick"] = full["dp_"]
            full["draft_year"]  = full["dy"]
            full.drop(columns=["dr", "dp_", "dy"], inplace=True)
        # name fallback for rows still unmatched (picks without gsis_id)
        nmcol = next((c for c in ["pfr_player_name", "full_name", "player_name"] if c in dp.columns), None)
        if nmcol:
            dp["norm_name"] = dp[nmcol].map(norm_name)
            by_nm = (dp.sort_values("season").groupby("norm_name")
                     .agg(dr=("round", "first"), dp_=("pick", "first"), dy=("season", "first")).reset_index())
            full = full.merge(by_nm, on="norm_name", how="left")
            full["draft_round"] = full["draft_round"].fillna(full["dr"])
            full["draft_pick"]  = full["draft_pick"].fillna(full["dp_"])
            full["draft_year"]  = full["draft_year"].fillna(full["dy"])
            full.drop(columns=["dr", "dp_", "dy"], inplace=True)
        print(f"  draft capital matched: {full['draft_pick'].notna().sum():,} "
              f"({full[['player_id','draft_pick']].dropna()['player_id'].nunique():,} unique players)")
    except KeyError as e:
        print(f"  WARNING: draft picks schema changed (missing {e}); draft_round/pick left NaN")
    except Exception as e:
        print(f"  WARNING: draft picks load failed ({type(e).__name__}: {e}); draft_round/pick left NaN")

    # fix (d): entry year = draft year (1980+); UDFA fallback = first active season.
    # Left-edge caveat: pre-2011-debut UDFAs still inherit a too-late first_active.
    full["entry_year"] = full["draft_year"].fillna(full["first_active"])
    full["years_exp"]  = full["season"] - full["entry_year"]
    full["is_rookie"]  = (full["season"] == full["entry_year"]).astype(int)
    return full


# ── 5b. Week-1 sources (leakage fixes a-c): rosters + depth-chart QB1 ────────
def _load_rosters_week1(seasons):
    rw = nfl.load_rosters_weekly(seasons).to_pandas()
    return rw[rw["week"] == 1][["season", "team", "gsis_id"]].dropna()


def _load_qb1_week1(seasons):
    """Week-1 (preseason-knowable) depth-chart QB1 per team-season.

    Depth charts have two schemas: <=2024 weekly charts (club_code/week/
    game_type/depth_team, with era team codes), 2025+ daily snapshots
    (dt/team/pos_abb/pos_rank). For 2025+ we take the last snapshot strictly
    BEFORE the season's first REG gameday (from schedules), so it is pre-kickoff.
    """
    frames = []
    old = [s for s in seasons if s <= 2024]
    if old:
        dc = nfl.load_depth_charts(old).to_pandas()
        dc = dc[(dc["game_type"] == "REG") & (dc["week"] == 1) &
                (dc["position"].astype(str).str.strip() == "QB") &
                (dc["depth_team"].astype(str) == "1")]
        f = dc[["season", "club_code", "gsis_id"]].dropna().rename(columns={"club_code": "team"})
        f["team"] = canon_team(f["team"])
        frames.append(f)
    for s in [s for s in seasons if s >= 2025]:
        dc = nfl.load_depth_charts([s]).to_pandas()
        if not len(dc) or "dt" not in dc.columns:
            continue
        sched = nfl.load_schedules([s]).to_pandas()
        kickoff = pd.Timestamp(sched[sched["game_type"] == "REG"]["gameday"].min(), tz="UTC")
        dc["dt"] = pd.to_datetime(dc["dt"])
        pre = dc[(dc["dt"] < kickoff) & (dc["pos_abb"] == "QB") & (dc["pos_rank"] == 1)]
        if not len(pre):
            continue
        pre = pre[pre["dt"] == pre["dt"].max()]
        f = pre.assign(season=s)[["season", "team", "gsis_id"]].dropna()
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def add_context_team(full):
    """Fix (c): the player's week-1 roster team = his preseason-knowable team.

    Drives every season-N context join and the output `team`. Stats-team stays
    in place for season-N volume aggregation and prior-season attribution
    (history, not hindsight). Fallback for players absent from the week-1
    roster (post-week-1 signees) = stats team; residual, documented.
    """
    rw1 = snap(f"rosters_weekly_w1_{W1_FROM}_2025", _load_rosters_week1, list(range(W1_FROM, 2026)))
    w1 = (rw1.drop_duplicates(["season", "gsis_id"])
             .rename(columns={"gsis_id": "player_id", "team": "w1_team"}))
    w1["w1_team"] = canon_team(w1["w1_team"])   # legacy ARZ/BLT/CLV/HST/SL/SD/OAK -> canonical
    full = full.merge(w1, on=["player_id", "season"], how="left")
    full["context_team"] = full["w1_team"].fillna(full["team"])
    n = full["season"].isin(TARGET_SEASONS)
    moved = (full.loc[n, "w1_team"].notna() &
             full.loc[n, "team"].notna() &
             (full.loc[n, "w1_team"] != full.loc[n, "team"])).sum()
    print(f"  context_team: week-1 coverage {full.loc[n, 'w1_team'].notna().mean()*100:.0f}% "
          f"| differs from stats-team on {moved:,} target rows")
    return full.drop(columns=["w1_team"])


# ── 6. Team context: pass rate, coaching change, QB change, vacated opp ─────
def add_team_context(full, primary_qb, team_vol=None):
    # team offensive volume per season (weekly-sourced; see build_season_aggregates)
    if team_vol is None:
        team = full[full["games"] > 0].groupby(["team", "season"]).agg(
            team_pass_att=("pass_att", "sum"), team_carries=("carries", "sum")).reset_index()
    else:
        team = team_vol.copy()
    team["team_pass_rate"] = team["team_pass_att"] / (team["team_pass_att"] + team["team_carries"]).replace(0, np.nan)
    team["team_plays_est"] = team["team_pass_att"] + team["team_carries"]
    full = full.merge(team[["team", "season", "team_pass_rate", "team_plays_est"]], on=["team", "season"], how="left")

    # coaching change (clean: coaches known at season start); joined on the
    # preseason-knowable context_team (fix c)
    sched = snap(f"schedules_{LOAD_FROM}_2025", nfl.load_schedules, list(range(LOAD_FROM, 2026)))
    _sc = sched[sched.get("game_type", "REG").astype(str).eq("REG")] if "game_type" in sched.columns else sched
    _ord = "gameday" if "gameday" in _sc.columns else "week"
    h = _sc[["season", _ord, "home_team", "home_coach"]].rename(columns={"home_team": "team", "home_coach": "coach"})
    a = _sc[["season", _ord, "away_team", "away_coach"]].rename(columns={"away_team": "team", "away_coach": "coach"})
    coaches = pd.concat([h, a]).dropna(subset=["team", "season", "coach"])
    coaches["team"] = canon_team(coaches["team"])          # schedules use STL/SD/OAK
    # Use the WEEK-1 coach, not the season-mode coach. The mode reflects whoever coached
    # most of season Y, so a mid-season firing IN season Y flipped coach_changed for that
    # season -- an event that had not happened at draft time. Week 1 is preseason-knowable.
    coaches = (coaches.sort_values(["team", "season", _ord])
                      .groupby(["team", "season"], as_index=False).first()[["team", "season", "coach"]])
    coaches = coaches.sort_values(["team", "season"])
    coaches["prev_coach"] = coaches.groupby("team")["coach"].shift(1)
    coaches["coach_changed"] = (coaches["coach"] != coaches["prev_coach"]) & coaches["prev_coach"].notna()
    full = full.merge(coaches[["team", "season", "coach_changed"]].rename(columns={"team": "context_team"}),
                      on=["context_team", "season"], how="left")

    # QB change, fix (a): week-1 REG depth-chart QB1 of season N vs the N-1
    # primary passer — both strictly knowable before Week 1 (was: season-N
    # primary passer, i.e. hindsight whenever the starter changed in-season).
    qb1 = snap(f"depthchart_qb1_w1_{W1_FROM}_2025", _load_qb1_week1, list(range(W1_FROM, 2026)))
    qb1 = (qb1.sort_values("gsis_id").drop_duplicates(["season", "team"])
              .rename(columns={"team": "context_team", "gsis_id": "qb1_id"}))
    prev_pq = primary_qb.copy()
    prev_pq["season"] = prev_pq["season"] + 1          # N-1 passer aligned to season N
    prev_pq = prev_pq.rename(columns={"team": "context_team", "primary_qb_id": "prev_qb"})
    qbctx = qb1.merge(prev_pq, on=["context_team", "season"], how="left")
    qbctx["qb_changed"] = (qbctx["qb1_id"] != qbctx["prev_qb"]) & qbctx["prev_qb"].notna() & qbctx["qb1_id"].notna()
    n_match = qbctx["prev_qb"].notna().sum()
    print(f"  qb_changed (preseason): {len(qbctx):,} team-seasons with a wk1 QB1, "
          f"{n_match:,} matched to a prior passer, {int(qbctx['qb_changed'].sum()):,} changes")
    full = full.merge(qbctx[["context_team", "season", "qb_changed"]],
                      on=["context_team", "season"], how="left")
    return full


def add_vacated(full, share_tbl=None):
    # vacated opportunity: share of a team's N-1 targets/carries held by players
    # NOT on the team's WEEK-1 roster in season N (fix b — was full-season-N
    # rosters, which include in-season signings). Joined on context_team (fix c).
    print("Loading week-1 rosters for vacated-opportunity ...")
    ros = snap(f"rosters_weekly_w1_{W1_FROM}_2025", _load_rosters_week1, list(range(W1_FROM, 2026)))
    ros = ros.rename(columns={"gsis_id": "player_id"})
    ros["team"] = canon_team(ros["team"])   # roster feed uses legacy codes; `active` uses stats codes
    roster_set = ros.groupby(["team", "season"])["player_id"].apply(set).to_dict()
    # Fallback for team-seasons absent from the week-1 feed. 2017 MIA and TB had Week 1
    # postponed (Hurricane Irma), so `if (team, s_next) not in roster_set: continue` skipped
    # those team-seasons entirely and every player on them lost both vacated_* features.
    # Fall back to the season roster snapshot rather than dropping the team-season.
    try:
        sr = snap(f"rosters_{LOAD_FROM}_2025", nfl.load_rosters, list(range(LOAD_FROM, 2026)))
        idc = "gsis_id" if "gsis_id" in sr.columns else "player_id"
        sr = sr[["season", "team", idc]].dropna().rename(columns={idc: "player_id"})
        sr["team"] = canon_team(sr["team"])
        for key, pids in sr.groupby(["team", "season"])["player_id"].apply(set).items():
            roster_set.setdefault(key, pids)
    except Exception as e:                                    # snapshot absent / schema drift
        print(f"  (season-roster fallback unavailable: {type(e).__name__})")

    if share_tbl is not None:
        # per-(player, season, TEAM) shares -> each team's shares sum to exactly 1, so the
        # vacated sum is a real fraction of the team's prior opportunity. Using the
        # season-last-team player rows instead double-counted traded players.
        active = full[full["games"] > 0][["player_id", "season", "team", "carries"]].copy()
        active = (share_tbl[["player_id", "season", "team", "target_share"]]
                  .merge(active[["player_id", "season", "team", "carries"]],
                         on=["player_id", "season", "team"], how="left"))
    else:
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
    full = full.merge(vac.rename(columns={"team": "context_team"}),
                      on=["context_team", "season"], how="left")
    tgt = full["season"].isin(TARGET_SEASONS)
    miss = int(full.loc[tgt, "vacated_target_share"].isna().sum())
    print(f"  vacated join: {miss:,} of {int(tgt.sum()):,} target-season rows unmatched "
          f"({miss / max(int(tgt.sum()), 1) * 100:.1f}%)")
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

    # Bool -> float, PRESERVING NaN. The old .eq(True).astype(int) turned a failed
    # team join into a hard 0, i.e. "no coach/QB change", indistinguishable from a real
    # answer. The deploy models are native-NaN trees, so an honest NaN routes correctly
    # and an unknown never masquerades as an informative value.
    for c in ["coach_changed", "qb_changed"]:
        out[c] = out[c].map({True: 1.0, False: 0.0}).astype(float)

    # targets — only on rows that actually happened (reconstructed rows are
    # Model-B examples: games=0, target_ppg NaN, kept for availability)
    out["target_games"]  = out["games"]
    out["sample_weight"] = out["games"]
    out["target_ppg"]    = out["ppg"].where(out["games"] >= MIN_GAMES_TARGET, np.nan)
    return out


def main():
    agg, primary_qb, team_vol, share_tbl = build_season_aggregates()
    full = reconstruct_missed(agg)
    full = add_snaps(full)
    full = add_rates(full)
    full = add_bio(full)
    full = add_context_team(full)
    full = add_team_context(full, primary_qb, team_vol)
    full = add_vacated(full, share_tbl)
    rows = build_feature_rows(full)
    rows["team"] = rows["context_team"].fillna(rows["team"])   # fix (c): output team = preseason team

    if ADP_CSV.exists():
        adp = pd.read_csv(ADP_CSV)
        adp["norm_name"] = adp["norm_name"].replace(SLEEPER_NAME_ALIASES)
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
