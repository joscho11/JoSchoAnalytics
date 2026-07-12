"""H8v (PREREGISTRATION.md, H8 V1-V5): veteran room-competition signal — one shot.

Hypothesis (frozen, H8 V2): among TEAM-STABLE veteran RB/WR (is_rookie == 0,
week-1 team == prior-season week-1 team, both non-null, NO prior-games floor),
incoming draft-day room competition predicts ADP error. Statistic: per
position-season Spearman r between
    signal = room_competition = min pick number the player's team spent on his
             position in the season-N draft; rooms receiving no such pick take
             the sentinel (that draft's max pick + 1). Higher = LESS new
             competition. Direction pinned: Spearman(signal, z-perf) > 0.
and
    perf   = z-scored (actual_pts - ADP-implied points), z within
             position-season over ALL pool rows (isotonic implied-points
             machinery inherited from h6_value_signal.py / step2, RB/WR).
Pooled = unweighted mean over {RB, WR} of per-position 5-season means.
Panel 2021-2025. Pool = phase0 convention (reconstructed == 0, ADP top-180
overall per season). Ranks and curves computed on the FULL pool BEFORE any
subset filter (h6 pattern). Signal presence is 100% by construction
(sentinels); id-join integrity is asserted instead of an exclusion clause.
QB/TE veteran rooms are OUT OF SCOPE entirely — no QB/TE signal or statistic
is computed anywhere in this script (membership counts only, for the audited
630-row population assert). H8r (rookies) is NOT built here — deferred on
power grounds; only the prereg's F-step join-integrity counts are asserted.

Decision rule (verbatim H8 V3; applied ONLY under --fire): PASS iff ALL of
  (a) pooled 5-season mean r above the fire-time frozen-seed permutation
      placebo's 95th percentile (design estimate ~0.080; the placebo BINDS);
  (b) season-level pooled r positive in >= 4 of 5 seasons;
  (c) neither RB nor WR 5-season mean r below -0.03;
  (d) one shot, rejection final — no threshold changes, no panel swaps, no
      component additions.
A FAIL headlines as "FAIL (true r up to ~0.13 not excluded at 80% power)".

Pre-declared descriptive DIAGNOSTIC (V5; fire-time only, gates nothing, never
promotable): the same Spearman against a PER-GAME residual — actual_pts/games
minus isotonic ADP-implied PPG (walk-forward, same floor), z within
position-season over eligible rows; minimum-games floor = 3 (MIN_GAMES_TARGET
convention, build_season_dataset.py).

Placebo: 1,000 draws, signal permuted among H8v-POPULATION rows within each
position-season (non-population rows never enter the shuffle pool). SEED IS
FROZEN (20260713, pre-registered in V3). Computing the bar pre-fire is
sanctioned (N3 precedent): every draw uses a randomized pairing, so the bar
reveals the threshold, never whether the true pairing clears it. The real
Spearman(signal, perf) is computed NOWHERE outside --fire.

Modes:
  python h8v_competition_signal.py          -> F-step build: structural
      asserts, population reconciliation vs the V1-audited blind counts,
      frozen-seed placebo bar, sha256. NO outcome statistic of any kind.
  python h8v_competition_signal.py --fire   -> the one shot (fresh session
      only; the fire session re-verifies the frozen sha256 first).
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

HERE          = Path(__file__).resolve().parent
OUT_JSON      = HERE / "h8v_results.json"
POS4          = ["QB", "RB", "WR", "TE"]      # pool membership only
POS2          = ["RB", "WR"]                  # the H8v instrument scope
PANEL         = list(range(2021, 2026))
N_PLACEBO     = 1000
PLACEBO_SEED  = 20260713                      # frozen (H8 V3); never re-roll
FLOOR         = -0.03
DESIGN_BAR    = 0.080                          # V3 design estimate, reference only
MIN_GAMES_PPG = 3                              # V5 diagnostic floor (MIN_GAMES_TARGET)

# V1-audited invariants — drift in any of these means STOP, do not fire.
MAX_PICK   = {2021: 259, 2022: 262, 2023: 259, 2024: 257, 2025: 257}
H8_TEAM_MAP = {"GNB": "GB", "KAN": "KC", "LAR": "LA", "LVR": "LV",
               "NOR": "NO", "NWE": "NE", "SFO": "SF", "TAM": "TB"}
BLIND_CELLS = {"RB": [38, 40, 39, 35, 41], "WR": [56, 44, 48, 49, 50]}   # 193 + 247 = 440
STABLE_POS4 = {"QB": 99, "RB": 193, "WR": 247, "TE": 91}                 # total 630
ROOKIE_JOIN = {"total": 130, "matched": 128, "unmatched_by_season": {2021: 1, 2023: 1}}


def load_draft():
    """Season-N draft picks (nflverse), mapped to dataset team codes.
    Positions normalized HB/FB -> RB (pinned, V1). Audited invariants asserted."""
    import nflreadpy as nfl
    dp = nfl.load_draft_picks().to_pandas()
    dp = dp[dp["season"].isin(PANEL)].copy()
    for s in PANEL:
        mx = int(dp.loc[dp.season == s, "pick"].max())
        assert mx == MAX_PICK[s], f"{s}: draft max pick {mx} != audited {MAX_PICK[s]} — source drifted, STOP"
    dp["team_ds"] = dp["team"].map(lambda t: H8_TEAM_MAP.get(t, t))
    dp["pos_n"] = dp["position"].replace({"HB": "RB", "FB": "RB"})
    return dp


def build():
    df = pb.assemble()                                   # reconstructed==0, adp, actual_pts
    assert int(df["season"].min()) == 2014, "dataset floor drifted (sealed-slice fence)"
    # campaign invariant (H8 touches no Sleeper projection field, asserted anyway):
    assert df.loc[df.season == 2020, "sleeper_pts_half_ppr"].isna().all(), \
        "2020 Sleeper projections present — quarantine broken"

    pool = df[df["adp"].notna()].copy()
    pool["adp_overall"] = pool.groupby("season")["adp"].rank(method="first")
    pool = pool[pool["adp_overall"] <= pb.POOL_SIZE]
    pool = pool[pool["position"].isin(POS4)].copy()

    # ADP provenance: every panel pool row is Sleeper half-PPR sourced
    for s in PANEL:
        assert pool.loc[pool.season == s, "adp_half_ppr"].notna().all(), \
            f"{s}: pool contains non-Sleeper ADP rows"

    # ── ranks on the FULL pool, BEFORE any subset filter (h6 pattern) ───────
    pool["adp_pos_rank"] = pool.groupby(["season", "position"])["adp"].rank(method="first")
    pool.attrs["ranks_before_filter"] = True

    # ── implied points + implied PPG: per-position isotonic, walk-forward ───
    # Instrument scope is RB/WR only; QB/TE never receive a curve, signal, or z.
    curves = {}
    pool["implied"] = np.nan
    pool["implied_ppg"] = np.nan
    for t in PANEL:
        tr = pool[pool.season < t]
        assert tr["season"].max() < t, f"fold {t}: walk-forward fence broken"
        for p in POS2:
            trp = tr[tr.position == p]
            iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
            iso.fit(trp["adp_pos_rank"], trp["actual_pts"])
            grid = iso.predict(np.arange(1, 61))
            assert np.all(np.diff(grid) <= 1e-9), f"iso not non-increasing: fold {t} {p}"
            curves[(t, p)] = {r: float(iso.predict([r])[0]) for r in (1, 6, 12, 24, 36)}
            m = (pool.season == t) & (pool.position == p)
            pool.loc[m, "implied"] = iso.predict(pool.loc[m, "adp_pos_rank"])

            # V5 diagnostic curve: rank -> PPG, same fold, games >= 3 floor
            trg = trp[trp["target_games"] >= MIN_GAMES_PPG]
            assert trg["season"].max() < t, f"fold {t} {p}: PPG walk-forward fence broken"
            iso_pg = IsotonicRegression(increasing=False, out_of_bounds="clip")
            iso_pg.fit(trg["adp_pos_rank"], trg["actual_pts"] / trg["target_games"])
            grid_pg = iso_pg.predict(np.arange(1, 61))
            assert np.all(np.diff(grid_pg) <= 1e-9), f"PPG iso not non-increasing: fold {t} {p}"
            pool.loc[m, "implied_ppg"] = iso_pg.predict(pool.loc[m, "adp_pos_rank"])

    # ── perf: z-scored residual within position-season over ALL pool rows ───
    panel = pool[pool.season.isin(PANEL) & pool.position.isin(POS2)].copy()
    assert set(panel["season"].unique()) == set(PANEL) and 2020 not in panel["season"].values
    panel["resid"] = panel["actual_pts"] - panel["implied"]
    panel["perf"] = panel.groupby(["season", "position"])["resid"] \
                         .transform(lambda x: (x - x.mean()) / x.std(ddof=1))
    for (s, p), g in panel.groupby(["season", "position"]):
        assert abs(g["perf"].mean()) < 1e-9 and abs(g["perf"].std(ddof=1) - 1) < 1e-6, \
            f"z-scoring broken at {s} {p}"
        assert g["perf"].notna().all() and len(g) == ((pool.season == s) &
               (pool.position == p)).sum(), \
            f"{s} {p}: z-score cell excludes pool rows (denominator fence)"

    # V5 diagnostic residual: eligible rows only (games >= 3), z over eligible
    panel["eligible_pg"] = panel["target_games"] >= MIN_GAMES_PPG
    panel.loc[panel.eligible_pg, "resid_pg"] = (
        panel.loc[panel.eligible_pg, "actual_pts"] / panel.loc[panel.eligible_pg, "target_games"]
        - panel.loc[panel.eligible_pg, "implied_ppg"])
    panel.loc[panel.eligible_pg, "z_pg"] = (
        panel[panel.eligible_pg].groupby(["season", "position"])["resid_pg"]
        .transform(lambda x: (x - x.mean()) / x.std(ddof=1)))
    for (s, p), g in panel[panel.eligible_pg].groupby(["season", "position"]):
        assert abs(g["z_pg"].mean()) < 1e-9 and abs(g["z_pg"].std(ddof=1) - 1) < 1e-6, \
            f"diagnostic z broken at {s} {p}"

    # ── population: team-stable veterans (NO games floor), RB/WR ────────────
    prior = df[["player_id", "season", "team"]].copy()
    prior["season"] += 1
    prior = prior.rename(columns={"team": "prior_team"})

    # audited 630-row POS4 membership check (counts only; no QB/TE signal/z)
    pool4 = pool[pool.season.isin(PANEL)][["player_id", "season", "position",
                                           "team", "is_rookie", "draft_round"]].copy()
    pool4 = pool4.merge(prior, on=["player_id", "season"], how="left")
    pool4["stable"] = ((pool4.is_rookie == 0) & pool4.team.notna()
                       & pool4.prior_team.notna() & (pool4.team == pool4.prior_team))
    stable_by_pos = {p: int((pool4.stable & (pool4.position == p)).sum()) for p in POS4}
    assert stable_by_pos == STABLE_POS4, \
        f"team-stable POS4 counts {stable_by_pos} != audited {STABLE_POS4} — STOP"
    assert sum(stable_by_pos.values()) == 630

    panel = panel.merge(prior, on=["player_id", "season"], how="left")
    panel["stable"] = ((panel.is_rookie == 0) & panel.team.notna()
                       & panel.prior_team.notna() & (panel.team == panel.prior_team))
    assert panel.attrs.get("ranks_before_filter") or pool.attrs.get("ranks_before_filter"), \
        "signal ranks were not computed on the pre-filter pool"

    # ── signal: min own-room pick, sentinel = max pick + 1 ──────────────────
    dp = load_draft()
    ds_teams = set(pool4.team.dropna().unique())
    mapped = set(dp["team_ds"].unique())
    assert mapped == ds_teams, f"team map not bijective: {sorted(mapped ^ ds_teams)}"

    minpick = (dp[dp.pos_n.isin(POS2)]
               .groupby(["season", "team_ds", "pos_n"])["pick"].min().reset_index()
               .rename(columns={"team_ds": "team", "pos_n": "position",
                                "pick": "min_pick"}))
    # the signal exists ONLY on the population: a mover's season-N room would be
    # a September-dated assignment (the J-class reason team-stability is required)
    sub = panel[panel.stable].copy()
    sub = sub.merge(minpick, on=["season", "team", "position"], how="left")
    sub["signal"] = sub["min_pick"].where(
        sub["min_pick"].notna(), sub["season"].map(lambda s: MAX_PICK[s] + 1))
    assert sub["signal"].notna().all(), "sentinel fill failed — signal must be 100% present"
    counts_ok = True
    print("population reconciliation vs blind H8 V3 counts (team-stable RB/WR):")
    for p in POS2:
        got = [int(((sub.position == p) & (sub.season == s)).sum()) for s in PANEL]
        ok = got == BLIND_CELLS[p]
        counts_ok &= ok
        print(f"  {p}: {got}  expected {BLIND_CELLS[p]}  {'OK' if ok else 'DRIFTED'}")
    assert counts_ok, "population cells drifted since the V1 audit — STOP, do not fire"
    assert len(sub) == 440

    for (s, p), g in sub.groupby(["season", "position"]):
        assert np.ptp(g["signal"].to_numpy(float)) > 0, f"degenerate signal cell {s} {p}"

    # ── rookie id-join integrity (prereg F-step assert-teeth; COUNTS ONLY — ─
    # ── no rookie signal is defined or computed; H8r stays deferred) ────────
    rook = pool4[pool4.is_rookie == 1][["player_id", "season", "draft_round"]]
    assert len(rook) == ROOKIE_JOIN["total"], f"rookie membership {len(rook)} != 130"
    dpg = dp[dp["gsis_id"].notna()][["gsis_id", "season"]].drop_duplicates() \
        .rename(columns={"gsis_id": "player_id"})
    rj = rook.merge(dpg, on=["player_id", "season"], how="left", indicator=True)
    matched = int((rj["_merge"] == "both").sum())
    um = rj[rj["_merge"] != "both"]
    um_by_season = um.groupby("season").size().to_dict()
    assert matched == ROOKIE_JOIN["matched"], f"rookie id-join {matched} != 128 — STOP"
    assert um_by_season == ROOKIE_JOIN["unmatched_by_season"], \
        f"unmatched rookies {um_by_season} != audited {{2021:1, 2023:1}}"
    assert um["draft_round"].isna().all(), "unmatched rookie has dataset draft_round — id gap, not undrafted"
    print(f"  rookie id-join integrity (counts only): {matched}/{len(rook)} matched, "
          f"unmatched {um_by_season} both dataset-undrafted: OK")

    return panel, sub, curves


def pooled_stat(cells):
    """cells: dict (season,pos)->r. Pooled = mean over RB/WR of 5-season means."""
    return float(np.mean([np.mean([cells[(s, p)] for s in PANEL]) for p in POS2]))


def placebo_draws(sub, n_draws, seed):
    """Null distribution of the pooled statistic: signal shuffled among
    H8v-population rows within each position-season (randomized pairings only)."""
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


def observed_cells(sub, perf_col):
    """The real pairing. Called NOWHERE outside fire() — embargo self-check below."""
    cells = {}
    for (s, p), g in sub.groupby(["season", "position"]):
        cells[(s, p)] = spearmanr(g["signal"], g[perf_col]).statistic
    return cells


def _embargo_selfcheck():
    """Assert the real-statistic path is inert in the F phase: observed_cells
    is referenced only at its def site and inside fire()."""
    src = Path(__file__).read_text(encoding="utf-8")
    pre_fire = src.split("def fire(")[0]
    offenders = [ln for ln in pre_fire.splitlines()
                 if "observed_cells(" in ln
                 and not ln.strip().startswith("def observed_cells")
                 and '"observed_cells(' not in ln]
    assert not offenders, f"observed_cells referenced outside fire(): {offenders}"


def substep_f():
    panel, sub, curves = build()

    # placebo plumbing on a SYNTHETIC seeded signal (never the real pairing logic)
    synth = sub.copy()
    synth["signal"] = np.random.default_rng(0).standard_normal(len(synth))
    before = synth.groupby(["season", "position"]).size()
    _ = placebo_draws(synth, 3, seed=0)
    after = synth.groupby(["season", "position"]).size()
    assert before.equals(after), "placebo altered group sizes"
    assert len(sub) + int((~panel.stable).sum()) == len(panel), "placebo shuffle pool mis-scoped"
    print("  assert placebo plumbing (synthetic signal): sizes preserved, "
          "shuffle confined to population rows: PASS")
    _embargo_selfcheck()
    print("  assert embargo: observed_cells referenced only inside fire(): PASS")

    # frozen-seed FIRE-TIME bar (sanctioned pre-fire: randomized pairings only)
    draws = placebo_draws(sub, N_PLACEBO, PLACEBO_SEED)
    bar = float(np.percentile(draws, 95))

    print(f"\n=== H8v F-step report (NO outcome statistic) ===")
    print(f"  panel {PANEL[0]}-{PANEL[-1]} | RB/WR pool rows {len(panel):,} | "
          f"population rows {len(sub):,} (RB 193 + WR 247)")
    print(f"  team-stable POS4 membership: 630 (QB 99 / RB 193 / WR 247 / TE 91) — "
          f"audited counts reproduced")
    print("  sentinels (draft max pick + 1): " +
          "  ".join(f"{s}:{MAX_PICK[s] + 1}" for s in PANEL))
    print("  signal structure per cell (n, sentinel share — structure only):")
    for p in POS2:
        cells_txt = []
        for s in PANEL:
            g = sub[(sub.position == p) & (sub.season == s)]
            sh = float((g["signal"] == MAX_PICK[s] + 1).mean())
            cells_txt.append(f"{s}:{len(g)}({sh:.0%})")
        print(f"    {p}: " + "  ".join(cells_txt))
    print("  isotonic totals curve, fold t=2021 (fit on 2014-2020 pool), implied pts "
          "at pos-rank 1/6/12/24/36:")
    for p in POS2:
        c = curves[(2021, p)]
        print(f"    {p}: " + "  ".join(f"r{r}={c[r]:.0f}" for r in (1, 6, 12, 24, 36)))
    elig = panel[panel.stable & panel.eligible_pg]
    print("  V5 diagnostic eligibility (games >= 3), population rows per cell:")
    for p in POS2:
        got = [int(((elig.position == p) & (elig.season == s)).sum()) for s in PANEL]
        print(f"    {p}: {got}")
    print(f"  placebo: {N_PLACEBO} draws, seed {PLACEBO_SEED} (FROZEN), shuffle scope = "
          f"population rows within position-season")
    print(f"  FIRE-TIME placebo 95th-percentile bar: {bar:.4f}  "
          f"(V3 design estimate ~{DESIGN_BAR})")
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(f"\n  script sha256: {sha}")
    print("  CODE IS FROZEN. --fire runs this exact code once, in a fresh session.")
    return panel, sub, bar


def fire():
    panel, sub, bar = substep_f()
    cells = observed_cells(sub, "perf")

    pooled = pooled_stat(cells)
    season_pooled = {s: float(np.mean([cells[(s, p)] for p in POS2])) for s in PANEL}
    pos_means = {p: float(np.mean([cells[(s, p)] for s in PANEL])) for p in POS2}
    a = pooled > bar
    b = sum(v > 0 for v in season_pooled.values()) >= 4
    c = min(pos_means.values()) >= FLOOR
    verdict = "PASS" if (a and b and c) else "FAIL"
    headline = ("PASS" if verdict == "PASS"
                else "FAIL (true r up to ~0.13 not excluded at 80% power)")

    print("\n" + "=" * 78)
    print("H8v — THE ONE SHOT (decision rule verbatim)")
    print("=" * 78)
    print(f"per-position 5-season mean r: " +
          "  ".join(f"{p} {pos_means[p]:+.3f}" for p in POS2))
    print(f"season-level pooled r: " +
          "  ".join(f"{s}:{v:+.3f}" for s, v in season_pooled.items()))
    print(f"\n  (a) pooled r {pooled:+.3f} > frozen placebo bar {bar:.3f} : {a}")
    print(f"  (b) positive pooled r in {sum(v > 0 for v in season_pooled.values())}/5 "
          f"seasons >= 4 : {b}")
    print(f"  (c) worst position {min(pos_means.values()):+.3f} >= {FLOOR} : {c}")
    print(f"\nH8v VERDICT: {headline}")

    # V5 pre-declared diagnostic — descriptive, gates NOTHING, never promotable.
    elig = sub[sub.eligible_pg].copy()
    cells_pg = observed_cells(elig, "z_pg")
    pooled_pg = pooled_stat(cells_pg)
    pos_pg = {p: float(np.mean([cells_pg[(s, p)] for s in PANEL])) for p in POS2}
    print(f"\nDIAGNOSTIC (V5, descriptive, gates nothing, never promotable):")
    print(f"  per-game-residual Spearman, pooled {pooled_pg:+.3f}  "
          f"(RB {pos_pg['RB']:+.3f}, WR {pos_pg['WR']:+.3f}; games>=3 floor)")

    OUT_JSON.write_text(json.dumps(
        {"pooled": pooled, "bar": bar, "season_pooled": season_pooled,
         "pos_means": pos_means,
         "criteria": {"a": bool(a), "b": bool(b), "c": bool(c)},
         "verdict": verdict, "headline": headline,
         "cells": {f"{s}_{p}": v for (s, p), v in cells.items()},
         "diagnostic_per_game": {"pooled": pooled_pg, "pos_means": pos_pg,
                                 "cells": {f"{s}_{p}": v for (s, p), v in cells_pg.items()},
                                 "floor_games": MIN_GAMES_PPG,
                                 "license": "descriptive only; never promotable"},
         "placebo_seed": PLACEBO_SEED, "n_placebo": N_PLACEBO},
        indent=2, default=float))
    print(f"wrote {OUT_JSON.name}")
    return verdict


if __name__ == "__main__":
    if "--fire" in sys.argv:
        fire()
    else:
        substep_f()
