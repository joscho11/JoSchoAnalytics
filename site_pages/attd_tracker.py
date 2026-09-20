"""Paper-betting accounting for the public Touchdown Props board (Anytime,
2+, and First TD markets).

This module intentionally contains no Streamlit code.  The page and its tests
share the same odds settlement, deduplication, and game-block bootstrap rules.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


# Published Anytime TD paper-bet cutoff: model probability must exceed
# DraftKings' implied probability by at least one percentage point (raised from
# half a point on 2026-09-19 at Joseph's direction). +0.5pp and +1.0pp were the
# two thresholds fixed before the 2025 holdout was scored; on the deployed
# product model +1.0pp was +8.21% on 1,428 bets vs +6.83% on 1,605 at +0.5pp,
# both intervals crossing zero (td_count_model_beta/README.md).
ATTD_VALUE_THRESHOLD = 0.01
# 2+ TD candidate rule (Joseph approved 2026-09-19, replaces the flat +0.5pp
# gap kept above for legacy reference only -- see qualifies_two_plus_ratio).
# A flat percentage-point gap rewards long shots: the same 0.5pp gap is a 50%
# relative edge on a 1% DraftKings price and a 3% relative edge on a 15%
# price, so it mostly flagged players where a small model error reads as a
# huge edge (2026-09-19 Week 2 board: 37 of 37 flagged players skewed long
# shot). The model's probability must be at least TWO_PLUS_RATIO_THRESHOLD
# times DraftKings' implied probability, and that implied probability must be
# at least TWO_PLUS_PRICE_FLOOR (screens out the longest shots, where the
# ratio is easiest to clear by accident). No 2+ TD price history exists to
# backtest either rule; this is a design choice, not a validated threshold.
TWO_PLUS_VALUE_THRESHOLD = 0.005
TWO_PLUS_RATIO_THRESHOLD = 1.25
TWO_PLUS_PRICE_FLOOR = 0.02
# First TD's threshold is wider than ATTD's. Exactly one player per game can
# score first, so p_first is not an independent per-player probability like
# p_ge1/p_ge2 -- it is a lambda-share allocation within a fixed per-game pool
# (p_offense_scores_first), with no fitted role/opening-script correction.
# Real bell-cow backs and starting QBs (Hurts, Hall, Bijan, Jeanty, Gibbs)
# already show a consistent -5pp to -8pp gap vs DraftKings' price on the
# 2026 Week 1 board -- a structural allocator bias, not noise. A 0.5pp bar
# would flag that known bias as "value" every week. 3.0pp sits below the
# observed bias band while still leaving room for a real signal to clear it
# as graded weeks accumulate. There is no historical First TD backtest to
# calibrate this against (see FIRST_TD note in page_anytime_td.py); treat
# this constant as a conservative placeholder, not a validated number. Since
# 2026-09-19 the live rule also requires a positive expected return at
# DraftKings' actual (vigged) price -- see qualifies_first_td_ev.
FIRST_TD_VALUE_THRESHOLD = 0.03
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260911
MIN_SETTLED_GAMES_FOR_CI = 5
MIN_SETTLED_BETS_FOR_CI = 20


def qualifies_probability_gap(gap, threshold: float = ATTD_VALUE_THRESHOLD):
    """Apply an inclusive raw gap rule without binary-float boundary misses.

    A missing gap (no book price, no model probability, or a nullable-dtype
    NaN) never qualifies -- .ge() on a nullable Float64/boolean dtype
    propagates pd.NA instead of False for a NaN comparison, and every
    downstream `if candidate:` check (the three _style functions in
    page_anytime_td.py) crashes with "boolean value of NA is ambiguous" the
    first time it hits one. Reproduced on the 2025 demo season, which has no
    two_plus_amer/first_amer columns at all, so every gap there is NaN.
    """
    result = pd.to_numeric(gap, errors="coerce").ge(float(threshold) - 1e-12)
    return result.fillna(False).astype(bool)


def qualifies_two_plus_ratio(
    model_probability,
    book_probability,
    *,
    ratio_threshold: float = TWO_PLUS_RATIO_THRESHOLD,
    price_floor: float = TWO_PLUS_PRICE_FLOOR,
):
    """2+ TD candidate rule: model probability >= ratio_threshold x book
    probability, AND book probability >= price_floor. See the
    TWO_PLUS_RATIO_THRESHOLD comment for why a ratio-plus-floor replaced the
    flat gap. Coerced to plain float64 before comparing, same discipline as
    qualifies_probability_gap, so a nullable-dtype NaN can never propagate
    pd.NA through the boolean result.
    """
    model = pd.to_numeric(model_probability, errors="coerce").astype("float64")
    book = pd.to_numeric(book_probability, errors="coerce").astype("float64")
    ratio_ok = model.ge(book * ratio_threshold - 1e-12)
    price_ok = book.ge(price_floor - 1e-12)
    return (ratio_ok & price_ok).fillna(False).astype(bool)


def qualifies_first_td_ev(
    model_probability,
    book_price,
    gap,
    *,
    gap_threshold: float = FIRST_TD_VALUE_THRESHOLD,
):
    """First TD candidate rule: the raw value gap (model minus DraftKings'
    de-vigged price) clears gap_threshold, AND the model shows a positive
    expected return at DraftKings' real, vigged price.

    The gap alone compares to a de-vigged price nobody actually pays --
    First TD raw implied probabilities sum to about 121% per game, not 100%
    (see FIRST_TD_VALUE_THRESHOLD). A player can clear the de-vigged gap and
    still lose money at the real price: confirmed on the 2026 Week 2 board,
    Christian McCaffrey cleared +3.5pp (24.6% model vs a 21.1% de-vigged
    price) but the real +295 price implies 25.3%, an expected return of -3%.
    Expected value = model probability x decimal odds - 1.
    """
    model = pd.to_numeric(model_probability, errors="coerce").astype("float64")
    price = pd.to_numeric(book_price, errors="coerce").astype("float64")
    gap_ok = qualifies_probability_gap(gap, gap_threshold)
    decimal = price.map(lambda value: american_to_decimal(value) if pd.notna(value) else np.nan)
    ev = model * decimal - 1.0
    ev_ok = pd.Series(ev, index=model.index).gt(0.0)
    return (gap_ok & ev_ok).fillna(False).astype(bool)


def rule_description(market: str) -> str:
    """Plain-language description of the paper-bet qualifying rule for `market`."""
    if market == "two_plus":
        return (
            f"model probability at least {TWO_PLUS_RATIO_THRESHOLD:.2f}x DraftKings' "
            f"price, with that price at least {100 * TWO_PLUS_PRICE_FLOOR:.0f}%"
        )
    if market == "first":
        return (
            f"+{100 * FIRST_TD_VALUE_THRESHOLD:.1f}pp value gap AND a positive "
            "expected return at DraftKings' actual price"
        )
    return f"+{100 * ATTD_VALUE_THRESHOLD:.1f}pp value gap"


def american_to_decimal(price) -> float:
    """Convert American odds to decimal odds, rejecting the invalid zero."""
    value = float(price)
    if not np.isfinite(value) or value == 0:
        raise ValueError("American odds must be finite and non-zero")
    return 1.0 + value / 100.0 if value > 0 else 1.0 + 100.0 / abs(value)


def implied_probability(price):
    """Return the sportsbook's implied Yes probability for American odds."""
    if pd.isna(price):
        return np.nan
    return 1.0 / american_to_decimal(price)


def _dedup_key_columns(frame: pd.DataFrame) -> list[str]:
    if {"game_id", "player_id"} <= set(frame.columns):
        return ["game_id", "player_id"]
    preferred = [
        "season", "week", "player_id", "player_display_name", "team",
        "opponent_team",
    ]
    return [column for column in preferred if column in frame.columns]


def deduplicate_player_games(frames: list[pd.DataFrame] | tuple[pd.DataFrame, ...]) -> pd.DataFrame:
    """Combine releases and retain one row per player-game, newest last."""
    nonempty = [frame.copy() for frame in frames if frame is not None and not frame.empty]
    if not nonempty:
        return pd.DataFrame()
    combined = pd.concat(nonempty, ignore_index=True)
    keys = _dedup_key_columns(combined)
    if keys:
        combined = combined.drop_duplicates(keys, keep="last")
    return combined.reset_index(drop=True)


def aggregate_published_csvs(paths: list[str | Path] | tuple[str | Path, ...]) -> pd.DataFrame:
    """Load published weekly files and deduplicate their player-game rows."""
    frames = [pd.read_csv(path) for path in paths]
    return deduplicate_player_games(frames)


def _numeric_series(frame: pd.DataFrame, column: str | None) -> pd.Series:
    """Return a numeric column aligned to ``frame`` or an all-missing series."""
    if column and column in frame:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype="float64")


def prepare_paper_bets(
    frame: pd.DataFrame,
    *,
    threshold: float = ATTD_VALUE_THRESHOLD,
    model_probability_col: str = "p_ge1",
    book_probability_col: str | None = "p_book",
    book_price_col: str = "book_amer",
    outcome_col: str = "scored_anytime",
    qualifies=None,
) -> pd.DataFrame:
    """Add value-gap, candidate, settlement, and profit fields to one market.

    `qualifies`, when given, is a callable taking the frame after
    `_model_probability`/`_book_probability`/`_book_price`/`_value_gap` are
    attached and returning a boolean mask -- this is how 2+ TD's ratio rule
    and First TD's expected-value rule plug in without duplicating the
    settlement/profit/bootstrap machinery below. `threshold` alone (the
    default) reproduces the flat percentage-point gap rule.
    """
    out = frame.copy()
    model_probability = _numeric_series(out, model_probability_col)
    book_price = _numeric_series(out, book_price_col)
    if book_probability_col and book_probability_col in out:
        book_probability = _numeric_series(out, book_probability_col)
    else:
        # The 2+ release schema stores the DraftKings price but does not need a
        # second implied-probability column; derive it from that price.
        book_probability = book_price.map(implied_probability)
    outcome = _numeric_series(out, outcome_col)

    out["_model_probability"] = model_probability
    out["_book_probability"] = book_probability
    out["_book_price"] = book_price
    out["_outcome"] = outcome
    out["_value_gap"] = model_probability - book_probability
    if "bet_eligible" in out:
        raw_eligibility = out["bet_eligible"]
        if pd.api.types.is_bool_dtype(raw_eligibility):
            eligibility = raw_eligibility.fillna(True).astype(bool)
        else:
            normalized = raw_eligibility.astype("string").str.strip().str.lower()
            eligibility = ~normalized.isin({"false", "0", "no", "n", "off"})
            eligibility &= ~raw_eligibility.isna()
            eligibility |= raw_eligibility.isna()
    else:
        # Legacy demo releases predate the serving eligibility contract.
        eligibility = pd.Series(True, index=out.index, dtype=bool)
    qualifying = (
        qualifies(out) if qualifies is not None
        else qualifies_probability_gap(out["_value_gap"], threshold)
    )
    out["_candidate"] = (
        model_probability.notna()
        & book_probability.notna()
        & book_price.notna()
        & eligibility
        & qualifying
    )
    out["_settled"] = out["_candidate"] & outcome.isin([0, 1])
    out["_win"] = out["_settled"] & outcome.eq(1)
    out["_loss"] = out["_settled"] & outcome.eq(0)
    out["_stake_units"] = out["_candidate"].astype(float)
    decimal = book_price.map(lambda value: american_to_decimal(value) if pd.notna(value) else np.nan)
    out["_profit_units"] = np.where(
        out["_settled"],
        np.where(out["_win"], decimal - 1.0, -1.0),
        np.nan,
    )
    return out


def _group_label(frame: pd.DataFrame) -> pd.Series:
    if "game_id" in frame:
        game = frame["game_id"].astype("string")
        fallback = "week:" + frame.get("week", pd.Series("unknown", index=frame.index)).astype("string")
        return game.where(game.notna() & game.str.strip().ne(""), fallback)
    if "week" in frame:
        return "week:" + frame["week"].astype("string")
    return pd.Series("all", index=frame.index, dtype="string")


def _max_drawdown(frame: pd.DataFrame) -> float:
    settled = frame[frame["_settled"]].copy()
    if settled.empty:
        return 0.0
    if "week" in settled:
        weekly = settled.groupby("week", dropna=False)["_profit_units"].sum().sort_index()
    else:
        weekly = pd.Series([settled["_profit_units"].sum()], index=[0])
    equity = weekly.cumsum()
    drawdown = equity - equity.cummax()
    return float(drawdown.min())


def strategy_summary(frame: pd.DataFrame, *, threshold: float | None, qualifies=None) -> dict:
    """Summarize one paper-betting rule using settled bets only for P&L.

    `qualifies`, when given, replaces the flat-gap re-derivation below with
    the same callable `prepare_paper_bets` used to build `_candidate` --
    2+ TD's ratio rule or First TD's expected-value rule, most often.
    """
    if threshold is None and qualifies is None:
        bets = frame[frame["_book_price"].notna()].copy()
    else:
        mask = (
            qualifies(frame) if qualifies is not None
            else qualifies_probability_gap(frame["_value_gap"], float(threshold))
        )
        bets = frame[mask & frame["_book_price"].notna()].copy()
    settled = bets[bets["_outcome"].isin([0, 1])].copy()
    wins = int(settled["_win"].sum())
    losses = int(settled["_loss"].sum())
    stake = float(len(settled))
    net = float(settled["_profit_units"].sum()) if not settled.empty else 0.0
    return {
        "threshold": None if threshold is None else float(threshold),
        "bets": int(len(bets)),
        "settled_bets": int(len(settled)),
        "open_bets": int(len(bets) - len(settled)),
        "settled_games": int(_group_label(settled).nunique()) if not settled.empty else 0,
        "wins": wins,
        "losses": losses,
        "stake_units": stake,
        "net_units": net,
        "roi": (net / stake) if stake else None,
        "positive_weeks": int(
            (settled.groupby("week")["_profit_units"].sum() > 0).sum()
        ) if not settled.empty and "week" in settled else 0,
        "max_drawdown": _max_drawdown(settled.assign(_settled=True)) if not settled.empty else 0.0,
    }


def _summary_for_mask(frame: pd.DataFrame, mask: pd.Series, threshold=None) -> dict:
    work = frame.copy()
    work["_candidate"] = mask.fillna(False).astype(bool)
    work["_settled"] = work["_candidate"] & pd.to_numeric(
        work.get("_outcome", pd.Series(np.nan, index=work.index)), errors="coerce"
    ).isin([0, 1])
    return strategy_summary(work, threshold=threshold)


def block_bootstrap_roi(
    frame: pd.DataFrame,
    *,
    threshold: float = ATTD_VALUE_THRESHOLD,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """Bootstrap settled games, retaining every candidate bet inside each game."""
    bets = frame[frame["_candidate"] & frame["_settled"]].copy()
    games = _group_label(bets)
    if bets.empty:
        n_games = 0
    else:
        grouped = bets.assign(_game=games).groupby("_game", sort=True).agg(
            net=("_profit_units", "sum"), stake=("_stake_units", "sum")
        )
        n_games = len(grouped)
    result = {
        "available": bool(
            n_games >= MIN_SETTLED_GAMES_FOR_CI
            and len(bets) >= MIN_SETTLED_BETS_FOR_CI
        ),
        "threshold": float(threshold),
        "resamples": int(n_resamples),
        "seed": int(seed),
        "method": "game-block bootstrap; all qualifying player bets in a game stay together",
        "settled_games": int(n_games),
        "settled_bets": int(len(bets)),
        "lower": None,
        "upper": None,
    }
    if not result["available"]:
        return result
    rng = np.random.default_rng(seed)
    net = grouped["net"].to_numpy(dtype=float)
    stake = grouped["stake"].to_numpy(dtype=float)
    sampled = rng.integers(0, n_games, size=(int(n_resamples), n_games))
    rois = net[sampled].sum(axis=1) / stake[sampled].sum(axis=1)
    result["lower"] = float(np.quantile(rois, 0.025))
    result["upper"] = float(np.quantile(rois, 0.975))
    return result


def season_tracker(
    frame: pd.DataFrame,
    *,
    model_probability_col: str = "p_ge1",
    book_probability_col: str | None = "p_book",
    book_price_col: str = "book_amer",
    outcome_col: str = "scored_anytime",
    threshold: float = ATTD_VALUE_THRESHOLD,
    qualifies=None,
) -> dict:
    """Return fixed-rule cards and its suppressed-or-available ROI interval.

    `qualifies` overrides the flat-gap rule end to end (candidate flagging,
    the tracker cards, and the bootstrap all read the same `_candidate`
    column or re-derive from the same callable). `threshold` is still passed
    through for the reported metadata even when `qualifies` does the actual
    gatekeeping.
    """
    prepared = prepare_paper_bets(
        frame,
        model_probability_col=model_probability_col,
        book_probability_col=book_probability_col,
        book_price_col=book_price_col,
        outcome_col=outcome_col,
        threshold=threshold,
        qualifies=qualifies,
    )
    fixed = strategy_summary(prepared, threshold=threshold, qualifies=qualifies)
    ci = block_bootstrap_roi(prepared, threshold=threshold)
    return {"summary": fixed, "ci": ci, "rows": prepared}
