"""Turn the spread model's abstract edge into an honest, user-facing cover probability.

The dashboard's bettor-first job is to answer "how often do bets like this actually
win?" — not "what is the model's point edge?". This module computes that answer from
the graded prediction history (``predictions_tracker.csv``) and reports it with a
Wilson confidence interval so the small live sample stays legible instead of being
dressed up as certainty.

Design choices (deliberate, given the data):

- **Calibrate on the tier, not a continuous edge curve.** The confidence tier
  (HIGH/MEDIUM/PASS) is the production decision unit, and edge is collinear with it
  (HIGH ≈ edge ≥ 3, PASS ≈ edge < 1). Fitting a smooth edge→probability curve on ~100
  live games overfits noise — the project's whole ethos is to not do that. Edge buckets
  are still computed, but only as a diagnostic, and a bucket is only trusted for a
  point estimate once it clears ``MIN_BUCKET_N``.
- **Wilson interval, not normal approximation.** Small n and rates near the 52.4%
  break-even are exactly where the normal approximation lies; Wilson does not.
- **Pools whatever it's given.** Feed it one season or five — it recomputes from the
  graded rows present, so it sharpens automatically as the live record grows.

Pure functions, no Streamlit, no I/O — unit-tested in ``test_calibration.py`` (CI).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

# Break-even ATS hit rate at standard -110 odds (risk 110 to win 100).
BREAKEVEN = 0.524

# Default edge buckets (absolute ensemble edge, in points). Right-open intervals.
EDGE_BINS = [0.0, 1.0, 2.0, 3.0, 5.0, float("inf")]

# A tier/bucket needs at least this many graded games before its own hit rate is
# trusted as a point estimate; below it we fall back to a broader basis.
MIN_BUCKET_N = 10


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95%-by-default Wilson score interval for a binomial proportion.

    Returns ``(0.0, 1.0)`` for an empty sample so callers can render "no data" without
    special-casing a ``None``.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass(frozen=True)
class Estimate:
    """A cover-probability estimate for one group of bets."""

    rate: float          # observed hit rate (point estimate)
    lo: float            # Wilson lower bound
    hi: float            # Wilson upper bound
    n: int               # graded games in the group
    wins: int            # games covered
    basis: str           # what the estimate keys on: "tier:HIGH", "edge:[1,2)", "overall"

    @property
    def beats_breakeven(self) -> bool:
        """True only if the *lower* bound clears break-even — the honest bar."""
        return self.lo > BREAKEVEN

    @property
    def edge_pp(self) -> float:
        """Point-estimate edge over break-even, in percentage points."""
        return (self.rate - BREAKEVEN) * 100


def _group_estimate(frame: pd.DataFrame, correct_col: str, basis: str) -> Estimate:
    n = int(len(frame))
    wins = int(frame[correct_col].sum()) if n else 0
    rate = wins / n if n else 0.0
    lo, hi = wilson_interval(wins, n)
    return Estimate(rate=rate, lo=lo, hi=hi, n=n, wins=wins, basis=basis)


def _edge_bucket_label(edge_abs: float, bins=EDGE_BINS) -> str:
    for left, right in zip(bins, bins[1:]):
        if left <= edge_abs < right:
            hi = "inf" if math.isinf(right) else _trim(right)
            return f"[{_trim(left)},{hi})"
    return f"[{_trim(bins[-1])},inf)"  # edge exactly at/over the top edge


def _trim(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def build_calibration(
    df: pd.DataFrame,
    *,
    correct_col: str = "ens_model_correct",
    tier_col: str = "consensus_tier",
    edge_col: str = "ens_model_edge",
    edge_bins=EDGE_BINS,
) -> dict:
    """Compute calibration tables from a (possibly ungraded) tracker DataFrame.

    Only rows with a non-null ``correct_col`` are used, so it's safe to pass the raw
    tracker mid-week. Returns a dict with ``overall``, ``by_tier``, ``by_edge_bucket``
    (each mapping to an :class:`Estimate`) plus light provenance.
    """
    needed = {correct_col, tier_col, edge_col}
    missing = needed - set(df.columns)
    if missing:
        raise KeyError(f"tracker is missing required columns: {sorted(missing)}")

    g = df.dropna(subset=[correct_col]).copy()
    g[correct_col] = g[correct_col].astype(int)

    overall = _group_estimate(g, correct_col, "overall")

    by_tier: dict[str, Estimate] = {}
    for tier, frame in g.groupby(tier_col):
        by_tier[str(tier)] = _group_estimate(frame, correct_col, f"tier:{tier}")

    by_edge_bucket: dict[str, Estimate] = {}
    if len(g):
        g["_abs_edge"] = g[edge_col].abs()
        g["_bucket"] = pd.cut(g["_abs_edge"], edge_bins, right=False)
        for bucket, frame in g.groupby("_bucket", observed=True):
            label = _edge_bucket_label(frame["_abs_edge"].iloc[0], edge_bins)
            by_edge_bucket[label] = _group_estimate(frame, correct_col, f"edge:{label}")

    return {
        "overall": overall,
        "by_tier": by_tier,
        "by_edge_bucket": by_edge_bucket,
        "edge_bins": list(edge_bins),
        "seasons": sorted(g["season"].unique().tolist()) if "season" in g else [],
        "n_graded": int(len(g)),
    }


def cover_probability(tier: str | None, calib: dict) -> Estimate:
    """Honest cover-probability estimate for a single upcoming pick.

    Keys on the confidence tier (the stable, production-relevant signal). Falls back to
    the pooled ``overall`` rate when the tier is unknown or too thin to trust on its own
    (< ``MIN_BUCKET_N`` graded games) — so a brand-new tier never shows a wild rate off
    two games.
    """
    by_tier = calib.get("by_tier", {})
    est = by_tier.get(str(tier)) if tier is not None else None
    if est is not None and est.n >= MIN_BUCKET_N:
        return est
    return calib["overall"]


def card_line(tier: str | None, calib: dict) -> str:
    """One honest sentence for a dashboard pick card.

    e.g. ``"HIGH-confidence bets have covered 64.7% (95% CI 41–83%, n=17)."``
    The CI is the point — it stops a hot 17-game stretch from reading as a guarantee.
    """
    est = cover_probability(tier, calib)
    label = f"{tier}-confidence bets" if tier and est.basis.startswith("tier") else "Bets at this model"
    return (
        f"{label} have covered {est.rate * 100:.1f}% "
        f"(95% CI {est.lo * 100:.0f}–{est.hi * 100:.0f}%, n={est.n})."
    )
