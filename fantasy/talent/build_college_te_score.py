"""Build the College TE Talent Score — SPEC R40 (RATIFIED-2026-07-27).

Emits `college_te_score_2026.csv`. gamma = 0.6. Weights sum 1.000.
`yardshare`, `dominator` and any target-share term are DELIBERATELY ABSENT (opportunity confounds).

Display anchored on TEs who REACHED THE NFL (318 of 1,101), standardised on qualified FBS TEs
with the rank displayed within that reached-NFL pool.

FRAMING (carried from Joseph): TE fired at +0.294 (grade+share+age) and +0.326 (richer) — both
DEAD. These anchors test only whether the score DESCRIBES college TE talent. A high score for a
future bust is the construct working, not failing.

TWO DISCLOSED DEFECTS, shipped knowingly:
  1. `contested_catch_rate` is functionally absent: it delivers ~3.0% EFFECTIVE against its .065
     nominal (r = 0.100 on a median SEVEN contested targets — the lowest reliability of any facet
     across the five builds). Raising it does NOT fix its own anchors: the rescaled players are
     structurally immune, and Hunter Henry gets WORSE (94.8 -> 97.5 -> 99.0) because pulling
     weight out of route renormalises his remaining facets over a smaller base. Measured, rejected.
  2. The missing-contested omit-and-rescale path affects a large minority of the panel, so the
     composite's facet set varies by row — those players are scored on five facets, not six.
     `weight_covered` records it per row and the provenance JSON counts them.

The route-craft block therefore runs ~77% effective against 68.5% nominal.

SUBSTITUTION: no `catchable_targets` column exists; `grades_hands_drop` uses `targets`.
TE is the THINNEST panel of the four college indices; route floor lowered to 100.

Run:  python fantasy/talent/build_college_te_score.py
Read-only on every other artifact.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import hashlib, json, sys

HERE = Path(__file__).resolve().parent
SEAS = HERE.parent / "seasonal_projections"
PFF = SEAS / "pff"
XWALK = SEAS / "snapshots" / "players.parquet"
DATASET = SEAS / "season_dataset_2014_2026.csv"
OUT = HERE / "college_te_score_2026.csv"
PROV = HERE / "college_te_score_2026.provenance.json"
sys.path.insert(0, str(SEAS))
from _utils import norm_name  # noqa: E402
GAMMA, ROUTE_FLOOR, YEARS = 0.6, 100, range(2014, 2026)
ANCHOR = dict(lo_pct=5, hi_pct=98, lo_score=52, hi_score=95, clip=(50, 99))

W = {"grades_pass_route": .435, "yprr": .250, "avoided_tackles_rec": .100,
     "grades_hands_drop": .075, "yac_per_reception": .075, "contested_catch_rate": .065}
DEN = {"grades_pass_route": "routes", "yprr": "routes", "contested_catch_rate": "contested_targets",
       "avoided_tackles_rec": "receptions", "grades_hands_drop": "targets",
       "yac_per_reception": "receptions"}


def _p(kind, y):
    a = PFF / f"college_{y}" / f"college_{kind}_{y}.csv"
    return a if a.exists() else PFF / f"college_{y}" / f"{kind}.csv"


def season(y):
    d = pd.read_csv(_p("receiving_summary", y))
    d = d[d.position.isin(["TE"])].copy()
    d = d[d.routes >= ROUTE_FLOOR]
    d = d.sort_values("routes", ascending=False).drop_duplicates("player_id")
    d["avoided_tackles_rec"] = d["avoided_tackles"] / d["receptions"].replace(0, np.nan)
    d["yac_per_reception"] = d["yards_after_catch_per_reception"]
    d["season"] = y
    return d


def build():
    """Run the build and write the artifact + provenance JSON.

    Everything below lives in here so that IMPORTING this module is side-effect free —
    the tests read the ratified constants above, and an import must never fetch data,
    burn network, or rewrite a shipped artifact.
    """
    panel = pd.concat([season(y) for y in YEARS], ignore_index=True)
    print(f"college TE player-seasons (>= {ROUTE_FLOOR} routes, 2014-2025): {len(panel):,}")
    miss = panel["contested_targets"].fillna(0).eq(0).sum()
    print(f"  player-seasons with ZERO contested targets: {miss} -> omit-and-rescale path")

    for f in W:
        panel[f"z_{f}"] = np.nan
    for _y, g in panel.groupby("season"):
        for f in W:
            x = pd.to_numeric(g[f], errors="coerce")
            panel.loc[g.index, f"z_{f}"] = (x - x.mean()) / x.std(ddof=1)


    def mom_k(f):
        d = DEN[f]
        sub = panel[["player_id", f"z_{f}", d]].dropna()
        sub = sub[sub[d] > 0]
        multi = sub.groupby("player_id").filter(lambda g: len(g) >= 2)
        if len(multi) < 40:
            return np.nan
        parts = []
        for _pid, g in multi.groupby("player_id"):
            m, sc = g[f"z_{f}"].mean(), len(g) / (len(g) - 1)
            parts.extend(((g[f"z_{f}"] - m) ** 2 * g[d] * sc).tolist())
        s2e = float(np.mean(parts))
        pm = multi.groupby("player_id").apply(lambda g: np.average(g[f"z_{f}"], weights=g[d]),
                                              include_groups=False)
        mn = float(multi.groupby("player_id")[d].sum().mean())
        return s2e / max(float(pm.var(ddof=1)) - s2e / mn, 1e-6)


    K = {f: mom_k(f) for f in W}
    print("\n=== k VECTOR (before the anchors) ===")
    print(f"{'facet':24s}{'den':>18s}{'k':>9s}{'med N_eff':>11s}{'r':>8s}")
    for f in W:
        ne = panel[panel[DEN[f]].fillna(0) > 0].groupby("player_id")[DEN[f]].sum().median()
        print(f"{f:24s}{DEN[f]:>18s}{K[f]:9.0f}{ne:11.1f}{ne/(ne+K[f]):8.3f}")

    rows = []
    for pid, g in panel.groupby("player_id"):
        F = int(g.season.max())
        g = g.copy(); g["decay"] = GAMMA ** (F - g.season)
        last = g.loc[g.season.idxmax()]
        row = {"player_id": pid, "player": last["player"], "college": last["team_name"],
               "final_season": F, "seasons": len(g)}
        num = den = 0.0
        for f, wt in W.items():
            z = pd.to_numeric(g[f"z_{f}"], errors="coerce")
            n = pd.to_numeric(g[DEN[f]], errors="coerce")
            ok = (z.notna() & n.notna() & (n > 0)).to_numpy()
            if not ok.any():
                continue                      # omit-and-rescale (the missing-contested rule)
            w = n.to_numpy()[ok] * g["decay"].to_numpy()[ok]
            zbar = float(np.average(z.to_numpy()[ok], weights=w)); ne = float(w.sum())
            r = ne / (ne + K[f]) if np.isfinite(K[f]) else .5
            row[f"z_{f}"], row[f"neff_{f}"], row[f"r_{f}"] = round(zbar, 4), round(ne, 1), round(r, 4)
            num += wt * np.sqrt(r) * zbar; den += wt
        if den == 0:
            continue
        row["weight_covered"] = round(den, 3)
        row["college_te"] = num / den
        rows.append(row)

    C = pd.DataFrame(rows)
    print(f"\nscored {len(C):,} TEs | rescaled for missing contested: "
          f"{int((C.weight_covered < 0.999).sum())}")

    eff = {f: W[f] * np.sqrt(C[f"r_{f}"].median()) for f in W if f"r_{f}" in C}
    tot = sum(eff.values())
    print("\n=== NOMINAL vs EFFECTIVE ===")
    for f in W:
        print(f"  {f:24s} nominal {W[f]:.3f}   effective {eff[f]/tot:.3f}")
    print(f"  route-craft block (route+yprr) nominal {W['grades_pass_route']+W['yprr']:.3f} "
          f"-> effective {(eff['grades_pass_route']+eff['yprr'])/tot:.3f}")

    xw = pd.read_parquet(XWALK).dropna(subset=["pff_id", "gsis_id"]).copy()
    xw["pff_id"] = xw["pff_id"].astype(str).astype(float).astype("Int64")
    C["gsis_id"] = C.player_id.map(xw.set_index("pff_id")["gsis_id"].to_dict())
    C["drafted"] = C.gsis_id.notna()
    print(f"\npool sizes — all TEs {len(C):,} | reached NFL {int(C.drafted.sum()):,}")

    for tag, mask in (("DRAFTED-ONLY", C.drafted), ("ALL TEs", pd.Series(True, index=C.index))):
        sl = C.loc[mask, "college_te"]
        z2, z98 = np.percentile(sl, [ANCHOR["lo_pct"], ANCHOR["hi_pct"]])
        b = (ANCHOR["hi_score"] - ANCHOR["lo_score"]) / (z98 - z2)
        a = ANCHOR["lo_score"] - b * z2
        C[f"score_{tag}"] = (a + b * C.college_te).clip(*ANCHOR["clip"]).round(1)

    # ---- 2026 rookie flag via GUARDED name join (placeholder ids; no shared namespace) ----
    C["norm_name"] = C.player.map(norm_name)
    ds = pd.read_csv(DATASET, usecols=["player_id", "player", "season", "position", "is_rookie"],
                     low_memory=False)
    rk = ds[(ds.season == 2026) & (ds.position == "TE") & (ds.is_rookie == 1)].copy()
    rk["norm_name"] = rk.player.map(norm_name)
    amb = set(rk.loc[rk.norm_name.duplicated(keep=False), "norm_name"]) |       set(C.loc[C.norm_name.duplicated(keep=False), "norm_name"])
    usable = rk[~rk.norm_name.isin(amb)]
    C["nfl_player_id"] = C.norm_name.map(usable.set_index("norm_name")["player_id"].to_dict())
    C["is_2026_rookie"] = C.nfl_player_id.notna()
    C["score"] = C["score_DRAFTED-ONLY"]
    C["rank_final_season"] = C.groupby("final_season")["score"].rank(method="min",
                                                                    ascending=False).astype(int)
    cols = (["player_id", "gsis_id", "nfl_player_id", "player", "norm_name", "college",
             "final_season", "seasons", "drafted", "is_2026_rookie", "weight_covered",
             "college_te", "score", "rank_final_season"]
            + [f"z_{f}" for f in W] + [f"neff_{f}" for f in W] + [f"r_{f}" for f in W])
    C = C[[c for c in cols if c in C.columns]].sort_values(["final_season", "score"],
                                                           ascending=[False, False])
    C.to_csv(OUT, index=False)
    PROV.write_text(json.dumps({
        "spec": "R40 (RATIFIED-2026-07-27)", "built": "2026-07-27",
        "gamma": GAMMA, "route_floor": ROUTE_FLOOR, "weights": W,
        "mom_k": {f: round(float(K[f]), 1) for f in W},
        "effective_weights": {f: round(eff[f] / tot, 4) for f in W},
        "anchor": {**ANCHOR, "fitted_on": "TEs who reached the NFL",
                   "n": int(C.drafted.sum()),
                   "pool_rule": "standardize on qualified FBS TEs; rank display within reached-NFL"},
        "rows": int(len(C)), "rookies_2026": int(C.is_2026_rookie.sum()),
        "missing_contested_rescaled": int((C.weight_covered < 0.999).sum()),
        "missing_contested_rescaled_drafted": int(((C.weight_covered < 0.999) & C.drafted).sum()),
        "route_block": {"nominal": round(W["grades_pass_route"] + W["yprr"], 4),
                        "effective": round((eff["grades_pass_route"] + eff["yprr"]) / tot, 4)},
        "known_defects": [
            f"contested_catch_rate delivers {eff['contested_catch_rate'] / tot:.3f} effective "
            f"vs {W['contested_catch_rate']:.3f} nominal — functionally absent",
            "rescaled rows are scored on 5 facets, not 6 (see missing_contested_rescaled)"],
        "framing": "TE fired at +0.294 (grade+share+age) and +0.326 (richer) - both DEAD; descriptive only",
        "md5": hashlib.md5(OUT.read_bytes()).hexdigest(),
    }, indent=2), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(C):,} TEs ({int(C.drafted.sum())} reached NFL, "
          f"{int(C.is_2026_rookie.sum())} are 2026 rookies) | md5 "
          f"{json.loads(PROV.read_text())['md5']}")

if __name__ == "__main__":
    build()
