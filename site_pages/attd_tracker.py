"""Paper-betting accounting for the public Anytime TD board.

This module intentionally contains no Streamlit code.  The page and its tests
share the same odds settlement, deduplication, and game-block bootstrap rules.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


# Published paper-bet cutoff: model probability must exceed DraftKings'
# implied probability by at least half a percentage point.
ATTD_VALUE_THRESHOLD = 0.005
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260911
MIN_SETTLED_GAMES_FOR_CI = 5
MIN_SETTLED_BETS_FOR_CI = 20


def qualifies_probability_gap(gap, threshold: float = ATTD_VALUE_THRESHOLD):
    """Apply an inclusive raw gap rule without binary-float boundary misses."""
    return pd.to_numeric(gap, errors="coerce").ge(float(threshold) - 1e-12)


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
) -> pd.DataFrame:
    """Add value-gap, candidate, settlement, and profit fields to one market."""
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
    out["_candidate"] = (
        model_probability.notna()
        & book_probability.notna()
        & book_price.notna()
        & qualifies_probability_gap(out["_value_gap"], threshold)
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


def strategy_summary(frame: pd.DataFrame, *, threshold: float | None) -> dict:
    """Summarize one paper-betting rule using settled bets only for P&L."""
    if threshold is None:
        bets = frame[frame["_book_price"].notna()].copy()
    else:
        bets = frame[
            qualifies_probability_gap(frame["_value_gap"], float(threshold))
            & frame["_book_price"].notna()
        ].copy()
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
) -> dict:
    """Return fixed-rule cards and its suppressed-or-available ROI interval."""
    prepared = prepare_paper_bets(
        frame,
        model_probability_col=model_probability_col,
        book_probability_col=book_probability_col,
        book_price_col=book_price_col,
        outcome_col=outcome_col,
    )
    fixed = strategy_summary(prepared, threshold=ATTD_VALUE_THRESHOLD)
    ci = block_bootstrap_roi(prepared)
    return {"summary": fixed, "ci": ci, "rows": prepared}
