"""Tier-weighted fractional-Kelly staking, sized off the out-of-sample edge.

Win probability = each tier's **ATS-vs-OPEN** cover rate from the CLV backtest —
the bet you'd actually have placed (pushes excluded). Use predictions generated
with the OPENING line as the line feature (`..._openline.csv`), or the win rate is
confounded by a closing-line-anchored model. Then size by Kelly, conservatively:
  1. Size off the Wilson lower confidence bound, not the point estimate.
  2. Fractional Kelly (default 1/4) + a hard per-bet cap.
  3. Tiers whose conservative edge doesn't clear the break-even price get $0.

    python betting/kelly_staking.py --preds experiments/walkforward_oos_preds_openline.csv
    python betting/kelly_staking.py --odds -110 --kelly-fraction 0.25 --cap 0.02
"""
from __future__ import annotations

import argparse
import math

import numpy as np

import clv_backtest as cb

OOS_PREDS = "experiments/walkforward_oos_preds_openline.csv"


def american_to_decimal(a: float) -> float:
    return 1 + (a / 100 if a > 0 else 100 / abs(a))


def wilson_lower(wins: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for a binomial rate."""
    if n == 0:
        return 0.0
    phat = wins / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    return (center - margin) / denom


def kelly_fraction(p: float, dec_odds: float) -> float:
    """Full-Kelly stake fraction for win prob p at decimal odds. Floored at 0."""
    b = dec_odds - 1
    return max(0.0, (p * (b + 1) - 1) / b)


def tier_stats(preds_path: str, min_edge: float) -> dict:
    """(wins, n) per tier from the realized bet (ATS vs the OPEN you placed,
    pushes excluded) — the honest win probability to size Kelly against."""
    df = cb.run(min_edge, preds_path)
    out = {}
    for tier in ["HIGH", "MEDIUM", "PASS"]:
        g = df[(df["tier"] == tier) & df["won_open"].notna()]  # drop pushes
        if len(g):
            out[tier] = (int(np.nansum(g["won_open"])), len(g))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Tier-weighted fractional-Kelly staking plan")
    p.add_argument("--bankroll", type=float, default=1000.0)
    p.add_argument("--odds", type=float, default=-110, help="American odds of the bet (default -110)")
    p.add_argument("--kelly-fraction", type=float, default=0.25, help="fraction of full Kelly (default 1/4)")
    p.add_argument("--cap", type=float, default=0.02, help="max stake per bet as bankroll fraction (default 2%)")
    p.add_argument("--confidence", type=float, default=1.96, help="z for the Wilson lower bound (default 95%)")
    p.add_argument("--min-edge", type=float, default=1.0)
    p.add_argument("--preds", default=OOS_PREDS)
    args = p.parse_args()

    dec = american_to_decimal(args.odds)
    breakeven = 1 / dec
    stats = tier_stats(args.preds, args.min_edge)
    if not stats:
        print("No tier stats (predictions didn't join to historical lines).")
        return

    print(f"=== Tier-weighted Kelly staking plan ===")
    print(f"  bankroll ${args.bankroll:,.0f}   price {args.odds:+.0f} (decimal {dec:.3f}, "
          f"break-even {breakeven*100:.1f}%)")
    print(f"  sizing: {args.kelly_fraction:g} Kelly, off the Wilson 95% lower bound, "
          f"capped at {args.cap*100:.1f}%/bet\n")
    print(f"  {'tier':6s} {'n':>4} {'win%':>6} {'95%lo':>7} {'edge':>6} "
          f"{'fullKelly':>10} {'stake%':>7} {'$/bet':>7}")
    print("  " + "-" * 64)

    total_note = []
    # only the production-bettable tiers — PASS means "don't bet" (voters disagree),
    # so it's excluded even if a noisy subsample looks positive.
    for tier in ["HIGH", "MEDIUM"]:
        if tier not in stats:
            continue
        wins, n = stats[tier]
        phat = wins / n
        p_lo = wilson_lower(wins, n, args.confidence)
        edge = p_lo - breakeven
        f_full = kelly_fraction(p_lo, dec)
        stake_pct = min(f_full * args.kelly_fraction, args.cap) if p_lo > breakeven else 0.0
        dollars = stake_pct * args.bankroll
        flag = "" if stake_pct > 0 else "  <- no edge at this price"
        print(f"  {tier:6s} {n:>4} {phat*100:5.0f}% {p_lo*100:6.1f}% {edge*100:+5.1f}% "
              f"{f_full*100:9.1f}% {stake_pct*100:6.1f}% {dollars:6.0f}{flag}")
        if stake_pct > 0:
            total_note.append((tier, stake_pct, dollars))

    print()
    if total_note:
        for t, pct, d in total_note:            # EVERY clearing tier (review U4A-10)
            print(f"  => Bet the {t} tier at {pct*100:.1f}% (${d:.0f}) per play.")
        print("     Tiers not listed don't clear the vig on this conservative read.")
    else:
        print("  => No tier clears break-even on the conservative read at this price.")
    print(f"\n  Win prob = ATS vs the line you BET (the open), out-of-sample, pushes excluded.")
    print(f"  The model does NOT beat the close (no CLV edge) — the edge is raw ATS skill on")
    print(f"  HIGH-tier picks. Re-fit as the live 2026 record grows.")


if __name__ == "__main__":
    main()
