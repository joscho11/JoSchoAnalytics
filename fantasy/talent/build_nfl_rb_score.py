"""Build the NFL RB Talent Score — SPEC R37 (RATIFIED-2026-07-27).

Emits `nfl_rb_score_2026.csv`. Shipped with the RATIFIED weights unchanged (60 rush / 40
receive nominal). A reliability-driven alternative ("P1") was measured and recorded in SPEC but
NOT applied, at Joseph's direction.

Pool: qualified RBs, >= 100 carries across the 3-season window; per-season z uses a >= 40-carry
reference. Display 0-100 anchored WITHIN that pool, clip [50, 99].

VOLUME DISCIPLINE. Every facet is a rate or a grade — touches, snap share, red-zone share, total
yards/TDs, yards-before-contact and top speed are excluded by design. Volume still enters through
two channels, deliberately: the within-player season weight (n_s) and the Stage-3 reliability
(corr(carries, sqrt(r)) = +0.91). Net corr(carries, score) = +0.15. ONE facet carries a genuine
volume signature — `grades_run` at corr +0.47 with carries, since PFF run grades rise with
workload; it INFLATES high-volume backs.

SUBSTITUTION: `success_over_expected` has no source (NGS carries RYOE and `efficiency`, no
expected-success model). PBP rush SUCCESS RATE is used in its place.

Stage 5 gate is CAREER NFL seasons <= 3, never window volume — an injured or part-season veteran
must not be scored on college tape. College_RB input is the R36 index, which fired rc +0.329
(DEAD, < .35 band); the blend is DESCRIPTIVE and must not be labelled validated.

Run:  python fantasy/talent/build_nfl_rb_score.py     (needs network for nflverse feeds)
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
COLLEGE = HERE / "college_rb_score_2026.csv"
OUT = HERE / "nfl_rb_score_2026.csv"
PROV = HERE / "nfl_rb_score_2026.provenance.json"

T, GAMMA = 2025, 0.55
SEASONS = [T - 2, T - 1, T]
ATT_Z_FLOOR, POOL_CARRIES = 40, 100        # per-season z reference; qualified pool over window
CAREER_MAX = 3
ANCHOR = dict(lo_pct=5, hi_pct=98, lo_score=52, hi_score=95, clip=(50, 99))

RUSH = {"grades_run": .100, "RYOE": .100, "yco_attempt": .100, "MTF_rush": .100,
        "success_rate": .075, "breakaway_pct": .075, "EPA_rush": .050}
RECV = {"grades_pass_route": .125, "yprr": .100, "receiving_EPA_target": .100,
        "YAC_reception": .050, "drop_rate": .025}
W = {**RUSH, **RECV}
SIGN = {"drop_rate": -1}
DEN = {"grades_run": "att", "RYOE": "att", "yco_attempt": "att", "MTF_rush": "att",
       "success_rate": "att", "breakaway_pct": "att", "EPA_rush": "att",
       "grades_pass_route": "routes", "yprr": "routes",
       "receiving_EPA_target": "targets", "drop_rate": "targets", "YAC_reception": "receptions"}

def build():
    """Run the build and write the artifact + provenance JSON.

    Everything below lives in here so that IMPORTING this module is side-effect free —
    the tests read the ratified constants above, and an import must never fetch data,
    burn network, or rewrite a shipped artifact.
    """
    xw = pd.read_parquet(XWALK).dropna(subset=["pff_id", "gsis_id"]).copy()
    xw["pff_id"] = xw["pff_id"].astype(str).astype(float).astype("Int64")
    p2g = xw.set_index("pff_id")["gsis_id"].to_dict()

    ngs = nfl.load_nextgen_stats(seasons=SEASONS, stat_type="rushing").to_pandas()
    ngs = ngs[(ngs.week == 0)] if (ngs.week == 0).any() else ngs
    ryoe = ngs.groupby(["season", "player_gsis_id"])["rush_yards_over_expected_per_att"].mean()

    pbp = nfl.load_pbp(seasons=SEASONS).to_pandas()
    ru = pbp[(pbp.rush_attempt == 1) & pbp.rusher_player_id.notna() & pbp.epa.notna()]
    rush_pbp = ru.groupby(["season", "rusher_player_id"]).agg(
        EPA_rush=("epa", "mean"), success_rate=("success", "mean"), n=("epa", "size"))
    rc = pbp[(pbp.pass_attempt == 1) & pbp.receiver_player_id.notna() & pbp.epa.notna()]
    recv_pbp = rc.groupby(["season", "receiver_player_id"]).agg(
        receiving_EPA_target=("epa", "mean"), n=("epa", "size"))

    rows = []
    for s in SEASONS:
        r = pd.read_csv(PFF / f"nfl_{s}" / f"nfl_rushing_summary_{s}.csv")
        r = r[r.position.isin(["HB", "RB", "FB"])].copy()
        r = r[r.attempts >= ATT_Z_FLOOR]
        r = r.sort_values("attempts", ascending=False).drop_duplicates("player_id")
        r = r.rename(columns={"attempts": "att", "elu_yco": "_eluyco",
                              "elu_rush_mtf": "MTF_rush", "breakaway_percent": "breakaway_pct"})
        r["MTF_rush"] = r["MTF_rush"] / r["att"].replace(0, np.nan)
        # the rushing table ALSO carries routes/targets/receptions/yprr/grades_pass_route; the
        # RECEIVING table is the one of record for those, so drop the rushing copies before merging
        r = r.drop(columns=["grades_pass_route", "receptions", "routes", "targets", "yprr",
                            "yards_after_catch_per_reception", "drop_rate"], errors="ignore")
        c = pd.read_csv(PFF / f"nfl_{s}" / f"nfl_receiving_summary_{s}.csv")
        c = c.sort_values("routes", ascending=False).drop_duplicates("player_id")
        c = c.rename(columns={"yards_after_catch_per_reception": "YAC_reception"})
        r = r.merge(c[["player_id", "routes", "targets", "receptions", "grades_pass_route",
                       "yprr", "YAC_reception", "drop_rate"]], on="player_id", how="left")
        r["gsis"] = r.player_id.map(p2g)
        r["RYOE"] = r.gsis.map(ryoe.loc[s] if s in ryoe.index.get_level_values(0)
                               else pd.Series(dtype=float))
        rp = rush_pbp.loc[s] if s in rush_pbp.index.get_level_values(0) else pd.DataFrame()
        cp = recv_pbp.loc[s] if s in recv_pbp.index.get_level_values(0) else pd.DataFrame()
        for col in ("EPA_rush", "success_rate"):
            r[col] = r.gsis.map(rp[col]) if len(rp) else np.nan
        r["receiving_EPA_target"] = r.gsis.map(cp["receiving_EPA_target"]) if len(cp) else np.nan
        for f in W:
            if f not in r.columns:
                continue
            x = pd.to_numeric(r[f], errors="coerce")
            if x.isna().all():
                continue
            z = SIGN.get(f, 1) * (x - x.mean()) / x.std(ddof=1)
            n = pd.to_numeric(r[DEN[f]], errors="coerce")
            for i in r.index:
                # A facet with no denominator carries no information about the player. Skip it
                # here, as the WR/TE builds do, rather than emitting n=NaN and relying on the
                # downstream `w > 0` filter — note `float(NaN or 0)` is NaN, not 0, because NaN
                # is truthy. Provably output-identical; the guard is for the next reader.
                if pd.isna(z.get(i)) or pd.isna(n.get(i)) or n.get(i) <= 0:
                    continue
                rows.append(dict(season=s, pff_id=r.player_id[i], gsis=r.gsis[i],
                                 player=r.player[i], team=r.team_name[i], facet=f,
                                 z=float(z[i]), n=float(n[i]), att=float(r.att[i])))

    panel = pd.DataFrame(rows)
    panel["w"] = panel.n * GAMMA ** (T - panel.season)
    carries = panel[panel.facet == "grades_run"].groupby("pff_id").att.sum()
    pool = set(carries[carries >= POOL_CARRIES].index)
    print(f"RB panel: {panel.pff_id.nunique()} backs with a >={ATT_Z_FLOOR}-carry season {SEASONS[0]}-{SEASONS[-1]}")
    print(f"qualified pool (>= {POOL_CARRIES} carries in window): {len(pool)}")

    K = {}
    for f in W:
        sub = panel[(panel.facet == f) & panel.pff_id.isin(pool) & (panel.n > 0)]
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

    print("\n=== k VECTOR (printed BEFORE the anchors) ===")
    print(f"{'facet':24s}{'den':>10s}{'k':>10s}{'med N_eff':>11s}{'r':>8s}")
    for f in W:
        ne = panel[(panel.facet == f) & panel.pff_id.isin(pool)].groupby("pff_id").w.sum().median()
        r_ = ne / (ne + K[f]) if np.isfinite(K[f]) else np.nan
        print(f"{f:24s}{DEN[f]:>10s}{K[f]:10.0f}{ne:11.1f}{r_:8.3f}")

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
            r_ = ne / (ne + K[f]) if np.isfinite(K[f]) else .5
            row[f"z_{f}"], row[f"neff_{f}"], row[f"r_{f}"] = round(zbar, 4), round(ne, 1), round(r_, 4)
            num += wt * np.sqrt(r_) * zbar; den += wt
        if den == 0:
            continue
        row["NFL_RB"] = num / den
        row["N_career"] = float(g[g.facet == "grades_run"].n.sum())
        out.append(row)
    N = pd.DataFrame(out)

    eff = {f: W[f] * np.sqrt(N[f"r_{f}"].median()) for f in W if f"r_{f}" in N}
    tot = sum(eff.values())
    print("\n=== NOMINAL vs EFFECTIVE WEIGHTS (before the anchors) ===")
    rn = sum(eff[f] for f in RUSH if f in eff) / tot
    rcv = sum(eff[f] for f in RECV if f in eff) / tot
    print(f"  nominal RUSH {sum(RUSH.values())*100:.0f} / RECEIVE {sum(RECV.values())*100:.0f}"
          f"   ->   EFFECTIVE {rn*100:.0f} / {rcv*100:.0f}")

    ids = nfl.load_players().to_pandas()
    fc = "rookie_season" if "rookie_season" in ids.columns else "draft_year"
    fm = ids.dropna(subset=[fc]).set_index("gsis_id")[fc].to_dict()
    N["nfl_seasons"] = T - N.gsis.map(fm) + 1
    kl = float(N[N.nfl_seasons > 3].N_career.median()) * (1 - .95) / .95
    N["lambda"] = N.N_career / (N.N_career + kl)
    N["blend"] = N.nfl_seasons.le(CAREER_MAX).fillna(False)
    N.loc[~N.blend, "lambda"] = 1.0
    col = pd.read_csv(COLLEGE).dropna(subset=["gsis_id"])
    N["college_rb"] = N.gsis.map(col.set_index("gsis_id")["college_rb"])
    N["Talent_RB"] = np.where(N.blend & N.college_rb.notna(),
                              N["lambda"] * N.NFL_RB + (1 - N["lambda"]) * N.college_rb, N.NFL_RB)
    z2, z98 = np.percentile(N.Talent_RB, [5, 98])
    B = (95 - 52) / (z98 - z2); a = 52 - B * z2
    N["score"] = (a + B * N.Talent_RB).clip(50, 99).round(1)

    N["rank_rb"] = N.score.rank(method="min", ascending=False).astype(int)
    N = N.rename(columns={"gsis": "gsis_id"})
    keep = ["pff_id", "gsis_id", "player", "team", "nfl_seasons", "blend", "lambda",
            "NFL_RB", "college_rb", "Talent_RB", "score", "rank_rb", "N_career"]
    keep += [c for c in N.columns if c.startswith(("z_", "neff_", "r_"))]
    N = N[[c for c in keep if c in N.columns]].sort_values("score", ascending=False)
    N.to_csv(OUT, index=False)
    PROV.write_text(json.dumps({
        "spec": "R37 (RATIFIED-2026-07-27)", "built": "2026-07-27",
        "gamma": GAMMA, "window": SEASONS, "z_reference_carry_floor": ATT_Z_FLOOR,
        "qualified_pool_carries": POOL_CARRIES, "weights": W,
        "nominal_split": {"rush": round(sum(RUSH.values()), 3), "receive": round(sum(RECV.values()), 3)},
        "effective_split": {"rush": round(rn, 3), "receive": round(rcv, 3)},
        "mom_k": {f: round(float(K[f]), 1) for f in W},
        "k_lambda": round(float(kl), 2), "career_gate_max_seasons": CAREER_MAX,
        "substitution": "success_over_expected -> PBP rush success rate (no expected-success model)",
        "college_blend_input": "R36 college_rb (rc +0.329 DEAD) — descriptive, not validated",
        "anchor": {**ANCHOR, "fitted_on": "qualified RB pool", "n": int(len(N))},
        "rows": int(len(N)), "blended": int(N.blend.sum()),
        "md5": hashlib.md5(OUT.read_bytes()).hexdigest(),
    }, indent=2), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(N)} RBs | md5 {json.loads(PROV.read_text())['md5']}")

if __name__ == "__main__":
    build()
