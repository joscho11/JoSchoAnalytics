"""H11 (PREREGISTRATION.md, H11): freshness decomposition of the validated H6
signal — the P5 dated-ADP instrument. One shot.

Hypothesis (frozen): H6's edge conflates SKILL with FRESHNESS (the K4
confound — the Sleeper projection is a week-1-eve snapshot; the campaign ADP
is a summer aggregate). Freshness is operationalized as the staleness gap
between the fixed projection snapshot and a DATED Underdog BBM market
benchmark, manipulated by draft window w. Instrument family, per window w:
    signal_w = adp_w_pos_rank - sleeper_pos_rank
    perf_w   = z(actual_pts - implied(adp_w_pos_rank))
H6's exact instrument transported to the window-w market; both sides
reference the same dated benchmark. THE GATE IS r_FINAL (last populated
window: W10; W9 for 2024 per q4). The early->final window curve is the
declared descriptive sizing of the freshness component — computed ONLY at
fire, gating nothing, never promotable.

Population (D1): H6's stable-role subset EXACTLY — is_rookie == 0, week-1
team == prior-season week-1 team (both non-null), prior_games >= 14,
signal-present; QB/RB/WR/TE; panel 2021-2025; blind operative cells
QB 14/14/13/14/16, RB 23/23/25/24/34, TE 14/14/15/18/16, WR 44/36/34/41/41
(473 rows). NOT the full pool — a full-pool fire would unblind the
volatile-slice prereg next in queue; no volatile row is touched anywhere.

Windows (D3/D4/D5, J1's audited grid): axis = Jul 1 - Sep 10 only; W1..W9
weekly from Jul 1, W10 = Sep 2-10; EARLY = W1 u W2 (Jul 1-14); FINAL = W10
(2021/2022/2023/2025) or W9 (2024). Pre-July drafts NEVER enter the axis.
Window ADP = mean overall_pick_number over the window's drafts, alias table
applied (q1: Gabriel Davis->Gabe Davis, Robby Anderson->Robbie Chosen,
Hollywood Brown->Marquise Brown, Taysom Hill TE position rule), pool-rank
recomputed within (season, position) on the full pool BEFORE any subset
filter (h6 pattern). Benchmark is Underdog best-ball (format delta q3 rides
on the claim wording, D6).

Decision rule (verbatim H11; applied ONLY under --fire): PASS iff ALL of
  (a) pooled 5-season mean r_FINAL above the fire-time frozen-seed placebo
      95th percentile (FINAL frame);
  (b) season-level pooled r_FINAL positive in >= 4 of 5 seasons;
  (c) no position's 5-season mean r_FINAL below -0.03 (all four positions);
  (d) one shot, rejection final — no threshold/window/panel/vendor swaps.
FAIL headline: "FAIL (freshness-controlled edge not established; true r up
to ~0.144 not excluded at 80% power)." Pattern rule (mechanical, only if the
gate fails): freshness-consistent iff pooled r_EARLY exceeds its own
frozen-seed placebo 95th percentile; otherwise flat/inconclusive. H6's PASS
is not revoked under any outcome.

Placebo: 1,000 draws, signal shuffled among STABLE-ROLE SIGNAL-PRESENT rows
within position-season (H6's exact scope), run for the FINAL frame then the
EARLY frame from a single rng stream. SEED IS FROZEN (20260716). Computing
the bars pre-fire is sanctioned (N3): randomized pairings reveal the
threshold, never the answer. The real Spearman(signal_w, perf_w) is computed
NOWHERE outside --fire.

Modes:
  python h11_freshness_signal.py          -> F-step build: manifest sha256
      verification, structural asserts, population reconciliation vs H6's
      blind cells, window-population asserts, frozen-seed bars, sha256.
      NO dated-window x outcome statistic of any kind.
  python h11_freshness_signal.py --fire   -> the one shot (fresh session
      only; verify this script's frozen sha256 + no-prior-fire first).
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
OUT_JSON     = HERE / "h11_results.json"
POS4         = ["QB", "RB", "WR", "TE"]
PANEL        = list(range(2021, 2026))
N_PLACEBO    = 1000
PLACEBO_SEED = 20260716                     # frozen (H11); never re-roll
FLOOR        = -0.03
DESIGN_BAR   = 0.085                        # Q3-arithmetic reference only
H6_CELLS     = {"QB": [14, 14, 13, 14, 16], "RB": [23, 23, 25, 24, 34],
                "TE": [14, 14, 15, 18, 16], "WR": [44, 36, 34, 41, 41]}   # 473
FINAL_WIN    = {2021: "W10", 2022: "W10", 2023: "W10", 2024: "W9", 2025: "W10"}
AXIS         = ["EARLY", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10"]
ALIAS        = {"gabriel davis": "gabe davis", "robby anderson": "robbie chosen",
                "hollywood brown": "marquise brown"}                       # q1
POS_OVERRIDE = {"taysom hill": "TE"}                                       # q1
UD_COLS      = ["draft_id", "draft_time", "player_name", "position_name",
                "overall_pick_number"]      # allowlist — never any points column
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
    print(f"  assert staged-file sha256s match J1 manifest (16/16): PASS")


def load_windows(yr):
    """Per-window Underdog ADP for season yr (market inputs only) + draft counts."""
    lf = pl.concat([pl.scan_csv(UD / f, infer_schema_length=50000,
                                null_values=["NA", "NULL", ""]).select(UD_COLS)
                    for f in SEASON_FILES[yr]], how="vertical_relaxed")
    df = lf.collect().with_columns(
        pl.col("draft_time").str.replace("T", " ").str.slice(0, 19)
        .str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False).alias("dt"))
    assert int(df["dt"].is_null().sum()) == 0, f"{yr}: unparsed draft_time — STOP"
    p = df.select(["draft_id", "dt", "player_name", "position_name",
                   "overall_pick_number"]).to_pandas()
    p["win"] = p["dt"].dt.date.map(lambda d: win_label(d, yr))
    assert (p["win"] != "post").all(), f"{yr}: post-Sep-10 drafts present — STOP"

    dd = p.drop_duplicates("draft_id")
    counts = dd["win"].value_counts().to_dict()
    for w in [f"W{i}" for i in range(1, 10)]:
        assert counts.get(w, 0) >= 400, f"{yr} {w}: {counts.get(w, 0)} drafts < 400 — STOP"
    if yr == 2024:
        assert counts.get("W10", 0) == 0, "2024 W10 must be EMPTY (q4) — STOP"
    else:
        assert counts.get("W10", 0) > 0, f"{yr}: W10 unpopulated — STOP"

    ax = p[p["win"] != "pre"].copy()                    # D3: pre-July never enters
    assert ax["dt"].dt.date.min() >= date(yr, 7, 1)
    ax["grp"] = ax["win"].where(~ax["win"].isin(["W1", "W2"]), "EARLY")   # D4
    ax["pos_n"] = ax["position_name"].replace({"FB": "RB", "HB": "RB"})
    names = ax[["player_name"]].drop_duplicates().copy()
    names["nn"] = names["player_name"].map(nm)
    ax = ax.merge(names, on="player_name", how="left")
    ax.loc[ax["nn"].isin(POS_OVERRIDE), "pos_n"] = \
        ax.loc[ax["nn"].isin(POS_OVERRIDE), "nn"].map(POS_OVERRIDE)        # q1 Taysom
    wadp = (ax.groupby(["grp", "nn", "pos_n"])["overall_pick_number"]
            .mean().rename("ud_adp").reset_index())
    return wadp, counts


def build():
    verify_manifest()
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

    # ranks on the FULL pool, BEFORE any subset filter (h6 pattern)
    pool["adp_pos_rank"] = pool.groupby(["season", "position"])["adp"].rank(method="first")
    pool["slp_pos_rank"] = pool.groupby(["season", "position"])["sleeper_pts_half_ppr"] \
                               .rank(ascending=False, method="first")
    pool.attrs["ranks_before_filter"] = True

    # campaign walk-forward isotonic curves (D2), all four positions
    isos, curves = {}, {}
    for t in PANEL:
        tr = pool[pool.season < t]
        assert tr["season"].max() < t, f"fold {t}: walk-forward fence broken"
        for p in POS4:
            trp = tr[tr.position == p]
            iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
            iso.fit(trp["adp_pos_rank"], trp["actual_pts"])
            grid = iso.predict(np.arange(1, 61))
            assert np.all(np.diff(grid) <= 1e-9), f"iso not non-increasing: fold {t} {p}"
            isos[(t, p)] = iso
            curves[(t, p)] = {r: float(iso.predict([r])[0]) for r in (1, 6, 12, 24, 36)}

    # panel + H6 stable-role subset flags
    panel = pool[pool.season.isin(PANEL)].copy()
    prior = df[["player_id", "season", "team"]].copy()
    prior["season"] += 1
    panel = panel.merge(prior.rename(columns={"team": "prior_team"}),
                        on=["player_id", "season"], how="left")
    panel["stable"] = ((panel.is_rookie == 0) & panel.prior_team.notna()
                       & panel.team.notna() & (panel.team == panel.prior_team)
                       & (panel.prior_games >= 14))
    for s in PANEL:
        miss = panel.loc[panel.season == s, "sleeper_pts_half_ppr"].isna().mean()
        assert miss <= 0.03, f"{s}: {miss:.1%} of pool missing projection (> 3%)"
    panel["sig_present"] = panel["sleeper_pts_half_ppr"].notna()

    sub_base = panel[panel.stable & panel.sig_present]
    print("population reconciliation vs H6 blind operative counts (stable-role, signal-present):")
    ok = True
    for p in POS4:
        got = [int(((sub_base.position == p) & (sub_base.season == s)).sum()) for s in PANEL]
        match = got == H6_CELLS[p]
        ok &= match
        print(f"  {p}: {got}  expected {H6_CELLS[p]}  {'OK' if match else 'DRIFTED'}")
    assert ok, "subset cells drifted from H6's operative counts — STOP, do not fire"
    assert len(sub_base) == 473

    # dated windows -> per-window frames (signal_w, perf_w on the full pool first)
    panel["nn"] = panel["player"].map(nm)
    dup = panel.groupby(["season", "nn", "position"]).size()
    assert (dup <= 1).all(), "pool-side name collision — STOP"
    frames, wcounts, losses = {}, {}, []
    for yr in PANEL:
        wadp, counts = load_windows(yr)
        wcounts[yr] = counts
        for grp in AXIS:
            if yr == 2024 and grp == "W10":
                continue
            c = wadp[wadp.grp == grp].rename(columns={"pos_n": "position"})
            assert not c.duplicated(["nn", "position"]).any(), \
                f"{yr} {grp}: duplicate (name, position) in window ADP — STOP"
            m = panel[panel.season == yr].merge(c[["nn", "position", "ud_adp"]],
                                                on=["nn", "position"], how="left")
            m = m[m["ud_adp"].notna()].copy()
            # rank within the matched pool, before any subset use (h6 pattern)
            m["rank_w"] = m.groupby("position")["ud_adp"].rank(method="first")
            m["implied_w"] = np.nan
            for p in POS4:
                mask = m.position == p
                m.loc[mask, "implied_w"] = isos[(yr, p)].predict(m.loc[mask, "rank_w"])
            m["resid_w"] = m["actual_pts"] - m["implied_w"]
            m["perf_w"] = m.groupby("position")["resid_w"] \
                           .transform(lambda x: (x - x.mean()) / x.std(ddof=1))
            for p in POS4:
                g = m[m.position == p]
                assert abs(g["perf_w"].mean()) < 1e-9 and \
                    abs(g["perf_w"].std(ddof=1) - 1) < 1e-6, f"z broken {yr} {grp} {p}"
            m["signal_w"] = np.where(m["sig_present"],
                                     m["rank_w"] - m["slp_pos_rank"], np.nan)
            # per-cell subset loss vs H6 cells (<= 2% or STOP)
            for pi, p in enumerate(POS4):
                have = int((m.stable & m.sig_present & (m.position == p)).sum())
                exp = H6_CELLS[p][PANEL.index(yr)]
                loss = (exp - have) / exp
                assert loss <= 0.02, \
                    f"{yr} {grp} {p}: subset window loss {loss:.1%} > 2% — STOP"
                if have != exp:
                    losses.append(f"{yr} {grp} {p}: {have}/{exp}")
            frames.setdefault(grp, []).append(
                m[m.stable & m.sig_present][["season", "position", "signal_w", "perf_w"]])
    frames = {g: pd.concat(v, ignore_index=True) for g, v in frames.items()}
    # FINAL frame: per-season final windows (W10 rows; 2024's W9 rows)
    final = pd.concat([frames["W10"],
                       frames["W9"][frames["W9"].season == 2024]], ignore_index=True)
    assert sorted(final["season"].unique()) == PANEL and 2020 not in final["season"].values
    early = frames["EARLY"]
    assert sorted(early["season"].unique()) == PANEL
    return panel, frames, final, early, curves, wcounts, losses


def pooled_stat(cells):
    """cells: dict (season,pos)->r. Pooled = mean over POS4 of per-position
    means over the seasons present."""
    out = []
    for p in POS4:
        vals = [v for (s, q), v in cells.items() if q == p]
        out.append(float(np.mean(vals)))
    return float(np.mean(out))


def placebo_draws(frame, n_draws, rng):
    """Null distribution: signal shuffled among stable-role signal-present rows
    within position-season (randomized pairings only)."""
    groups = {k: g for k, g in frame.groupby(["season", "position"])}
    draws = np.empty(n_draws)
    for d in range(n_draws):
        cells = {}
        for (s, p), g in groups.items():
            shuffled = rng.permutation(g["signal_w"].to_numpy())
            cells[(s, p)] = spearmanr(shuffled, g["perf_w"]).statistic
        draws[d] = pooled_stat(cells)
    return draws


def observed_cells(frame):
    """The real pairing. Called NOWHERE outside fire() — self-check below."""
    cells = {}
    for (s, p), g in frame.groupby(["season", "position"]):
        cells[(s, p)] = spearmanr(g["signal_w"], g["perf_w"]).statistic
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
    panel, frames, final, early, curves, wcounts, losses = build()

    # placebo plumbing on a SYNTHETIC seeded signal
    synth = final.copy()
    synth["signal_w"] = np.random.default_rng(0).standard_normal(len(synth))
    before = synth.groupby(["season", "position"]).size()
    _ = placebo_draws(synth, 3, np.random.default_rng(0))
    assert before.equals(synth.groupby(["season", "position"]).size()), \
        "placebo altered group sizes"
    print("  assert placebo plumbing (synthetic signal): sizes preserved, "
          "shuffle confined to population rows: PASS")
    _embargo_selfcheck()
    print("  assert embargo: observed_cells referenced only inside fire(): PASS")

    # frozen-seed FIRE-TIME bars: FINAL first, then EARLY, one rng stream (pinned)
    rng = np.random.default_rng(PLACEBO_SEED)
    bar_final = float(np.percentile(placebo_draws(final, N_PLACEBO, rng), 95))
    bar_early = float(np.percentile(placebo_draws(early, N_PLACEBO, rng), 95))

    print(f"\n=== H11 F-step report (NO dated-window x outcome statistic) ===")
    print(f"  panel {PANEL[0]}-{PANEL[-1]} | FINAL frame rows {len(final)} | "
          f"EARLY frame rows {len(early)} | base subset 473")
    if losses:
        print(f"  window-match losses within tolerance (<=2%): {losses}")
    else:
        print("  window-match losses: NONE (100% subset coverage in every axis window)")
    print("  drafts per axis window by season:")
    for yr in PANEL:
        c = wcounts[yr]
        e = c.get("W1", 0) + c.get("W2", 0)
        print(f"    {yr}: EARLY:{e} " +
              " ".join(f"W{i}:{c.get(f'W{i}', 0)}" for i in range(3, 11)))
    print("  isotonic totals curve, fold t=2021 (fit 2014-2020 pool), implied pts "
          "at pos-rank 1/6/12/24/36:")
    for p in POS4:
        c = curves[(2021, p)]
        print(f"    {p}: " + "  ".join(f"r{r}={c[r]:.0f}" for r in (1, 6, 12, 24, 36)))
    print(f"  placebo: {N_PLACEBO} draws x 2 frames, seed {PLACEBO_SEED} (FROZEN), "
          f"scope = stable-role signal-present rows within position-season")
    print(f"  FIRE-TIME bars: FINAL {bar_final:.4f}  EARLY {bar_early:.4f}  "
          f"(design expectation ~{DESIGN_BAR})")
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(f"\n  script sha256: {sha}")
    print("  CODE IS FROZEN. --fire runs this exact code once, in a fresh session,")
    print("  after verifying this hash and the no-prior-fire check.")
    return frames, final, early, bar_final, bar_early


def fire():
    frames, final, early, bar_final, bar_early = substep_f()
    cells = observed_cells(final)
    pooled = pooled_stat(cells)
    season_pooled = {s: float(np.mean([cells[(s, p)] for p in POS4])) for s in PANEL}
    pos_means = {p: float(np.mean([cells[(s, p)] for s in PANEL])) for p in POS4}
    a = pooled > bar_final
    b = sum(v > 0 for v in season_pooled.values()) >= 4
    c = min(pos_means.values()) >= FLOOR
    verdict = "PASS" if (a and b and c) else "FAIL"
    headline = ("PASS" if verdict == "PASS" else
                "FAIL (freshness-controlled edge not established; true r up to "
                "~0.144 not excluded at 80% power)")

    print("\n" + "=" * 78)
    print("H11 — THE ONE SHOT (decision rule verbatim; gate = r_FINAL)")
    print("=" * 78)
    print(f"per-position 5-season mean r_FINAL: " +
          "  ".join(f"{p} {pos_means[p]:+.3f}" for p in POS4))
    print(f"season-level pooled r_FINAL: " +
          "  ".join(f"{s}:{v:+.3f}" for s, v in season_pooled.items()))
    print(f"\n  (a) pooled r_FINAL {pooled:+.3f} > frozen placebo bar "
          f"{bar_final:.3f} : {a}")
    print(f"  (b) positive pooled r_FINAL in "
          f"{sum(v > 0 for v in season_pooled.values())}/5 seasons >= 4 : {b}")
    print(f"  (c) worst position {min(pos_means.values()):+.3f} >= {FLOOR} : {c}")
    print(f"\nH11 VERDICT: {headline}")

    # declared descriptive curve (one execution, gates nothing, never promotable)
    curve = {}
    for grp in AXIS:
        cc = observed_cells(frames[grp])
        curve[grp] = pooled_stat(cc)
    r_early = curve["EARLY"]
    print(f"\nDESCRIPTIVE CURVE (declared; gates nothing, never promotable):")
    print("  " + "  ".join(f"{g}:{curve[g]:+.3f}" for g in AXIS))
    if verdict == "PASS":
        reading = ("PASS — edge survives freshness control; freshness share "
                   f"(descriptive) r_EARLY - r_FINAL = {r_early - pooled:+.3f}")
    elif r_early > bar_early:
        reading = ("FAIL, freshness-consistent pattern (r_EARLY "
                   f"{r_early:+.3f} > EARLY bar {bar_early:.3f}); H6 not revoked; "
                   "mechanism attribution narrows")
    else:
        reading = ("FAIL, flat pattern (r_EARLY does not clear its bar); "
                   "inconclusive decomposition; H6 stands as worded")
    print(f"\nPRE-COMMITTED READING APPLIED: {reading}")

    OUT_JSON.write_text(json.dumps(
        {"pooled_final": pooled, "bar_final": bar_final, "bar_early": bar_early,
         "season_pooled": season_pooled, "pos_means": pos_means,
         "criteria": {"a": bool(a), "b": bool(b), "c": bool(c)},
         "verdict": verdict, "headline": headline, "curve": curve,
         "reading": reading,
         "cells_final": {f"{s}_{p}": v for (s, p), v in cells.items()},
         "placebo_seed": PLACEBO_SEED, "n_placebo": N_PLACEBO},
        indent=2, default=float))
    print(f"wrote {OUT_JSON.name}")
    return verdict


if __name__ == "__main__":
    if "--fire" in sys.argv:
        fire()
    else:
        substep_f()
