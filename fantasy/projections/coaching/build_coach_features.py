"""COACH FEATURE ENGINE — the shrunk, strictly-prior histories that Arms 1, 2 and 4 consume.

Governing prereg: PREREG_coach_quality_2026-07-28.md (v3, RATIFIED AND T0 PASSED).
Source table frozen at md5 98f1c66b7387c16bba6a5463f4e0fa06 (v3.4 PREFIT).

HASH CHAIN (all superseded values are historical, not active):
  ac9883e98cdb1bd04a1c0978746cc023  T0-ratified table
  391be44c4e4205ceea6456ea935794c0  v3.2 -- n_games_attributed counted, not week arithmetic
  3752405a4f499223aac08841dabc5f74  PROVISIONAL/INTERMEDIATE -- never a canonical freeze
  98f1c66b7387c16bba6a5463f4e0fa06  v3.4 -- audited source dates + provenance

NOTE ON METRIC NAMES BELOW: `off_points_per_game` and `points_per_drive` are the PRE-v3.3 names.
Phase 1B renamed them to `drive_scoring_points_per_game_proxy` and
`drive_scoring_points_per_drive_proxy` because a flat TD=7 assumes the extra point, ignores 2-point
attempts and missed XPs, and excludes all defensive and special-teams scoring. This module has NOT
yet been migrated to the segment-level, caller-first inputs -- see REQUIREMENT_MATRIX.md.

Produces one row per (season, team) carrying, for BOTH coach entities:
  hc_*   head coach          (nflverse schedules, game-by-game, 100% coverage)
  pc_*   ACTUAL play-caller  (citation-backed table; UNKNOWN routes to league prior)

FROZEN SHRINKAGE (§2, not tunable):
    reliability  = prior_games / (prior_games + 32)
    shrunk_value = reliability * observed + (1 - reliability) * league_prior
  league prior 0.500 for win pct and rank percentiles; 0.000 for z-scores and residuals.

STRICT PRIORITY: every quantity attached to season Y uses ONLY games/seasons with season < Y.
The league prior itself is an EXPANDING mean recomputed from seasons < Y — never the full panel.

UNKNOWN ROUTING (§1.2): a team-season with no attributable play-caller, and a first-time caller
with no prior history, both receive the league prior, reliability 0 and no_prior_history 1. Never
a penalty, never a bonus, and never the nominal OC.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

K_SHRINK = 32                 # FROZEN
ROLL_WINDOW = 3               # FROZEN
PRIOR_PCT = 0.500             # FROZEN: win pct + rank percentiles
PRIOR_Z = 0.000               # FROZEN: z-scores + residual effects

# Arm 1 composite components (§4 ARM 1) — equal weight, >=3 of 5 required
RANK_METRICS = ["off_points_per_game", "yards_play", "epa_play", "success_rate", "points_per_drive"]
# Arm 2 continuous dimensions (§4 ARM 2) — kept separate, never collapsed
Z_METRICS = ["epa_play", "success_rate", "points_per_drive", "yards_play",
             "explosive_rate", "redzone_td_rate"]
# Arm 4 scheme / allocation tendencies (§4 ARM 4)
SCHEME_METRICS = ["plays_per_game", "neutral_pass_rate", "proe", "early_down_pass_rate",
                  "redzone_pass_rate", "seconds_per_play", "rb_carry_share", "qb_carry_share",
                  "rb_target_share", "wr_target_share", "te_target_share", "rz_rb_share",
                  "rz_wr_share", "rz_te_share", "rz_qb_share", "team_adot"]


# ------------------------------------------------------------------ coach-season ledgers
def head_coach_ledger():
    """Per (season, team, head_coach): games coached and regular-season wins (tie = 0.5).

    IDENTITY and RECORD are separated on purpose. The win/loss ledger needs a played game, but the
    deploy season is unplayed -- filtering on `result` would leave 2026 with no head coach at all
    and silently NaN every hc_* feature on the rows we actually project. So identity comes from the
    full REG schedule and only the win columns require a result.
    """
    import nflreadpy as nfl
    s = nfl.load_schedules().to_pandas()
    s = s[s["game_type"] == "REG"].copy()
    TEAM_CANON = {"ARZ": "ARI", "AZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
                  "SL": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV"}
    rows = []
    for side in ("home", "away"):
        d = s[["season", "week", f"{side}_team", f"{side}_coach", "result"]].copy()
        d.columns = ["season", "week", "team", "coach", "result"]
        margin = d["result"] if side == "home" else -d["result"]
        d["win"] = np.where(d["result"].isna(), np.nan,
                            np.where(margin > 0, 1.0, np.where(margin < 0, 0.0, 0.5)))  # TIE = 0.5
        d["played"] = d["result"].notna().astype(float)
        rows.append(d)
    hc = pd.concat(rows, ignore_index=True).dropna(subset=["coach"])
    hc["team"] = hc["team"].replace(TEAM_CANON)
    led = hc.groupby(["season", "team", "coach"]).agg(
        games=("played", "sum"), wins=("win", "sum"), scheduled=("played", "size")).reset_index()
    led["person_id"] = led["coach"].map(_pid)
    return led


def _pid(name):
    import re
    import unicodedata
    if not isinstance(name, str) or not name.strip():
        return None
    x = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    x = x.lower().replace(".", "").replace("'", "").replace("-", " ")
    x = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", x)
    return "_".join(x.split())


def play_caller_ledger():
    """Per (season, team, person_id): games called. Splits carry their own game counts."""
    pc = pd.read_csv(DATA / "actual_play_caller.csv")
    pc = pc[pc.person_id.notna()].copy()
    led = pc.groupby(["season", "team", "person_id", "actual_play_caller"]).agg(
        games=("n_games_attributed", "sum")).reset_index()
    led = led[led.games > 0]
    return led


# ------------------------------------------------------------------ team-offense derived views
def team_offense_views():
    """Season-standardised views of the offense panel: rank percentiles, z-scores, raw scheme."""
    p = pd.read_csv(DATA / "team_offense_panel.csv")

    # rank percentile, 1.0 = best in that season (§4 ARM 1)
    for m in RANK_METRICS:
        if m in p.columns:
            r = p.groupby("season")[m].rank(ascending=False, method="min")
            n = p.groupby("season")[m].transform(lambda s: s.notna().sum())
            p[f"rankpct_{m}"] = 1 - (r - 1) / (n - 1)

    # composite: equal-weight mean of AVAILABLE percentiles, >=3 of 5 or missing
    rp = p[[f"rankpct_{m}" for m in RANK_METRICS if f"rankpct_{m}" in p.columns]]
    p["off_rank_composite"] = np.where(rp.notna().sum(axis=1) >= 3, rp.mean(axis=1), np.nan)

    # within-season z-scores (§4 ARM 2)
    for m in Z_METRICS:
        if m in p.columns:
            g = p.groupby("season")[m]
            p[f"z_{m}"] = (p[m] - g.transform("mean")) / g.transform("std")
    return p


# ------------------------------------------------------------------ shrinkage core
def _shrink(obs, games, prior):
    rel = games / (games + K_SHRINK)
    return rel * obs + (1 - rel) * prior, rel


def prior_history(ledger, panel, value_cols, seasons, prior_kind):
    """For every (coach, target season Y): games-weighted mean of value_cols over seasons < Y,
    shrunk toward the EXPANDING league mean of seasons < Y. Returns career + rolling-3 variants.

    `prior_kind` selects the frozen league prior: 'pct' -> 0.500, 'z' -> 0.000.
    """
    base = ledger.merge(panel[["season", "team"] + value_cols], on=["season", "team"], how="left")
    fixed_prior = PRIOR_PCT if prior_kind == "pct" else PRIOR_Z
    out = []
    for Y in seasons:
        hist = base[base.season < Y]
        if not len(hist):
            continue
        for label, window in (("career", None), ("roll3", ROLL_WINDOW)):
            h = hist if window is None else hist[hist.season >= Y - window]
            if not len(h):
                continue
            agg = {}
            for c in value_cols:
                hh = h.dropna(subset=[c])
                if not len(hh):
                    continue
                num = (hh[c] * hh["games"]).groupby(hh["person_id"]).sum()
                den = hh.groupby("person_id")["games"].sum()
                agg[c] = num / den
            g = h.groupby("person_id")["games"].sum()
            df = pd.DataFrame(agg)
            df["prior_games"] = g
            df = df.reset_index().rename(columns={"index": "person_id"})
            for c in value_cols:
                if c not in df.columns:
                    df[c] = np.nan
                sh, rel = _shrink(df[c].fillna(fixed_prior), df["prior_games"], fixed_prior)
                df[f"{label}_{c}_shrunk"] = np.where(df[c].notna(), sh, fixed_prior)
            df["season"] = Y
            df["window"] = label
            out.append(df)
    if not out:
        return pd.DataFrame()
    return pd.concat(out, ignore_index=True)


def _pivot(hist, value_cols, prefix):
    """career/roll3 long -> one wide row per (person_id, season) with prefixed columns."""
    keep = ["person_id", "season", "window", "prior_games"] + \
           [f"{w}_{c}_shrunk" for w in ("career", "roll3") for c in value_cols]
    frames = []
    for w in ("career", "roll3"):
        h = hist[hist.window == w].copy()
        cols = {f"{w}_{c}_shrunk": f"{prefix}_{w}_{c}_shrunk" for c in value_cols
                if f"{w}_{c}_shrunk" in h.columns}
        h = h[["person_id", "season", "prior_games"] + list(cols)].rename(columns=cols)
        if w == "career":
            h = h.rename(columns={"prior_games": f"{prefix}_prior_games"})
        else:
            h = h.drop(columns=["prior_games"])
        frames.append(h)
    _ = keep
    m = frames[0]
    for f in frames[1:]:
        m = m.merge(f, on=["person_id", "season"], how="outer")
    return m


def build(seasons=None):
    seasons = seasons or list(range(2014, 2027))
    print("=" * 80)
    print("COACH FEATURE ENGINE — shrunk strictly-prior histories (HC + actual play-caller)")
    print("=" * 80)

    hc_led = head_coach_ledger()
    pc_led = play_caller_ledger()
    panel = team_offense_views()
    print(f"  HC ledger {len(hc_led):,} coach-team-seasons | PC ledger {len(pc_led):,} "
          f"| offense panel {len(panel):,} team-seasons")

    # ---- HEAD COACH: win pct (games/wins live in the ledger itself, not the offense panel)
    hc_rows = []
    for Y in seasons:
        h = hc_led[hc_led.season < Y]
        if not len(h):
            continue
        for label, window in (("career", None), ("roll3", ROLL_WINDOW)):
            hh = h if window is None else h[h.season >= Y - window]
            if not len(hh):
                continue
            g = hh.groupby("person_id").agg(prior_games=("games", "sum"), wins=("wins", "sum"))
            g["win_pct"] = g["wins"] / g["prior_games"]
            sh, rel = _shrink(g["win_pct"], g["prior_games"], PRIOR_PCT)
            g[f"hc_{label}_win_pct_shrunk"] = sh
            if label == "career":
                g["hc_prior_games"] = g["prior_games"]
                g["hc_reliability"] = rel
            g["season"] = Y
            hc_rows.append(g.reset_index()[
                ["person_id", "season", f"hc_{label}_win_pct_shrunk"]
                + (["hc_prior_games", "hc_reliability"] if label == "career" else [])])
    hc_hist = hc_rows[0]
    for f in hc_rows[1:]:
        hc_hist = pd.concat([hc_hist, f], ignore_index=True)
    hc_hist = hc_hist.groupby(["person_id", "season"], as_index=False).first()

    # ---- PLAY-CALLER: Arm 1 composite, Arm 2 z-dims, Arm 4 scheme
    a1 = prior_history(pc_led, panel, ["off_rank_composite"], seasons, "pct")
    a2 = prior_history(pc_led, panel, [f"z_{m}" for m in Z_METRICS if f"z_{m}" in panel.columns],
                       seasons, "z")
    a4 = prior_history(pc_led, panel, [m for m in SCHEME_METRICS if m in panel.columns],
                       seasons, "z")

    pc_hist = _pivot(a1, ["off_rank_composite"], "pc")
    pc_hist = pc_hist.merge(
        _pivot(a2, [f"z_{m}" for m in Z_METRICS if f"z_{m}" in panel.columns], "pc")
        .drop(columns=["pc_prior_games"]), on=["person_id", "season"], how="outer")
    pc_hist = pc_hist.merge(
        _pivot(a4, [m for m in SCHEME_METRICS if m in panel.columns], "pc")
        .drop(columns=["pc_prior_games"]), on=["person_id", "season"], how="outer")
    pc_hist["pc_reliability"] = pc_hist["pc_prior_games"] / (pc_hist["pc_prior_games"] + K_SHRINK)

    # ---- attach to (season, team): primary HC and primary PC by games
    hc_prim = hc_led.sort_values("scheduled", ascending=False).drop_duplicates(["season", "team"])
    pc_prim = pc_led.sort_values("games", ascending=False).drop_duplicates(["season", "team"])

    grid = pd.MultiIndex.from_product(
        [seasons, sorted(hc_led.team.unique())], names=["season", "team"]).to_frame(index=False)
    out = grid.merge(hc_prim[["season", "team", "person_id", "coach"]]
                     .rename(columns={"person_id": "hc_person_id", "coach": "head_coach"}),
                     on=["season", "team"], how="left")
    out = out.merge(pc_prim[["season", "team", "person_id", "actual_play_caller"]]
                    .rename(columns={"person_id": "pc_person_id"}),
                    on=["season", "team"], how="left")

    out = out.merge(hc_hist, left_on=["hc_person_id", "season"],
                    right_on=["person_id", "season"], how="left").drop(columns=["person_id"])
    out = out.merge(pc_hist, left_on=["pc_person_id", "season"],
                    right_on=["person_id", "season"], how="left").drop(columns=["person_id"])

    # ---- UNKNOWN / no-history routing (§1.2): league prior, zero reliability, flag
    out["hc_no_prior_history"] = out["hc_prior_games"].isna().astype(int)
    out["pc_no_prior_history"] = out["pc_prior_games"].isna().astype(int)
    out["pc_is_unknown"] = out["pc_person_id"].isna().astype(int)
    for c in out.columns:
        if c.endswith("_shrunk"):
            fill = PRIOR_PCT if ("win_pct" in c or "rank_composite" in c) else PRIOR_Z
            out[c] = out[c].fillna(fill)
    for c in ("hc_prior_games", "pc_prior_games", "hc_reliability", "pc_reliability"):
        out[c] = out[c].fillna(0.0)
    out["hc_prior_games_log"] = np.log1p(out["hc_prior_games"])
    out["pc_prior_games_log"] = np.log1p(out["pc_prior_games"])

    # ---- tenure + change flags (computed on the PRIMARY identity, prior seasons only)
    for pre, idcol in (("hc", "hc_person_id"), ("pc", "pc_person_id")):
        out = out.sort_values(["team", "season"])
        prev = out.groupby("team")[idcol].shift(1)
        out[f"{pre}_changed"] = np.where(out[idcol].isna() | prev.isna(), np.nan,
                                         (out[idcol] != prev).astype(float))
        ten, last, run = [], {}, {}
        for _, r in out.iterrows():
            k = (r["team"],)
            cur = r[idcol]
            if pd.isna(cur):
                ten.append(np.nan); last[k] = None; run[k] = 0; continue
            if last.get(k) == cur:
                run[k] = run.get(k, 0) + 1
            else:
                run[k] = 0
            last[k] = cur
            ten.append(run[k])
        out[f"{pre}_tenure_current_team"] = ten

    out["pc_is_head_coach"] = np.where(
        out["pc_person_id"].isna(), np.nan,
        (out["pc_person_id"] == out["hc_person_id"]).astype(float))

    out = out.sort_values(["season", "team"]).reset_index(drop=True)
    out.to_csv(DATA / "coach_features.csv", index=False)

    print(f"\ncoach features: {out.shape[0]} team-seasons x {out.shape[1]} cols")
    print(f"  PC unknown (league-prior routed): {int(out.pc_is_unknown.sum())} "
          f"({100*out.pc_is_unknown.mean():.1f}%)")
    print(f"  PC no prior history            : {int(out.pc_no_prior_history.sum())}")
    print(f"  HC no prior history            : {int(out.hc_no_prior_history.sum())}")
    print("\nSANITY — 2026 Chargers / Rams:")
    show = ["season", "team", "head_coach", "actual_play_caller", "hc_changed", "pc_changed",
            "pc_prior_games", "pc_reliability", "pc_career_off_rank_composite_shrunk",
            "pc_no_prior_history"]
    print(out[(out.season == 2026) & (out.team.isin(["LAC", "LA"]))][show].to_string(index=False))
    print("\nSANITY — highest career play-caller rank composite entering 2026:")
    top = out[out.season == 2026].nlargest(6, "pc_career_off_rank_composite_shrunk")
    print(top[["team", "actual_play_caller", "pc_prior_games",
               "pc_career_off_rank_composite_shrunk"]].to_string(index=False))
    print(f"\nwrote {DATA/'coach_features.csv'}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    else:
        raise SystemExit("pass --build")
