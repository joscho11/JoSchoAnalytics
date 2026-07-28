"""WR RECENT FULL-PARTICIPATION-GAME ROLE FEATURES — harness for
PREREG_wr_recent_full_game_features_2026-07-26.md.

Research-only. Writes NOTHING into the repo; every output goes to
C:\\tmp\\wr_recent_full_game_features_2026-07-26.

Three frozen arms on the non-rookie WR panel, corrected dataset, folds 2021-2025:
  BASE              32-col WR_VET_ALL, inherited nested_select              (research baseline)
  FIXED-FEATURE     32 + the 16-col frozen block, BASE's per-fold config    (PRIMARY comparison)
  RESELECTED        32 + the block, nested_select re-run                    (report-only)

MODES
  --check  STRUCTURAL ONLY. Probes, assertions, coverage counts, the outcome-free power
           approximation, the BASE selection reproduction, protected hashes, frozen SHA256.
           Computes NO challenger metric of any kind.
  --fire   The one shot.

Interpreter: BettingEdgeContinued/.venv-test/Scripts/python.exe
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp, norm

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
MODELS_DIR = HERE / "models"
RESULTS_DIR = HERE / "results"
SEAS_DIR = REPO / "fantasy" / "seasonal_projections"
SNAPS = SEAS_DIR / "snapshots"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SEAS_DIR))

OUT = Path(os.environ.get("RFG_OUT", r"C:\tmp\wr_recent_full_game_features_2026-07-26"))
OUT.mkdir(parents=True, exist_ok=True)

# read-only, solely for the G0 metric reproduction (prereg §10.1 check 3)
RETRAIN_SCRATCH = Path(
    r"C:\Users\josep\AppData\Local\Temp\claude\c--Users-josep-Desktop-random-stuff-cowork-OS"
    r"\19483edc-3155-4194-8790-1ec4281ff28f\scratchpad\retrain_eval")

# ------------------------------------------------------------------ FROZEN CONSTANTS (prereg §3-§10)
SEED = 42
BOOT_DRAWS = 2000
EVAL_SEASONS = [2021, 2022, 2023, 2024, 2025]
DEPLOY = 2026
MAXOBS = 2025
TOP_K = 24
SKILL = ("QB", "RB", "WR", "TE")

MIN_SNAPS = 20              # §5.3
MIN_PCT_ABS = 0.35          # §5.3
PCT_OF_NORMAL = 0.70        # §5.3
NORMAL_PCTILE = 75          # §5.2
MIN_ACTIVE_WEEKS = 3        # §5.2
WINDOWS = (4, 8)            # §6

G1_FLOOR = -0.26            # measured junk-column noise floor
G5_MAE_TOL = 0.26
G5_BIAS_TOL = 2.0
G6_RMSE_REL = 0.010
G4_MIN_SEASONS = 3
G7_L4_MIN = 0.60
G7_L8_MIN = 0.40
G7_MAX_DROP_PP = 0.10
G8_SLATE_PCT = 0.10
G8_PLAYER_PTS = 25.0

# corrected-data retrain, WR NEW arm, recorded in PREREG_corrected_data_retrain_2026-07-26.md §11
G0_TARGET_MAE = 30.062
G0_TARGET_RHO = 0.74640
G0_TARGET_N = 1242
G0_SELECTIONS = {                       # from that run's fire.log (2023-2025 certified unchanged)
    2021: ("catboost", {"depth": 4, "learning_rate": 0.03, "l2_leaf_reg": 3, "iterations": 400}),
    2022: ("lightgbm", {"num_leaves": 15, "learning_rate": 0.03, "n_estimators": 400}),
}

NEW_FEATS = (
    [f"last{k}_{s}" for k in WINDOWS
     for s in ("half_ppr_pg", "targets_pg", "target_share", "air_yards_share", "snap_share_mean")]
    + ["prior_full_participation_games", "prior_active_games_excluded",
       "last4_calendar_span", "last8_calendar_span", "has_last4_full", "has_last8_full"]
)
assert len(NEW_FEATS) == 16, NEW_FEATS

PROTECTED = {
    "fantasy/projections/models/qb_veteran_model.pkl": "7632549f95995b9702baefdf016d7271",
    "fantasy/projections/models/rb_rookie_model.pkl": "da230ee66575ca574f02cbc2139e1a80",
    "fantasy/projections/models/rb_veteran_model.pkl": "167aca71a8511afcced37c0abc846004",
    "fantasy/projections/models/te_rookie_model.pkl": "f79dad0ab26af5cb4e06a9f1723328cd",
    "fantasy/projections/models/te_veteran_model.pkl": "5a2f0b504d4cc6fc9a2e04453fd76a44",
    "fantasy/projections/models/wr_rookie_model.pkl": "6c9a3f3ed02ce32c53594f383aade882",
    "fantasy/projections/models/wr_veteran_model.pkl": "17dfbcf01054bdd5ce032f2b55df9ad2",
    "fantasy/seasonal_projections/models/rookie_ppg_model.pkl": "872467b2295fce27761f9e04da01b6e8",
    "fantasy/seasonal_projections/season_dataset_2014_2025.csv": "d9f06a2fd77adae6b5b58158650fc7ea",
    "fantasy/seasonal_projections/season_dataset_2014_2026.csv": "8322a59e43251820cb393d40787f60e6",
}
EXTRA_PROTECTED = ["draft_board_2026.py",
                   "fantasy/projections/wr_player_scenarios_2026.csv"]


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def self_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def snapshot() -> dict:
    out = {k: _md5(REPO / k) for k in PROTECTED if (REPO / k).exists()}
    for k in EXTRA_PROTECTED:
        if (REPO / k).exists():
            out[k] = _md5(REPO / k)
    for f in sorted(RESULTS_DIR.glob("*.csv")):
        out[str(f.relative_to(REPO)).replace("\\", "/")] = _md5(f)
    return out


def assert_protected(snap: dict):
    bad = [f"{k}: {snap[k]} != {v}" for k, v in PROTECTED.items() if k in snap and snap[k] != v]
    assert not bad, f"PROTECTED ARTIFACT MISMATCH: {bad}"


# ------------------------------------------------------------------------------------- METRICS
def _mae(y, p):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def _rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y, float) - np.asarray(p, float)) ** 2)))


def _rho(y, p):
    return float(spearmanr(y, p).statistic)


def block_metrics(df, col):
    y, p = df["y"].to_numpy(float), df[col].to_numpy(float)
    return dict(n=int(len(df)), MAE=_mae(y, p), RMSE=_rmse(y, p), rho=_rho(y, p),
                bias=float(np.mean(y - p)), med_bias=float(np.median(y - p)),
                predSD=float(np.std(p, ddof=1)), actSD=float(np.std(y, ddof=1)))


def paired_bootstrap(df, a_col, b_col, seed=SEED, draws=BOOT_DRAWS):
    """95% percentile interval for MAE(b) - MAE(a), resampling player_id clusters."""
    rng = np.random.default_rng(seed)
    ids = df.player_id.unique()
    pos = {i: np.where(df.player_id.values == i)[0] for i in ids}
    ae_a = np.abs(df["y"].values - df[a_col].values)
    ae_b = np.abs(df["y"].values - df[b_col].values)
    out = np.empty(draws)
    for k in range(draws):
        sel = np.concatenate([pos[i] for i in rng.choice(ids, size=len(ids), replace=True)])
        out[k] = ae_b[sel].mean() - ae_a[sel].mean()
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


# ============================================================================ WEEKLY SOURCES (§3/§6)
def _canon(s):
    from build_season_dataset import TEAM_CANON
    return s.replace(TEAM_CANON)


def load_weekly_stats():
    """Pinned weekly player stats, REG + skill only, with team weekly denominators.

    Denominators reproduce build_season_aggregates(): REG rows, SKILL positions, grouped by
    (team, season, week) — so a traded player's window is priced against the room he was in.
    """
    ps = pd.read_parquet(SNAPS / "player_stats_2011_2025.parquet")
    assert "season_type" in ps.columns, "player_stats schema changed: no season_type"
    ps = ps[ps["season_type"] == "REG"].copy()
    assert (ps["season_type"] == "REG").all(), "POSTSEASON LEAKED into weekly stats"
    ps = ps[ps["position"].isin(SKILL)].copy()
    ps["team"] = _canon(ps["team"].astype(str))
    ps["half_ppr"] = ps["fantasy_points"].fillna(0) + 0.5 * ps["receptions"].fillna(0)
    ps["targets"] = ps["targets"].fillna(0.0)
    ps["receiving_air_yards"] = ps["receiving_air_yards"].fillna(0.0)
    tm = ps.groupby(["team", "season", "week"], as_index=False).agg(
        team_wk_tgt=("targets", "sum"), team_wk_ay=("receiving_air_yards", "sum"))
    keep = ["player_id", "season", "week", "team", "targets", "receiving_air_yards", "half_ppr"]
    return ps[keep].copy(), tm


def load_weekly_snaps():
    """Pinned weekly snap counts, REG + active only, keyed to player_id by the pfr->gsis crosswalk
    with the unambiguous-name fallback (the add_snaps() rule, at weekly grain)."""
    from _utils import norm_name
    sc = pd.read_parquet(SNAPS / "snap_counts_2013_2025.parquet")
    need = {"offense_snaps", "offense_pct", "player", "season", "week", "pfr_player_id", "team"}
    assert not (need - set(sc.columns)), f"snap_counts schema changed: {sorted(need - set(sc.columns))}"
    assert "game_type" in sc.columns, "snap_counts schema changed: no game_type"
    sc = sc[sc["game_type"].astype(str).str.upper().eq("REG")].copy()
    assert sc["game_type"].astype(str).str.upper().eq("REG").all(), "POSTSEASON LEAKED into snaps"
    sc = sc[sc["offense_snaps"].fillna(0) > 0].copy()          # §5.1 active week
    sc["norm_name"] = sc["player"].map(norm_name)
    sc["team"] = _canon(sc["team"].astype(str))
    xw = pd.read_parquet(SNAPS / "players.parquet")
    xw = (xw[["pfr_id", "gsis_id"]].dropna().drop_duplicates("pfr_id")
            .rename(columns={"pfr_id": "pfr_player_id", "gsis_id": "player_id"}))
    sc = sc.merge(xw, on="pfr_player_id", how="left")
    amb = (sc.groupby(["norm_name", "season"])["pfr_player_id"].nunique()
             .rename("n_ids").reset_index())
    cols = ["season", "week", "team", "offense_snaps", "offense_pct"]
    by_id = sc[sc["player_id"].notna()][["player_id"] + cols].copy()
    rest = sc[sc["player_id"].isna()].merge(amb, on=["norm_name", "season"], how="left")
    by_nm = rest[rest["n_ids"] <= 1][["norm_name"] + cols].copy()
    # a player plays one game per week; keep the largest-snap row deterministically if not
    dup_id = int(by_id.duplicated(["player_id", "season", "week"]).sum())
    dup_nm = int(by_nm.duplicated(["norm_name", "season", "week"]).sum())
    by_id = (by_id.sort_values(["player_id", "season", "week", "offense_snaps"])
                  .drop_duplicates(["player_id", "season", "week"], keep="last"))
    by_nm = (by_nm.sort_values(["norm_name", "season", "week", "offense_snaps"])
                  .drop_duplicates(["norm_name", "season", "week"], keep="last"))
    return by_id, by_nm, dict(dup_id=dup_id, dup_name=dup_nm, id_players=int(by_id.player_id.nunique()))


def load_gamedays():
    """(season, week, canonical team) -> REG gameday, from the pinned schedules snapshot."""
    s = pd.read_parquet(SNAPS / "schedules_2011_2025.parquet")
    s = s[s["game_type"] == "REG"].copy()
    assert (s["game_type"] == "REG").all(), "POSTSEASON LEAKED into schedules"
    rows = []
    for side in ("home_team", "away_team"):
        d = s[["season", "week", side, "gameday"]].rename(columns={side: "team"})
        rows.append(d)
    gd = pd.concat(rows, ignore_index=True)
    gd["team"] = _canon(gd["team"].astype(str))
    gd["gameday"] = pd.to_datetime(gd["gameday"])
    gd = gd.drop_duplicates(["season", "week", "team"])
    wk = (gd.groupby(["season", "week"], as_index=False)["gameday"].min()
            .rename(columns={"gameday": "gameday_wk"}))
    return gd, wk


# ============================================================ THE FROZEN 16-COLUMN BLOCK (§5/§6)
def build_block(max_source_season=None, verbose=False):
    """Return (block, audit, diag). One block row per (player_id, source_season).

    Qualification is decided by the SNAP row alone (§5). A qualifying week with no weekly stat row
    contributes 0 targets / 0 air yards / 0 half-PPR and still carries its team denominator (§6).
    `max_source_season` truncates every weekly source, for the feature-timing probe.
    """
    stats, team_wk = load_weekly_stats()
    snap_id, snap_nm, snapdiag = load_weekly_snaps()
    gd, gd_wk = load_gamedays()
    if max_source_season is not None:
        stats = stats[stats.season <= max_source_season]
        team_wk = team_wk[team_wk.season <= max_source_season]
        snap_id = snap_id[snap_id.season <= max_source_season]
        snap_nm = snap_nm[snap_nm.season <= max_source_season]
        gd = gd[gd.season <= max_source_season]
        gd_wk = gd_wk[gd_wk.season <= max_source_season]

    # --- panel identity map so the name fallback can resolve to a player_id ---
    sd = pd.read_csv(SEAS_DIR / "season_dataset_2014_2026.csv",
                     usecols=["player_id", "norm_name", "position"])
    ident = (sd[sd.position == "WR"][["player_id", "norm_name"]]
             .dropna().drop_duplicates("player_id"))
    have_id = set(snap_id.player_id.unique())
    need_nm = ident[~ident.player_id.isin(have_id)]
    fallback = snap_nm.merge(need_nm, on="norm_name", how="inner").drop(columns=["norm_name"])
    wk = pd.concat([snap_id, fallback], ignore_index=True)
    wk = wk.sort_values(["player_id", "season", "week", "offense_snaps"]) \
           .drop_duplicates(["player_id", "season", "week"], keep="last")
    n_fallback = int(len(fallback))

    # --- §5.2 normal snap share: p75 of offense_pct over active weeks, >= 3 active weeks ---
    g = wk.groupby(["player_id", "season"])["offense_pct"]
    norm_tbl = g.quantile(NORMAL_PCTILE / 100.0).rename("normal_snap_share").reset_index()
    cnt = g.size().rename("active_weeks").reset_index()
    norm_tbl = norm_tbl.merge(cnt, on=["player_id", "season"])
    norm_tbl.loc[norm_tbl.active_weeks < MIN_ACTIVE_WEEKS, "normal_snap_share"] = np.nan
    wk = wk.merge(norm_tbl, on=["player_id", "season"], how="left")

    # --- §5.3 full-participation proxy (snaps only) ---
    thresh = np.maximum(MIN_PCT_ABS, PCT_OF_NORMAL * wk["normal_snap_share"])
    wk["qualifies"] = ((wk["offense_snaps"] >= MIN_SNAPS) & (wk["offense_pct"] >= thresh)
                       & wk["normal_snap_share"].notna())

    # --- attach weekly production; missing stat row on a played week => zeros (§6) ---
    wk = wk.merge(stats.rename(columns={"team": "stats_team"}),
                  on=["player_id", "season", "week"], how="left")
    # The raw snap frame carries every offensive player (linemen included), none of whom have a
    # skill-position stat row, so a global no-stat count is meaningless. Scope it to the players
    # this block is actually joined to.
    _wr = set(ident.player_id.unique())
    _w = wk[wk.player_id.isin(_wr)]
    n_nostat = int(_w["targets"].isna().sum())
    n_nostat_qual = int(_w.loc[_w.qualifies, "targets"].isna().sum())
    n_wr_weeks = int(len(_w))
    n_wr_qual = int(_w.qualifies.sum())
    n_zero_tgt = int((_w["targets"] == 0).sum())
    for c in ("targets", "receiving_air_yards", "half_ppr"):
        wk[c] = wk[c].fillna(0.0)
    wk["team_use"] = wk["stats_team"].fillna(wk["team"])
    wk = wk.merge(team_wk.rename(columns={"team": "team_use"}),
                  on=["team_use", "season", "week"], how="left")
    wk = wk.merge(gd.rename(columns={"team": "team_use"}),
                  on=["season", "week", "team_use"], how="left")
    wk = wk.merge(gd_wk, on=["season", "week"], how="left")
    wk["gameday"] = wk["gameday"].fillna(wk["gameday_wk"])
    n_nogd = int(wk["gameday"].isna().sum())

    wk = wk.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
    q = wk[wk.qualifies].copy()

    # --- §6 windows ---
    q["_rev"] = q.groupby(["player_id", "season"]).cumcount(ascending=False)   # 0 == last game
    per = []
    for K in WINDOWS:
        w = q[q._rev < K].copy()
        agg = w.groupby(["player_id", "season"]).agg(
            _n=("week", "size"),
            _hp=("half_ppr", "sum"), _tg=("targets", "sum"), _ay=("receiving_air_yards", "sum"),
            _tden=("team_wk_tgt", "sum"), _aden=("team_wk_ay", "sum"),
            _sn=("offense_pct", "mean"),
            _first=("gameday", "min"), _last=("gameday", "max")).reset_index()
        agg = agg[agg._n == K].copy()                    # populated ONLY when >= K qualifying games
        out = pd.DataFrame({
            "player_id": agg.player_id, "season": agg.season,
            f"last{K}_half_ppr_pg": agg._hp / K,
            f"last{K}_targets_pg": agg._tg / K,
            f"last{K}_target_share": agg._tg / agg._tden.replace(0, np.nan),
            f"last{K}_air_yards_share": agg._ay / agg._aden.replace(0, np.nan),
            f"last{K}_snap_share_mean": agg._sn,
            f"last{K}_calendar_span": (agg._last - agg._first).dt.days.astype(float),
        })
        per.append(out)

    counts = wk.groupby(["player_id", "season"]).agg(
        active_weeks=("week", "size"), prior_full_participation_games=("qualifies", "sum")).reset_index()
    counts["prior_active_games_excluded"] = (counts.active_weeks
                                             - counts.prior_full_participation_games).astype(float)
    counts["prior_full_participation_games"] = counts["prior_full_participation_games"].astype(float)
    blk = counts[["player_id", "season", "prior_full_participation_games",
                  "prior_active_games_excluded"]].copy()
    for out in per:
        blk = blk.merge(out, on=["player_id", "season"], how="left")
    blk["has_last4_full"] = blk["last4_half_ppr_pg"].notna().astype(float)
    blk["has_last8_full"] = blk["last8_half_ppr_pg"].notna().astype(float)
    blk = blk.rename(columns={"season": "source_season"})
    assert not blk.duplicated(["player_id", "source_season"]).any(), "duplicate block key"

    # --- §9 exclusion audit + outcome-free ISOLATED / TERMINAL_RUN classification ---
    wk["_later_qual"] = (wk[::-1].groupby(["player_id", "season"])["qualifies"]
                         .cumsum()[::-1] - wk["qualifies"].astype(int))
    ex = wk[~wk.qualifies].copy()
    ex["exclusion_class"] = np.where(ex["_later_qual"] > 0, "ISOLATED", "TERMINAL_RUN")
    audit = ex[["player_id", "season", "week", "offense_snaps", "offense_pct",
                "normal_snap_share", "active_weeks", "exclusion_class"]].copy()
    audit = audit.rename(columns={"season": "source_season"}).sort_values(
        ["player_id", "source_season", "week"])

    diag = dict(weekly_snap_rows_all=int(len(wk)), wr_panel_weeks=n_wr_weeks,
                wr_panel_qualifying_weeks=n_wr_qual, name_fallback_rows=n_fallback,
                wr_weeks_without_stat_row=n_nostat, wr_qualifying_weeks_without_stat_row=n_nostat_qual,
                wr_weeks_with_stat_row_zero_targets=n_zero_tgt,
                weeks_without_gameday=n_nogd, block_rows=int(len(blk)), **snapdiag)
    if verbose:
        print(f"    weekly snap rows (all players) {len(wk):,} | WR-panel weeks {n_wr_weeks:,} "
              f"(qualifying {n_wr_qual:,}) | name-fallback {n_fallback:,}")
        print(f"    WR weeks with no stat row {n_nostat:,} ({n_nostat/max(n_wr_weeks,1):.2%}), "
              f"of which qualifying {n_nostat_qual:,} ({n_nostat_qual/max(n_wr_qual,1):.2%}); "
              f"WR weeks WITH a stat row and 0 targets {n_zero_tgt:,} | no-gameday {n_nogd}")
    return blk, audit, diag


# ==================================================================== PANEL (deterministic, §3/§10.1)
def build_panel():
    """Non-rookie WR panel from the corrected dataset + the PINNED weekly snapshot. No live pull."""
    import numpy as _np
    ps = pd.read_parquet(SNAPS / "player_stats_2011_2025.parquet")
    ps = ps[(ps.season_type == "REG") & (ps.season.between(2014, MAXOBS))].copy()
    ps["half_ppr"] = ps["fantasy_points"].fillna(0) + 0.5 * ps["receptions"].fillna(0)
    tgt = (ps.groupby(["player_id", "season"])["half_ppr"].sum().reset_index()
             .rename(columns={"half_ppr": "y"}))
    sd = pd.read_csv(SEAS_DIR / "season_dataset_2014_2026.csv")
    wr = sd[sd["position"] == "WR"].copy()
    wr["log_pick"] = _np.log(wr["draft_pick"].clip(lower=1))
    wr = wr.merge(tgt, on=["player_id", "season"], how="left")
    pre = wr["season"] <= MAXOBS
    wr.loc[pre, "y"] = wr.loc[pre, "y"].fillna(0.0)
    vet = wr[wr["is_rookie"] == 0].copy().reset_index(drop=True)
    assert not vet.duplicated(["player_id", "season"]).any(), "duplicate (player_id, season) in panel"
    return vet


def attach_block(panel, blk):
    """Join the block on source_season == season - 1. Strictly Y-1, asserted."""
    p = panel.copy()
    p["_src"] = p["season"] - 1
    m = p.merge(blk, left_on=["player_id", "_src"], right_on=["player_id", "source_season"],
                how="left")
    assert ((m["source_season"].isna()) | (m["source_season"] == m["season"] - 1)).all(), \
        "FEATURE TIMING: block joined on a season other than Y-1"
    m["has_last4_full"] = m["has_last4_full"].fillna(0.0)
    m["has_last8_full"] = m["has_last8_full"].fillna(0.0)
    m["prior_full_participation_games"] = m["prior_full_participation_games"].fillna(0.0)
    m["prior_active_games_excluded"] = m["prior_active_games_excluded"].fillna(0.0)
    return m.drop(columns=["_src", "source_season"])


# ==================================================================================== ARMS (§7)
def walk_arm(df, feats, tag, frozen=None, verbose=True):
    """One arm's walk-forward. frozen=None -> nested_select; else apply that exact config."""
    import build_rb_projection as B
    rows, chosen = [], {}
    for Y in EVAL_SEASONS:
        tr = df[df.season < Y].dropna(subset=["y"])
        te = df[df.season == Y].dropna(subset=["y"])
        if len(tr) < 60 or len(te) == 0:
            continue
        assert tr.season.max() < Y, f"WALK-FORWARD LEAK ({tag}, {Y})"
        t0 = time.time()
        if frozen is None:
            (fam, params, _imae), _ = B.nested_select(tr, feats)
        else:
            fam, params = frozen[Y]
        Xtr, Xte = B._prep(fam, tr, te, feats)
        p = B._fit_predict(fam, params, Xtr, tr["y"].to_numpy(float), Xte)
        chosen[Y] = (fam, params)
        rows.append(pd.DataFrame({"season": Y, "player_id": te.player_id.values,
                                  "player": te.player.values, "team": te.team.values,
                                  "y": te.y.values, "pred": p}))
        if verbose:
            print(f"    [{tag}] {Y}: {fam} {params} train={len(tr)} test={len(te)} "
                  f"({time.time()-t0:.0f}s)", flush=True)
    return pd.concat(rows, ignore_index=True), chosen


def deploy_arm(df, feats, tag, frozen=None):
    import build_rb_projection as B
    tr = df[df.season <= MAXOBS].dropna(subset=["y"])
    sc = df[df.season == DEPLOY].copy()
    if frozen is None:
        (fam, params, _), _ = B.nested_select(tr, feats)
    else:
        fam, params = frozen
    Xtr, Xsc = B._prep(fam, tr, sc, feats)
    model = B._make_model(fam, params)
    model.fit(Xtr, tr["y"].to_numpy(float))
    sc["pred"] = np.round(np.asarray(model.predict(Xsc), float), 1)
    return sc, (fam, params), model


def feature_usage(model, fam, feats):
    """gain / split usage for tree families; |coef| for elasticnet."""
    try:
        if fam == "lightgbm":
            b = model.booster_
            return pd.DataFrame({"feature": feats,
                                 "gain": b.feature_importance("gain"),
                                 "split": b.feature_importance("split")})
        if fam == "catboost":
            return pd.DataFrame({"feature": feats,
                                 "gain": model.get_feature_importance(), "split": np.nan})
        if fam == "xgboost":
            g = model.get_booster().get_score(importance_type="gain")
            s = model.get_booster().get_score(importance_type="weight")
            idx = {f"f{i}": f for i, f in enumerate(feats)}
            return pd.DataFrame({"feature": feats,
                                 "gain": [g.get(k, 0.0) for k in idx],
                                 "split": [s.get(k, 0.0) for k in idx]})
        return pd.DataFrame({"feature": list(feats) + [f"{c}_isna" for c in feats],
                             "gain": np.abs(model.coef_), "split": np.nan})
    except Exception as e:                                     # never let reporting kill the fire
        return pd.DataFrame({"feature": feats, "gain": np.nan, "split": np.nan,
                             "note": str(e)[:120]})


# ============================================================ TEAM ALLOCATION (report-only, §8)
def allocation_stats(df, pred_col="pred"):
    d = df.dropna(subset=["team"]).copy()
    d["cp"] = d[pred_col].clip(lower=0)
    g = d.groupby(["team", "season"])
    tot = g.agg(tp=("cp", "sum"), ta=("y", "sum")).reset_index()
    d = d.merge(tot, on=["team", "season"])
    d = d[(d.tp > 0) & (d.ta > 0)].copy()
    d["_rk"] = d.groupby(["team", "season"])[pred_col].rank(ascending=False, method="first")
    top2 = d[d._rk <= 2].groupby(["team", "season"]).agg(
        p2=("cp", "sum"), a2=("y", "sum"), k=("cp", "size")).reset_index()
    t = top2.merge(tot, on=["team", "season"])
    t = t[t.k == 2]
    err = (t.p2 / t.tp) - (t.a2 / t.ta)
    d["pred_share"] = d.cp / d.tp
    d["act_share"] = d.y / d.ta
    d["bucket"] = np.select(
        [d._rk == 1, d._rk == 2, d._rk == 3, d._rk <= 6], ["1", "2", "3", "4-6"], "7+")
    res = d.groupby("bucket").apply(
        lambda x: float((x.act_share - x.pred_share).mean()), include_groups=False)
    r12 = float((d.loc[d._rk <= 2, "act_share"] - d.loc[d._rk <= 2, "pred_share"]).mean())
    return dict(n_team_seasons=int(len(t)), alloc_err=float(err.mean()),
                rank12=r12, rank7plus=float(res.get("7+", np.nan)),
                buckets={k: float(v) for k, v in res.items()})


# ===================================================================================== PROBES
def probe_noise():
    """A 16-column random block carries no rank signal and cannot beat the baseline."""
    import build_rb_projection as B
    rng = np.random.default_rng(101)
    n = 900
    d = pd.DataFrame({"season": np.repeat([2019, 2020, 2021], n // 3),
                      "player_id": [f"p{i}" for i in range(n)]})
    for j in range(3):
        d[f"f{j}"] = rng.normal(0, 1, n)
    d["y"] = 40 + 20 * d.f0 + 8 * d.f1 + rng.normal(0, 10, n)
    base = ["f0", "f1", "f2"]
    for j in range(16):
        d[f"z{j}"] = rng.normal(0, 1, n)
    tr, te = d[d.season < 2021], d[d.season == 2021]
    cfg = dict(num_leaves=15, learning_rate=0.03, n_estimators=400)
    out = {}
    for tag, feats in (("base", base), ("noise", base + [f"z{j}" for j in range(16)])):
        Xtr, Xte = B._prep("lightgbm", tr, te, feats)
        out[tag] = _mae(te.y, B._fit_predict("lightgbm", cfg, Xtr, tr.y.to_numpy(float), Xte))
    rz = max(abs(_rho(d.y, d[f"z{j}"])) for j in range(16))
    ok = (out["noise"] - out["base"]) > -0.26 and rz < 0.15
    return ok, (f"base {out['base']:.3f} vs +16 noise cols {out['noise']:.3f} "
                f"(d={out['noise']-out['base']:+.3f}, must NOT clear -0.26) | max|rho(z,y)| {rz:.4f}")


def probe_planted():
    """A block carrying a real signal must be detected THROUGH the FIXED-FEATURE code path."""
    import build_rb_projection as B
    rng = np.random.default_rng(102)
    n = 900
    d = pd.DataFrame({"season": np.repeat([2019, 2020, 2021], n // 3),
                      "player_id": [f"p{i}" for i in range(n)]})
    for j in range(3):
        d[f"f{j}"] = rng.normal(0, 1, n)
    d["y"] = 40 + 20 * d.f0 + 8 * d.f1 + rng.normal(0, 10, n)
    d["planted"] = d.y + rng.normal(0, 3, n)                  # a genuinely informative column
    base = ["f0", "f1", "f2"]
    tr, te = d[d.season < 2021], d[d.season == 2021]
    cfg = dict(num_leaves=15, learning_rate=0.03, n_estimators=400)
    res = {}
    for tag, feats in (("base", base), ("planted", base + ["planted"])):
        Xtr, Xte = B._prep("lightgbm", tr, te, feats)
        res[tag] = _mae(te.y, B._fit_predict("lightgbm", cfg, Xtr, tr.y.to_numpy(float), Xte))
    ok = (res["planted"] - res["base"]) < -0.26
    return ok, (f"base {res['base']:.3f} -> planted {res['planted']:.3f} "
                f"(d={res['planted']-res['base']:+.3f}, must clear -0.26)")


def probe_future_peek():
    """Season-specific effect: only a model that has seen the test season can get it right."""
    import build_rb_projection as B
    rng = np.random.default_rng(103)
    n = 900
    d = pd.DataFrame({"season": np.repeat([2019, 2020, 2021], n // 3),
                      "player_id": [f"p{i}" for i in range(n)]})
    for j in range(3):
        d[f"f{j}"] = rng.normal(0, 1, n)
    coef = d.season.map({2019: 30.0, 2020: 30.0, 2021: -30.0})
    d["y"] = 40 + coef * d.f0 + 10 * d.f1 + rng.normal(0, 6, n)
    feats = ["f0", "f1", "f2"]
    tr, te = d[d.season < 2021], d[d.season == 2021]
    cfg = dict(num_leaves=15, learning_rate=0.03, n_estimators=400)
    Xtr, Xte = B._prep("lightgbm", tr, te, feats)
    honest = _mae(te.y, B._fit_predict("lightgbm", cfg, Xtr, tr.y.to_numpy(float), Xte))
    Xp, Xte2 = B._prep("lightgbm", te, te, feats)
    peek = _mae(te.y, B._fit_predict("lightgbm", cfg, Xp, te.y.to_numpy(float), Xte2))
    return peek < honest * 0.5, f"walk-forward {honest:.2f} vs FUTURE-PEEK {peek:.2f}"


def probe_feature_timing(blk_full):
    """Rebuild the block from weekly sources truncated at Y-1 and require identity for source Y-1."""
    Y = 2024
    blk_tr, _, _ = build_block(max_source_season=Y - 1)
    a = (blk_full[blk_full.source_season == Y - 1]
         .sort_values("player_id").reset_index(drop=True))
    b = (blk_tr[blk_tr.source_season == Y - 1]
         .sort_values("player_id").reset_index(drop=True))
    if not a["player_id"].equals(b["player_id"]):
        return False, f"key sets differ ({len(a)} vs {len(b)})"
    worst = 0.0
    for c in NEW_FEATS:
        x, z = a[c].astype(float), b[c].astype(float)
        if (x.isna() != z.isna()).any():
            return False, f"NaN pattern differs on {c}"
        d = float(np.nanmax(np.abs(x - z))) if x.notna().any() else 0.0
        worst = max(worst, d)
    return worst == 0.0, (f"source_season {Y-1} block rebuilt from data truncated at {Y-1}: "
                          f"{len(a)} rows, max |delta| {worst:g}")


def probe_pool_purity(base_feats, chal_feats):
    banned = ("sleeper", "adp", "depth_rank", "depth_chart", "depth_team", "talent")
    for pool, nm in ((base_feats, "BASE"), (chal_feats, "CHALLENGER")):
        bad = [c for c in pool if any(t in c.lower() for t in banned) or c == "y"]
        if bad:
            return False, f"{nm} pool contains {bad}"
    if list(chal_feats[:len(base_feats)]) != list(base_feats):
        return False, "challenger does not begin with the exact ordered BASE pool"
    if list(chal_feats[len(base_feats):]) != list(NEW_FEATS):
        return False, "challenger tail is not exactly the 16 frozen columns"
    return True, (f"BASE {len(base_feats)} cols untouched and in order; challenger = BASE + the 16 "
                  f"named columns; no market/depth/talent token in either")


# ==================================================================== POWER (outcome-free, §11.4)
def power_table(n_rows, n_clusters, sd_grid=(5.0, 10.0, 15.0, 20.0), rho_grid=(0.0, 0.3, 0.6)):
    m = n_rows / n_clusters
    rows = []
    for sd in sd_grid:
        for r in rho_grid:
            deff = 1 + (m - 1) * r
            n_eff = n_rows / deff
            se = sd / np.sqrt(n_eff)
            rows.append(dict(assumed_sd=sd, icc=r, design_effect=round(deff, 3),
                             n_eff=round(n_eff, 1), se=round(se, 4),
                             mde_80=round(2.802 * se, 4),
                             power_at_0p26=round(float(norm.cdf(0.26 / se - 1.96)), 3)))
    return pd.DataFrame(rows)


# ======================================================================================= CHECK
def run_check():
    print("=" * 100)
    print("WR RECENT FULL-PARTICIPATION FEATURES — STRUCTURAL CHECK (no challenger metric)")
    print("=" * 100)
    from build_wr_projection import WR_VET_ALL
    base_feats = list(WR_VET_ALL)
    chal_feats = base_feats + list(NEW_FEATS)

    before = snapshot()
    assert_protected(before)
    print(f"\n[1] PROTECTED ARTIFACTS: {len(before)} files snapshotted; all "
          f"{len(PROTECTED)} pinned hashes match")
    print(f"    frozen harness SHA256: {self_sha256()}")

    print("\n[2] PANEL — deterministic rebuild from the corrected dataset + pinned weekly snapshot")
    panel = build_panel()
    ev = panel[panel.season.isin(EVAL_SEASONS)].dropna(subset=["y"])
    print(f"    non-rookie WR rows {len(panel)} | 2021-2025 eval {len(ev)} "
          f"| player clusters {ev.player_id.nunique()} | 2026 deploy {int((panel.season==DEPLOY).sum())}")
    cached = RETRAIN_SCRATCH / "assembled_WR_new.parquet"
    if cached.exists():
        c = pd.read_parquet(cached).sort_values(["player_id", "season"]).reset_index(drop=True)
        a = panel.sort_values(["player_id", "season"]).reset_index(drop=True)
        keys_ok = a[["player_id", "season"]].equals(c[["player_id", "season"]])
        ydiff = float(np.nanmax(np.abs(a.y.fillna(-1e9) - c.y.fillna(-1e9))))
        fdiff = max(float(np.nanmax(np.abs(a[x].astype(float) - c[x].astype(float))))
                    for x in base_feats)
        print(f"    G0.1 vs corrected-retrain assembled_WR_new.parquet: keys identical {keys_ok} | "
              f"max |y delta| {ydiff:g} | max |feature delta| {fdiff:g}")
        assert keys_ok and ydiff == 0.0 and fdiff == 0.0, "G0.1 PANEL REPRODUCTION FAILED"
    else:
        print("    G0.1 SKIPPED — retrain scratch panel not present")

    print("\n[3] FROZEN BLOCK")
    t0 = time.time()
    blk, audit, diag = build_block(verbose=True)
    print(f"    built {len(blk):,} (player_id, source_season) block rows in {time.time()-t0:.0f}s")
    print(f"    diagnostics: {json.dumps(diag)}")
    assert not blk.duplicated(["player_id", "source_season"]).any(), "duplicate block key"
    full = attach_block(panel, blk)
    assert not full.duplicated(["player_id", "season"]).any(), "duplicate panel key after join"
    assert len(full) == len(panel), "block join changed the row count"

    print("\n[4] COVERAGE (structural counts, not outcomes)")
    cov = []
    for Y in EVAL_SEASONS + [DEPLOY]:
        d = full[full.season == Y]
        if Y != DEPLOY:
            d = d.dropna(subset=["y"])
        cov.append(dict(season=Y, n=len(d),
                        has_last4_full=float(d.has_last4_full.mean()),
                        has_last8_full=float(d.has_last8_full.mean()),
                        mean_full_games=float(d.prior_full_participation_games.mean()),
                        mean_excluded=float(d.prior_active_games_excluded.mean())))
    covdf = pd.DataFrame(cov)
    print(covdf.to_string(index=False))
    evd = full[full.season.isin(EVAL_SEASONS)].dropna(subset=["y"])
    dep = full[full.season == DEPLOY]
    e4, e8 = float(evd.has_last4_full.mean()), float(evd.has_last8_full.mean())
    d4, d8 = float(dep.has_last4_full.mean()), float(dep.has_last8_full.mean())
    print(f"    pooled eval  L4 {e4:.3f}  L8 {e8:.3f}")
    print(f"    2026 deploy  L4 {d4:.3f}  L8 {d8:.3f}   (G7 bars .60 / .40, max drop 10pp)")
    print(f"    G7 preview (not a verdict until --fire): L4>=.60 {d4>=G7_L4_MIN} | "
          f"L8>=.40 {d8>=G7_L8_MIN} | drops {e4-d4:+.3f} / {e8-d8:+.3f}")

    print("\n[5] PROBES")
    probes = [("noise block carries nothing", probe_noise()),
              ("planted signal detected through the fixed-config path", probe_planted()),
              ("future-peek screams", probe_future_peek()),
              ("feature timing: Y features use only REG Y-1", probe_feature_timing(blk)),
              ("feature-pool purity", probe_pool_purity(base_feats, chal_feats))]
    for name, (ok, msg) in probes:
        print(f"    {'PASS' if ok else 'FAIL'}  {name}: {msg}")
    assert all(ok for _, (ok, _) in probes), "PROBE FAILED — STOP"

    print("\n[6] STRUCTURAL ASSERTIONS")
    for Y in EVAL_SEASONS:
        tr = full[full.season < Y].dropna(subset=["y"])
        assert tr.season.max() < Y, f"fold boundary {Y}"
    print(f"    fold boundaries: train.season.max() < Y for all of {EVAL_SEASONS}  PASS")
    b = full[base_feats + ["player_id", "season", "y"]]
    f = full[chal_feats + ["player_id", "season", "y"]]
    assert b[["player_id", "season"]].equals(f[["player_id", "season"]]), "row identity"
    print("    row identity BASE vs FIXED-FEATURE: identical (player_id, season) order  PASS")
    print("    postseason exclusion: asserted inside load_weekly_stats / load_weekly_snaps / "
          "load_gamedays  PASS")
    print(f"    sealed slice: min season touched = {int(full.season.min())} (>= 2014)  PASS")

    print("\n[7] BASE SELECTION REPRODUCTION (G0.2) — 2021 fold only, the cheapest probe")
    import build_rb_projection as B
    tr = full[full.season < 2021].dropna(subset=["y"])
    t0 = time.time()
    (fam, params, imae), _ = B.nested_select(tr, base_feats)
    exp_fam, exp_par = G0_SELECTIONS[2021]
    ok = (fam == exp_fam) and (params == exp_par)
    print(f"    2021: {fam} {params} (inner {imae:.3f}, {time.time()-t0:.0f}s)")
    print(f"    expected from the corrected-retrain fire.log: {exp_fam} {exp_par} -> "
          f"{'MATCH' if ok else 'MISMATCH'}")
    assert ok, "G0.2 SELECTION REPRODUCTION FAILED"

    print("\n[8] OUTCOME-FREE POWER APPROXIMATION (panel counts + simulated effects only)")
    pw = power_table(len(ev), ev.player_id.nunique())
    print(f"    n={len(ev)} rows, {ev.player_id.nunique()} player clusters, "
          f"m={len(ev)/ev.player_id.nunique():.2f} rows/cluster, bar = 0.26 MAE")
    print(pw.to_string(index=False))

    print("\n[9] RUNTIME ESTIMATE")
    print("    measured: nested_select on this panel is ~167s (2021 fold, 1260 rows) to ~310s "
          "(2025 fold, 2074 rows) at 32 features")
    print("    fire = 6 BASE + 6 RESELECTED nested_select (48 cols ~1.4x) + 5 rookie folds "
          "(G0.3) + 12 cheap fits  ->  roughly 70-95 min")

    after = snapshot()
    assert after == before, f"PROTECTED DRIFT: {[k for k in before if before[k]!=after.get(k)]}"
    print(f"\n[10] PROTECTED ARTIFACTS byte-identical before and after --check: True ({len(after)} files)")
    print(f"\nFROZEN SHA256: {self_sha256()}")
    print("CHECK: PASS — no challenger metric was computed.")


# ======================================================================================== FIRE
def run_fire():
    log_lines = []

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        log_lines.append(s)

    P("=" * 100)
    P("WR RECENT FULL-PARTICIPATION FEATURES — FIRE (one shot)")
    P(f"harness SHA256 {self_sha256()}")
    P("=" * 100)
    from build_wr_projection import WR_VET_ALL
    import build_rb_projection as B
    base_feats = list(WR_VET_ALL)
    chal_feats = base_feats + list(NEW_FEATS)

    before = snapshot()
    assert_protected(before)
    P(f"\nPROTECTED: {len(before)} files snapshotted, {len(PROTECTED)} pins verified")

    panel = build_panel()
    blk, audit, diag = build_block()
    full = attach_block(panel, blk)
    audit.to_csv(OUT / "full_game_exclusion_audit.csv", index=False)
    P(f"panel {len(full)} rows | block {len(blk)} rows | exclusion audit {len(audit)} rows")
    P(f"block diagnostics: {json.dumps(diag)}")

    # ---------------------------------------------------------------- arms
    P("\n--- BASE (32 cols, nested_select) ---")
    base, base_cfg = walk_arm(full, base_feats, "BASE")
    P("\n--- FIXED-FEATURE (48 cols, BASE's per-fold config) ---")
    fixed, _ = walk_arm(full, chal_feats, "FIXED", frozen=base_cfg)
    P("\n--- RESELECTED-FEATURE (48 cols, nested_select re-run) ---")
    resel, resel_cfg = walk_arm(full, chal_feats, "RESEL")

    key = ["player_id", "season"]
    m = (base.rename(columns={"pred": "p_base"})
             .merge(fixed[key + ["pred"]].rename(columns={"pred": "p_fixed"}), on=key, how="inner")
             .merge(resel[key + ["pred"]].rename(columns={"pred": "p_resel"}), on=key, how="inner"))
    assert len(m) == len(base) == len(fixed) == len(resel), "ROW IDENTITY FAILED across arms"
    assert not m.duplicated(key).any(), "duplicate key on the matched panel"
    P(f"\nmatched primary panel n={len(m)} (BASE {len(base)}, FIXED {len(fixed)}, RESEL {len(resel)})")

    # ---------------------------------------------------------------- G0.3 metric reproduction
    g0_metric, g0_msg = False, "rookie panel unavailable"
    rook_p = RETRAIN_SCRATCH / "assembled_WR_new_rook.parquet"
    if rook_p.exists():
        from build_wr_projection import WR_ROOK_ALL
        rook = pd.read_parquet(rook_p)
        P("\n--- G0.3: rookie arm re-run (read-only panel) to reproduce the retrain's WR NEW panel ---")
        rk, _ = walk_arm(rook, list(WR_ROOK_ALL), "ROOK")
        merged = pd.concat([base[["season", "player_id", "y", "pred"]],
                            rk[["season", "player_id", "y", "pred"]]], ignore_index=True)
        mae_m, rho_m, n_m = _mae(merged.y, merged.pred), _rho(merged.y, merged.pred), len(merged)
        g0_metric = (n_m == G0_TARGET_N and abs(mae_m - G0_TARGET_MAE) < 5e-4
                     and abs(rho_m - G0_TARGET_RHO) < 5e-6)
        g0_msg = (f"n {n_m} (target {G0_TARGET_N}) | MAE {mae_m:.5f} (target {G0_TARGET_MAE}) | "
                  f"rho {rho_m:.6f} (target {G0_TARGET_RHO})")
        P(f"    {g0_msg}")
    g0_sel = all(base_cfg.get(Y, (None, None)) == v for Y, v in G0_SELECTIONS.items())
    P(f"    G0.2 selections 2021/2022 match the retrain record: {g0_sel}")
    P(f"    BASE per-fold configs: " + " | ".join(f"{Y}:{c[0]}{c[1]}" for Y, c in base_cfg.items()))
    P(f"    RESEL per-fold configs: " + " | ".join(f"{Y}:{c[0]}{c[1]}" for Y, c in resel_cfg.items()))

    # ---------------------------------------------------------------- metrics
    P("\n" + "=" * 100)
    P("METRICS — primary panel")
    arms = {"BASE": "p_base", "FIXED-FEATURE": "p_fixed", "RESELECTED-FEATURE": "p_resel"}
    mb = {}
    for nm, c in arms.items():
        mb[nm] = block_metrics(m.rename(columns={c: "pred"}), "pred")
        s = mb[nm]
        P(f"  {nm:20s} MAE {s['MAE']:8.4f}  RMSE {s['RMSE']:8.4f}  rho {s['rho']:.5f}  "
          f"bias {s['bias']:+8.3f}  med {s['med_bias']:+8.3f}  predSD {s['predSD']:6.2f} "
          f"(actual {s['actSD']:.2f})")

    d_mae = mb["FIXED-FEATURE"]["MAE"] - mb["BASE"]["MAE"]
    d_rho = mb["FIXED-FEATURE"]["rho"] - mb["BASE"]["rho"]
    d_rmse = mb["FIXED-FEATURE"]["RMSE"] - mb["BASE"]["RMSE"]
    lo, hi = paired_bootstrap(m, "p_base", "p_fixed")
    P(f"\n  FIXED-BASE  dMAE {d_mae:+.4f}  boot95 [{lo:+.4f}, {hi:+.4f}]  "
      f"drho {d_rho:+.5f}  dRMSE {d_rmse:+.4f} ({100*d_rmse/mb['BASE']['RMSE']:+.2f}%)")
    lo_r, hi_r = paired_bootstrap(m, "p_base", "p_resel")
    P(f"  RESEL-BASE  dMAE {mb['RESELECTED-FEATURE']['MAE']-mb['BASE']['MAE']:+.4f} "
      f"boot95 [{lo_r:+.4f}, {hi_r:+.4f}]  (report-only)")

    rows = []
    for Y in EVAL_SEASONS:
        d = m[m.season == Y]
        r = dict(season=Y, n=len(d))
        for nm, c in arms.items():
            s = block_metrics(d.rename(columns={c: "pred"}), "pred")
            r[f"MAE_{nm[:5]}"] = round(s["MAE"], 4)
            r[f"rho_{nm[:5]}"] = round(s["rho"], 5)
            r[f"bias_{nm[:5]}"] = round(s["bias"], 3)
        r["dMAE_fixed"] = round(r["MAE_FIXED"] - r["MAE_BASE"], 4)
        rows.append(r)
    per = pd.DataFrame(rows)
    per.to_csv(OUT / "per_season.csv", index=False)
    P("\nPER-SEASON")
    P(per.to_string(index=False))
    seasons_better = int((per.dMAE_fixed < 0).sum())
    t = ttest_1samp(per.dMAE_fixed.to_numpy(float), 0.0)
    P(f"  seasons improved {seasons_better}/5 | season-clustered t(4) p = {float(t.pvalue):.4f}")

    # ---------------------------------------------------------------- frozen top-24 cohort
    mm = m.copy()
    mm["_rk"] = mm.groupby("season")["p_base"].rank(ascending=False, method="first")
    coh = mm[mm._rk <= TOP_K]
    P(f"\nFROZEN TOP-{TOP_K} COHORT (by BASE rank, identical rows in all arms) n={len(coh)}")
    cm = {}
    for nm, c in arms.items():
        cm[nm] = block_metrics(coh.rename(columns={c: "pred"}), "pred")
        s = cm[nm]
        P(f"  {nm:20s} MAE {s['MAE']:8.4f}  rho {s['rho']:.5f}  bias {s['bias']:+8.3f}")
    coh_dmae = cm["FIXED-FEATURE"]["MAE"] - cm["BASE"]["MAE"]
    coh_dabs = abs(cm["FIXED-FEATURE"]["bias"]) - abs(cm["BASE"]["bias"])
    P(f"  cohort dMAE {coh_dmae:+.4f} | d|bias| {coh_dabs:+.4f}")

    # ---------------------------------------------------------------- coverage
    cov = []
    for Y in EVAL_SEASONS + [DEPLOY]:
        d = full[full.season == Y]
        d = d if Y == DEPLOY else d.dropna(subset=["y"])
        row = dict(season=Y, n=len(d), has_last4_full=round(float(d.has_last4_full.mean()), 4),
                   has_last8_full=round(float(d.has_last8_full.mean()), 4),
                   mean_full_games=round(float(d.prior_full_participation_games.mean()), 3),
                   mean_excluded=round(float(d.prior_active_games_excluded.mean()), 3))
        for c in NEW_FEATS:
            row[f"nonnull_{c}"] = round(float(d[c].notna().mean()), 4)
        cov.append(row)
    covdf = pd.DataFrame(cov)
    covdf.to_csv(OUT / "coverage.csv", index=False)
    evd = full[full.season.isin(EVAL_SEASONS)].dropna(subset=["y"])
    dep_rows = full[full.season == DEPLOY]
    e4, e8 = float(evd.has_last4_full.mean()), float(evd.has_last8_full.mean())
    d4, d8 = float(dep_rows.has_last4_full.mean()), float(dep_rows.has_last8_full.mean())
    P(f"\nCOVERAGE  eval L4 {e4:.4f} L8 {e8:.4f} | deploy L4 {d4:.4f} L8 {d8:.4f} | "
      f"drops {e4-d4:+.4f} / {e8-d8:+.4f}")

    # ---------------------------------------------------------------- deploy
    P("\n--- 2026 DEPLOY ---")
    dep_b, cfg_b, model_b = deploy_arm(full, base_feats, "BASE")
    dep_f, _, model_f = deploy_arm(full, chal_feats, "FIXED", frozen=cfg_b)
    dep_r, cfg_r, model_r = deploy_arm(full, chal_feats, "RESEL")
    P(f"  BASE deploy config {cfg_b[0]} {cfg_b[1]} | RESEL deploy config {cfg_r[0]} {cfg_r[1]}")
    dm = dep_b[["player_id", "player", "team", "pred"]].rename(columns={"pred": "base_proj"})
    dm = dm.merge(dep_f[["player_id", "pred"]].rename(columns={"pred": "fixed_proj"}), on="player_id")
    dm = dm.merge(dep_r[["player_id", "pred"]].rename(columns={"pred": "resel_proj"}), on="player_id")
    dm = dm.merge(full.loc[full.season == DEPLOY,
                           ["player_id"] + NEW_FEATS + ["prior_games", "prior_half_ppr"]],
                  on="player_id", how="left")
    dm["move"] = (dm.fixed_proj - dm.base_proj).round(1)
    dm = dm.sort_values("move", key=lambda s: s.abs(), ascending=False)
    dm.to_csv(OUT / "deploy_move_WR.csv", index=False)
    slate_b, slate_f = float(dm.base_proj.mean()), float(dm.fixed_proj.mean())
    slate_pct = (slate_f - slate_b) / slate_b if slate_b else np.nan
    movers = dm[dm.move.abs() > G8_PLAYER_PTS]
    P(f"  n={len(dm)} slate mean {slate_b:.2f} -> {slate_f:.2f} ({slate_pct:+.2%}) | "
      f"movers >|{G8_PLAYER_PTS:.0f}|: {len(movers)}")
    P(dm.head(15)[["player", "base_proj", "fixed_proj", "move", "has_last4_full",
                   "has_last8_full", "prior_full_participation_games",
                   "prior_active_games_excluded"]].to_string(index=False))

    fu = feature_usage(model_f, cfg_b[0], chal_feats)
    fu["is_new_block"] = fu.feature.isin(NEW_FEATS)
    tot = float(np.nansum(fu.gain.to_numpy(float)))
    fu["gain_share"] = fu.gain / tot if tot else np.nan
    fu.sort_values("gain", ascending=False).to_csv(OUT / "feature_usage.csv", index=False)
    blk_share = float(fu.loc[fu.is_new_block, "gain_share"].sum())
    P(f"\nFEATURE USAGE (FIXED deploy model, {cfg_b[0]}): the 16-col block takes "
      f"{blk_share:.2%} of total gain")
    P(fu.sort_values("gain", ascending=False).head(12)[
        ["feature", "gain", "split", "gain_share", "is_new_block"]].to_string(index=False))

    # ---------------------------------------------------------------- diagnostics
    P("\nEXCLUSION CLASSIFICATION (outcome-free)")
    if len(audit):
        vc = audit.exclusion_class.value_counts()
        P(f"  excluded active games {len(audit)} | ISOLATED {int(vc.get('ISOLATED',0))} "
          f"({vc.get('ISOLATED',0)/len(audit):.1%}) | TERMINAL_RUN {int(vc.get('TERMINAL_RUN',0))} "
          f"({vc.get('TERMINAL_RUN',0)/len(audit):.1%})")
        ex_pl = audit.groupby(["player_id", "source_season"]).size().rename("n_excl").reset_index()
        j = full[["player_id", "season", "prior_games_missed", "prior_active_games_excluded"]].copy()
        j["source_season"] = j.season - 1
        j = j.merge(ex_pl, on=["player_id", "source_season"], how="left")
        j["n_excl"] = j.n_excl.fillna(0)
        jj = j.dropna(subset=["prior_games_missed"])
        P(f"  rho(excluded active games, prior_games_missed) = "
          f"{_rho(jj.n_excl, jj.prior_games_missed):+.4f} over n={len(jj)}")

    P("\nCOHORT BY PRIOR-SEASON GAMES PLAYED (report-only)")
    mg = m.merge(full[["player_id", "season", "prior_games"]], on=key, how="left")
    mg["bucket"] = pd.cut(mg.prior_games, [-0.1, 0.5, 8, 12, 16, 99],
                          labels=["0", "1-8", "9-12", "13-16", "17+"])
    for b, d in mg.groupby("bucket", observed=True):
        if len(d) < 5:
            continue
        P(f"  {str(b):6s} n={len(d):4d}  BASE {_mae(d.y,d.p_base):7.3f} -> FIXED "
          f"{_mae(d.y,d.p_fixed):7.3f}  ({_mae(d.y,d.p_fixed)-_mae(d.y,d.p_base):+.3f})")

    P("\nTEAM-ALLOCATION MOVEMENT (report-only; the audit found NO defect, sign inverted)")
    al_b = allocation_stats(m.rename(columns={"p_base": "pred"}), "pred")
    al_f = allocation_stats(m.rename(columns={"p_fixed": "pred"}), "pred")
    P(f"  admissible team-seasons {al_b['n_team_seasons']} (NON-ROOKIE ONLY — not comparable in "
      f"level to the audit's 1,242-row panel; only the BASE->FIXED movement is meaningful)")
    P(f"  alloc_err   BASE {al_b['alloc_err']:+.6f} -> FIXED {al_f['alloc_err']:+.6f} "
      f"({al_f['alloc_err']-al_b['alloc_err']:+.6f})   [audit measured +0.012153]")
    P(f"  rank 1-2    BASE {al_b['rank12']:+.6f} -> FIXED {al_f['rank12']:+.6f}   "
      f"[audit -0.006076]")
    P(f"  rank 7+     BASE {al_b['rank7plus']:+.6f} -> FIXED {al_f['rank7plus']:+.6f}   "
      f"[audit +0.007638]")

    # ---------------------------------------------------------------- GATES
    P("\n" + "=" * 100)
    P("FROZEN GATES")
    g = {}
    g["G0"] = bool(g0_sel and g0_metric)
    g["G1"] = bool(d_mae <= G1_FLOOR)
    g["G2"] = bool(hi < 0)
    g["G3"] = bool(d_rho >= 0)
    g["G4"] = bool(seasons_better >= G4_MIN_SEASONS)
    g["G5"] = bool(coh_dmae <= G5_MAE_TOL and coh_dabs <= G5_BIAS_TOL)
    g["G6"] = bool(d_rmse <= G6_RMSE_REL * mb["BASE"]["RMSE"])
    g["G7"] = bool(d4 >= G7_L4_MIN and d8 >= G7_L8_MIN
                   and (e4 - d4) <= G7_MAX_DROP_PP and (e8 - d8) <= G7_MAX_DROP_PP)
    g["G8"] = bool(abs(slate_pct) <= G8_SLATE_PCT)
    detail = {
        "G0": f"selections match {g0_sel}; metric reproduction {g0_msg}",
        "G1": f"dMAE {d_mae:+.4f} <= {G1_FLOOR}",
        "G2": f"boot95 upper {hi:+.4f} < 0",
        "G3": f"drho {d_rho:+.5f} >= 0",
        "G4": f"{seasons_better}/5 seasons improved >= {G4_MIN_SEASONS}",
        "G5": f"cohort dMAE {coh_dmae:+.4f} <= {G5_MAE_TOL} AND d|bias| {coh_dabs:+.4f} <= {G5_BIAS_TOL}",
        "G6": f"dRMSE {d_rmse:+.4f} <= {G6_RMSE_REL*mb['BASE']['RMSE']:+.4f} "
              f"({100*d_rmse/mb['BASE']['RMSE']:+.2f}% vs +1.00%)",
        "G7": f"deploy L4 {d4:.4f}>={G7_L4_MIN} L8 {d8:.4f}>={G7_L8_MIN}; "
              f"drops {e4-d4:+.4f}/{e8-d8:+.4f} <= {G7_MAX_DROP_PP}",
        "G8": f"slate {slate_pct:+.2%} within +/-{G8_SLATE_PCT:.0%}; movers>|25| = {len(movers)}",
    }
    for k in sorted(g):
        P(f"  {k}  {'PASS' if g[k] else 'FAIL'}   {detail[k]}")
    verdict = "PASS" if all(g.values()) else "REJECT"
    P(f"\nVERDICT: {verdict} — RECENT FULL-PARTICIPATION FEATURES")

    summary = dict(
        verdict=verdict, harness_sha256=self_sha256(), n_primary=int(len(m)),
        n_clusters=int(m.player_id.nunique()), gates=g, gate_detail=detail,
        arms={k: mb[k] for k in mb}, cohort={k: cm[k] for k in cm},
        delta=dict(mae=d_mae, rho=d_rho, rmse=d_rmse, boot95=[lo, hi],
                   resel_mae=mb["RESELECTED-FEATURE"]["MAE"] - mb["BASE"]["MAE"],
                   resel_boot95=[lo_r, hi_r], seasons_better=seasons_better,
                   t4_p=float(t.pvalue), cohort_dmae=coh_dmae, cohort_dabs_bias=coh_dabs),
        coverage=dict(eval_l4=e4, eval_l8=e8, deploy_l4=d4, deploy_l8=d8),
        deploy=dict(n=int(len(dm)), slate_base=slate_b, slate_fixed=slate_f, slate_pct=slate_pct,
                    movers_gt25=int(len(movers)),
                    top_moves=dm.head(20)[["player", "base_proj", "fixed_proj", "move"]]
                    .to_dict("records")),
        base_configs={str(k): [v[0], v[1]] for k, v in base_cfg.items()},
        resel_configs={str(k): [v[0], v[1]] for k, v in resel_cfg.items()},
        deploy_configs=dict(base=[cfg_b[0], cfg_b[1]], resel=[cfg_r[0], cfg_r[1]]),
        block_gain_share=blk_share, block_diagnostics=diag,
        allocation=dict(base=al_b, fixed=al_f),
        g0=dict(selections_match=bool(g0_sel), metric=g0_msg, metric_ok=bool(g0_metric)),
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

    after = snapshot()
    drift = [k for k in before if before[k] != after.get(k)] + [k for k in after if k not in before]
    P(f"\nPROTECTED ARTIFACTS byte-identical before and after --fire: {not drift} "
      f"({len(after)} files){'; DRIFT: ' + str(drift) if drift else ''}")
    (OUT / "fire.log").write_text("\n".join(log_lines), encoding="utf-8")
    assert not drift, f"PROTECTED DRIFT: {drift}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--fire", action="store_true")
    a = ap.parse_args()
    if a.check:
        run_check()
    elif a.fire:
        run_fire()
    else:
        raise SystemExit("pass --check or --fire")


if __name__ == "__main__":
    main()
