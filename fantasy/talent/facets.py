"""Facet-input construction (Phase 1).

Ports the prototype's data preparation verbatim so reproduction mode consumes
byte-identical frames, plus: an `o` opportunity column on every model-facet frame
(needed for the R1 sigma^2_eps derivation; changes no legacy value), the deepCPOE
per-attempt feed (R6), and row-level QB feeds for the MoM k derivation.

Denominator law: player_stats / PFR-own denominators only. NGS is NEVER a
denominator (it supplies the CPOE numerator series only). The gsis<->pfr_id
crosswalk (ff_playerids) is IDENTITY ONLY.
"""
import warnings; warnings.filterwarnings("ignore")
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import nflreadpy as nfl

from config import PF, LAM, WORK
from schemas import validate, join_audit

SEASONAL = Path(__file__).resolve().parents[1] / "seasonal_projections"


def build_inputs():
    # gsis<->pfr_id crosswalk: IDENTITY ONLY (ff_playerids id-pair table; no name
    # matching anywhere in this map — asserted by test_no_name_in_crosswalk)
    xw = nfl.load_ff_playerids().to_pandas()[["gsis_id", "pfr_id"]].dropna()
    validate(xw, "ff_playerids", required=["gsis_id", "pfr_id"],
             no_nan=["gsis_id", "pfr_id"])
    p2g = dict(zip(xw.pfr_id, xw.gsis_id))
    names = nfl.load_players().to_pandas().set_index("gsis_id").display_name.to_dict()
    psw = nfl.load_player_stats(seasons=PF).to_pandas()
    n0 = len(psw)
    psw = psw.dropna(subset=["player_id"])   # keyless team-filler rows: drop LOUDLY
    if n0 - len(psw):
        print(f"[input-filter] player_stats: dropped {n0 - len(psw)} rows with NaN "
              f"player_id (keyless feed rows; prototype ingested these silently)")
    validate(psw, "player_stats", required=["player_id", "season", "week",
                                            "position", "receptions"],
             no_nan=["player_id", "season", "week"])
    nfl_ids = set(psw.player_id.unique())   # the dash-rule population (R12)
    pos = psw.groupby("player_id").position.agg(lambda s: s.value_counts().index[0])
    from config import POSITION_OVERRIDES
    for _g, _P in POSITION_OVERRIDES.items():   # R22 documented data corrections
        print(f"[position-override:R22] {_g}: {pos.get(_g, '(absent)')} -> {_P}")
        pos.loc[_g] = _P
    oppc = "opponent_team" if "opponent_team" in psw.columns else "opponent"
    ids = {P: set(pos[pos == P].index) for P in ["RB", "WR", "TE", "QB"]}

    RU, RC, CP, AT = [], [], [], []
    for yr in PF:
        p = nfl.load_pbp(seasons=[yr]).to_pandas()
        r = p[(p.rush_attempt == 1) & p.rusher_player_id.notna() & p.epa.notna()
              & p.yards_gained.notna() & p.posteam.notna() & p.defteam.notna()]
        RU.append(r[["rusher_player_id", "season", "week", "posteam", "defteam",
                     "epa", "yards_gained"]].rename(columns={"rusher_player_id": "pid"}))
        c = p[(p.complete_pass == 1) & p.xyac_mean_yardage.notna()
              & p.receiver_player_id.notna() & p.yards_after_catch.notna()
              & p.posteam.notna() & p.defteam.notna()]
        RC.append(pd.DataFrame({"pid": c.receiver_player_id.values, "season": c.season.values,
                                "week": c.week.values, "posteam": c.posteam.values,
                                "defteam": c.defteam.values,
                                "oe": (c.yards_after_catch - c.xyac_mean_yardage).values}))
        t = p[(p.pass_attempt == 1) & p.receiver_player_id.notna() & p.cp.notna()
              & p.complete_pass.notna() & p.posteam.notna() & p.defteam.notna()]
        CP.append(pd.DataFrame({"pid": t.receiver_player_id.values, "season": t.season.values,
                                "week": t.week.values, "posteam": t.posteam.values,
                                "defteam": t.defteam.values,
                                "coe": (t.complete_pass - t.cp).values}))
        d = p[p.passer_player_id.notna() & (p.pass_attempt == 1) & p.air_yards.notna()
              & p.cp.notna() & p.complete_pass.notna()]
        AT.append(pd.DataFrame({"pid": d.passer_player_id.values, "season": d.season.values,
                                "air": d.air_yards.values,
                                "coe": (d.complete_pass - d.cp).values}))
    RU = pd.concat(RU); RC = pd.concat(RC); CP = pd.concat(CP); AT = pd.concat(AT)

    def wr_(pids, fn):
        d = RU[RU.pid.isin(pids)].copy(); d["v"] = fn(d)
        g = d.groupby(["pid", "season", "week", "posteam", "defteam"]).agg(
            y=("v", "mean"), o=("v", "size")).reset_index()
        return g.assign(ts=g.posteam + "_" + g.season.astype(str),
                        os=g.defteam + "_" + g.season.astype(str),
                        w=g.o * np.exp(-LAM * (2025 - g.season)))[
            ["pid", "season", "ts", "os", "y", "w", "o"]]

    def wc_(src, pids, vc):
        d = src[src.pid.isin(pids)]
        g = d.groupby(["pid", "season", "week", "posteam", "defteam"]).agg(
            s=(vc, "sum"), o=(vc, "size")).reset_index()
        g["y"] = g.s / g.o
        return g.assign(ts=g.posteam + "_" + g.season.astype(str),
                        os=g.defteam + "_" + g.season.astype(str),
                        w=g.o * np.exp(-LAM * (2025 - g.season)))[
            ["pid", "season", "ts", "os", "y", "w", "o"]]

    pr = nfl.load_pfr_advstats(seasons=PF, stat_type="rush", summary_level="week").to_pandas()
    pr = pr[pr.carries > 0].copy()
    n_pr = len(pr)
    pr["gsis"] = pr.pfr_player_id.map(p2g); pr = pr.dropna(subset=["gsis"])
    join_audit("pfr_rush->gsis (identity crosswalk)", n_pr, len(pr))
    pr["ts"] = pr.team + "_" + pr.season.astype(str)
    pr["os"] = pr.opponent + "_" + pr.season.astype(str)
    pr["w"] = pr.carries * np.exp(-LAM * (2025 - pr.season))
    prc = nfl.load_pfr_advstats(seasons=PF, stat_type="rec", summary_level="week").to_pandas()
    prc["gsis"] = prc.pfr_player_id.map(p2g)
    prc = prc[["gsis", "season", "week", "receiving_broken_tackles"]]

    def brk(pids):
        den = psw[psw.player_id.isin(pids)][["player_id", "season", "week", "team",
                                             oppc, "receptions"]]
        m = prc.merge(den, left_on=["gsis", "season", "week"],
                      right_on=["player_id", "season", "week"])
        m = m[m.receptions > 0].copy()
        m["y"] = m.receiving_broken_tackles / m.receptions
        m["w"] = m.receptions * np.exp(-LAM * (2025 - m.season))
        m["ts"] = m.team + "_" + m.season.astype(str)
        m["os"] = m[oppc].astype(str) + "_" + m.season.astype(str)
        m["pid"] = m.gsis; m["o"] = m.receptions
        return m[["pid", "season", "ts", "os", "y", "w", "o"]]

    board = pd.read_csv(SEASONAL / "phase4_band_2026.csv")
    sd = pd.read_csv(SEASONAL / "season_dataset_2014_2026.csv",
                     usecols=["player_id", "player", "norm_name", "position",
                              "adp_overall_rank", "season"])
    sd = sd[sd.season == 2026]

    PR = {f: pr.rename(columns={"gsis": "pid"}).assign(y=v, o=pr.carries.values)[
        ["pid", "season", "ts", "os", "y", "w", "o"]]
        for f, v in [("YACcon", pr.rushing_yards_after_contact / pr.carries),
                     ("brkTkl_ru", pr.rushing_broken_tackles / pr.carries)]}
    # facet order below is the prototype's defs order — reproduction-mode RNG parity
    # depends on it; do not reorder.
    defs = {"RB": [("YACcon", PR["YACcon"]), ("brkTkl_ru", PR["brkTkl_ru"]),
                   ("success", wr_(ids["RB"], lambda d: (d.epa > 0).astype(float))),
                   ("explosive", wr_(ids["RB"], lambda d: (d.yards_gained >= 15).astype(float))),
                   ("yac_oe_rec", wc_(RC, ids["RB"], "oe")),
                   ("brkTkl_rec", brk(ids["RB"]))],
            "WR": [("yac_oe", wc_(RC, ids["WR"], "oe")),
                   ("cp", wc_(CP, ids["WR"], "coe")),
                   ("brkTkl_rec", brk(ids["WR"]))],
            "TE": [("yac_oe", wc_(RC, ids["TE"], "oe")),
                   ("brkTkl_rec", brk(ids["TE"]))]}

    # ---- QB feeds (three sources + deepCPOE; row-level kept for MoM k) ------
    ng = nfl.load_nextgen_stats(seasons=PF, stat_type="passing").to_pandas()
    ng = ng[(ng.week != 0) & (ng.season_type == "REG")].copy()
    ng["w"] = np.exp(-LAM * (2025 - ng.season))
    ngrows = pd.DataFrame({"pid": ng.player_gsis_id.values,
                           "v": ng.completion_percentage_above_expectation.values,
                           "att": ng.attempts.values, "wgt": (ng.attempts * ng.w).values})
    cpoe = ng.groupby("player_gsis_id").apply(lambda x: pd.Series({
        "v": np.sum(x.completion_percentage_above_expectation * x.attempts * x.w)
             / np.sum(x.attempts * x.w),
        "n": np.sum(x.attempts * x.w)}))
    pp = nfl.load_pfr_advstats(seasons=PF, stat_type="pass", summary_level="season").to_pandas()
    pp["pid"] = pp.pfr_id.map(p2g); pp["w"] = np.exp(-LAM * (2025 - pp.season))
    ppr = pp.dropna(subset=["pid"])
    badrows = pd.DataFrame({"pid": ppr.pid.values, "v": (-ppr.bad_throw_pct).values,
                            "att": ppr.pass_attempts.values,
                            "wgt": (ppr.pass_attempts * ppr.w).values})
    bad = ppr.groupby("pid").apply(lambda x: pd.Series({
        "v": -np.sum(x.bad_throw_pct * x.pass_attempts * x.w) / np.sum(x.pass_attempts * x.w),
        "n": np.sum(x.pass_attempts * x.w)}))
    qr = RU[RU.pid.isin(ids["QB"])].copy(); qr["w"] = np.exp(-LAM * (2025 - qr.season))
    qsrows = pd.DataFrame({"pid": qr.pid.values, "v": (qr.epa > 0).astype(float).values,
                           "wgt": qr.w.values})
    q10rows = pd.DataFrame({"pid": qr.pid.values,
                            "v": (qr.yards_gained >= 10).astype(float).values,
                            "wgt": qr.w.values})
    qs = qr.groupby("pid").apply(lambda x: pd.Series(
        {"v": np.sum((x.epa > 0) * x.w) / x.w.sum(), "n": x.w.sum()}))
    q10 = qr.groupby("pid").apply(lambda x: pd.Series(
        {"v": np.sum((x.yards_gained >= 10) * x.w) / x.w.sum(), "n": x.w.sum()}))
    deep = AT[(AT.pid.isin(ids["QB"])) & (AT.air >= 20)].copy()
    deep["w"] = np.exp(-LAM * (2025 - deep.season))
    deeprows = pd.DataFrame({"pid": deep.pid.values, "v": deep.coe.values,
                             "wgt": deep.w.values})
    dcar = deep.groupby("pid").apply(lambda x: pd.Series(
        {"v": np.average(x.coe, weights=x.w), "n": x.w.sum()}))

    for P in defs:
        for f, df in defs[P]:
            validate(df, f"facet:{P}/{f}",
                     required=["pid", "season", "ts", "os", "y", "w", "o"],
                     no_nan=["pid", "ts", "os", "w", "o"],
                     checks={"w>0": lambda d: d.w > 0, "o>0": lambda d: d.o > 0})
    out = {"defs": defs, "names": names, "p2g": p2g, "board": board, "sd": sd,
           "nfl_ids": nfl_ids,
           "qb_career": {"cpoe": cpoe, "bad": bad, "qsucc": qs, "q10": q10, "deep": dcar},
           "qb_rows": {"cpoe": ngrows, "bad": badrows, "qsucc": qsrows,
                       "q10": q10rows, "deep": deeprows}}
    Path(WORK).mkdir(parents=True, exist_ok=True)
    with open(Path(WORK) / "FACETS.pkl", "wb") as fh:
        pickle.dump(out, fh)
    print("facets checkpoint saved:", {P: [(f, len(df)) for f, df in defs[P]] for P in defs})
    print("qb feeds:", {k: len(v) for k, v in out["qb_career"].items()})
    return out


if __name__ == "__main__":
    build_inputs()
