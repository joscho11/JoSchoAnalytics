"""Rookie Score build (Phase 2b) — 2026 class.

R32/R33 state (2026-07-18; supersedes the "not deployable" era):
- RB ships the FROZEN PBP instrument — mean(z(EPA/rush), z(explosive)) against the
  frozen scoped-pool constants in rb_pbp_facets_2026.provenance.json, x games/(games+6),
  anchored 52-95 / clipped 40-99. Clean-panel evidence (PREREG_pbp_index_2026-07-17
  OUTCOMES): disatt .474 (raw .215, n=300) = WEAK-DISCLOSED; box RB .298 = dead,
  superseded. Reads ONLY the frozen artifact — no CFBD cache, no scratchpad.
- WR/TE ship the box-score index DESCRIPTIVE ONLY {dom_best, recshare, ypr}, EQUAL
  thirds (WR reverted by R33 — R31's fit did not replicate on the clean panel;
  TE ratified by R31's gate-fail), z within position over the drafted-prospect
  reference pool (2014-2026 classes, games>=8), shrink w = games/(games+6), same
  monotone anchor family FIT ON THE ROOKIE POOL. Clean-panel box agreement with the
  NFL talent construct: WR .028 / TE .295 — both dead; the column describes college
  production, it does not predict. QB: no instrument ships — no QB rookie rows.

2025 college season: fetched ONCE via fetch_college.aggregate_season(2025) and
cached to college_production_2025_cache.csv (the freeze plan); subsequent builds
read the cache — deterministic.
"""
import json
import sys
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SEASONAL = HERE.parent / "seasonal_projections"
sys.path.insert(0, str(SEASONAL))
from _utils import norm_name                      # noqa: E402
from config import ANCHOR, RULED, WORK, NAME_ALIASES, ROOKIE_WEIGHTS   # noqa: E402
from schemas import (validate, join_audit, is_nfl, write_artifact,  # noqa: E402
                     SchemaError)

CLASS_YEAR = 2026   # R27: the class keys off the ADP board's rookie rows

FAC = {"RB": ["dom_best", "ypc"], "WR": ["dom_best", "recshare", "ypr"],
       "TE": ["dom_best", "recshare", "ypr"]}
GAMES_MIN = 8
K_GAMES = 6          # the heuristic college-games shrink (prototype convention)


def _wcomp(zdf, facs, wv):
    """R31 weighted composite = renormalized weighted nanmean over the facets a
    player actually has. Reduces EXACTLY to the old equal-weight nanmean when the
    weights are equal and all facets are present (RB/TE), so those rows are
    byte-unchanged; WR uses the fitted ROOKIE_WEIGHTS vector."""
    Z = zdf[facs].to_numpy(dtype=float)
    Wv = np.array([wv[f] for f in facs])
    num = np.nansum(Z * Wv, axis=1)
    den = (~np.isnan(Z) * Wv).sum(axis=1)
    return num / np.where(den == 0, np.nan, den)
CACHE_2025 = HERE / "college_production_2025_cache.csv"
COLS = ["pid", "name", "team", "rec_yds", "rec", "rush_yds", "car", "games",
        "dominator", "rec_yds_share", "season"]


def load_college():
    cp = pd.read_csv(SEASONAL / "college_production_2014_2024.csv")
    if CACHE_2025.exists():
        p25 = pd.read_csv(CACHE_2025)
        print(f"[college] 2025 season from cache ({len(p25)} rows)")
    else:
        import fetch_college as fc
        p25 = fc.aggregate_season(2025)
        p25["rec_yds_share"] = p25.rec_yds / p25.team_rec_yds.replace(0, np.nan)
        p25 = p25[[c for c in COLS if c in p25.columns]]
        p25.to_csv(CACHE_2025, index=False)
        print(f"[college] 2025 season fetched ONCE and cached ({len(p25)} rows)")
    both = pd.concat([cp[[c for c in COLS if c in cp.columns]], p25],
                     ignore_index=True)
    n0 = len(both)
    both = both.dropna(subset=["name"])   # pid-only 0-game rows: unjoinable, drop LOUDLY
    if n0 - len(both):
        print(f"[input-filter] college_production: dropped {n0 - len(both)} rows with "
              f"NaN name (prototype ingested these silently as nn='nan')")
    validate(both, "college_production", required=["name", "games", "season",
                                                   "dominator"],
             no_nan=["name", "season"])
    return both


def build(out_path=None):
    out_path = Path(out_path) if out_path else (HERE / "rookie_score_2026.csv")
    import nflreadpy as nfl
    cpall = load_college()
    cpall["ypc"] = cpall.rush_yds / cpall.car.replace(0, np.nan)
    cpall["ypr"] = cpall.rec_yds / cpall.rec.replace(0, np.nan)
    cpall["nn"] = cpall.name.map(lambda s: norm_name(str(s)))
    cpall = cpall.sort_values(["season", "nn"], kind="mergesort")

    def summ(g):
        last = g.iloc[-1]
        return pd.Series({"dom_best": g.dominator.max(),
                          "recshare": last.rec_yds_share,
                          "ypc": np.nanmean(g.ypc) if g.ypc.notna().any() else np.nan,
                          "ypr": np.nanmean(g.ypr) if g.ypr.notna().any() else np.nan,
                          "games": g.games.sum()})

    # R27: pool membership = ADP-BOARD ROOKIES, not the draft class. draft_picks is
    # an ATTRIBUTE join (round/pick where present; absent for UDFA), never a
    # membership gate. Career = the ELIGIBILITY WINDOW [class_year-5, class_year-1]
    # (5-year eligibility; kills the era-mixing the prototype merged silently).
    # Historical reference rows (the scale's backbone) stay draft-keyed 2015-2025.
    dp = nfl.load_draft_picks().to_pandas()
    dp["pos"] = dp.position.replace({"HB": "RB", "FB": "RB"})
    dp = dp[dp.pos.isin(["RB", "WR", "TE"]) & (dp.season >= 2015)]
    dp = dp.drop_duplicates(["pfr_player_name", "season", "position"])
    dp["nn"] = dp.pfr_player_name.map(lambda s: norm_name(str(s)))
    by_nn = {nn: g for nn, g in cpall.groupby("nn")}

    def window_summary(nn, year):
        g = by_nn.get(nn)
        if g is None:
            return None
        g = g[(g.season >= year - 5) & (g.season <= year - 1)]
        if not len(g):
            return None
        return summ(g.sort_values("season", kind="mergesort"))

    rows_ref = []
    for _, d in dp[dp.season <= 2025].iterrows():
        s = window_summary(d.nn, d.season)
        if s is None:
            continue
        s["nn"] = d.nn; s["pos"] = d.pos; s["draft_year"] = d.season
        rows_ref.append(s)
    ref = pd.DataFrame(rows_ref)
    ref = ref[ref.games >= GAMES_MIN]
    dp26 = dp[dp.season == 2026].set_index("nn")
    join_audit("JOIN-A college<->draft_picks 2026 (ATTRIBUTE join only, R27)",
               len(dp26), int(dp26.index.isin(cpall.nn).sum()))

    # scored 2026 rookie universe: ADP<=250 + board, per position, ZERO NFL snaps
    fac = pickle.load(open(Path(WORK) / "FACETS.pkl", "rb"))
    nfl_ids, sd, board, names = (fac["nfl_ids"], fac["sd"], fac["board"],
                                 fac["names"])
    gname = dict(zip(sd.player_id, sd.norm_name.fillna(
        sd.player.map(lambda s: norm_name(str(s))))))
    rows, dropped_qb = [], []
    for P in ["RB", "WR", "TE", "QB"]:
        univ = set(board[board.position == P].player_id) | set(
            sd[(sd.position == P) & (sd.adp_overall_rank <= 250)].player_id)
        rookies = [g for g in sorted(univ) if not is_nfl(g, nfl_ids)]
        if P == "QB":
            dropped_qb = rookies      # no college QB instrument shipped
            continue
        if P == "RB":
            # R32 (2026-07-18): RB is scored on the FROZEN PBP instrument — the fired
            # composite from PREREG_pbp_index_2026-07-17.md (clean-panel disatt .474
            # weak-disclosed; box .298 dead): mean(z(EPA/rush), z(explosive)) against
            # the frozen scoped-pool constants, x games/(games+6), anchored 52-95,
            # clip 40-99. NO reweighting. Reads ONLY rb_pbp_facets_2026.csv + its
            # provenance (pool mu/sd, anchor percentiles) — no cache, no scratchpad.
            fz = pd.read_csv(HERE / "rb_pbp_facets_2026.csv")
            fprov = json.loads(
                (HERE / "rb_pbp_facets_2026.provenance.json").read_text())
            fmu, fsd = fprov["pool_mu"], fprov["pool_sd"]
            z5, z98 = fprov["anchor_z5"], fprov["anchor_z98"]
            Bm = (ANCHOR["hi_score"] - ANCHOR["lo_score"]) / (z98 - z5)
            am = ANCHOR["lo_score"] - Bm * z5
            assert set(fz.gsis_id) == set(rookies), (
                "frozen RB artifact != scored universe: "
                f"{sorted(set(fz.gsis_id) ^ set(rookies))}")
            nn_of = {g: (NAME_ALIASES.get(g) or gname.get(g)
                         or norm_name(str(names.get(g, g)))) for g in rookies}
            for _, r in fz.iterrows():
                z1 = (r.epa_per_rush - fmu["EPA/rush"]) / fsd["EPA/rush"]
                z2 = (r.explosive - fmu["explosive"]) / fsd["explosive"]
                wg = r.games / (r.games + K_GAMES)
                rz = float(np.mean([z1, z2])) * wg
                att = (dp26.loc[nn_of[r.gsis_id]]
                       if nn_of[r.gsis_id] in dp26.index else None)
                rows.append(dict(gsis_id=r.gsis_id, display_name=r.display_name,
                                 position="RB",
                                 rookie_score=round(float(np.clip(am + Bm * rz,
                                                                  *ANCHOR["clip"])), 1),
                                 games=int(r.games), wg=round(float(wg), 4),
                                 draft_round=(int(att["round"]) if att is not None
                                              and pd.notna(att.get("round")) else pd.NA),
                                 z_epa_rush=round(float(z1), 4),
                                 z_explosive=round(float(z2), 4)))
            continue
        # R26/R27: assemble the CLASS rows from the ADP-board rookies themselves.
        nn_of = {g: (NAME_ALIASES.get(g) or gname.get(g)
                     or norm_name(str(names.get(g, g)))) for g in rookies}
        nn2g = {}
        for g, nn in nn_of.items():
            nn2g.setdefault(nn, []).append(g)
        cls_rows = {}
        for g, nn in nn_of.items():
            s = window_summary(nn, CLASS_YEAR)
            if s is not None and s["games"] >= GAMES_MIN:
                cls_rows[g] = s
        join_audit(f"JOIN-B scored-gsis<->college ({P} rookies, R26 aliases live)",
                   len(rookies), len(cls_rows),
                   collision_map=nn2g, fail_on_collision=True)
        for g in rookies:
            if g not in cls_rows:
                print(f"  [JOIN-B miss] {P} {names.get(g, g)} [{g}] -> no qualifying "
                      f"college window, no cell")
        # R27 widened pool: historical drafted rows + THIS class's board rows
        cls = pd.DataFrame(cls_rows).T
        pool = pd.concat([ref[ref.pos == P][FAC[P] + ["games"]], cls[FAC[P] + ["games"]]],
                         ignore_index=True)
        mu = {c: pool[c].mean() for c in FAC[P]}
        sdv = {c: pool[c].std() for c in FAC[P]}
        pool_z = pd.DataFrame({c: (pool[c] - mu[c]) / sdv[c] for c in FAC[P]})
        pool_rz = pd.Series(_wcomp(pool_z, FAC[P], ROOKIE_WEIGHTS[P])) * (
            pool.games / (pool.games + K_GAMES))
        sl = pool_rz.dropna()
        z2, z98 = np.percentile(sl, [ANCHOR["lo_pct"], ANCHOR["hi_pct"]])
        if not z98 > z2:
            raise SchemaError(f"{P}: degenerate rookie anchor")
        Bm = (ANCHOR["hi_score"] - ANCHOR["lo_score"]) / (z98 - z2)
        am = ANCHOR["lo_score"] - Bm * z2
        for g, s in cls_rows.items():
            zs = {c: (s[c] - mu[c]) / sdv[c] for c in FAC[P]}
            wg = s["games"] / (s["games"] + K_GAMES)
            rz = float(_wcomp(pd.DataFrame([zs]), FAC[P], ROOKIE_WEIGHTS[P])[0]) * wg
            att = dp26.loc[nn_of[g]] if nn_of[g] in dp26.index else None
            rows.append(dict(gsis_id=g,
                             display_name=names.get(g, nn_of[g].title()),
                             position=P,
                             rookie_score=round(float(np.clip(am + Bm * rz,
                                                              *ANCHOR["clip"])), 1),
                             games=int(s["games"]), wg=round(float(wg), 4),
                             draft_round=(int(att["round"]) if att is not None
                                          and pd.notna(att.get("round")) else pd.NA),
                             **{f"z_{c}": round(float(zs[c]), 4) for c in FAC[P]}))
    if dropped_qb:
        print(f"[QB rookies] {len(dropped_qb)} scored-universe QB rookies get NO cell "
              f"(no college QB instrument): "
              f"{[(names.get(g, g), g) for g in dropped_qb]}")
    df = pd.DataFrame(rows)
    df = df.sort_values(["position", "rookie_score", "gsis_id"],
                        ascending=[True, False, True], kind="mergesort")
    df["rank_pos"] = df.groupby("position").cumcount() + 1
    # Column contract: the original 12 columns in their original order (z_ypc kept,
    # now all-NA — RB moved to the PBP instrument), then the two RB PBP z columns
    # appended AFTER rank_pos so WR/TE lines stay byte-prefix-identical to the
    # pre-R32 artifact (their line + ",,").
    df = df.reindex(columns=["gsis_id", "display_name", "position", "rookie_score",
                             "games", "wg", "draft_round", "z_dom_best", "z_ypc",
                             "z_recshare", "z_ypr", "rank_pos",
                             "z_epa_rush", "z_explosive"])
    validate(df, "rookie_score_2026",
             required=["gsis_id", "display_name", "position", "rookie_score",
                       "games", "wg", "rank_pos"],
             no_nan=["gsis_id", "position", "rookie_score", "rank_pos"],
             checks={"rookies only": lambda d: ~d.gsis_id.map(
                 lambda g: is_nfl(g, nfl_ids))})
    write_artifact(df, out_path, RULED["NS"], RULED["SEED"],
                   extra={"index": "R32/R33 (2026-07-18): RB = frozen PBP instrument "
                                   "(rb_pbp_facets_2026.csv; PREREG_pbp_index_2026-07-17 "
                                   "OUTCOMES: disatt .474 raw .215 n=300 weak-disclosed; "
                                   "box RB .298 dead, superseded). WR REVERTED to equal "
                                   "thirds (R33: R31's fitted vector did not replicate on "
                                   "the clean panel, +.106 OOF -> -.009; fitted on the "
                                   "defective step2 panel, ~32% truncated/out-of-scope). "
                                   "TE equal RATIFIED (R31 gate-fail). WR/TE box columns "
                                   "are DESCRIPTIVE ONLY (clean-panel box .028/.295, "
                                   "both dead).",
                          "scale": "rookie drafted-prospect pool; NOT the NFL scale"})
    return df


if __name__ == "__main__":
    build()
