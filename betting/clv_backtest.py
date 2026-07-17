"""Historical CLV backtest: did the model's picks beat the line — honestly?

Joins model predictions to historical opening & closing spreads (historical_lines),
derives the pick AT THE OPENING line, and reports:
  - ATS-vs-OPEN  = did the pick cover the line you'd actually have bet (the real
    realized win rate, pushes excluded). THIS is the headline.
  - ATS-vs-close = cover vs the closing line (a CLV-direction diagnostic, NOT a
    bet you could place; it flatters a line-correlated model).
  - CLV           = how far the line moved toward the pick (open->close).

IMPORTANT (council 2026-06-18): if the predictions come from a model whose
`spread_line` feature is the CLOSING line, "beating the close" is partly
mechanical. Use predictions generated with the OPENING line as the line feature
(`experiments/walkforward_oos_preds.py --line open`) for an honest read.

    python betting/clv_backtest.py --preds experiments/walkforward_oos_preds_openline.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import historical_lines as hl

TRACKER = Path(__file__).resolve().parent / "predictions_tracker.csv"
# nflverse uses the contemporaneous abbrev (OAK/SD/STL); historical_lines uses the
# current franchise code. Normalize predictions before the join or relocated-team
# games (≈5%) silently drop and bias the sample.
FRANCHISE_NORM = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


def clv_points(spread_open: float, spread_close: float, side: str) -> float:
    """nflverse sign (positive = home favored). HOME pick benefits when the home
    side gets MORE favored by close (close > open); AWAY pick benefits the opposite."""
    if side == "HOME":
        return round(spread_close - spread_open, 2)
    if side == "AWAY":
        return round(spread_open - spread_close, 2)
    return float("nan")


def _cover(margin: pd.Series, line: pd.Series, side: pd.Series) -> np.ndarray:
    """1 = pick covered, 0 = lost, NaN = push (margin == line, no action)."""
    diff = margin - line  # > 0 => home covers
    home_res = np.where(diff > 0, 1.0, np.where(diff < 0, 0.0, np.nan))
    return np.where(side.values == "HOME", home_res, 1.0 - home_res)


def run(min_edge: float, preds_path: str | None = None) -> pd.DataFrame:
    src = Path(preds_path) if preds_path else TRACKER
    preds = pd.read_csv(src).dropna(subset=["predicted_margin"]).copy()
    datecol = "gameday" if "gameday" in preds.columns else "date"
    preds["date"] = pd.to_datetime(preds[datecol])
    for col in ("home_team", "away_team"):
        preds[col] = preds[col].replace(FRANCHISE_NORM)
    lines = hl.load_lines().rename(columns={"home_score": "ls_home", "away_score": "ls_away"})

    df = preds.merge(lines[["date", "home", "away", "spread_open", "spread_close",
                            "ls_home", "ls_away"]],
                     left_on=["date", "home_team", "away_team"],
                     right_on=["date", "home", "away"], how="inner",
                     validate="one_to_one")   # dup fan-out guard (review U4A-11)
    dropped = len(preds) - len(df)
    if dropped > 0.05 * len(preds):
        miss = preds.merge(lines[["date", "home", "away"]], left_on=["date", "home_team", "away_team"],
                           right_on=["date", "home", "away"], how="left", indicator=True)
        miss = miss[miss["_merge"] == "left_only"][["date", "home_team", "away_team"]]
        print(f"  WARNING: {dropped}/{len(preds)} predictions ({dropped/len(preds)*100:.0f}%) did not "
              f"join historical lines (team/date mismatch). First few unmatched:")
        print(miss.head(8).to_string(index=False))
    if df.empty:
        return df

    df["open_edge"] = df["predicted_margin"] - df["spread_open"]
    df["side"] = np.where(df["open_edge"] >= min_edge, "HOME",
                          np.where(df["open_edge"] <= -min_edge, "AWAY", "PASS"))
    # production tier at the OPENING line (3 voters agree on direction + edge size)
    voters = {"xgb_margin", "ridge_margin", "lgbm_margin"}
    if voters.issubset(df.columns):
        ex, er = np.sign(df["xgb_margin"] - df["spread_open"]), np.sign(df["ridge_margin"] - df["spread_open"])
        el, es = np.sign(df["lgbm_margin"] - df["spread_open"]), np.sign(df["open_edge"])
        agree = (ex == er) & (er == el) & (ex == es)
        ae = df["open_edge"].abs()
        df["tier"] = np.where(agree & (ae >= 3), "HIGH", np.where(agree & (ae >= 1), "MEDIUM", "PASS"))
        tier_method = "voter-reconstructed @ open"
    else:
        df["tier"] = df.get("consensus_tier", "NA")
        tier_method = "stored consensus_tier (set vs CLOSE — not comparable to open-derived picks)"

    df = df[df["side"] != "PASS"].copy()
    df["clv"] = [clv_points(o, c, s) for o, c, s in zip(df["spread_open"], df["spread_close"], df["side"])]
    margin = df["ls_home"] - df["ls_away"]
    df["won_open"] = _cover(margin, df["spread_open"], df["side"])    # the bet you placed
    df["won_close"] = _cover(margin, df["spread_close"], df["side"])  # CLV diagnostic only
    df.attrs["tier_method"] = tier_method
    return df


def _summary(df: pd.DataFrame, label: str) -> None:
    n = len(df)
    if n == 0:
        print(f"  {label:18s} n=0")
        return
    ats_open = np.nanmean(df["won_open"]) * 100
    ats_close = np.nanmean(df["won_close"]) * 100
    beat = (df["clv"] > 0).mean() * 100
    avg = df["clv"].mean()
    print(f"  {label:18s} n={n:4d}  ATS-vs-open {ats_open:4.0f}%  "
          f"(vs-close {ats_close:4.0f}%)  beat-close {beat:4.0f}%  avgCLV {avg:+.2f}")


def main() -> None:
    p = argparse.ArgumentParser(description="Historical CLV backtest of model picks")
    p.add_argument("--min-edge", type=float, default=1.0,
                   help="min |predicted_margin - opening line| to make a pick (default 1.0)")
    p.add_argument("--preds", default=None,
                   help="out-of-sample predictions CSV; default = predictions_tracker.csv")
    args = p.parse_args()

    df = run(args.min_edge, args.preds)
    if df.empty:
        print("No prediction rows joined to historical lines (date/team mismatch).")
        return

    seasons = f"{int(df['season'].min())}-{int(df['season'].max())}"
    print(f"\n=== CLV backtest, {seasons}, edge>={args.min_edge} ===")
    print(f"  tier method: {df.attrs.get('tier_method')}")
    print("  ATS-vs-open = the bet you actually placed (headline); pushes excluded.\n")
    _summary(df, "ALL picks")
    _summary(df[df["tier"].isin(["HIGH", "MEDIUM"])], "HIGH+MEDIUM")
    print()
    for tier in ["HIGH", "MEDIUM", "PASS"]:
        g = df[df["tier"] == tier]
        if len(g):
            _summary(g, f"  tier {tier}")


if __name__ == "__main__":
    main()
