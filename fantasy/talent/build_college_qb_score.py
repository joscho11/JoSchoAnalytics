"""Build the College QB Talent Score — SPEC R35 (RATIFIED-2026-07-27).

Emits `college_qb_score_2026.csv`: one row per college QB, scored on his own college career and
anchored on the NFL-reaching QB population so the scale is comparable with the NFL Talent Score.

Fills the gap that blocked R34 Stage 5: `rookie_score_2026.csv` carries ZERO QB rows because the
2025 passer parse is degraded for the class-scoring path. This builds QBs directly from PFF
college, which is complete 2014-2025.

Pipeline (SPEC R35):
  Stage 0  pool = FBS QB seasons with dropbacks >= 200, one row per player-season;
           w_{i,s} = n_{i,s} * gamma^(F - s), gamma = 0.4, F = the player's FINAL college season
  Stage 1  z per facet WITHIN position WITHIN season; twp_rate sign-flipped here and only here
  Stage 2  zbar_i = weighted mean; N_eff,i = sum of weights (facet-indexed volume)
  Stage 3  z~_i = sqrt(r_i) * zbar_i, r_i = N_eff,i / (N_eff,i + k_i); k by method of moments
           on the COLLEGE pool, per facet, in that facet's own units (never the NFL k)
  Stage 4  composite over the ratified weights, rescaled across facets actually present
  Stage 5  0-100 two-point anchor p5 -> 52, p98 -> 95, clip [40, 99], FITTED ON NFL-REACHING QBs

Run:  python fantasy/talent/build_college_qb_score.py
Read-only on every other artifact; writes only its own CSV + provenance JSON.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SEAS = HERE.parent / "seasonal_projections"
PFF = SEAS / "pff"
XWALK = SEAS / "snapshots" / "players.parquet"
DATASET = SEAS / "season_dataset_2014_2026.csv"
OUT = HERE / "college_qb_score_2026.csv"
PROV = HERE / "college_qb_score_2026.provenance.json"

sys.path.insert(0, str(SEAS))
from _utils import norm_name                                    # noqa: E402

# ---- SPEC R35 ratified constants — NO CODE PATH MAY ALTER THESE ----
GAMMA = 0.4                                   # RATIFIED-2026-07-27 (64/26/10 over three seasons)
DB_FLOOR = 200                                # qualified starters only
YEARS = range(2014, 2026)
WEIGHTS = {"grades_pass": .250, "accuracy_pct": .200, "btt_rate": .175,
           "twp_rate": .100, "grades_run": .250, "pressure_grade": .025}
ANCHOR = dict(lo_pct=5, hi_pct=98, lo_score=52, hi_score=95, clip=(40, 99), min_rel=0.30)
DEPLOY = 2026


def _path(kind, year):
    """PFF college filenames: `college_{kind}_{y}.csv` 2019-2025, bare `{kind}.csv` 2014-2018."""
    dated = PFF / f"college_{year}" / f"college_{kind}_{year}.csv"
    return dated if dated.exists() else PFF / f"college_{year}" / f"{kind}.csv"


def _season_frame(year):
    s = pd.read_csv(_path("passing_summary", year))
    s = s[(s.position == "QB") & (s.dropbacks >= DB_FLOOR)].copy()
    s = s.rename(columns={"accuracy_percent": "accuracy_pct"})
    # one row per player-season: keep the max-dropback row where a player has multiple team rows
    s = s.sort_values("dropbacks", ascending=False).drop_duplicates("player_id", keep="first")
    s["season"] = year

    pressure = pd.read_csv(_path("passing_pressure", year))
    s = s.merge(pressure[["player_id", "pressure_grades_pass", "pressure_dropbacks"]],
                on="player_id", how="left")
    s = s.rename(columns={"pressure_grades_pass": "pressure_grade"})

    # passing_summary also carries a `grades_run`; the rushing table's is the one of record
    # (it is the grade that pairs with designed-rush attempts, our `n_s` for this facet).
    s = s.drop(columns=["grades_run"], errors="ignore")
    rush = pd.read_csv(_path("rushing_summary", year))[["player_id", "grades_run", "attempts"]]
    s = s.merge(rush.rename(columns={"attempts": "run_att"}), on="player_id", how="left")
    # ZERO DESIGNED RUNS IS NOT MISSING DATA (SPEC R35): a rushing row present means low activity
    # -> keep the z and let Stage 3 shrink it. No row at all is a coverage gap -> omit + rescale.
    s["has_rush_row"] = s["grades_run"].notna()

    s["n_grades_pass"] = s["n_accuracy_pct"] = s["n_btt_rate"] = s["n_twp_rate"] = s["dropbacks"]
    s["n_pressure_grade"] = s["pressure_dropbacks"]
    s["n_grades_run"] = s["run_att"]
    return s


def _mom_k(panel, facet):
    """Method-of-moments k on the COLLEGE pool, in this facet's own volume units."""
    sub = panel[["player_id", f"z_{facet}", f"n_{facet}"]].dropna()
    sub = sub[sub[f"n_{facet}"] > 0]
    multi = sub.groupby("player_id").filter(lambda g: len(g) >= 2)
    if len(multi) < 50:
        return np.nan
    parts = []
    for _pid, g in multi.groupby("player_id"):
        mean = g[f"z_{facet}"].mean()
        scale = len(g) / (len(g) - 1)
        parts.extend(((g[f"z_{facet}"] - mean) ** 2 * g[f"n_{facet}"] * scale).tolist())
    s2_eps = float(np.mean(parts))
    per_player = multi.groupby("player_id").apply(
        lambda g: np.average(g[f"z_{facet}"], weights=g[f"n_{facet}"]), include_groups=False)
    mean_n = float(multi.groupby("player_id")[f"n_{facet}"].sum().mean())
    s2_alpha = max(float(per_player.var(ddof=1)) - s2_eps / mean_n, 1e-6)
    return s2_eps / s2_alpha


def build():
    panel = pd.concat([_season_frame(y) for y in YEARS], ignore_index=True)

    # Stage 1 — z within position, within season
    for facet in WEIGHTS:
        panel[f"z_{facet}"] = np.nan
    for _year, g in panel.groupby("season"):
        for facet in WEIGHTS:
            x = pd.to_numeric(g[facet], errors="coerce")
            sign = -1 if facet == "twp_rate" else 1
            panel.loc[g.index, f"z_{facet}"] = sign * (x - x.mean()) / x.std(ddof=1)

    k = {f: _mom_k(panel, f) for f in WEIGHTS}

    rows = []
    for pid, g in panel.groupby("player_id"):
        final = int(g.season.max())
        g = g.copy()
        g["decay"] = GAMMA ** (final - g.season)
        last = g.loc[g.season.idxmax()]
        row = {"pff_player_id": pid, "player": last["player"], "college": last["team_name"],
               "final_season": final, "seasons": len(g)}
        num = den = 0.0
        for facet, weight in WEIGHTS.items():
            z = pd.to_numeric(g[f"z_{facet}"], errors="coerce")
            n = pd.to_numeric(g[f"n_{facet}"], errors="coerce")
            ok = (g["has_rush_row"] & z.notna()) if facet == "grades_run" \
                else (z.notna() & n.notna() & (n > 0))
            mask = ok.to_numpy()
            if not mask.any():
                continue                                    # absent -> omit, rescaled below
            w = np.nan_to_num(n.to_numpy()[mask]) * g["decay"].to_numpy()[mask]
            zbar = float(np.average(z.to_numpy()[mask], weights=w)) if w.sum() > 0 \
                else float(np.nanmean(z.to_numpy()[mask]))
            n_eff = float(w.sum())
            r = n_eff / (n_eff + k[facet]) if np.isfinite(k[facet]) else 0.5
            row[f"z_{facet}"] = round(zbar, 4)
            row[f"neff_{facet}"] = round(n_eff, 1)
            num += weight * np.sqrt(r) * zbar
            den += weight
        if den == 0:
            continue
        row["college_qb"] = num / den
        row["reliability"] = float(np.mean(
            [row[f"neff_{f}"] / (row[f"neff_{f}"] + k[f])
             for f in WEIGHTS if f"neff_{f}" in row and np.isfinite(k[f])]))
        rows.append(row)

    df = pd.DataFrame(rows)
    df["norm_name"] = df["player"].map(norm_name)

    # identity: pff_id -> gsis_id (NFL-reaching QBs only), and the 2026 NFL rookie flag
    xw = pd.read_parquet(XWALK).dropna(subset=["pff_id", "gsis_id"]).copy()
    xw["pff_id"] = xw["pff_id"].astype(str).astype(float).astype("Int64")
    df["gsis_id"] = df["pff_player_id"].map(xw.set_index("pff_id")["gsis_id"].to_dict())
    df["reached_nfl"] = df["gsis_id"].notna()

    # 2026 NFL rookie QBs must be matched by NORMALIZED NAME, not id: a brand-new player has no
    # gsis_id yet and carries a placeholder in the deploy builder (MEN516487, SIM639376,
    # ALL015451, pfr_BeckCa01 ...), so no id namespace is shared with PFF college. This mirrors
    # assemble_features.py, which keys college/PFF on norm_name for the same reason.
    # GUARD: names that are ambiguous on EITHER side are refused rather than mis-joined.
    ds = pd.read_csv(DATASET, usecols=["player_id", "player", "season", "position", "is_rookie"],
                     low_memory=False)
    rookies = ds[(ds.season == DEPLOY) & (ds.position == "QB") & (ds.is_rookie == 1)].copy()
    rookies["norm_name"] = rookies["player"].map(norm_name)
    dup_nfl = set(rookies.loc[rookies.norm_name.duplicated(keep=False), "norm_name"])
    dup_cfb = set(df.loc[df.norm_name.duplicated(keep=False), "norm_name"])
    ambiguous = dup_nfl | dup_cfb
    usable = rookies[~rookies.norm_name.isin(ambiguous)]
    name2id = usable.set_index("norm_name")["player_id"].to_dict()
    df["nfl_player_id"] = df["norm_name"].map(name2id)
    df["is_2026_rookie"] = df["nfl_player_id"].notna()
    refused = sorted(set(rookies.norm_name) & ambiguous)
    if refused:
        print(f"  name-join REFUSED as ambiguous ({len(refused)}): {refused}")
    print(f"  2026 rookie QBs: {len(rookies)} in dataset, "
          f"{int(df.is_2026_rookie.sum())} matched to a college score")

    # Stage 5 — anchor fitted on NFL-REACHING QBs (SPEC R35)
    slice_ = df.loc[df.reached_nfl & (df.reliability >= ANCHOR["min_rel"]), "college_qb"]
    lo, hi = np.percentile(slice_, [ANCHOR["lo_pct"], ANCHOR["hi_pct"]])
    b = (ANCHOR["hi_score"] - ANCHOR["lo_score"]) / (hi - lo)
    a = ANCHOR["lo_score"] - b * lo
    df["score"] = (a + b * df["college_qb"]).clip(*ANCHOR["clip"]).round(1)
    df["college_qb"] = df["college_qb"].round(4)
    df["reliability"] = df["reliability"].round(4)
    df["rank_final_season"] = df.groupby("final_season")["score"] \
                                .rank(method="min", ascending=False).astype(int)

    cols = (["pff_player_id", "gsis_id", "nfl_player_id", "player", "norm_name", "college", "final_season",
             "seasons", "reached_nfl", "is_2026_rookie", "college_qb", "score", "reliability",
             "rank_final_season"]
            + [f"z_{f}" for f in WEIGHTS] + [f"neff_{f}" for f in WEIGHTS])
    df = df[cols].sort_values(["final_season", "score"], ascending=[False, False])
    df.to_csv(OUT, index=False)

    prov = {
        "spec": "R35 (RATIFIED-2026-07-27)", "built": "2026-07-27",
        "gamma": GAMMA, "dropback_floor": DB_FLOOR, "weights": WEIGHTS,
        "anchor": {**{k_: v for k_, v in ANCHOR.items()},
                   "fitted_on": "NFL-reaching QBs", "n": int(len(slice_)),
                   "p5_raw": round(float(lo), 6), "p98_raw": round(float(hi), 6)},
        "mom_k": {f: round(float(v), 2) for f, v in k.items()},
        "rows": int(len(df)), "player_seasons": int(len(panel)),
        "reached_nfl": int(df.reached_nfl.sum()),
        "rookies_2026": int(df.is_2026_rookie.sum()),
        "md5": hashlib.md5(OUT.read_bytes()).hexdigest(),
    }
    PROV.write_text(json.dumps(prov, indent=2), encoding="utf-8")

    print(f"panel: {len(panel):,} qualifying player-seasons ({YEARS.start}-{YEARS.stop - 1})")
    print(f"MoM k: " + " ".join(f"{f}={k[f]:.0f}" for f in WEIGHTS))
    print(f"anchor on {len(slice_)} NFL-reaching QBs: p5={lo:+.4f}->52  p98={hi:+.4f}->95")
    print(f"wrote {OUT.name}: {len(df):,} QBs "
          f"({int(df.reached_nfl.sum())} reached NFL, {int(df.is_2026_rookie.sum())} are 2026 rookies)")
    print(f"md5 {prov['md5']}")
    return df


if __name__ == "__main__":
    build()
