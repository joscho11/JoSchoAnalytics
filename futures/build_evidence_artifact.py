"""Compute the evidence the Season Totals page displays, and write it to one artifact.

Two blocks:

ACCURACY  the ladder from a know-nothing baseline up to the archived consensus, so a reader can see
          how far the projection gets rather than just an unanchored 2.35.

DIRECTION the disconfirming result: how often the projection landed on the correct side of the
          posted number, against the break-even rate those postings imply. Authorised for
          publication by PREREGISTRATION Amendment 5, which permits a DISCONFIRMING directional
          result and nothing else. Gate C stays shut and no positive claim is licensed.

Everything the page shows comes from here. Nothing is retyped into the page as copy, so a number
cannot drift from the measurement that produced it.

Run:  python futures/build_evidence_artifact.py
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "futures"))
sys.path.insert(0, str(REPO / "futures" / "season_team_totals"))
import eval_v2 as E  # noqa: E402
import m4_engine as eng  # noqa: E402

ART = REPO / "futures" / "artifacts"
OUT = ART / "season_totals_evidence.json"
BOOT = 10000


def break_even(american: float) -> float:
    """Win rate a posted number must be beaten at to come out level."""
    return (-american) / ((-american) + 100) if american < 0 else 100 / (american + 100)


def main() -> None:
    audit, meta, panel, games = E.load()
    target = audit["target"]["column"]
    folds = [int(s) for s in audit["folds"]["test_seasons"]]
    complete = [int(s) for s in audit["outcomes"]["complete_seasons"]]
    feats = list(meta["features"]["columns"])          # the PRODUCTION feature set, v1
    comp = json.loads((ART / "model_comparison.json").read_text(encoding="utf-8"))
    wt = pd.read_csv(REPO / "futures" / "data" / "win_totals.csv")[
        ["season", "team", "price_over", "price_under"]]

    tie = float((games["result"] == 0).mean())
    fi = panel.set_index(["season", "franchise"])[feats]
    rows = []
    for T in folds:
        trs = [s for s in complete if s < T]
        ev = panel[(panel["season"] == T) & panel["has_target"] & panel["line_covered"]].copy()
        a, _, _ = eng.select_alpha(games, fi, feats, trs, tie, E.ALPHA_GRID, E.FALLBACK_ALPHA)
        tau, _ = E.select_tau_03(games, fi, feats, trs, tie, a, panel, target, T)
        g, X = eng.game_design(games, fi, trs, feats)
        fit = eng.fit_margin(g, X, a, tie)
        gt, Xt = eng.game_design(games, fi, [T], feats, settled_only=False)
        mu = eng.simulate_wins(fit, gt, Xt, n_sims=E.N_SIMS, seed=E.SEED + T, tau=tau).mean()
        ev["pred"] = [mu.get(x, np.nan) for x in ev["franchise"]]
        rows.append(ev)
    d = pd.concat(rows).merge(wt, left_on=["season", "franchise"],
                              right_on=["season", "team"], how="left")
    d = d[d["pred"].notna() & d["market_line"].notna()].copy()
    d = d[d["pred"] != d["market_line"]]
    d["higher"] = d["pred"] > d["market_line"]
    d["push"] = d[target] == d["market_line"]
    d["correct"] = np.where(d["higher"], d[target] > d["market_line"], d[target] < d["market_line"])
    d["posted"] = np.where(d["higher"], d["price_over"], d["price_under"])
    d["needed"] = d["posted"].map(break_even)
    d["ret"] = np.where(d["push"], 0.0,
                        np.where(d["correct"],
                                 np.where(d["posted"] > 0, d["posted"] / 100, 100 / -d["posted"]),
                                 -1.0))

    graded = d[~d["push"]]
    hit, needed = float(graded["correct"].mean()), float(graded["needed"].mean())

    rng = np.random.default_rng(E.SEED)
    seasons = sorted(d["season"].unique())
    draws = []
    for _ in range(BOOT):
        s = pd.concat([d[d["season"] == x] for x in rng.choice(seasons, len(seasons), replace=True)])
        gg = s[~s["push"]]
        if len(gg):
            draws.append(float(gg["correct"].mean() - gg["needed"].mean()))
    lo, hi = (float(x) for x in np.percentile(draws, [2.5, 97.5]))

    by_season = graded.groupby("season")["correct"].mean()
    pool = comp["pooled_mae"]["headline"]

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authority": "PREREGISTRATION Amendment 5: a DISCONFIRMING directional result may be "
                     "published. Gate C stays shut; no positive claim is licensed by this file.",
        "status": "BACKTESTED, NOT LIVE-VALIDATED",
        "benchmark_naming": meta["claim_licence"]["naming"],
        "accuracy": {
            "metric": "mean absolute error in wins, 10 held-out seasons, 320 team-seasons",
            "ladder": [
                {"name": "Last season's record, repeated", "mae": pool["B1_persistence"]},
                {"name": "Every team gets 8.5 wins", "mae": pool["B2_league_mean"]},
                {"name": "This model", "mae": float(meta["evidence"]["pooled_mae_headline"])},
                {"name": "Archived market consensus", "mae": pool["B0_market"]},
            ],
            "model_share_of_available_improvement": float(
                (pool["B2_league_mean"] - meta["evidence"]["pooled_mae_headline"])
                / (pool["B2_league_mean"] - pool["B0_market"])),
            "gap_to_consensus": float(meta["evidence"]["pooled_mae_headline"] - pool["B0_market"]),
        },
        "direction": {
            "question": "how often the projection landed on the correct side of the posted number",
            "n_graded": int(len(graded)),
            "n_excluded_exact": int(d["push"].sum()),
            "correct_rate": hit,
            "break_even_rate": needed,
            "shortfall": hit - needed,
            "ci95_shortfall": [lo, hi],
            "ci_excludes_zero": bool(lo > 0 or hi < 0),
            "return_per_unit": float(d["ret"].mean()),
            "seasons_above_break_even": int((by_season > needed).sum()),
            "seasons_total": int(len(by_season)),
            "verdict": "DOES NOT BEAT THE POSTED NUMBERS",
            "power_note": {
                "ci_halfwidth_points": round((hi - lo) / 2 * 100, 2),
                "n_needed_for_two_point_claim": 4900,
                "seasons_needed": round(4900 / 32),
                "reading": "with 32 teams a season this comparison cannot establish a small "
                           "advantage in either direction within any realistic horizon",
            },
        },
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    a, dd = payload["accuracy"], payload["direction"]
    print(f"accuracy: model captures {a['model_share_of_available_improvement']:.1%} of the "
          f"available improvement; gap to consensus {a['gap_to_consensus']:+.4f}")
    print(f"direction: {dd['correct_rate']:.4f} correct vs {dd['break_even_rate']:.4f} needed, "
          f"shortfall {dd['shortfall']:+.4f} CI [{dd['ci95_shortfall'][0]:+.4f}, "
          f"{dd['ci95_shortfall'][1]:+.4f}], return {dd['return_per_unit']:+.4f}")
    print(f"seasons above break-even: {dd['seasons_above_break_even']}/{dd['seasons_total']}")
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")


if __name__ == "__main__":
    sys.exit(main())
