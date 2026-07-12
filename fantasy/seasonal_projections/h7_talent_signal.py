"""H7 (PREREGISTRATION.md, H7 T1-T7): efficiency-over-expectation signal — one shot.

Hypothesis (frozen, direction pinned POSITIVE): prior-season play-level
efficiency above expectation predicts POSITIVE ADP error on the full drafted
pool. Signal for pool season t = the player's season-(t-1) week-0 NGS value:
  QB  completion_percentage_above_expectation   (CPOE)
  RB  rush_yards_over_expected_per_att          (RYOE/att)
  WR  avg_yac_above_expectation                 (xYAC +/-)
  TE  avg_yac_above_expectation                 (same receiving mechanism)
Volume floor = the vendor's own week-0 qualification (the join source contains
ONLY qualified season aggregates). Rookies and unqualified players carry no
signal: excluded from correlation rows, never imputed.

Instrument (H6 family, unchanged): Spearman(signal, z-perf) per position-season
on the FULL ADP-top-180 pool (phase0 convention, reconstructed == 0),
signal-present rows only; unweighted pooling over four positions of
per-position 5-season means; panel 2021-2025. z-perf = actual - walk-forward
isotonic ADP-implied points, z-scored within position-season over ALL pool
rows. Placebo: signal permuted among SIGNAL-PRESENT pool rows within
position-season, 1,000 draws, FROZEN SEED 20260712 (pre-registered).
The prereg's optional 2017-2019 descriptive context is DECLINED (a "MAY");
it is not implemented, so it can never be computed post-hoc.

Decision rule (verbatim H7 T4; applied ONLY under --fire): PASS iff ALL of
  (a) pooled 5-season mean r above the fire-time frozen-seed placebo bar
      (T4 blind design estimate ~0.071);
  (b) season-level pooled r positive in >= 4 of 5 seasons;
  (c) no position's 5-season mean r below -0.03;
  (d) one shot, rejection final (H7's own two-designs cap: this design plus
      at most one blind power-grounds redesign, never a third).
A FAIL headline carries: true r up to ~0.115 not excluded at 80% power.
T6 embargo: no historical efficiency index with visible outcomes until fired.

Modes:
  python h7_talent_signal.py          -> U-step build: structural asserts,
      count reconciliation vs the T1/T4 audit, frozen-seed placebo bar,
      sha256. NO outcome statistic of any kind.
  python h7_talent_signal.py --fire   -> the one shot (fresh session only).
"""
import sys
import json
import inspect
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.isotonic import IsotonicRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase0_benchmark as pb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE         = Path(__file__).resolve().parent
OUT_JSON     = HERE / "h7_results.json"
POS4         = ["QB", "RB", "WR", "TE"]
PANEL        = list(range(2021, 2026))
FEAT_SEASONS = list(range(2020, 2025))
N_PLACEBO    = 1000
PLACEBO_SEED = 20260712              # pre-registered (H7 T4); never re-roll
FLOOR        = -0.03
NGS_METRIC   = {"QB": ("passing", "completion_percentage_above_expectation"),
                "RB": ("rushing", "rush_yards_over_expected_per_att"),
                "WR": ("receiving", "avg_yac_above_expectation"),
                "TE": ("receiving", "avg_yac_above_expectation")}
# T1 audit: NGS-matched VETERAN totals into the pool (feature seasons 2020-2024)
T1_MATCHED = {"QB": 102, "RB": 202, "WR": 281, "TE": 95}
# T4 audit: signal-present rows per position-season (2021..2025)
BLIND_COUNTS = {"QB": [19, 21, 21, 20, 21], "RB": [40, 42, 39, 42, 39],
                "WR": [60, 56, 52, 58, 55], "TE": [20, 19, 17, 19, 20]}


def load_ngs():
    """Week-0 REG season aggregates (vendor-qualified), stripped to id+metric —
    a name join is structurally impossible on these frames."""
    import nflreadpy as nfl
    frames = {}
    for st in {"passing", "rushing", "receiving"}:
        d = nfl.load_nextgen_stats(seasons=FEAT_SEASONS, stat_type=st).to_pandas()
        d = d[(d.week == 0) & (d.season_type == "REG")].copy()
        d["player_id"] = d["player_gsis_id"].astype(str)
        d["ngs_season"] = d["season"].astype(int)
        frames[st] = d
    return frames


def build():
    df = pb.assemble()
    assert int(df["season"].min()) == 2014, "dataset floor drifted"
    assert df.loc[df.season == 2020, "sleeper_pts_half_ppr"].isna().all(), \
        "2020 Sleeper projection quarantine broken"

    pool = df[df["adp"].notna()].copy()
    pool["adp_overall"] = pool.groupby("season")["adp"].rank(method="first")
    pool = pool[(pool["adp_overall"] <= pb.POOL_SIZE) & pool["position"].isin(POS4)]
    pool["adp_pos_rank"] = pool.groupby(["season", "position"])["adp"].rank(method="first")
    for s in PANEL:
        assert pool.loc[pool.season == s, "adp_half_ppr"].notna().all(), \
            f"{s}: non-Sleeper ADP rows on the panel"

    # z-perf machinery, H4/H6 unchanged: iso fit on pool seasons < t
    pool["implied"] = np.nan
    for t in PANEL:
        tr = pool[pool.season < t]
        assert tr["season"].max() < t, f"fold {t}: walk-forward fence broken"
        for p in POS4:
            iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
            trp = tr[tr.position == p]
            iso.fit(trp["adp_pos_rank"], trp["actual_pts"])
            grid = iso.predict(np.arange(1, 61))
            assert np.all(np.diff(grid) <= 1e-9), f"iso not monotone: {t} {p}"
            m = (pool.season == t) & (pool.position == p)
            pool.loc[m, "implied"] = iso.predict(pool.loc[m, "adp_pos_rank"])

    panel = pool[pool.season.isin(PANEL)].copy()
    assert int(panel.season.min()) == 2021 and int(panel.season.max()) == 2025, "panel fence"
    panel["resid"] = panel["actual_pts"] - panel["implied"]
    panel["perf"] = panel.groupby(["season", "position"])["resid"] \
                         .transform(lambda x: (x - x.mean()) / x.std(ddof=1))
    for (s, p), g in panel.groupby(["season", "position"]):
        assert abs(g["perf"].mean()) < 1e-9 and abs(g["perf"].std(ddof=1) - 1) < 1e-6
        assert g["perf"].notna().all(), f"{s} {p}: z denominator excludes pool rows"

    # signal join: gsis id + explicit season-(t-1) lag; frames are name-free
    ngs = load_ngs()
    panel["player_id"] = panel["player_id"].astype(str)
    panel["prior"] = (panel["season"] - 1).astype(int)
    panel["signal"] = np.nan
    panel["ngs_season_check"] = np.nan
    for p in POS4:
        st, metric = NGS_METRIC[p]
        src = ngs[st][["ngs_season", "player_id", metric]].rename(
            columns={metric: "sig_val"})
        assert set(src.columns) == {"ngs_season", "player_id", "sig_val"}, \
            "NGS join frame carries extra columns (name-join risk)"
        assert src["sig_val"].notna().all(), "vendor frame has null metric values"
        assert not src.duplicated(["player_id", "ngs_season"]).any(), \
            "NGS week-0 frame has duplicate (player, season) rows — merge would misalign"
        rows = panel[panel.position == p]
        m = rows.merge(src, left_on=["player_id", "prior"],
                       right_on=["player_id", "ngs_season"], how="left")
        panel.loc[rows.index, "signal"] = m["sig_val"].to_numpy()
        panel.loc[rows.index, "ngs_season_check"] = m["ngs_season"].to_numpy()

    # LAG ASSERT (loud): every matched row's NGS season == panel season - 1
    matched = panel[panel.signal.notna()]
    lag_ok = (matched["ngs_season_check"] == matched["season"] - 1).all()
    assert lag_ok, "OFF-BY-ONE LAG: NGS season != panel season - 1 — same-season leak"
    print(f"  LAG ASSERT: all {len(matched):,} matched rows use season-(t-1) NGS: PASS")
    # rookies cannot carry signal (no prior season); volume floor is the vendor's
    assert (matched["is_rookie"] == 0).all(), "a rookie row carries signal"
    assert matched["signal"].notna().all()          # values come only from the vendor merge
    n_excluded = panel.signal.isna().sum()
    print(f"  signal-absent rows excluded from correlation rows (never imputed): {n_excluded}")

    # count reconciliation vs the T1/T4 audit
    vets = panel[panel.is_rookie == 0]
    ok = True
    print("  T1 matched-veteran totals: ", end="")
    for p in POS4:
        got = int(vets[(vets.position == p)].signal.notna().sum())
        ok &= got == T1_MATCHED[p]
        print(f"{p} {got}/{T1_MATCHED[p]}", end="  ")
    print()
    print("  T4 per-cell signal-present counts:")
    for p in POS4:
        got = [int(((matched.position == p) & (matched.season == s)).sum()) for s in PANEL]
        cell_ok = got == BLIND_COUNTS[p]
        ok &= cell_ok
        print(f"    {p}: {got}  expected {BLIND_COUNTS[p]}  {'OK' if cell_ok else 'DRIFTED'}")
    assert ok, "counts drifted since the T1/T4 audit — STOP"
    return panel


def pooled_stat(cells):
    return float(np.mean([np.mean([cells[(s, p)] for s in PANEL]) for p in POS4]))


def placebo_draws(sub, n_draws, seed):
    rng = np.random.default_rng(seed)
    groups = {k: g for k, g in sub.groupby(["season", "position"])}
    draws = np.empty(n_draws)
    for d in range(n_draws):
        cells = {}
        for (s, p), g in groups.items():
            cells[(s, p)] = spearmanr(rng.permutation(g["signal"].to_numpy()),
                                      g["perf"]).statistic
        draws[d] = pooled_stat(cells)
    return draws


def observed_cells(sub):
    """The ONLY place the true signal-perf pairing is evaluated. --fire only."""
    return {(s, p): spearmanr(g["signal"], g["perf"]).statistic
            for (s, p), g in sub.groupby(["season", "position"])}


def substep_u():
    panel = build()
    sub = panel[panel.signal.notna()].copy()

    # placebo scope asserts: shuffle pool == signal-present rows, groups preserved
    synth = sub.copy()
    synth["signal"] = np.random.default_rng(0).standard_normal(len(synth))
    before = synth.groupby(["season", "position"]).size()
    _ = placebo_draws(synth, 3, seed=0)
    assert synth.groupby(["season", "position"]).size().equals(before)
    assert len(sub) + panel.signal.isna().sum() == len(panel), "shuffle pool mis-scoped"
    print("  placebo plumbing (synthetic signal): groups preserved, scope = "
          "signal-present rows only: PASS")

    # embargo self-check: the observed-pairing function is referenced nowhere in
    # the compute-path functions of the build phase (grep-level, per U2)
    for fn in (build, placebo_draws, pooled_stat, load_ngs):
        assert "observed_cells" not in inspect.getsource(fn), \
            f"embargo breach in {fn.__name__}"
    print("  embargo self-check: observed-pairing function referenced only in "
          "fire(): PASS")

    draws = placebo_draws(sub, N_PLACEBO, PLACEBO_SEED)
    bar = float(np.percentile(draws, 95))
    print(f"\n=== H7 U-step report (NO outcome statistic) ===")
    print(f"  panel {PANEL[0]}-{PANEL[-1]} | pool rows {len(panel):,} | "
          f"signal-present rows {len(sub):,}")
    print(f"  placebo: {N_PLACEBO} draws, seed {PLACEBO_SEED} (FROZEN, pre-registered), "
          f"shuffle scope = signal-present rows within position-season")
    print(f"  FIRE-TIME placebo 95th-percentile bar: {bar:.4f}  "
          f"(T4 blind design estimate ~0.071)")
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(f"\n  script sha256: {sha}")
    print("  CODE IS FROZEN. --fire runs this exact code once, in a fresh session.")
    return panel, sub, bar


def fire():
    panel, sub, bar = substep_u()
    cells = observed_cells(sub)
    pooled = pooled_stat(cells)
    season_pooled = {s: float(np.mean([cells[(s, p)] for p in POS4])) for s in PANEL}
    pos_means = {p: float(np.mean([cells[(s, p)] for s in PANEL])) for p in POS4}
    a = pooled > bar
    b = sum(v > 0 for v in season_pooled.values()) >= 4
    c = min(pos_means.values()) >= FLOOR
    verdict = "PASS" if (a and b and c) else "FAIL"
    headline = ("PASS" if verdict == "PASS"
                else "FAIL (true r up to ~0.115 not excluded at 80% power)")
    print("\n" + "=" * 78)
    print("H7 — THE ONE SHOT (decision rule verbatim)")
    print("=" * 78)
    print("per-position 5-season mean r: " +
          "  ".join(f"{p} {pos_means[p]:+.3f}" for p in POS4))
    print("season-level pooled r: " +
          "  ".join(f"{s}:{v:+.3f}" for s, v in season_pooled.items()))
    print(f"\n  (a) pooled r {pooled:+.3f} > frozen placebo bar {bar:.3f} : {a}")
    print(f"  (b) positive in {sum(v > 0 for v in season_pooled.values())}/5 seasons >= 4 : {b}")
    print(f"  (c) worst position {min(pos_means.values()):+.3f} >= {FLOOR} : {c}")
    print(f"\nH7 VERDICT: {headline}")
    print("licenses on PASS (T7): aggregate drafted-pool claim, volatile players "
          "included;\n  never tiers, never player-level calls; measurement, not alpha.")
    OUT_JSON.write_text(json.dumps(
        {"pooled": pooled, "bar": bar, "season_pooled": season_pooled,
         "pos_means": pos_means, "criteria": {"a": bool(a), "b": bool(b), "c": bool(c)},
         "verdict": verdict, "headline": headline,
         "cells": {f"{s}_{p}": v for (s, p), v in cells.items()},
         "placebo_seed": PLACEBO_SEED, "n_placebo": N_PLACEBO}, indent=2, default=float))
    print(f"wrote {OUT_JSON.name}")
    return verdict


if __name__ == "__main__":
    if "--fire" in sys.argv:
        fire()
    else:
        substep_u()
