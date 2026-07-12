"""H12 (PREREGISTRATION.md, H12): volatile-slice validation — the R0
population under the dated FINAL benchmark. One shot.

Hypothesis (frozen): among volatile players (pool AND signal-present AND NOT
stable-role — rookies, team-changers, low-prior-games veterans, full-miss
returners), Sleeper's disagreement with the FINAL dated Underdog market
predicts that market's error:
    signal_FINAL = adp_FINAL_pos_rank - sleeper_pos_rank
    perf_FINAL   = z(actual_pts - implied(adp_FINAL_pos_rank))
— H11's instrument verbatim, transported to the fenced population. GATE
SCOPE: RB and WR ONLY (D2; QB/TE volatile rows are out of scope entirely —
not gated, not descriptive, not computed). ONE pooled gate over the union
(D1); NO sub-group statistic is computed at fire, descriptive or otherwise
(D1/D4). No draft-capital variable exists anywhere in this harness (D4,
H8r adjacency fence). GATE-ONLY: no EARLY frame, no window curve (D3).

Population asserts (T-step audited, frozen): union 420 rows = rookies 130 +
team-changers 129 + low-prior 151 + returners 10; gate cells RB
34/35/34/35/28, WR 30/38/37/32/29 (332 rows); union disjoint from H6/H11's
473 stable-role rows. FINAL window = W10 (2021/2022/2023/2025), W9 for 2024
(q4/D5). Alias table q1 + Taysom rule carried (moot at RB/WR). The isotonic
curve is a rank->points prior and needs no player history — rookies flow
through with no prior-season dependency (asserted).

Decision rule (verbatim H12; applied ONLY under --fire): PASS iff ALL of
  (a) pooled 5-season mean r (RB/WR, FINAL benchmark, H12 population) above
      the fire-time frozen-seed placebo 95th percentile;
  (b) season-level pooled r positive in >= 4 of 5 seasons;
  (c) neither RB nor WR 5-season mean r below -0.03;
  (d) one shot, rejection final — no threshold changes, no position
      re-inclusion, no sub-group re-slicing, no window/panel/vendor swaps.
FAIL headline: "FAIL (true r up to ~0.15 not excluded at 80% power)."

Pre-declared descriptive DIAGNOSTIC (V5 mirror; fire-time only, gates
nothing, never promotable): the same Spearman against the PER-GAME residual
(actual_pts/games - isotonic rank->PPG at the FINAL rank, walk-forward,
games >= 3 = MIN_GAMES_TARGET convention, z over eligible rows).

Placebo: 1,000 draws, signal shuffled among H12-POPULATION rows within
position-season (FINAL frame only). SEED IS FROZEN (20260717). Bars pre-fire
are sanctioned (N3): randomized pairings reveal the threshold, never the
answer. The real Spearman(signal, perf) on volatile rows is computed NOWHERE
outside --fire.

Modes:
  python h12_volatile_signal.py          -> F-step build: manifest sha256
      verification, structural asserts, population/taxonomy reconciliation,
      join-loss teeth, frozen-seed bar, sha256. NO volatile signal x outcome
      quantity of any kind.
  python h12_volatile_signal.py --fire   -> the one shot (fresh session
      only; verify the frozen sha256 + no-prior-fire first: h12_results.json
      absent, no H12 OUTCOMES entry).
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr
from sklearn.isotonic import IsotonicRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase0_benchmark as pb
from _utils import norm_name

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE         = Path(__file__).resolve().parent
UD           = HERE / "data_audits" / "underdog"
OUT_JSON     = HERE / "h12_results.json"
POS4         = ["QB", "RB", "WR", "TE"]        # pool membership / taxonomy only
POS2         = ["RB", "WR"]                    # the H12 gate scope (D2)
PANEL        = list(range(2021, 2026))
N_PLACEBO    = 1000
PLACEBO_SEED = 20260717                        # frozen (H12); never re-roll
FLOOR        = -0.03
DESIGN_BAR   = 0.093                           # T-step sim reference only
MIN_GAMES_PPG = 3                              # V5 diagnostic floor
FINAL_WIN    = {2021: "W10", 2022: "W10", 2023: "W10", 2024: "W9", 2025: "W10"}
UNION_TOTALS = {"rookie": 130, "team_changer": 129, "low_prior": 151, "null_prior": 10}
GATE_CELLS   = {"RB": [34, 35, 34, 35, 28], "WR": [30, 38, 37, 32, 29]}     # 332
H6_CELLS     = {"QB": [14, 14, 13, 14, 16], "RB": [23, 23, 25, 24, 34],
                "TE": [14, 14, 15, 18, 16], "WR": [44, 36, 34, 41, 41]}     # 473
ALIAS        = {"gabriel davis": "gabe davis", "robby anderson": "robbie chosen",
                "hollywood brown": "marquise brown"}                         # q1
POS_OVERRIDE = {"taysom hill": "TE"}                                         # q1
UD_COLS      = ["draft_id", "draft_time", "player_name", "position_name",
                "overall_pick_number"]         # allowlist — never any points column
SEASON_FILES = {
    2021: ["BBM_II_Data_Dump_Regular_Season_01312022.csv"],
    2022: [f"BBM_III_Regular_Season_Dump_Part_{p}_01302023.csv"
           for p in ["00", "01", "02", "03", "04", "05", "06", "07", "08", "09",
                     "010", "011"]],
    2023: ["best_ball_mania_iv_2023_r1_results_pick_by_pick.csv"],
    2024: ["best_ball_mania_v_rd1.csv"],
    2025: ["best_ball_mania_vi_rd1.csv"],
}


def nm(s):
    n = norm_name(s)
    return ALIAS.get(n, n)


def win_label(d, yr):
    if d < date(yr, 7, 1):
        return "pre"
    if d > date(yr, 9, 10):
        return "post"
    if d >= date(yr, 9, 2):
        return "W10"
    return f"W{min((d - date(yr, 7, 1)).days // 7 + 1, 9)}"


def verify_manifest():
    man = json.loads((UD / "manifest.json").read_text())
    assert len(man["files"]) == 16, "J1 manifest drifted (expected 16 files)"
    for rec in man["files"]:
        f = UD / rec["file"]
        assert f.exists(), f"staged file missing: {rec['file']}"
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 23), b""):
                h.update(chunk)
        assert h.hexdigest() == rec["sha256"], f"sha256 drift: {rec['file']} — STOP"
    print("  assert staged-file sha256s match J1 manifest (16/16): PASS")


def load_final_window(yr):
    """FINAL-window Underdog ADP for season yr (market inputs only)."""
    lf = pl.concat([pl.scan_csv(UD / f, infer_schema_length=50000,
                                null_values=["NA", "NULL", ""]).select(UD_COLS)
                    for f in SEASON_FILES[yr]], how="vertical_relaxed")
    df = lf.collect().with_columns(
        pl.col("draft_time").str.replace("T", " ").str.slice(0, 19)
        .str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False).alias("dt"))
    assert int(df["dt"].is_null().sum()) == 0, f"{yr}: unparsed draft_time — STOP"
    p = df.to_pandas()
    p["win"] = p["dt"].dt.date.map(lambda d: win_label(d, yr))
    assert (p["win"] != "post").all(), f"{yr}: post-Sep-10 drafts present — STOP"
    n_w10 = p[p.win == "W10"]["draft_id"].nunique()
    if yr == 2024:
        assert n_w10 == 0, "2024 W10 must be EMPTY (q4/D5) — STOP"
    fin = p[p["win"] == FINAL_WIN[yr]].copy()
    n_drafts = fin["draft_id"].nunique()
    assert n_drafts >= 400, f"{yr}: FINAL window only {n_drafts} drafts — STOP"
    fin["pos_n"] = fin["position_name"].replace({"FB": "RB", "HB": "RB"})
    names = fin[["player_name"]].drop_duplicates().copy()
    names["nn"] = names["player_name"].map(nm)
    fin = fin.merge(names, on="player_name", how="left")
    fin.loc[fin["nn"].isin(POS_OVERRIDE), "pos_n"] = \
        fin.loc[fin["nn"].isin(POS_OVERRIDE), "nn"].map(POS_OVERRIDE)
    wadp = (fin.groupby(["nn", "pos_n"])["overall_pick_number"]
            .mean().rename("ud_adp").reset_index())
    assert not wadp.duplicated(["nn", "pos_n"]).any(), f"{yr}: dup (name,pos) — STOP"
    return wadp, n_drafts


def _capital_fence():
    """D4: no draft-capital variable anywhere in this harness."""
    src = Path(__file__).read_text(encoding="utf-8")
    for tok in ("draft_" + "round", "draft_" + "pick", "load_draft" + "_picks"):
        assert src.count(tok) <= 1, f"capital fence: '{tok}' present in harness"
    # (count <= 1 permits only this fence's own split-token construction)


def build():
    verify_manifest()
    _capital_fence()
    print("  assert capital fence (no draft-capital variable in harness): PASS")
    df = pb.assemble()
    assert int(df["season"].min()) == 2014, "dataset floor drifted (sealed-slice fence)"
    assert df.loc[df.season == 2020, "sleeper_pts_half_ppr"].isna().all(), \
        "2020 Sleeper projections present — quarantine broken"

    pool = df[df["adp"].notna()].copy()
    pool["adp_overall"] = pool.groupby("season")["adp"].rank(method="first")
    pool = pool[pool["adp_overall"] <= pb.POOL_SIZE]
    pool = pool[pool["position"].isin(POS4)].copy()
    for s in PANEL:
        assert pool.loc[pool.season == s, "adp_half_ppr"].notna().all(), \
            f"{s}: pool contains non-Sleeper ADP rows"
    pool["slp_pos_rank"] = pool.groupby(["season", "position"])["sleeper_pts_half_ppr"] \
                               .rank(ascending=False, method="first")
    pool["adp_pos_rank"] = pool.groupby(["season", "position"])["adp"].rank(method="first")
    pool.attrs["ranks_before_filter"] = True

    # campaign walk-forward isotonic curves (H11 D2): totals + diagnostic PPG, RB/WR
    isos, isos_pg, curves = {}, {}, {}
    for t in PANEL:
        tr = pool[pool.season < t]
        assert tr["season"].max() < t, f"fold {t}: walk-forward fence broken"
        for p in POS2:
            trp = tr[tr.position == p]
            iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
            iso.fit(trp["adp_pos_rank"], trp["actual_pts"])
            grid = iso.predict(np.arange(1, 61))
            assert np.all(np.diff(grid) <= 1e-9), f"iso not non-increasing: {t} {p}"
            isos[(t, p)] = iso
            curves[(t, p)] = {r: float(iso.predict([r])[0]) for r in (1, 6, 12, 24, 36)}
            trg = trp[trp["target_games"] >= MIN_GAMES_PPG]
            assert trg["season"].max() < t, f"fold {t} {p}: PPG walk-forward broken"
            iso_pg = IsotonicRegression(increasing=False, out_of_bounds="clip")
            iso_pg.fit(trg["adp_pos_rank"], trg["actual_pts"] / trg["target_games"])
            assert np.all(np.diff(iso_pg.predict(np.arange(1, 61))) <= 1e-9)
            isos_pg[(t, p)] = iso_pg

    # panel + taxonomy (full pool, membership only)
    panel = pool[pool.season.isin(PANEL)].copy()
    prior = df[["player_id", "season", "team"]].copy()
    prior["season"] += 1
    panel = panel.merge(prior.rename(columns={"team": "prior_team"}),
                        on=["player_id", "season"], how="left")
    panel["sig"] = panel["sleeper_pts_half_ppr"].notna()
    for s in PANEL:
        assert (~panel.loc[panel.season == s, "sig"]).mean() <= 0.03, \
            f"{s}: missing projection > 3%"
    panel["stable"] = ((panel.is_rookie == 0) & panel.team.notna()
                       & panel.prior_team.notna() & (panel.team == panel.prior_team)
                       & (panel.prior_games >= 14))
    vetm = panel.is_rookie == 0
    panel["grp"] = "stable"
    panel.loc[panel.is_rookie == 1, "grp"] = "rookie"
    panel.loc[vetm & panel.prior_team.isna(), "grp"] = "null_prior"
    panel.loc[vetm & panel.prior_team.notna() & panel.team.notna()
              & (panel.team != panel.prior_team), "grp"] = "team_changer"
    panel.loc[vetm & panel.prior_team.notna() & panel.team.notna()
              & (panel.team == panel.prior_team)
              & (panel.prior_games < 14), "grp"] = "low_prior"

    # ── population reconciliation vs the T-step audited counts ──────────────
    union = panel[panel.sig & ~panel.stable]
    assert len(union) == 420, f"union {len(union)} != 420 — STOP"
    got_groups = union["grp"].value_counts().to_dict()
    for g, exp in UNION_TOTALS.items():
        assert got_groups.get(g, 0) == exp, \
            f"sub-group {g}: {got_groups.get(g, 0)} != {exp} — STOP"
    stable_sig = panel[panel.stable & panel.sig]
    for p in POS4:
        got = [int(((stable_sig.position == p) & (stable_sig.season == s)).sum())
               for s in PANEL]
        assert got == H6_CELLS[p], f"H6 stable cell drift {p}: {got} — STOP"
    ids_union = set(zip(union.player_id, union.season))
    ids_stable = set(zip(stable_sig.player_id, stable_sig.season))
    assert not (ids_union & ids_stable), "union overlaps stable-role rows — STOP"
    print("population reconciliation vs T-step audited counts:")
    print(f"  union 420 OK | sub-groups {UNION_TOTALS} OK | disjoint from the "
          f"473 stable rows OK (H6 cells re-verified 20/20)")
    gate_ok = True
    for p in POS2:
        got = [int(((union.position == p) & (union.season == s)).sum()) for s in PANEL]
        ok = got == GATE_CELLS[p]
        gate_ok &= ok
        print(f"  gate cells {p}: {got}  expected {GATE_CELLS[p]}  {'OK' if ok else 'DRIFTED'}")
    assert gate_ok, "gate cells drifted — STOP"

    # ── FINAL-window benchmark, RB/WR pool rows, ranks BEFORE subset ────────
    panel["nn"] = panel["player"].map(nm)
    dup = panel.groupby(["season", "nn", "position"]).size()
    assert (dup <= 1).all(), "pool-side name collision — STOP"
    frames, wcounts, lost = [], {}, []
    for yr in PANEL:
        wadp, n_drafts = load_final_window(yr)
        wcounts[yr] = n_drafts
        m = panel[(panel.season == yr) & panel.position.isin(POS2)].merge(
            wadp.rename(columns={"pos_n": "position"}),
            on=["nn", "position"], how="left")
        matched = m[m["ud_adp"].notna()].copy()
        # join-loss teeth on the gate cells (<= 2% per cell; print lost names)
        for p in POS2:
            cell = m[(m.position == p) & m.sig & ~m.stable]
            miss = cell[cell["ud_adp"].isna()]
            exp = GATE_CELLS[p][PANEL.index(yr)]
            loss = len(miss) / exp
            for r in miss.itertuples():
                lost.append(f"{yr} {p}: {r.player}")
            assert loss <= 0.02, f"{yr} {p}: join loss {loss:.1%} > 2% — STOP " \
                                 f"(lost: {[r.player for r in miss.itertuples()]})"
        matched["rank_w"] = matched.groupby("position")["ud_adp"].rank(method="first")
        matched["implied_w"] = np.nan
        matched["implied_ppg"] = np.nan
        for p in POS2:
            mask = matched.position == p
            matched.loc[mask, "implied_w"] = isos[(yr, p)].predict(
                matched.loc[mask, "rank_w"])
            matched.loc[mask, "implied_ppg"] = isos_pg[(yr, p)].predict(
                matched.loc[mask, "rank_w"])
        matched["resid_w"] = matched["actual_pts"] - matched["implied_w"]
        matched["perf_w"] = matched.groupby("position")["resid_w"] \
                                   .transform(lambda x: (x - x.mean()) / x.std(ddof=1))
        for p in POS2:
            g = matched[matched.position == p]
            assert abs(g["perf_w"].mean()) < 1e-9 and \
                abs(g["perf_w"].std(ddof=1) - 1) < 1e-6, f"z broken {yr} {p}"
        matched["eligible_pg"] = matched["target_games"] >= MIN_GAMES_PPG
        matched.loc[matched.eligible_pg, "resid_pg"] = (
            matched.loc[matched.eligible_pg, "actual_pts"]
            / matched.loc[matched.eligible_pg, "target_games"]
            - matched.loc[matched.eligible_pg, "implied_ppg"])
        matched.loc[matched.eligible_pg, "z_pg"] = (
            matched[matched.eligible_pg].groupby("position")["resid_pg"]
            .transform(lambda x: (x - x.mean()) / x.std(ddof=1)))
        matched["signal_w"] = np.where(matched["sig"],
                                       matched["rank_w"] - matched["slp_pos_rank"],
                                       np.nan)
        # rookies flow through the rank->points curve with no history (asserted)
        rk = matched[(matched.is_rookie == 1) & matched.sig & ~matched.stable]
        assert rk["implied_w"].notna().all() and rk["perf_w"].notna().all(), \
            f"{yr}: rookie rows failed curve evaluation — STOP"
        frames.append(matched[matched.sig & ~matched.stable]
                      [["season", "position", "grp", "signal_w", "perf_w",
                        "eligible_pg", "z_pg"]])
    sub = pd.concat(frames, ignore_index=True)
    assert sorted(sub["season"].unique()) == PANEL and 2020 not in sub["season"].values
    return sub, curves, wcounts, lost


def pooled_stat(cells):
    return float(np.mean([np.mean([cells[(s, p)] for s in PANEL]) for p in POS2]))


def placebo_draws(sub, n_draws, rng):
    groups = {k: g for k, g in sub.groupby(["season", "position"])}
    draws = np.empty(n_draws)
    for d in range(n_draws):
        cells = {}
        for (s, p), g in groups.items():
            shuffled = rng.permutation(g["signal_w"].to_numpy())
            cells[(s, p)] = spearmanr(shuffled, g["perf_w"]).statistic
        draws[d] = pooled_stat(cells)
    return draws


def observed_cells(frame, perf_col):
    """The real pairing. Called NOWHERE outside fire() — self-check below."""
    cells = {}
    for (s, p), g in frame.groupby(["season", "position"]):
        cells[(s, p)] = spearmanr(g["signal_w"], g[perf_col]).statistic
    return cells


def _embargo_selfcheck():
    src = Path(__file__).read_text(encoding="utf-8")
    pre_fire = src.split("def fire(")[0]
    offenders = [ln for ln in pre_fire.splitlines()
                 if "observed_cells(" in ln
                 and not ln.strip().startswith("def observed_cells")
                 and '"observed_cells(' not in ln]
    assert not offenders, f"observed_cells referenced outside fire(): {offenders}"


def substep_f():
    sub, curves, wcounts, lost = build()

    synth = sub.copy()
    synth["signal_w"] = np.random.default_rng(0).standard_normal(len(synth))
    before = synth.groupby(["season", "position"]).size()
    _ = placebo_draws(synth, 3, np.random.default_rng(0))
    assert before.equals(synth.groupby(["season", "position"]).size()), \
        "placebo altered group sizes"
    print("  assert placebo plumbing (synthetic signal): sizes preserved, "
          "shuffle confined to population rows: PASS")
    _embargo_selfcheck()
    print("  assert embargo: observed_cells referenced only inside fire(): PASS")

    rng = np.random.default_rng(PLACEBO_SEED)
    bar = float(np.percentile(placebo_draws(sub, N_PLACEBO, rng), 95))

    print(f"\n=== H12 F-step report (NO volatile signal x outcome statistic) ===")
    print(f"  panel {PANEL[0]}-{PANEL[-1]} | gate frame rows {len(sub)} (RB/WR union)")
    print(f"  join losses on gate cells: "
          f"{lost if lost else 'NONE (100% FINAL-window coverage, aliases applied)'}")
    print(f"  FINAL-window drafts: " +
          "  ".join(f"{yr}:{wcounts[yr]:,} ({FINAL_WIN[yr]})" for yr in PANEL))
    print("  isotonic totals curve, fold t=2021, implied pts at pos-rank 1/6/12/24/36:")
    for p in POS2:
        c = curves[(2021, p)]
        print(f"    {p}: " + "  ".join(f"r{r}={c[r]:.0f}" for r in (1, 6, 12, 24, 36)))
    elig = sub[sub.eligible_pg]
    print("  V5 diagnostic eligibility (games >= 3), gate rows per cell:")
    for p in POS2:
        got = [int(((elig.position == p) & (elig.season == s)).sum()) for s in PANEL]
        print(f"    {p}: {got}")
    print(f"  placebo: {N_PLACEBO} draws, seed {PLACEBO_SEED} (FROZEN), shuffle scope = "
          f"H12-population rows within position-season")
    print(f"  FIRE-TIME placebo 95th-percentile bar: {bar:.4f}  "
          f"(T-step design estimate ~{DESIGN_BAR})")
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(f"\n  script sha256: {sha}")
    print("  CODE IS FROZEN. --fire runs this exact code once, in a fresh session,")
    print("  after verifying this hash and the no-prior-fire check "
          "(h12_results.json absent, no H12 OUTCOMES entry).")
    return sub, bar


def fire():
    sub, bar = substep_f()
    cells = observed_cells(sub, "perf_w")
    pooled = pooled_stat(cells)
    season_pooled = {s: float(np.mean([cells[(s, p)] for p in POS2])) for s in PANEL}
    pos_means = {p: float(np.mean([cells[(s, p)] for s in PANEL])) for p in POS2}
    a = pooled > bar
    b = sum(v > 0 for v in season_pooled.values()) >= 4
    c = min(pos_means.values()) >= FLOOR
    verdict = "PASS" if (a and b and c) else "FAIL"
    headline = ("PASS" if verdict == "PASS" else
                "FAIL (true r up to ~0.15 not excluded at 80% power)")

    print("\n" + "=" * 78)
    print("H12 — THE ONE SHOT (decision rule verbatim; volatile RB/WR, FINAL benchmark)")
    print("=" * 78)
    print(f"per-position 5-season mean r: " +
          "  ".join(f"{p} {pos_means[p]:+.3f}" for p in POS2))
    print(f"season-level pooled r: " +
          "  ".join(f"{s}:{v:+.3f}" for s, v in season_pooled.items()))
    print(f"\n  (a) pooled r {pooled:+.3f} > frozen placebo bar {bar:.3f} : {a}")
    print(f"  (b) positive pooled r in {sum(v > 0 for v in season_pooled.values())}/5 "
          f"seasons >= 4 : {b}")
    print(f"  (c) worst position {min(pos_means.values()):+.3f} >= {FLOOR} : {c}")
    print(f"\nH12 VERDICT: {headline}")

    elig = sub[sub.eligible_pg].copy()
    cells_pg = observed_cells(elig, "z_pg")
    pooled_pg = pooled_stat(cells_pg)
    pos_pg = {p: float(np.mean([cells_pg[(s, p)] for s in PANEL])) for p in POS2}
    print(f"\nDIAGNOSTIC (V5 mirror, descriptive, gates nothing, never promotable):")
    print(f"  per-game-residual Spearman, pooled {pooled_pg:+.3f}  "
          f"(RB {pos_pg['RB']:+.3f}, WR {pos_pg['WR']:+.3f}; games>=3 floor)")

    OUT_JSON.write_text(json.dumps(
        {"pooled": pooled, "bar": bar, "season_pooled": season_pooled,
         "pos_means": pos_means,
         "criteria": {"a": bool(a), "b": bool(b), "c": bool(c)},
         "verdict": verdict, "headline": headline,
         "cells": {f"{s}_{p}": v for (s, p), v in cells.items()},
         "diagnostic_per_game": {"pooled": pooled_pg, "pos_means": pos_pg,
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
