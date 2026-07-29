"""ARM 3 — PERSONNEL-ADJUSTED COACH EFFECT.

Governing prereg §4 ARM 3. Two stages, both strictly expanding:

  STAGE 1  For every historical team-season S, fit an expectation model on seasons < S ONLY,
           target = offensive EPA/play in S, using the frozen preseason controls in
           personnel_controls.csv (lagged team form, prior QB identity/continuity, prior QB
           EPA + CPOE, returning attempt/carry/target shares, vacated opportunity, prior plays
           and pass rate, prior OL sack rate, relocation, season effects). NO season-S player
           performance may enter. Then
               team_offense_residual = actual_epa_play - expected_epa_play

  STAGE 2  For every target season Y, take ONLY residuals from seasons < Y and fit a ridge with
           separate HEAD-COACH and PLAY-CALLER identity blocks (cross-classified, partially
           pooled). Regularisation is chosen by cross-validation INSIDE the training residuals —
           the outer test season is never consulted.

IDENTIFIABILITY (§4): where one person is both head coach and play-caller, the two identity
columns are perfectly collinear for that team-season. Those rows are assigned to a SINGLE
offensive-lead column carried in `hc_adjusted_offense_effect`, and the `pc_` effect for that
person is left as no-history rather than duplicating the same number into both. Asserted by T4.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, RidgeCV

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
K_SHRINK = 32
ALPHAS = np.logspace(-1, 3, 25)

CONTROLS = ["prior_epa_play", "prior_success_rate", "prior_points_per_drive", "prior_plays",
            "prior_pass_rate", "prior_ol_sack_rate", "prior_qb_epa_play", "prior_qb_cpoe",
            "qb_returns", "ret_qb_attempt_share", "ret_rb_carry_share", "ret_wrte_target_share",
            "vacated_rush_share", "vacated_target_share", "ret_skill_fantasy_share", "relocated"]


def stage1_residuals(first=2015, last=2025):
    """Expanding expectation model -> team_offense_residual for every team-season."""
    panel = pd.read_csv(DATA / "team_offense_panel.csv")[["season", "team", "epa_play"]]
    ctrl = pd.read_csv(DATA / "personnel_controls.csv")
    df = panel.merge(ctrl, on=["season", "team"], how="left")
    df["prior_qb_same"] = df["qb_returns"].fillna(0.0)

    out = []
    for S in range(first, last + 1):
        tr = df[(df.season < S)].dropna(subset=["epa_play"])
        te = df[df.season == S]
        if len(tr) < 40 or not len(te):
            continue
        cols = [c for c in CONTROLS if c in df.columns]
        Xtr = tr[cols].astype(float)
        Xte = te[cols].astype(float)
        med = Xtr.median()
        Xtr = Xtr.fillna(med).fillna(0.0)
        Xte = Xte.fillna(med).fillna(0.0)
        # season fixed effect = training-season mean of the target, applied as an intercept shift
        m = RidgeCV(alphas=ALPHAS).fit(Xtr.to_numpy(), tr["epa_play"].to_numpy())
        pred = m.predict(Xte.to_numpy())
        r = te[["season", "team", "epa_play"]].copy()
        r["expected_epa_play"] = pred
        r["team_offense_residual"] = r["epa_play"] - r["expected_epa_play"]
        r["n_train"] = len(tr)
        out.append(r)
    res = pd.concat(out, ignore_index=True)
    res.to_csv(DATA / "arm3_residuals.csv", index=False)
    return res


def stage2_effects(res, seasons):
    """Cross-classified HC / play-caller ridge on residuals from seasons < Y."""
    cf = pd.read_csv(DATA / "coach_features.csv")[
        ["season", "team", "hc_person_id", "pc_person_id"]]
    r = res.merge(cf, on=["season", "team"], how="left")

    rows = []
    for Y in seasons:
        h = r[(r.season < Y) & r.team_offense_residual.notna()].copy()
        if len(h) < 40:
            continue
        # collapse to a single offensive-lead identity where HC == PC (identifiability, §4)
        h["same"] = (h["hc_person_id"] == h["pc_person_id"]) & h["pc_person_id"].notna()
        hc_ids = sorted(h["hc_person_id"].dropna().unique())
        pc_ids = sorted(h.loc[~h["same"], "pc_person_id"].dropna().unique())
        idx_hc = {p: i for i, p in enumerate(hc_ids)}
        idx_pc = {p: len(hc_ids) + i for i, p in enumerate(pc_ids)}
        X = np.zeros((len(h), len(hc_ids) + len(pc_ids)))
        for j, (_, row) in enumerate(h.iterrows()):
            if pd.notna(row["hc_person_id"]):
                X[j, idx_hc[row["hc_person_id"]]] = 1.0
            if (not row["same"]) and pd.notna(row["pc_person_id"]):
                X[j, idx_pc[row["pc_person_id"]]] = 1.0
        y = h["team_offense_residual"].to_numpy(float)
        # regularisation selected INSIDE the training residuals only
        cv = RidgeCV(alphas=ALPHAS).fit(X, y)
        model = Ridge(alpha=float(cv.alpha_)).fit(X, y)
        coef = model.coef_

        games = h.groupby("hc_person_id").size()
        for p, i in idx_hc.items():
            n = int(games.get(p, 0))
            rows.append(dict(season=Y, person_id=p, role="hc", effect=coef[i],
                             n_seasons=n, reliability=n / (n + K_SHRINK / 16),
                             alpha=float(cv.alpha_)))
        gp = h.loc[~h["same"]].groupby("pc_person_id").size()
        for p, i in idx_pc.items():
            n = int(gp.get(p, 0))
            rows.append(dict(season=Y, person_id=p, role="pc", effect=coef[i],
                             n_seasons=n, reliability=n / (n + K_SHRINK / 16),
                             alpha=float(cv.alpha_)))
    return pd.DataFrame(rows)


def build(seasons=None):
    seasons = seasons or list(range(2016, 2027))
    print("=" * 80)
    print("ARM 3 — personnel-adjusted coach effects (expanding expectation + cross-classified ridge)")
    print("=" * 80)

    res = stage1_residuals()
    print(f"\nSTAGE 1: {len(res)} team-season residuals, {res.season.min()}-{res.season.max()}")
    print(f"  residual mean {res.team_offense_residual.mean():+.4f} "
          f"sd {res.team_offense_residual.std():.4f}")
    print("  worst/best 2024 residuals (actual minus preseason expectation):")
    s24 = res[res.season == 2024]
    print(s24.nlargest(3, "team_offense_residual")[
        ["team", "epa_play", "expected_epa_play", "team_offense_residual"]].to_string(index=False))
    print(s24.nsmallest(3, "team_offense_residual")[
        ["team", "epa_play", "expected_epa_play", "team_offense_residual"]].to_string(index=False))

    eff = stage2_effects(res, seasons)
    eff.to_csv(DATA / "arm3_effects.csv", index=False)
    print(f"\nSTAGE 2: {len(eff)} (coach, season) effects | "
          f"{eff.role.value_counts().to_dict()}")
    print(f"  ridge alpha chosen inside training residuals: "
          f"{sorted(eff.alpha.unique())[:5]}")

    print("\nSANITY — largest positive adjusted offensive-lead effects entering 2026:")
    e26 = eff[eff.season == 2026].nlargest(8, "effect")
    print(e26[["person_id", "role", "effect", "n_seasons"]].to_string(index=False))
    print("\nSANITY — McDaniel / McVay adjusted effects entering 2026 (reported as computed):")
    for pid in ("mike_mcdaniel", "sean_mcvay"):
        sub = eff[(eff.season == 2026) & (eff.person_id == pid)]
        if len(sub):
            for _, x in sub.iterrows():
                print(f"  {pid:16s} role={x.role} effect={x.effect:+.5f} n_seasons={x.n_seasons}")
        else:
            print(f"  {pid:16s} no effect estimated (collapsed into offensive-lead or no history)")
    print(f"\nwrote {DATA/'arm3_residuals.csv'} + {DATA/'arm3_effects.csv'}")
    return eff


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    else:
        raise SystemExit("pass --build")
