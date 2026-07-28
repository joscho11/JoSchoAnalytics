"""Build the NFL QB Talent Score — SPEC R34 (RATIFIED-2026-07-27).

Emits `nfl_qb_score_2026.csv`. Supersedes the R29 5-facet PBP QB vector as the QB talent
instrument. `talent_score_2026.csv` is NOT regenerated (Joseph's call 2026-07-27) — it keeps its
pinned md5 and its R29 QB values; the board prefers this artifact for QBs.

Pipeline (SPEC R34), with the pool lesson carried from R35:
  Stage 0  window s in {T-2, T-1, T}; w_{i,s} = n_{i,s} * gamma^(T-s), gamma = 0.55.
           SCORED POOL = qualified starters, >= 300 dropbacks across the window. Per-season z
           uses a >= 150-dropback reference so the distribution is starters, not mop-up duty.
  Stage 1  z per facet WITHIN position WITHIN season; twp_rate sign-flipped here and ONLY here
           (the composite carries it at a POSITIVE weight — R35 convention, applied once).
  Stage 2  zbar_i = weighted mean; N_eff,i = sum of weights, indexed by FACET as well as season
  Stage 3  z~_i = sqrt(r_i) * zbar_i, r_i = N_eff,i / (N_eff,i + k_i). k_i estimated ONCE from
           the POOL, per facet, in that facet's OWN denominator — never from the scored player.
  Stage 4  9-facet composite. HYBRID: 7 facets from PFF NFL, CPOE + deep_CPOE from nflverse.
  Stage 5  lambda = N_eff/(N_eff + k_blend), GATED ON CAREER NFL SEASONS <= 3. A veteran with a
           thin window (injury) keeps lambda = 1 and takes ZERO college — the window decides
           WHICH football describes him, never whether we know him at all.
  Stage 6  0-100, two-point anchor p5 -> 52 / p98 -> 95, clip [50, 99], fitted WITHIN the pool.

Run:  python fantasy/talent/build_nfl_qb_score.py     (needs network for nflverse feeds)
Read-only on every other artifact; writes only its own CSV + provenance JSON.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import nflreadpy as nfl

HERE = Path(__file__).resolve().parent
SEAS = HERE.parent / "seasonal_projections"
PFF = SEAS / "pff"
XWALK = SEAS / "snapshots" / "players.parquet"
COLLEGE = HERE / "college_qb_score_2026.csv"
OUT = HERE / "nfl_qb_score_2026.csv"
PROV = HERE / "nfl_qb_score_2026.provenance.json"

# ---- SPEC R34 ratified constants — NO CODE PATH MAY ALTER THESE ----
T, GAMMA = 2025, 0.55                     # RATIFIED-2026-07-27 (54/30/16 over three seasons)
SEASONS = [T - 2, T - 1, T]
Z_FLOOR, POOL_FLOOR = 150, 300            # per-season z reference; qualified-starter pool
CAREER_MAX = 3                            # Stage 5 career-stage gate, in NFL SEASONS
LAMBDA_TARGET = 0.95                      # a median 3-season starter sits here
ANCHOR = dict(lo_pct=5, hi_pct=98, lo_score=52, hi_score=95, clip=(50, 99))
WEIGHTS = {"grades_pass": .20, "CPOE": .10, "btt_rate": .10, "twp_rate": .10,
           "pressure_grades_pass": .10, "accuracy_pct": .05, "EPA_dropback": .05,
           "deep_CPOE": .05, "grades_run": .25}
SIGN = {"twp_rate": -1}                   # applied ONCE, here


def _nflverse_feeds():
    """CPOE and deep_CPOE — the two facets PFF does NOT carry (no NFL PFF file contains 'cpoe').
    Derived exactly as facets.py does."""
    ng = nfl.load_nextgen_stats(seasons=SEASONS, stat_type="passing").to_pandas()
    ng = ng[(ng.week != 0) & (ng.season_type == "REG")]
    cpoe = (ng.assign(num=lambda d: d.completion_percentage_above_expectation * d.attempts)
              .groupby(["season", "player_gsis_id"])
              .apply(lambda x: pd.Series({"v": x.num.sum() / x.attempts.sum(),
                                          "n": x.attempts.sum()}), include_groups=False)
              .reset_index())
    pbp = nfl.load_pbp(seasons=SEASONS).to_pandas()
    deep = pbp[(pbp.pass_attempt == 1) & (pbp.air_yards >= 20) & pbp.cpoe.notna()]
    dcp = (deep.groupby(["season", "passer_player_id"])
               .agg(v=("cpoe", "mean"), n=("cpoe", "size")).reset_index()
               .rename(columns={"passer_player_id": "player_gsis_id"}))
    return cpoe, dcp


def _panel():
    xw = pd.read_parquet(XWALK).dropna(subset=["pff_id", "gsis_id"]).copy()
    xw["pff_id"] = xw["pff_id"].astype(str).astype(float).astype("Int64")
    p2g = xw.set_index("pff_id")["gsis_id"].to_dict()
    cpoe, dcp = _nflverse_feeds()

    rows = []
    for s in SEASONS:
        p = pd.read_csv(PFF / f"nfl_{s}" / f"nfl_passing_summary_{s}.csv")
        p = p[(p.position == "QB") & (p.dropbacks >= Z_FLOOR)].copy()
        p = p.sort_values("dropbacks", ascending=False).drop_duplicates("player_id")
        p["EPA_dropback"] = p.epa / p.dropbacks
        p["accuracy_pct"] = p.accuracy_percent
        pr = pd.read_csv(PFF / f"nfl_{s}" / f"nfl_passing_pressure_{s}.csv",
                         usecols=["player_id", "pressure_grades_pass"]).set_index("player_id")
        ru = pd.read_csv(PFF / f"nfl_{s}" / f"nfl_rushing_summary_{s}.csv",
                         usecols=["player_id", "grades_run", "attempts"]).set_index("player_id")
        p = p.drop(columns=["grades_run"], errors="ignore").set_index("player_id")
        p["pressure_grades_pass"] = pr["pressure_grades_pass"].reindex(p.index)
        p["grades_run"] = ru["grades_run"].reindex(p.index)
        p["run_att"] = ru["attempts"].reindex(p.index)
        p["gsis"] = pd.Series(p.index, index=p.index).map(p2g)
        c = cpoe[cpoe.season == s].set_index("player_gsis_id")
        d = dcp[dcp.season == s].set_index("player_gsis_id")
        p["CPOE"] = p.gsis.map(c["v"]); p["n_CPOE"] = p.gsis.map(c["n"])
        p["deep_CPOE"] = p.gsis.map(d["v"]); p["n_deep_CPOE"] = p.gsis.map(d["n"])
        for f in WEIGHTS:
            n = {"grades_run": p.run_att, "CPOE": p.n_CPOE,
                 "deep_CPOE": p.n_deep_CPOE}.get(f, p.dropbacks)
            x = pd.to_numeric(p[f], errors="coerce")
            z = SIGN.get(f, 1) * (x - x.mean()) / x.std(ddof=1)
            for pid in p.index:
                if pd.isna(z.get(pid)):
                    continue
                rows.append(dict(season=s, pff_id=pid, gsis=p.gsis.get(pid),
                                 player=p.player.get(pid), team=p.team_name.get(pid), facet=f,
                                 z=float(z[pid]), n=float(n.get(pid) or 0),
                                 dropbacks=float(p.dropbacks.get(pid))))
    panel = pd.DataFrame(rows)
    panel["w"] = panel.n * GAMMA ** (T - panel.season)
    return panel


def _mom_k(panel, pool, facet):
    """k for ONE facet, from the POOL, in that facet's OWN denominator.

    Never derived from the player being scored and never shared across facets: a QB season is
    ~600 dropbacks but only ~50 designed runs, so a dropback-scaled constant would crush
    grades_run for being measured in a smaller unit rather than for being noisy.
    """
    sub = panel[(panel.facet == facet) & panel.pff_id.isin(pool) & (panel.n > 0)]
    multi = sub.groupby("pff_id").filter(lambda g: len(g) >= 2)
    if len(multi) < 20:
        return np.nan
    parts = []
    for _pid, g in multi.groupby("pff_id"):
        mean, scale = g.z.mean(), len(g) / (len(g) - 1)
        parts.extend(((g.z - mean) ** 2 * g.n * scale).tolist())
    s2_eps = float(np.mean(parts))
    per_player = multi.groupby("pff_id").apply(
        lambda g: np.average(g.z, weights=g.n), include_groups=False)
    mean_n = float(multi.groupby("pff_id").n.sum().mean())
    return s2_eps / max(float(per_player.var(ddof=1)) - s2_eps / mean_n, 1e-6)


def build():
    panel = _panel()
    db = panel[panel.facet == "grades_pass"].groupby("pff_id").dropbacks.sum()
    pool = set(db[db >= POOL_FLOOR].index)
    k = {f: _mom_k(panel, pool, f) for f in WEIGHTS}

    out = []
    for pid, g in panel[panel.pff_id.isin(pool)].groupby("pff_id"):
        last = g.sort_values("season").iloc[-1]
        row = {"pff_id": pid, "gsis_id": last.gsis, "player": last.player, "team": last.team,
               "seasons_in_window": int(g.season.nunique())}
        num = den = 0.0
        for f, weight in WEIGHTS.items():
            sub = g[(g.facet == f) & g.w.notna() & (g.w > 0)]
            if sub.empty:
                continue
            zbar, n_eff = float(np.average(sub.z, weights=sub.w)), float(sub.w.sum())
            r = n_eff / (n_eff + k[f]) if np.isfinite(k[f]) else 0.5
            row[f"z_{f}"] = round(zbar, 4)
            row[f"neff_{f}"] = round(n_eff, 1)
            num += weight * np.sqrt(r) * zbar
            den += weight
        if den == 0:
            continue
        row["nfl_qb"] = num / den
        row["N_eff"] = float(g[g.facet == "grades_pass"].w.sum())
        out.append(row)
    N = pd.DataFrame(out)

    # Stage 5 — lambda. k_blend calibrated so a median 3-season starter sits at LAMBDA_TARGET.
    # NOTE (carried open): this k is in DROPBACK units. The principled construction is an
    # NFL-vs-college variance decomposition in season-equivalents; it is a DIFFERENT object from
    # the per-facet k vector above and must never be merged with it.
    ref = N[N.seasons_in_window == 3]["N_eff"]
    n_ref = float(ref.median()) if len(ref) else float(N.N_eff.median())
    k_blend = n_ref * (1 - LAMBDA_TARGET) / LAMBDA_TARGET
    N["lambda"] = N.N_eff / (N.N_eff + k_blend)

    ids = nfl.load_players().to_pandas()
    first_col = "rookie_season" if "rookie_season" in ids.columns else "draft_year"
    first = ids.dropna(subset=[first_col]).set_index("gsis_id")[first_col].to_dict()
    N["first_nfl_season"] = N.gsis_id.map(first)
    N["nfl_seasons"] = T - N.first_nfl_season + 1
    unresolved = int(N.nfl_seasons.isna().sum())
    assert unresolved == 0, f"career length unresolved for {unresolved} QBs — gate would fail open"
    N["blend_applies"] = N.nfl_seasons.le(CAREER_MAX)
    N.loc[~N.blend_applies, "lambda"] = 1.0

    col = pd.read_csv(COLLEGE).dropna(subset=["gsis_id"])
    N["college_qb"] = N.gsis_id.map(col.set_index("gsis_id")["college_qb"])
    N["talent_qb"] = np.where(N.blend_applies & N.college_qb.notna(),
                              N["lambda"] * N.nfl_qb + (1 - N["lambda"]) * N.college_qb, N.nfl_qb)

    # Stage 6 — anchored WITHIN the qualified pool
    lo, hi = np.percentile(N.talent_qb, [ANCHOR["lo_pct"], ANCHOR["hi_pct"]])
    b = (ANCHOR["hi_score"] - ANCHOR["lo_score"]) / (hi - lo)
    a = ANCHOR["lo_score"] - b * lo
    N["score"] = (a + b * N.talent_qb).clip(*ANCHOR["clip"]).round(1)
    N["rank_qb"] = N.score.rank(method="min", ascending=False).astype(int)
    for c in ("nfl_qb", "talent_qb", "college_qb", "lambda"):
        N[c] = N[c].round(4)

    cols = (["pff_id", "gsis_id", "player", "team",
             "seasons_in_window", "nfl_seasons", "blend_applies", "nfl_qb", "college_qb",
             "lambda", "talent_qb", "score", "rank_qb", "N_eff"]
            + [f"z_{f}" for f in WEIGHTS] + [f"neff_{f}" for f in WEIGHTS])
    N = N[cols].sort_values("score", ascending=False)
    N.to_csv(OUT, index=False)

    PROV.write_text(json.dumps({
        "spec": "R34 (RATIFIED-2026-07-27)", "built": "2026-07-27",
        "gamma": GAMMA, "window": SEASONS, "z_reference_floor": Z_FLOOR,
        "qualified_pool_floor": POOL_FLOOR, "weights": WEIGHTS,
        "hybrid": {"pff": [f for f in WEIGHTS if f not in ("CPOE", "deep_CPOE")],
                   "nflverse": ["CPOE", "deep_CPOE"]},
        "mom_k": {f: round(float(v), 1) for f, v in k.items()},
        "k_blend": round(float(k_blend), 2), "k_blend_units": "dropbacks (calibrated)",
        "career_gate_max_seasons": CAREER_MAX,
        "anchor": {**ANCHOR, "fitted_on": "qualified-starter pool", "n": int(len(N)),
                   "p5_raw": round(float(lo), 6), "p98_raw": round(float(hi), 6)},
        "rows": int(len(N)), "blended": int(N.blend_applies.sum()),
        "md5": hashlib.md5(OUT.read_bytes()).hexdigest(),
    }, indent=2), encoding="utf-8")

    print(f"pool: {len(pool)} qualified starters (>= {POOL_FLOOR} dropbacks, {SEASONS[0]}-{SEASONS[-1]})")
    print("MoM k: " + " ".join(f"{f}={k[f]:.0f}" for f in WEIGHTS))
    print(f"k_blend {k_blend:.1f} | career gate: {int(N.blend_applies.sum())} of {len(N)} blended")
    print(f"anchor within pool: p5={lo:+.4f}->52  p98={hi:+.4f}->95  clip{ANCHOR['clip']}")
    print(f"wrote {OUT.name}: {len(N)} QBs | md5 {json.loads(PROV.read_text())['md5']}")
    return N


if __name__ == "__main__":
    build()
