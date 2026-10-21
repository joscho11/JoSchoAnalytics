"""Postgame ranking accuracy for the Weekly Fantasy page.

This module intentionally contains no Streamlit code. The page and its tests
share one definition of every number under "How the rankings did". It reads
the rows of a completely graded weekly release (projected_pts, slp_proj,
actual_half_ppr) and never touches the immutable artifacts themselves.
"""
from __future__ import annotations

import pandas as pd

POSITIONS = ("QB", "RB", "WR", "TE")
ALL_LABEL = "All"
# Rows shown per position tab, and the pool behind average miss and rank
# correlation. QB is 24 to match the scored universe cap in the producer
# (UNIVERSE_CAPS), which is also roughly a 12-team league's startable pool
# plus streamers.
BOARD_TOP_N = {"QB": 24, "RB": 40, "WR": 40, "TE": 24}
# Starters at each position in a 12-team league (1 QB, 2 RB, 2 WR, 1 TE). Hit
# rate asks how many of a ranker's top K finished in the actual top K.
HIT_K = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}
REQUIRED_COLUMNS = ("player_id", "position", "projected_pts", "slp_proj", "actual_half_ppr")
SCORECARD_COLUMNS = (
    "position", "k", "our_hits", "slp_hits", "n",
    "our_mae", "slp_mae", "our_rho", "slp_rho", "n_excluded",
)
# A rank correlation over one or two players is always +1 or -1, not a result.
_MIN_RHO_ROWS = 3


def _require(frame: pd.DataFrame, columns) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")


def rank_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Add our_rank, slp_rank, finish_rank and rank_delta, ranked within position.

    our_rank and slp_rank are 1 for the highest projection, ties broken by row
    order. finish_rank is 1 for the most actual points, and tied scores share
    the best rank (a late scratch and every other zero finish together).
    rank_delta is our_rank minus finish_rank, so a positive value means he
    finished better than we ranked him. slp_rank stays NaN where Sleeper has no
    projection. Rows without a projection or a settled score cannot be placed
    in the finish order and are dropped.
    """
    _require(frame, REQUIRED_COLUMNS)
    out = frame.copy()
    for column in ("projected_pts", "slp_proj", "actual_half_ppr"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.loc[
        out["position"].isin(POSITIONS)
        & out["projected_pts"].notna()
        & out["actual_half_ppr"].notna()
    ].copy()
    by_position = out.groupby("position")
    out["our_rank"] = by_position["projected_pts"].rank(method="first", ascending=False)
    out["slp_rank"] = by_position["slp_proj"].rank(method="first", ascending=False)
    out["finish_rank"] = by_position["actual_half_ppr"].rank(method="min", ascending=False)
    out["rank_delta"] = out["our_rank"] - out["finish_rank"]
    return out


def _spearman(projected: pd.Series, actual: pd.Series) -> float:
    """Spearman rank correlation as Pearson on average ranks (scipy is not a site dependency)."""
    if len(projected) < _MIN_RHO_ROWS:
        return float("nan")
    return float(projected.rank().corr(actual.rank()))


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    usable = values.notna() & weights.gt(0)
    if not usable.any():
        return float("nan")
    return float((values[usable] * weights[usable]).sum() / weights[usable].sum())


def _combine(rows: pd.DataFrame, label: str) -> dict:
    """Pool scorecard rows into one. Hits and counts add, and average miss is
    pooled over the compared rows. Rank correlation is the n-weighted mean of
    the rows' values: ranks are never pooled across positions or weeks."""
    pooled = {"position": label}
    for column in ("k", "our_hits", "slp_hits", "n", "n_excluded"):
        pooled[column] = int(rows[column].sum())
    for column in ("our_mae", "slp_mae", "our_rho", "slp_rho"):
        pooled[column] = _weighted_mean(rows[column], rows["n"])
    return pooled


def position_scorecard(
    ranked: pd.DataFrame,
    *,
    hit_k: dict = HIT_K,
    top_n: dict = BOARD_TOP_N,
) -> pd.DataFrame:
    """One row per position present, plus an "All" row.

    k and the hit counts: of a ranker's top k at the position, how many finished
    in the actual top k (k is capped at the players ranked). n, the average
    miss (our_mae, slp_mae) and the rank correlation (our_rho, slp_rho) use the
    same players for both rankers: the union of our top N and Sleeper's top N
    that have a Sleeper projection. n_excluded counts union players with no
    Sleeper projection.
    """
    _require(ranked, (*REQUIRED_COLUMNS, "our_rank", "slp_rank", "finish_rank"))
    rows = []
    for position in POSITIONS:
        pool = ranked.loc[ranked["position"] == position]
        if pool.empty:
            continue
        k = min(int(hit_k[position]), len(pool))
        finished_top = pool["finish_rank"] <= k
        in_union = (pool["our_rank"] <= top_n[position]) | (pool["slp_rank"] <= top_n[position])
        union = pool.loc[in_union]
        compared = union.loc[union["slp_proj"].notna()]
        actual = compared["actual_half_ppr"]
        rows.append({
            "position": position,
            "k": k,
            "our_hits": int(((pool["our_rank"] <= k) & finished_top).sum()),
            "slp_hits": int(((pool["slp_rank"] <= k) & finished_top).sum()),
            "n": len(compared),
            "our_mae": float((compared["projected_pts"] - actual).abs().mean()),
            "slp_mae": float((compared["slp_proj"] - actual).abs().mean()),
            "our_rho": _spearman(compared["projected_pts"], actual),
            "slp_rho": _spearman(compared["slp_proj"], actual),
            "n_excluded": len(union) - len(compared),
        })
    card = pd.DataFrame(rows, columns=list(SCORECARD_COLUMNS))
    if card.empty:
        return card
    return pd.concat([card, pd.DataFrame([_combine(card, ALL_LABEL)])], ignore_index=True)


def season_table(weeks) -> pd.DataFrame:
    """Long-format scorecards for several graded weeks.

    `weeks` is (week, rows) pairs, where rows are one week's pregame-eligible
    graded rows (not yet ranked). The result has a week column and, per week,
    one row per position plus its "All" row.
    """
    cards = []
    for week, rows in sorted(weeks, key=lambda item: int(item[0])):
        card = position_scorecard(rank_frame(rows))
        card.insert(0, "week", int(week))
        cards.append(card)
    if not cards:
        return pd.DataFrame(columns=["week", *SCORECARD_COLUMNS])
    return pd.concat(cards, ignore_index=True)


def hits_text(hits, k) -> str:
    return f"{int(hits)} of {int(k)}"


def scorecard_display(rows: pd.DataFrame, *, label: str, column: str) -> pd.DataFrame:
    """Presentation copy of scorecard rows: hits as "17 of 24", two decimals elsewhere."""
    return pd.DataFrame({
        label: rows[column].to_numpy(),
        "Top-tier hits": [hits_text(h, k) for h, k in zip(rows["our_hits"], rows["k"])],
        "Sleeper hits": [hits_text(h, k) for h, k in zip(rows["slp_hits"], rows["k"])],
        "Avg miss": rows["our_mae"].round(2).to_numpy(),
        "Sleeper miss": rows["slp_mae"].round(2).to_numpy(),
        "Rank corr": rows["our_rho"].round(2).to_numpy(),
        "Sleeper corr": rows["slp_rho"].round(2).to_numpy(),
    })


def scorecard_display_phone(
    rows: pd.DataFrame, *, label: str, column: str, newest_first: bool = False,
) -> pd.DataFrame:
    """Phone copy: two narrow rows per position or week (ours, then Sleeper's).

    The site caps a phone table at 26rem and scrolls the rest, so a long list of
    weeks runs newest first and the latest week is never the one cut off.
    """
    records = []
    for row in rows.iloc[::-1 if newest_first else 1].to_dict("records"):
        for who, prefix in (("Ours", "our"), ("Sleeper", "slp")):
            records.append({
                label: row[column],
                "Who": who,
                "Top-tier hits": hits_text(row[f"{prefix}_hits"], row["k"]),
                "Avg miss": round(row[f"{prefix}_mae"], 2),
                "Rank corr": round(row[f"{prefix}_rho"], 2),
            })
    return pd.DataFrame(records)


def _wins(rows: pd.DataFrame, ours: str, theirs: str, *, lower_is_better: bool = False) -> tuple[int, int]:
    """Rows where we beat Sleeper, and rows that had both numbers. Values are
    compared as displayed (two decimals), so a tie on screen is a tie here."""
    ours_value = rows[ours].round(2)
    theirs_value = rows[theirs].round(2)
    comparable = rows["n"].gt(0) & ours_value.notna() & theirs_value.notna()
    better = ours_value.lt(theirs_value) if lower_is_better else ours_value.gt(theirs_value)
    return int((better & comparable).sum()), int(comparable.sum())


def week_summary(card: pd.DataFrame) -> str:
    """One plain sentence on how a week's position rows compare with Sleeper."""
    rows = card.loc[card["position"] != ALL_LABEL]
    hits, total = _wins(rows, "our_hits", "slp_hits")
    corr, _ = _wins(rows, "our_rho", "slp_rho")
    miss, _ = _wins(rows, "our_mae", "slp_mae", lower_is_better=True)
    if not total:
        return "Sleeper's projections were not available to compare this week."
    return (
        f"We beat Sleeper on top-tier hits at {hits} of {total} positions, "
        f"on rank correlation at {corr} of {total}, "
        f"and on average miss at {miss} of {total}."
    )


def season_summary(table: pd.DataFrame) -> str:
    """One plain sentence on how many graded weeks we beat Sleeper, from the "All" rows."""
    rows = table.loc[table["position"] == ALL_LABEL]
    hits, total = _wins(rows, "our_hits", "slp_hits")
    corr, _ = _wins(rows, "our_rho", "slp_rho")
    miss, _ = _wins(rows, "our_mae", "slp_mae", lower_is_better=True)
    if not total:
        return "Sleeper's projections were not available to compare."
    weeks = "week" if total == 1 else "weeks"
    return (
        f"Over {total} graded {weeks} we beat Sleeper on top-tier hits in {hits}, "
        f"on rank correlation in {corr}, and on average miss in {miss}."
    )
