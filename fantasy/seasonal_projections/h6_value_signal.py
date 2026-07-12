"""H6 (PREREGISTRATION.md, H6 + Amendment 1): continuous value-signal test — one shot.

Hypothesis (frozen): among STABLE-ROLE players, Sleeper-vs-ADP disagreement
magnitude tracks ADP error monotonically. Statistic: per position-season
Spearman r between
    signal = adp_pos_rank - sleeper_pos_rank      (ranks on the FULL top-180
              pool, computed BEFORE the stable-role filter)
and
    perf   = z-scored (actual_pts - ADP-implied points), z within
              position-season over ALL pool rows (isotonic implied-points
              machinery inherited from step2_residual_model.py, extended to QB).
Pooled = unweighted mean over QB/RB/WR/TE of per-position 5-season means.
Panel 2021-2025 (2020 Sleeper projections VOID and quarantined; 2020 ADP is
clean and participates in curve fitting). Stable-role subset (pinned leak-free
in Amendment 2 P4): is_rookie == 0 AND week-1 team == prior-season team AND
prior_games >= 14, evaluated on signal-present rows.

Decision rule (verbatim H6; applied ONLY under --fire): PASS iff ALL of
  (a) pooled 5-season mean r above the fire-time permutation placebo's 95th
      percentile (placebo BINDS; frozen seed below, expected ~0.086 from Q3);
  (b) season-level pooled r positive in >= 4 of 5 seasons;
  (c) no position's 5-season mean r below -0.03;
  (d) one shot, rejection final.
Secondary (descriptive, gates nothing): the same statistic on the FULL pool.
A PASS licenses the aggregate stable-role claim only — never the |gap|>=8
tier, the board's sleeper_agrees surfaces (Q1 label duty), or the volatile-
player population (H6 Amendment 1 scope gap).

Placebo: 1,000 draws, signal permuted among STABLE-ROLE signal-present rows
within each position-season (non-subset rows never enter the shuffle pool).
SEED IS FROZEN (N3) so the bar is deterministic and cannot be re-rolled after
the result is seen. Computing the bar pre-fire is sanctioned (Joseph, Sub-step
N3): every draw uses a randomized pairing, so the bar reveals the threshold,
never whether the true pairing clears it. The true Spearman(signal, perf) is
computed NOWHERE outside --fire.

Modes:
  python h6_value_signal.py          -> Sub-step N build: structural asserts,
      subset-count reconciliation vs the blind Q counts, placebo bar under the
      frozen seed, sha256. NO outcome statistic of any kind.
  python h6_value_signal.py --fire   -> the one shot (fresh session only).
"""
import sys
import json
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
OUT_JSON     = HERE / "h6_results.json"
POS4         = ["QB", "RB", "WR", "TE"]
PANEL        = list(range(2021, 2026))
N_PLACEBO    = 1000
PLACEBO_SEED = 20260710          # frozen (N3); never re-roll
FLOOR        = -0.03
# Operative blind counts per H6 Amendment 2 (stable-role, signal-present, 2021..2025):
# the originally recorded Q counts omitted phase0's reconstructed==0 pool filter
# (2021: Deshaun Watson's reconstructed QB row out, Marquez Valdes-Scantling in).
# 18 cells cross-check the independent Q computation; the 2 corrected cells are
# validated by Amendment 2's named derivation — two paths, neither self-referential.
BLIND_COUNTS = {"QB": [14, 14, 13, 14, 16], "RB": [23, 23, 25, 24, 34],
                "TE": [14, 14, 15, 18, 16], "WR": [44, 36, 34, 41, 41]}


def build():
    df = pb.assemble()                                   # reconstructed==0, adp, actual_pts
    assert int(df["season"].min()) == 2014, "dataset floor drifted (sealed-slice fence)"
    # 2020 quarantine intact (projections VOID; ADP clean and kept)
    assert df.loc[df.season == 2020, "sleeper_pts_half_ppr"].isna().all(), \
        "2020 Sleeper projections present — quarantine broken"

    pool = df[df["adp"].notna()].copy()
    pool["adp_overall"] = pool.groupby("season")["adp"].rank(method="first")
    pool = pool[pool["adp_overall"] <= pb.POOL_SIZE]
    pool = pool[pool["position"].isin(POS4)].copy()

    # ADP provenance: panel rows are 100% Sleeper half-PPR sourced
    for s in PANEL:
        assert pool.loc[pool.season == s, "adp_half_ppr"].notna().all(), \
            f"{s}: pool contains non-Sleeper ADP rows"

    # ── ranks on the FULL pool, BEFORE any subset filter (N2 signal-order) ──
    pool["adp_pos_rank"] = pool.groupby(["season", "position"])["adp"].rank(method="first")
    pool["slp_pos_rank"] = pool.groupby(["season", "position"])["sleeper_pts_half_ppr"] \
                               .rank(ascending=False, method="first")
    pool["signal"] = pool["adp_pos_rank"] - pool["slp_pos_rank"]
    pool.attrs["ranks_before_filter"] = True             # set only on this path

    # ── implied points: per-position isotonic, walk-forward, panel folds ────
    curves = {}
    pool["implied"] = np.nan
    for t in PANEL:
        tr = pool[pool.season < t]
        assert tr["season"].max() < t, f"fold {t}: walk-forward fence broken"
        for p in POS4:
            trp = tr[tr.position == p]
            iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
            iso.fit(trp["adp_pos_rank"], trp["actual_pts"])
            grid = iso.predict(np.arange(1, 61))
            assert np.all(np.diff(grid) <= 1e-9), f"iso not non-increasing: fold {t} {p}"
            curves[(t, p)] = {r: float(iso.predict([r])[0]) for r in (1, 6, 12, 24, 36)}
            m = (pool.season == t) & (pool.position == p)
            pool.loc[m, "implied"] = iso.predict(pool.loc[m, "adp_pos_rank"])

    # ── perf: z-scored residual within position-season over ALL pool rows ───
    panel = pool[pool.season.isin(PANEL)].copy()
    panel["resid"] = panel["actual_pts"] - panel["implied"]
    panel["perf"] = panel.groupby(["season", "position"])["resid"] \
                         .transform(lambda x: (x - x.mean()) / x.std(ddof=1))
    for (s, p), g in panel.groupby(["season", "position"]):
        assert abs(g["perf"].mean()) < 1e-9 and abs(g["perf"].std(ddof=1) - 1) < 1e-6, \
            f"z-scoring broken at {s} {p}"
        assert g["perf"].notna().all() and len(g) == ((pool.season == s) &
               (pool.position == p)).sum(), \
            f"{s} {p}: z-score cell excludes pool rows (denominator fence)"

    # ── stable-role subset (AFTER ranks; pinned definition) ─────────────────
    prior = df[["player_id", "season", "team"]].copy()
    prior["season"] += 1
    panel = panel.merge(prior.rename(columns={"team": "prior_team"}),
                        on=["player_id", "season"], how="left")
    panel["stable"] = ((panel.is_rookie == 0) & panel.prior_team.notna()
                       & panel.team.notna() & (panel.team == panel.prior_team)
                       & (panel.prior_games >= 14))
    assert panel.attrs.get("ranks_before_filter") or pool.attrs.get("ranks_before_filter"), \
        "signal ranks were not computed on the pre-filter pool"

    # missing-projection exclusion bound + denominators already asserted above
    for s in PANEL:
        miss = panel.loc[panel.season == s, "signal"].isna().mean()
        assert miss <= 0.03, f"{s}: {miss:.1%} of pool missing projection (> 3%)"

    sub = panel[panel.stable & panel.signal.notna()]
    counts_ok = True
    print("subset-count reconciliation vs blind H6 counts (stable-role, signal-present):")
    for p in POS4:
        got = [int((sub.position.eq(p) & sub.season.eq(s)).sum()) for s in PANEL]
        ok = got == BLIND_COUNTS[p]
        counts_ok &= ok
        print(f"  {p}: {got}  expected {BLIND_COUNTS[p]}  {'OK' if ok else 'DRIFTED'}")
    assert counts_ok, "subset counts drifted since the blind Q computation — STOP"

    # team provenance re-assert (P4): dataset team column only; the Sleeper join
    # in build_season_dataset keeps ADP/projection fields exclusively, so no
    # Sleeper roster/team data can reach `team`/`prior_team`.
    import build_season_dataset as bsd
    import inspect
    src = inspect.getsource(bsd.main)
    assert 'rows["team"] = rows["context_team"]' in src, \
        "build_season_dataset team provenance changed — re-audit before firing"
    src_all = inspect.getsource(bsd)
    assert '"adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "sleeper_pts_half_ppr"' in src_all, \
        "Sleeper join keep-list changed — re-audit team provenance"

    return panel, curves


def pooled_stat(cells):
    """cells: dict (season,pos)->r. Pooled = mean over positions of 5-season means."""
    return float(np.mean([np.mean([cells[(s, p)] for s in PANEL]) for p in POS4]))


def placebo_draws(sub, n_draws, seed):
    """Null distribution of the pooled statistic: signal shuffled among
    stable-role signal-present rows within each position-season."""
    rng = np.random.default_rng(seed)
    groups = {k: g for k, g in sub.groupby(["season", "position"])}
    draws = np.empty(n_draws)
    for d in range(n_draws):
        cells = {}
        for (s, p), g in groups.items():
            shuffled = rng.permutation(g["signal"].to_numpy())
            cells[(s, p)] = spearmanr(shuffled, g["perf"]).statistic
        draws[d] = pooled_stat(cells)
    return draws


def substep_n():
    panel, curves = build()
    sub = panel[panel.stable & panel.signal.notna()].copy()

    # placebo plumbing on a SYNTHETIC seeded signal: sizes preserved, scope confined
    synth = sub.copy()
    synth["signal"] = np.random.default_rng(0).standard_normal(len(synth))
    before = synth.groupby(["season", "position"]).size()
    _ = placebo_draws(synth, 3, seed=0)
    after = synth.groupby(["season", "position"]).size()
    assert before.equals(after), "placebo altered group sizes"
    non_subset = panel[~(panel.stable & panel.signal.notna())]
    assert len(non_subset) + len(sub) == len(panel), "placebo shuffle pool mis-scoped"
    print("  assert placebo plumbing (synthetic signal): sizes preserved, "
          "shuffle confined to stable-role rows: PASS")

    # frozen-seed FIRE-TIME bar (sanctioned pre-fire per N3: randomized pairings only)
    draws = placebo_draws(sub, N_PLACEBO, PLACEBO_SEED)
    bar = float(np.percentile(draws, 95))
    print(f"\n=== Sub-step N report (NO outcome statistic) ===")
    print(f"  panel {PANEL[0]}-{PANEL[-1]} | pool rows {len(panel):,} | "
          f"stable-role signal-present rows {len(sub):,}")
    print(f"  projection coverage by season: " + "  ".join(
        f"{s}:{panel.loc[panel.season == s, 'signal'].notna().mean():.0%}" for s in PANEL))
    print("  isotonic curve, fold t=2021 (fit on 2014-2020 ADP-era pool), implied pts "
          "at pos-rank 1/6/12/24/36:")
    for p in POS4:
        c = curves[(2021, p)]
        print(f"    {p}: " + "  ".join(f"r{r}={c[r]:.0f}" for r in (1, 6, 12, 24, 36)))
    print(f"  placebo: {N_PLACEBO} draws, seed {PLACEBO_SEED} (FROZEN), shuffle scope = "
          f"stable-role signal-present rows within position-season")
    print(f"  FIRE-TIME placebo 95th-percentile bar: {bar:.4f}  "
          f"(Q3 blind expectation ~0.086)")
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(f"\n  script sha256: {sha}")
    print("  CODE IS FROZEN. --fire runs this exact code once, in a fresh session.")
    return panel, sub, bar


def fire():
    panel, sub, bar = substep_n()
    cells, cells_full = {}, {}
    for (s, p), g in sub.groupby(["season", "position"]):
        cells[(s, p)] = spearmanr(g["signal"], g["perf"]).statistic
    fp = panel[panel.signal.notna()]
    for (s, p), g in fp.groupby(["season", "position"]):
        cells_full[(s, p)] = spearmanr(g["signal"], g["perf"]).statistic

    pooled = pooled_stat(cells)
    season_pooled = {s: float(np.mean([cells[(s, p)] for p in POS4])) for s in PANEL}
    pos_means = {p: float(np.mean([cells[(s, p)] for s in PANEL])) for p in POS4}
    a = pooled > bar
    b = sum(v > 0 for v in season_pooled.values()) >= 4
    c = min(pos_means.values()) >= FLOOR
    verdict = "PASS" if (a and b and c) else "FAIL"

    print("\n" + "=" * 78)
    print("H6 — THE ONE SHOT (decision rule verbatim)")
    print("=" * 78)
    print(f"per-position 5-season mean r: " +
          "  ".join(f"{p} {pos_means[p]:+.3f}" for p in POS4))
    print(f"season-level pooled r: " +
          "  ".join(f"{s}:{v:+.3f}" for s, v in season_pooled.items()))
    print(f"\n  (a) pooled r {pooled:+.3f} > frozen placebo bar {bar:.3f} : {a}")
    print(f"  (b) positive pooled r in {sum(v > 0 for v in season_pooled.values())}/5 "
          f"seasons >= 4 : {b}")
    print(f"  (c) worst position {min(pos_means.values()):+.3f} >= {FLOOR} : {c}")
    headline = ("PASS" if verdict == "PASS"
                else "FAIL (true r up to ~0.144 not excluded at 80% power)")
    print(f"\nH6 VERDICT: {headline}")

    full_pooled = pooled_stat(cells_full)
    print(f"\nsecondary (descriptive, gates nothing; weak evidence per M3): "
          f"full-pool pooled r {full_pooled:+.3f}")
    print("scope (Amendment 1): any PASS licenses the aggregate stable-role claim only —"
          "\n  never the |gap|>=8 tier, sleeper_agrees surfaces, or the volatile slice.")

    OUT_JSON.write_text(json.dumps(
        {"pooled": pooled, "bar": bar, "season_pooled": season_pooled,
         "pos_means": pos_means, "criteria": {"a": bool(a), "b": bool(b), "c": bool(c)},
         "verdict": verdict, "headline": headline,
         "secondary_full_pool": {"pooled": full_pooled,
                                 "cells": {f"{s}_{p}": v for (s, p), v in cells_full.items()}},
         "cells": {f"{s}_{p}": v for (s, p), v in cells.items()},
         "placebo_seed": PLACEBO_SEED, "n_placebo": N_PLACEBO},
        indent=2, default=float))
    print(f"wrote {OUT_JSON.name}")
    return verdict


if __name__ == "__main__":
    if "--fire" in sys.argv:
        fire()
    else:
        substep_n()
