"""Build the NFL WR Talent Score — SPEC R39 (RATIFIED-2026-07-27).

Emits `nfl_wr_score_2026.csv`. Ratified weights SHIPPED UNCHANGED — route block 40% nominal,
archetype block (contested + deep) 17.5% nominal. Alternatives were measured and rejected.

Pool: qualified WRs, >= 250 routes across the window; per-season z on a >= 150-route reference.

TWO DISCLOSED CONFOUNDS — two of nine facets measure situation as much as player:
  * `deep_explosive` (mean EPA on targets with air_yards >= 20) carries the QB confound —
    deep-ball production depends heavily on who is throwing.
  * `avg_separation` carries the slot/scheme confound — alignment buys separation, not skill.

DENOMINATOR LIMIT — the archetype facets cannot be rescued by weight. Contested targets run
~16.5/season and deep targets ~15.6 against ~532 routes, so contested lands at r = 0.219 (the WR
analog of the QB side's pressure_grades_pass at 0.231). The block delivers **12.6% effective
against 17.5% nominal**, and DOUBLING contested weight moves Mike Evans the WRONG way
(76.9 -> 76.5) because the weight comes out of route facets he is above average on.

Stage 5 gate is CAREER NFL seasons <= 3. College_WR is dead across six instrument classes; EB
drove its median contribution to **0.070** among blended players on its own — no k_lambda defect.

Run:  python fantasy/talent/build_nfl_wr_score.py     (needs network for nflverse feeds)
Read-only on every other artifact.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import nflreadpy as nfl

import hashlib, json

HERE = Path(__file__).resolve().parent
SEAS = HERE.parent / "seasonal_projections"
PFF = SEAS / "pff"
XWALK = SEAS / "snapshots" / "players.parquet"
COLLEGE = HERE / "college_wr_score_2026.csv"
OUT = HERE / "nfl_wr_score_2026.csv"
PROV = HERE / "nfl_wr_score_2026.provenance.json"

T, GAMMA = 2025, 0.55
SEASONS = [T - 2, T - 1, T]
Z_ROUTE_FLOOR, POOL_ROUTES = 150, 250
CAREER_MAX = 3
ANCHOR = dict(lo_pct=5, hi_pct=98, lo_score=52, hi_score=95, clip=(50, 99))

W = {"yprr": .200, "grades_pass_route": .200, "deep_explosive": .090,
     "receiving_EPA_target": .085, "avg_separation": .085, "contested_catch_rate": .085,
     "drop_rate": .085, "YAC_over_expected": .085, "MTF_rec": .085}
SIGN = {"drop_rate": -1}
DEN = {"yprr": "routes", "grades_pass_route": "routes", "receiving_EPA_target": "targets",
       "drop_rate": "targets", "avg_separation": "targets", "YAC_over_expected": "receptions",
       "MTF_rec": "receptions", "contested_catch_rate": "contested_targets",
       "deep_explosive": "deep_targets"}

def build():
    """Run the build and write the artifact + provenance JSON.

    Everything below lives in here so that IMPORTING this module is side-effect free —
    the tests read the ratified constants above, and an import must never fetch data,
    burn network, or rewrite a shipped artifact.
    """
    xw = pd.read_parquet(XWALK).dropna(subset=["pff_id", "gsis_id"]).copy()
    xw["pff_id"] = xw["pff_id"].astype(str).astype(float).astype("Int64")
    p2g = xw.set_index("pff_id")["gsis_id"].to_dict()

    ngs = nfl.load_nextgen_stats(seasons=SEASONS, stat_type="receiving").to_pandas()
    ngs = ngs[ngs.week == 0] if (ngs.week == 0).any() else ngs
    ngs_i = ngs.set_index(["season", "player_gsis_id"])

    pbp = nfl.load_pbp(seasons=SEASONS).to_pandas()
    tg = pbp[(pbp.pass_attempt == 1) & pbp.receiver_player_id.notna() & pbp.epa.notna()]
    rec_epa = tg.groupby(["season", "receiver_player_id"]).epa.mean()
    deep = tg[tg.air_yards >= 20]
    deep_epa = deep.groupby(["season", "receiver_player_id"]).agg(v=("epa", "mean"), n=("epa", "size"))

    rows = []
    for s in SEASONS:
        d = pd.read_csv(PFF / f"nfl_{s}" / f"nfl_receiving_summary_{s}.csv")
        d = d[(d.position == "WR") & (d.routes >= Z_ROUTE_FLOOR)].copy()
        d = d.sort_values("routes", ascending=False).drop_duplicates("player_id")
        d["MTF_rec"] = d["avoided_tackles"] / d["receptions"].replace(0, np.nan)
        d["gsis"] = d.player_id.map(p2g)
        d["receiving_EPA_target"] = d.gsis.map(rec_epa.loc[s] if s in rec_epa.index.get_level_values(0)
                                               else pd.Series(dtype=float))
        de = deep_epa.loc[s] if s in deep_epa.index.get_level_values(0) else pd.DataFrame()
        d["deep_explosive"] = d.gsis.map(de["v"]) if len(de) else np.nan
        d["deep_targets"] = d.gsis.map(de["n"]) if len(de) else np.nan
        for col, src in (("avg_separation", "avg_separation"),
                         ("YAC_over_expected", "avg_yac_above_expectation")):
            try:
                d[col] = d.gsis.map(ngs_i.loc[s][src])
            except Exception:
                d[col] = np.nan
        for f in W:
            if f not in d.columns:
                continue
            x = pd.to_numeric(d[f], errors="coerce")
            if x.isna().all():
                continue
            z = SIGN.get(f, 1) * (x - x.mean()) / x.std(ddof=1)
            n = pd.to_numeric(d[DEN[f]], errors="coerce")
            for i in d.index:
                if pd.isna(z.get(i)) or pd.isna(n.get(i)) or n.get(i) <= 0:
                    continue
                rows.append(dict(season=s, pff_id=d.player_id[i], gsis=d.gsis[i], player=d.player[i],
                                 team=d.team_name[i], facet=f, z=float(z[i]), n=float(n[i]),
                                 routes=float(d.routes[i])))

    panel = pd.DataFrame(rows)
    panel["w"] = panel.n * GAMMA ** (T - panel.season)
    rt = panel[panel.facet == "yprr"].groupby("pff_id").routes.sum()
    pool = set(rt[rt >= POOL_ROUTES].index)
    print(f"WR panel: {panel.pff_id.nunique()} receivers with a >={Z_ROUTE_FLOOR}-route season")
    print(f"qualified pool (>= {POOL_ROUTES} routes in window): {len(pool)}")

    K = {}
    for f in W:
        sub = panel[(panel.facet == f) & panel.pff_id.isin(pool)]
        multi = sub.groupby("pff_id").filter(lambda g: len(g) >= 2)
        if len(multi) < 20:
            K[f] = np.nan; continue
        parts = []
        for _p, g in multi.groupby("pff_id"):
            m, sc = g.z.mean(), len(g) / (len(g) - 1)
            parts.extend(((g.z - m) ** 2 * g.n * sc).tolist())
        s2e = float(np.mean(parts))
        pm = multi.groupby("pff_id").apply(lambda g: np.average(g.z, weights=g.n), include_groups=False)
        mn = float(multi.groupby("pff_id").n.sum().mean())
        K[f] = s2e / max(float(pm.var(ddof=1)) - s2e / mn, 1e-6)

    print("\n=== k VECTOR (BEFORE the anchors — Joseph's flag 1) ===")
    print(f"{'facet':24s}{'denominator':>18s}{'k':>9s}{'med N_eff':>11s}{'r':>8s}")
    for f in W:
        ne = panel[(panel.facet == f) & panel.pff_id.isin(pool)].groupby("pff_id").w.sum().median()
        print(f"{f:24s}{DEN[f]:>18s}{K[f]:9.0f}{ne:11.1f}{ne/(ne+K[f]):8.3f}")

    out = []
    for pid, g in panel[panel.pff_id.isin(pool)].groupby("pff_id"):
        last = g.sort_values("season").iloc[-1]
        row = {"pff_id": pid, "gsis": last.gsis, "player": last.player, "team": last.team}
        num = den = 0.0
        for f, wt in W.items():
            sub = g[(g.facet == f) & (g.w > 0)]
            if sub.empty:
                continue
            zbar, ne = float(np.average(sub.z, weights=sub.w)), float(sub.w.sum())
            r = ne / (ne + K[f]) if np.isfinite(K[f]) else .5
            row[f"z_{f}"], row[f"neff_{f}"], row[f"r_{f}"] = round(zbar, 4), round(ne, 1), round(r, 4)
            num += wt * np.sqrt(r) * zbar; den += wt
        if den == 0:
            continue
        row["NFL_WR"] = num / den
        row["weight_covered"] = round(den, 3)
        row["N_career"] = float(g[g.facet == "yprr"].n.sum())
        out.append(row)
    N = pd.DataFrame(out)

    eff = {f: W[f] * np.sqrt(N[f"r_{f}"].median()) for f in W if f"r_{f}" in N}
    tot = sum(eff.values())
    print("\n=== NOMINAL vs EFFECTIVE ===")
    for f in W:
        print(f"  {f:24s} nominal {W[f]:.3f}   effective {eff[f]/tot:.3f}")
    print(f"  route block (yprr+route) nominal {W['yprr']+W['grades_pass_route']:.3f} -> "
          f"effective {(eff['yprr']+eff['grades_pass_route'])/tot:.3f}")
    print(f"  archetype block (contested+deep) nominal "
          f"{W['contested_catch_rate']+W['deep_explosive']:.3f} -> effective "
          f"{(eff['contested_catch_rate']+eff['deep_explosive'])/tot:.3f}")

    ids = nfl.load_players().to_pandas()
    fc = "rookie_season" if "rookie_season" in ids.columns else "draft_year"
    fm = ids.dropna(subset=[fc]).set_index("gsis_id")[fc].to_dict()
    N["nfl_seasons"] = T - N.gsis.map(fm) + 1
    kl = float(N[N.nfl_seasons > 3].N_career.median()) * .05 / .95
    N["lambda"] = N.N_career / (N.N_career + kl)
    N["blend"] = N.nfl_seasons.le(CAREER_MAX).fillna(False)
    N.loc[~N.blend, "lambda"] = 1.0
    col = pd.read_csv(COLLEGE).dropna(subset=["gsis_id"])
    N["college_wr"] = N.gsis.map(col.set_index("gsis_id")["college_wr"])
    N["Talent_WR"] = np.where(N.blend & N.college_wr.notna(),
                              N["lambda"] * N.NFL_WR + (1 - N["lambda"]) * N.college_wr, N.NFL_WR)
    bl = N[N.blend & N.college_wr.notna()]
    print(f"\nk_lambda {kl:.1f} | blended {len(bl)} of {len(N)} | "
          f"median college WEIGHT (1-lambda) among blended = {(1 - bl['lambda']).median():.4f}")
    print("  (College_WR is dead across six instrument classes — EB should drive this toward ~0)")

    z2, z98 = np.percentile(N.Talent_WR, [5, 98])
    B = (95 - 52) / (z98 - z2); a = 52 - B * z2
    N["score"] = (a + B * N.Talent_WR).clip(50, 99).round(1)

    N = N.rename(columns={"gsis": "gsis_id"})
    N["rank_wr"] = N.score.rank(method="min", ascending=False).astype(int)
    keep = ["pff_id", "gsis_id", "player", "team", "nfl_seasons", "blend", "lambda",
            "NFL_WR", "college_wr", "Talent_WR", "score", "rank_wr", "N_career", "weight_covered"]
    keep += [c for c in N.columns if c.startswith(("z_", "neff_", "r_"))]
    N = N[[c for c in keep if c in N.columns]].sort_values("score", ascending=False)
    N.to_csv(OUT, index=False)
    PROV.write_text(json.dumps({
        "spec": "R39 (RATIFIED-2026-07-27)", "built": "2026-07-27",
        "gamma": GAMMA, "window": SEASONS, "z_route_floor": Z_ROUTE_FLOOR,
        "qualified_pool_routes": POOL_ROUTES, "weights": W,
        "mom_k": {f: round(float(K[f]), 1) for f in W},
        "effective_weights": {f: round(eff[f] / tot, 4) for f in W},
        # COMPUTED from W, never transcribed — a hardcoded block weight silently survives a
        # weight change and gets copied into sibling builds (it did, into the TE one).
        "route_block": {"nominal": round(W["yprr"] + W["grades_pass_route"], 4),
                        "effective": round((eff["yprr"] + eff["grades_pass_route"]) / tot, 4)},
        "archetype_block": {"nominal": round(W["contested_catch_rate"] + W["deep_explosive"], 4),
                            "effective": round((eff["contested_catch_rate"] + eff["deep_explosive"]) / tot, 4)},
        "k_lambda": round(float(kl), 2), "career_gate_max_seasons": CAREER_MAX,
        "median_college_weight_among_blended": round(float((1 - bl["lambda"]).median()), 4),
        "confounded_facets": {"deep_explosive": "QB dependency",
                              "avg_separation": "slot/scheme alignment"},
        "deep_explosive_construction": "mean EPA per target with air_yards >= 20",
        "anchor": {**ANCHOR, "fitted_on": "qualified WR pool", "n": int(len(N))},
        "rows": int(len(N)), "blended": int(N.blend.sum()),
        "md5": hashlib.md5(OUT.read_bytes()).hexdigest(),
    }, indent=2), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(N)} WRs | md5 {json.loads(PROV.read_text())['md5']}")

if __name__ == "__main__":
    build()
