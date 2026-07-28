"""Build the College RB Talent Score — SPEC R36 (RATIFIED-2026-07-27).

Emits `college_rb_score_2026.csv`. Weights locked 65 rush / 35 receive, age excluded.
`yardshare` (the opportunity confound that killed the original index) and `elusive_rating`
(double-counts yco + avoided) are DELIBERATELY absent.

gamma = 0.6 for RB. NOTE the deliberate difference: college QB (R35) uses gamma = 0.4.

HONEST LABEL — READ BEFORE CITING THIS ANYWHERE:
  This is the 8-facet PFF college index that fired **rc +0.329 = DEAD (< .35 band)** in
  PREREG_pff_richer_rookie_2026-07-20. The shipped RB rookie instrument is the PBP index at
  **rc +0.501 CLEAN**, and DOES-PFF-ADD was a FAIL. Where the two disagree the measured
  evidence favours PBP. This ships DESCRIPTIVELY, at Joseph's direction, and neither number
  may be cited as validation of it.

KNOWN LIMITATION — NO STRENGTH-OF-SCHEDULE ADJUSTMENT. Facets are z-scored within position
within season across ALL FBS players; a carry against Alabama and a carry against a Group of
Five defence count identically. PFF college carries no conference field. Consequence visible in
the 2026 class: nine of the top ten are UDFA or Day 3, and Group of Five backs outrank drafted
Power-conference backs. Descriptive only.

Run:  python fantasy/talent/build_college_rb_score.py
Read-only on every other artifact; writes only its own CSV + provenance JSON.
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
OUT = HERE / "college_rb_score_2026.csv"
PROV = HERE / "college_rb_score_2026.provenance.json"
sys.path.insert(0, str(SEAS))
from _utils import norm_name  # noqa: E402
GAMMA, ATT_FLOOR, YEARS = 0.6, 75, range(2014, 2026)
PENALTY_PCT = 0.10
ANCHOR = dict(lo_pct=5, hi_pct=98, lo_score=52, hi_score=95, clip=(50, 99))

RUSH = {"grades_run": .35, "yco_attempt": .10, "avoided_tackles_rush": .10, "explosive": .10}
RECV = {"grades_pass_route": .20, "yprr": .05, "yac_per_reception": .05, "avoided_tackles_rec": .05}
W = {**RUSH, **RECV}
DENOM = {"grades_run": "attempts", "yco_attempt": "attempts", "avoided_tackles_rush": "attempts",
         "explosive": "attempts", "grades_pass_route": "routes", "yprr": "routes",
         "yac_per_reception": "receptions", "avoided_tackles_rec": "receptions"}


def _p(kind, y):
    a = PFF / f"college_{y}" / f"college_{kind}_{y}.csv"
    return a if a.exists() else PFF / f"college_{y}" / f"{kind}.csv"


def season(y):
    r = pd.read_csv(_p("rushing_summary", y))
    r = r[(r.position == "HB") | (r.position == "RB")].copy()
    if r.empty:
        r = pd.read_csv(_p("rushing_summary", y)); r = r[r.position.isin(["HB", "RB", "FB"])].copy()
    r = r[r.attempts >= ATT_FLOOR]
    r = r.sort_values("attempts", ascending=False).drop_duplicates("player_id")
    r["avoided_tackles_rush"] = r["avoided_tackles"] / r["attempts"].replace(0, np.nan)
    if "explosive" not in r.columns or r["explosive"].isna().all():
        r["explosive"] = r.get("breakaway_percent")
    r["explosive_src"] = "explosive" if "explosive" in r.columns else "breakaway_percent"
    keep = ["player", "player_id", "team_name", "attempts", "grades_run", "yco_attempt",
            "avoided_tackles_rush", "explosive"]
    r = r[[c for c in keep if c in r.columns]].copy()

    c = pd.read_csv(_p("receiving_summary", y))
    c = c.sort_values("routes", ascending=False).drop_duplicates("player_id")
    c["avoided_tackles_rec"] = c["avoided_tackles"] / c["receptions"].replace(0, np.nan)
    c["yac_per_reception"] = c["yards_after_catch_per_reception"]
    c = c[["player_id", "routes", "receptions", "grades_pass_route", "yprr",
           "yac_per_reception", "avoided_tackles_rec"]]
    m = r.merge(c, on="player_id", how="left")
    m["season"] = y
    m["has_receiving"] = m["routes"].notna() & (m["routes"] > 0)
    return m


def build():
    """Run the build and write the artifact + provenance JSON.

    Everything below lives in here so that IMPORTING this module is side-effect free —
    the tests read the ratified constants above, and an import must never fetch data,
    burn network, or rewrite a shipped artifact.
    """
    panel = pd.concat([season(y) for y in YEARS], ignore_index=True)
    print(f"college RB player-seasons (>= {ATT_FLOOR} attempts, {YEARS.start}-{YEARS.stop-1}): {len(panel):,}")
    print(f"  with ANY receiving row: {int(panel.has_receiving.sum()):,} "
          f"({100*panel.has_receiving.mean():.1f}%)  -> the rest take the penalty path")

    for f in W:
        panel[f"z_{f}"] = np.nan
    for _y, g in panel.groupby("season"):
        for f in W:
            x = pd.to_numeric(g[f], errors="coerce")
            panel.loc[g.index, f"z_{f}"] = (x - x.mean()) / x.std(ddof=1)


    def mom_k(f):
        d = DENOM[f]
        sub = panel[["player_id", f"z_{f}", d]].dropna()
        sub = sub[sub[d] > 0]
        multi = sub.groupby("player_id").filter(lambda g: len(g) >= 2)
        if len(multi) < 40:
            return np.nan
        parts = []
        for _pid, g in multi.groupby("player_id"):
            m_, sc = g[f"z_{f}"].mean(), len(g) / (len(g) - 1)
            parts.extend(((g[f"z_{f}"] - m_) ** 2 * g[d] * sc).tolist())
        s2e = float(np.mean(parts))
        pm = multi.groupby("player_id").apply(lambda g: np.average(g[f"z_{f}"], weights=g[d]),
                                              include_groups=False)
        mn = float(multi.groupby("player_id")[d].sum().mean())
        return s2e / max(float(pm.var(ddof=1)) - s2e / mn, 1e-6)


    K = {f: mom_k(f) for f in W}
    print("MoM k (own denominators): " + " ".join(f"{f}={K[f]:.0f}" for f in W))

    rows = []
    for pid, g in panel.groupby("player_id"):
        F = int(g.season.max()); g = g.copy(); g["decay"] = GAMMA ** (F - g.season)
        last = g.loc[g.season.idxmax()]
        row = {"player_id": pid, "player": last["player"], "college": last["team_name"],
               "final_season": F, "seasons": len(g),
               "any_receiving": bool(g.has_receiving.any())}
        num = den = 0.0
        for f, wt in W.items():
            d = DENOM[f]
            z = pd.to_numeric(g[f"z_{f}"], errors="coerce"); n = pd.to_numeric(g[d], errors="coerce")
            ok = (z.notna() & n.notna() & (n > 0)).to_numpy()
            if not ok.any():
                continue
            w = n.to_numpy()[ok] * g["decay"].to_numpy()[ok]
            zbar = float(np.average(z.to_numpy()[ok], weights=w)); ne = float(w.sum())
            r = ne / (ne + K[f]) if np.isfinite(K[f]) else .5
            row[f"z_{f}"] = round(zbar, 4); row[f"neff_{f}"] = round(ne, 1); row[f"r_{f}"] = round(r, 4)
            num += wt * np.sqrt(r) * zbar; den += wt
        if den == 0:
            continue
        # NO receiving snaps at all -> penalty path (10th pct of the receiving block, flagged).
        # FEW receiving snaps -> the real z path above, shrunk. These are different answers.
        row["receiving_penalised"] = not row["any_receiving"]
        row["college_rb"] = num / den
        rows.append(row)

    C = pd.DataFrame(rows)
    if C.receiving_penalised.any():
        pen = np.percentile(C.loc[~C.receiving_penalised, "college_rb"], PENALTY_PCT * 100)
        C.loc[C.receiving_penalised, "college_rb"] = np.minimum(
            C.loc[C.receiving_penalised, "college_rb"], pen)
    print(f"receiving-penalty path applied to {int(C.receiving_penalised.sum())} RBs "
          f"(no receiving row at all); everyone else takes real shrunk z's")

    # ---- EFFECTIVE weights: nominal x sqrt(r), renormalised (read BEFORE the anchors) ----
    eff = {f: W[f] * np.sqrt(C[f"r_{f}"].median()) for f in W if f"r_{f}" in C}
    tot = sum(eff.values())
    print("\nNOMINAL vs EFFECTIVE weights (nominal x sqrt(median r), renormalised)")
    print(f"{'facet':24s}{'nominal':>9s}{'med r':>8s}{'effective':>11s}")
    for f in W:
        print(f"{f:24s}{W[f]:9.3f}{C[f'r_{f}'].median():8.3f}{eff[f]/tot:11.3f}")
    rn, rc = sum(eff[f] for f in RUSH) / tot, sum(eff[f] for f in RECV) / tot
    print(f"{'RUSH BLOCK':24s}{sum(RUSH.values()):9.3f}{'':>8s}{rn:11.3f}")
    print(f"{'RECEIVE BLOCK':24s}{sum(RECV.values()):9.3f}{'':>8s}{rc:11.3f}")
    print(f"  -> nominal 65/35 lands at EFFECTIVE {100*rn:.0f}/{100*rc:.0f}")

    # ---- display: ranked within DRAFTED RBs ----
    xw = pd.read_parquet(XWALK).dropna(subset=["pff_id", "gsis_id"]).copy()
    xw["pff_id"] = xw["pff_id"].astype(str).astype(float).astype("Int64")
    C["gsis_id"] = C.player_id.map(xw.set_index("pff_id")["gsis_id"].to_dict())
    C["drafted"] = C.gsis_id.notna()
    sl = C.loc[C.drafted, "college_rb"]
    z2, z98 = np.percentile(sl, [ANCHOR["lo_pct"], ANCHOR["hi_pct"]])
    B = (ANCHOR["hi_score"] - ANCHOR["lo_score"]) / (z98 - z2); a = ANCHOR["lo_score"] - B * z2
    C["score"] = (a + B * C.college_rb).clip(*ANCHOR["clip"]).round(1)
    print(f"\nanchor within DRAFTED RBs (n={int(C.drafted.sum())}): p5={z2:+.4f}->52 p98={z98:+.4f}->95")

    # ---- identity: 2026 rookie flag via GUARDED name join (placeholder ids, no shared namespace) ----
    C["norm_name"] = C.player.map(norm_name)
    ds = pd.read_csv(DATASET, usecols=["player_id", "player", "season", "position", "is_rookie"],
                     low_memory=False)
    rk = ds[(ds.season == 2026) & (ds.position == "RB") & (ds.is_rookie == 1)].copy()
    rk["norm_name"] = rk.player.map(norm_name)
    amb = set(rk.loc[rk.norm_name.duplicated(keep=False), "norm_name"]) |       set(C.loc[C.norm_name.duplicated(keep=False), "norm_name"])
    usable = rk[~rk.norm_name.isin(amb)]
    C["nfl_player_id"] = C.norm_name.map(usable.set_index("norm_name")["player_id"].to_dict())
    C["is_2026_rookie"] = C.nfl_player_id.notna()
    C["rank_final_season"] = C.groupby("final_season")["score"].rank(method="min",
                                                                    ascending=False).astype(int)
    cols = (["player_id", "gsis_id", "nfl_player_id", "player", "norm_name", "college",
             "final_season", "seasons", "drafted", "is_2026_rookie", "any_receiving",
             "receiving_penalised", "college_rb", "score", "rank_final_season"]
            + [f"z_{f}" for f in W] + [f"neff_{f}" for f in W] + [f"r_{f}" for f in W])
    C = C[[c for c in cols if c in C.columns]].sort_values(["final_season", "score"],
                                                           ascending=[False, False])
    C.to_csv(OUT, index=False)
    PROV.write_text(json.dumps({
        "spec": "R36 (RATIFIED-2026-07-27)", "built": "2026-07-27",
        "gamma": GAMMA, "attempt_floor": ATT_FLOOR, "weights": W,
        "nominal_split": {"rush": round(sum(RUSH.values()), 3), "receive": round(sum(RECV.values()), 3)},
        "effective_split": {"rush": round(rn, 3), "receive": round(rc, 3)},
        "mom_k": {f: round(float(K[f]), 1) for f in W},
        "anchor": {**ANCHOR, "fitted_on": "RBs who reached the NFL", "n": int(C.drafted.sum()),
                   "p5_raw": round(float(z2), 6), "p98_raw": round(float(z98), 6)},
        "rows": int(len(C)), "rookies_2026": int(C.is_2026_rookie.sum()),
        "instrument_band": "DEAD rc +0.329 (< .35) — ships DESCRIPTIVELY; PBP index is +0.501 CLEAN",
        "no_strength_of_schedule_adjustment": True,
        "md5": hashlib.md5(OUT.read_bytes()).hexdigest(),
    }, indent=2), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(C)} RBs ({int(C.drafted.sum())} reached NFL, "
          f"{int(C.is_2026_rookie.sum())} are 2026 rookies) | md5 "
          f"{json.loads(PROV.read_text())['md5']}")

if __name__ == "__main__":
    build()
