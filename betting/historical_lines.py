"""Historical NFL opening/closing lines (aussportsbetting) -> clean dataset + analysis.

Free data (manually downloaded to betting/data/nfl.xlsx; Cloudflare blocks scripts).
Used for two things: (1) answer "do lines move open->close, enough for CLV to be a
real lever?" (a documented open question) with zero model and zero leakage, and
(2) feed the CLV backtest (clv_backtest.py).

Sign convention: aussportsbetting "Home Line" is negative when the home team is
favored (standard -9.5 lay). We negate it to nflverse convention (positive = home
favored), matching predictions_tracker's `spread_line`.

    python betting/historical_lines.py movement              # open->close movement analysis
    python betting/historical_lines.py movement --since 2014
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from odds_client import NFL_TEAMS

DATA = Path(__file__).resolve().parent / "data" / "nfl.xlsx"

# historical / relocated names not in the current-32 map, mapped to current franchise abbr
TEAM_ALIASES = {
    "Oakland Raiders": "LV", "San Diego Chargers": "LAC", "St. Louis Rams": "LA",
    "Washington Redskins": "WAS", "Washington Football Team": "WAS",
}


def _abbr(name: str) -> str | None:
    return NFL_TEAMS.get(name) or TEAM_ALIASES.get(name)


def load_lines(path: Path = DATA, require_close: bool = True) -> pd.DataFrame:
    """Clean per-game lines in nflverse sign (positive spread = home favored)."""
    raw = pd.read_excel(path, engine="openpyxl")
    df = pd.DataFrame({
        "date": pd.to_datetime(raw["Date"]),
        "home": raw["Home Team"].map(_abbr),
        "away": raw["Away Team"].map(_abbr),
        "home_score": raw["Home Score"], "away_score": raw["Away Score"],
        # negate to nflverse convention (positive = home favored)
        "spread_open": -raw["Home Line Open"],
        "spread_close": -raw["Home Line Close"],
        "total_open": raw["Total Score Open"],
        "total_close": raw["Total Score Close"],
        "playoff": raw["Playoff Game?"].notna(),
    })
    # NFL season convention: Jan/Feb playoff games belong to the prior calendar
    # year's season (else they spawn a phantom next-year season).
    df["season"] = df["date"].dt.year - (df["date"].dt.month <= 2).astype(int)
    df = df.dropna(subset=["home", "away", "spread_open"])
    if require_close:
        df = df.dropna(subset=["spread_close"])
    return df.reset_index(drop=True)


def movement_summary(df: pd.DataFrame) -> dict:
    spread_move = (df["spread_close"] - df["spread_open"]).abs()
    total_move = (df["total_close"] - df["total_open"]).abs()
    return {
        "games": len(df),
        "seasons": f"{df['season'].min()}-{df['season'].max()}",
        "spread": {
            "mean_abs_move": float(spread_move.mean()),
            "median_abs_move": float(spread_move.median()),
            "pct_moved_0.5+": float((spread_move >= 0.5).mean() * 100),
            "pct_moved_1+": float((spread_move >= 1.0).mean() * 100),
            "pct_moved_2+": float((spread_move >= 2.0).mean() * 100),
            "max_move": float(spread_move.max()),
        },
        "total": {
            # ONE denominator (review U4A-4): all stats on the non-null total moves;
            # NaN >= 1.0 silently coerces False and understated the pcts before.
            "mean_abs_move": float(total_move.dropna().mean()),
            "pct_moved_1+": float((total_move.dropna() >= 1.0).mean() * 100),
            "pct_moved_2+": float((total_move.dropna() >= 2.0).mean() * 100),
            "n_totals": int(total_move.notna().sum()),
        },
    }


def closing_is_sharper(df: pd.DataFrame) -> dict:
    """Does the CLOSING line predict the result better than the OPENING line?
    Lower mean abs error = sharper. If close >> open, CLV (beating the close) is
    worth chasing; if equal, the open is already efficient."""
    d = df.dropna(subset=["home_score", "away_score"]).copy()
    margin = d["home_score"] - d["away_score"]
    err_open = (margin - d["spread_open"]).abs()
    err_close = (margin - d["spread_close"]).abs()
    # ATS: did the side the line moved toward end up covering the closing number?
    return {
        "mae_open": float(err_open.mean()),
        "mae_close": float(err_close.mean()),
        "close_better_pct": float((err_close < err_open).mean() * 100),
    }


def movement_cmd(args) -> None:
    df = load_lines()
    if args.since:
        df = df[df["season"] >= args.since]
    if not args.playoffs:
        df = df[~df["playoff"]]
    m = movement_summary(df)
    s = m["spread"]
    print(f"NFL line movement (open->close), {m['seasons']}, {m['games']} games\n")
    print("  SPREAD:")
    print(f"    mean |move|     {s['mean_abs_move']:.2f} pts   median {s['median_abs_move']:.2f}")
    print(f"    moved >= 0.5    {s['pct_moved_0.5+']:.0f}% of games")
    print(f"    moved >= 1.0    {s['pct_moved_1+']:.0f}%")
    print(f"    moved >= 2.0    {s['pct_moved_2+']:.0f}%   (max {s['max_move']:.1f})")
    t = m["total"]
    print(f"  TOTAL:")
    print(f"    mean |move|     {t['mean_abs_move']:.2f} pts   "
          f">=1: {t['pct_moved_1+']:.0f}%  >=2: {t['pct_moved_2+']:.0f}%")
    sharp = closing_is_sharper(df)
    print(f"\n  Is the close sharper than the open?")
    print(f"    spread MAE  open {sharp['mae_open']:.2f}  ->  close {sharp['mae_close']:.2f}"
          f"   (close better in {sharp['close_better_pct']:.0f}% of games)")
    verdict = ("lines move materially -- CLV is a real lever, worth tracking"
               if s["pct_moved_1+"] > 40 else
               "lines are fairly static -- CLV upside is limited")
    print(f"\n  => {verdict}")


def main() -> None:
    p = argparse.ArgumentParser(description="Historical NFL line movement")
    sub = p.add_subparsers(dest="cmd", required=True)
    mv = sub.add_parser("movement", help="open->close movement analysis")
    mv.add_argument("--since", type=int, help="first season to include")
    mv.add_argument("--playoffs", action="store_true", help="include playoff games")
    mv.set_defaults(func=movement_cmd)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
