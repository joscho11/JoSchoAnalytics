"""Touchdown Props tab: Anytime, 2+, and First TD comparison boards.

Sourced from the frozen td_count_model_beta releases. Rushing and receiving
TDs only. Passing TDs are out. CSV only. No model code. A priced comparison
board: model and book odds plus a value gap, not a pick list. First TD is
qualitatively different from the other two -- a competing-risk allocation
across one game's whole candidate pool, not a per-player marginal
probability -- see _first_td_display's docstring for the derivation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

import attd_tracker as tracker
import page_common
from dashboard_chrome import dataframe_phone_desktop, exact_table_height

_HERE = Path(__file__).resolve().parents[1]
_DIR = _HERE / "betting" / "anytime_td"
DEMO_SEASON = 2025
LIVE_SEASON = 2026
DEFAULT_RELEASE = (LIVE_SEASON, 1)
DEFAULT_WEEK = 10
# These completed games were intentionally retained as fun, display-only 2+
# TD model views. They have model probabilities and graded outcomes, but no
# historical DraftKings 2+ prices, so they must never create value bets or P&L.
DISPLAY_ONLY_TWO_PLUS_GAME_IDS = {"2026_01_NE_SEA", "2026_01_SF_LA"}
# Same two completed games, same rationale, for the First TD market: no
# DraftKings First TD price was captured for either, but the model
# probabilities and graded first-scorer outcomes exist, so they are kept as
# fun, display-only views rather than hidden entirely.
DISPLAY_ONLY_FIRST_TD_GAME_IDS = {"2026_01_NE_SEA", "2026_01_SF_LA"}
DESKTOP_COLS = [
    "#", "Player", "Pos", "Opp", "Model ATTD Odds", "Book ATTD Odds",
    "ATTD Value Gap", "Hit",
]
PHONE_COLS = [
    "#", "Player", "Model ATTD Odds", "Book ATTD Odds", "ATTD Value Gap", "Hit",
]
PHONE_LABELS = {
    "Model ATTD Odds": "Model",
    "Book ATTD Odds": "Book",
    "ATTD Value Gap": "Value",
}
PHONE_WIDTHS = {
    "#": 50,
    "Player": 128,
    "Model ATTD Odds": 132,
    "Book ATTD Odds": 132,
    "ATTD Value Gap": 118,
    "Hit": 44,
}
TWO_PLUS_DESKTOP_COLS = [
    "#", "Player", "Pos", "Opp", "Model 2+ TD Odds", "Book 2+ TD Odds",
    "2+ TD Value Gap",
]
TWO_PLUS_PHONE_COLS = [
    "#", "Player", "Model 2+ TD Odds", "Book 2+ TD Odds", "2+ TD Value Gap",
]
FIRST_TD_DESKTOP_COLS = [
    "#", "Player", "Pos", "Opp", "Model First TD Odds", "Book First TD Odds",
    "First TD Value Gap", "Hit",
]
FIRST_TD_PHONE_COLS = [
    "#", "Player", "Model First TD Odds", "Book First TD Odds", "First TD Value Gap", "Hit",
]
# No historical first-TD book prices exist anywhere in this workspace for any
# season, unlike 2+ TD which at least has a demo comparison. There is no
# display-only precedent list for first-TD -- every 2026 game either has a
# published first_amer market or it doesn't.


def _parse_week(name: str) -> int | None:
    stem = name.replace(".csv", "")
    parts = stem.split("_")
    try:
        if parts[0] != "anytime" or parts[2] != f"{DEMO_SEASON}":
            return None
        return int(parts[3].replace("week", ""))
    except (IndexError, ValueError):
        return None


def _parse_release(name: str) -> tuple[int, int] | None:
    stem = name.removesuffix(".csv")
    parts = stem.split("_")
    if len(parts) < 4 or parts[0] != "anytime" or parts[1] != "td":
        return None
    try:
        return int(parts[2]), int(parts[3].removeprefix("week"))
    except ValueError:
        return None


def available_releases() -> dict[tuple[int, int], Path]:
    found: dict[tuple[int, int], Path] = {}
    if not _DIR.is_dir():
        return found
    for path in sorted(_DIR.glob("anytime_td_*_week*.csv")):
        key = _parse_release(path.name)
        if key is not None:
            found[key] = path
    return found


def default_release(options: list[tuple[int, int]]) -> tuple[int, int]:
    """Prefer the live 2026 Week 1 board whenever it has been published."""
    if not options:
        raise ValueError("at least one release is required")
    if DEFAULT_RELEASE in options:
        return DEFAULT_RELEASE
    live = sorted(key for key in options if key[0] == LIVE_SEASON)
    return live[0] if live else sorted(options)[0]


def available_weeks() -> dict[int, Path]:
    found: dict[int, Path] = {}
    if not _DIR.is_dir():
        return found
    for path in sorted(_DIR.glob(f"anytime_td_{DEMO_SEASON}_week*.csv")):
        week = _parse_week(path.name)
        if week is not None:
            found[week] = path
    return found


def priced_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["book_amer"] = pd.to_numeric(out["book_amer"], errors="coerce")
    out["p_book"] = pd.to_numeric(out["p_book"], errors="coerce")
    out["p_ge1"] = pd.to_numeric(out["p_ge1"], errors="coerce")
    if "p_ge2" in out:
        out["p_ge2"] = pd.to_numeric(out["p_ge2"], errors="coerce")
    else:
        out["p_ge2"] = pd.Series(pd.NA, index=out.index, dtype="Float64")
    # A verified replacement can be quoted by DraftKings before the upstream
    # fantasy projection feed contains a current-week row. Keep that quote on
    # the board, but leave model fields missing so it cannot become a value bet
    # or enter the tracker until model inputs exist.
    return out[out.p_book.notna() & out.book_amer.notna()].copy()


def _bet_eligibility(df: pd.DataFrame) -> pd.Series:
    """Serving guard: retain legacy rows, but never bet an explicit exclusion."""
    if "bet_eligible" not in df:
        return pd.Series(True, index=df.index, dtype=bool)
    raw = df["bet_eligible"]
    if pd.api.types.is_bool_dtype(raw):
        return raw.fillna(True).astype(bool)
    normalized = raw.astype("string").str.strip().str.lower()
    eligibility = ~normalized.isin({"false", "0", "no", "n", "off"})
    return eligibility.fillna(True).astype(bool)


def by_position(df: pd.DataFrame, position: str) -> pd.DataFrame:
    if position == "All":
        return df
    if position == "RB":
        return df[df.position.isin(["RB", "FB"])]
    return df[df.position.eq(position)]


def _matchup_groups(df: pd.DataFrame):
    """Yield matchup sections in kickoff order, then alphabetical order."""
    work = df.copy()
    if "game_id" in work.columns and work.game_id.notna().any():
        work["_matchup_key"] = work.game_id.astype(str)
    else:
        work["_matchup_key"] = work.apply(
            lambda r: "_".join(sorted((str(r.team), str(r.opponent_team)))), axis=1
        )
    groups = []
    for key, group in work.groupby("_matchup_key", sort=False):
        parts = str(key).rsplit("_", 2)
        if len(parts) == 3 and parts[0].startswith("2026"):
            teams = [parts[1], parts[2]]
        else:
            teams = sorted(set(group.team.astype(str)) | set(group.opponent_team.astype(str)))
        label = f"{teams[0]} vs {teams[1]}" if len(teams) >= 2 else str(teams[0])
        kickoff = pd.to_datetime(group.get("kickoff_et"), errors="coerce")
        first_kickoff = kickoff.min() if kickoff is not None else pd.NaT
        groups.append((first_kickoff, label, teams, group.drop(columns=["_matchup_key"])))
    groups.sort(key=lambda item: (pd.Timestamp.max if pd.isna(item[0]) else item[0], item[1]))
    for _, label, teams, group in groups:
        yield label, teams, group


def _matchup_is_graded(group: pd.DataFrame) -> bool:
    if group.empty or "scored_anytime" not in group:
        return False
    resolved = pd.to_numeric(group["scored_anytime"], errors="coerce").notna()
    if "status" in group:
        resolved |= group["status"].astype(str).str.lower().eq("void")
    return bool(resolved.all())


def _matchup_is_started(group: pd.DataFrame) -> bool:
    """Return whether kickoff has passed, including before grading commits."""
    if group.empty or "kickoff_et" not in group:
        return False
    kickoff = pd.to_datetime(group["kickoff_et"], errors="coerce")
    if kickoff.empty or kickoff.notna().sum() == 0:
        return False
    if kickoff.dt.tz is not None:
        kickoff = kickoff.dt.tz_convert("America/New_York").dt.tz_localize(None)
    now_et = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    return bool(kickoff.min() <= now_et)


def default_matchup_label(matchups: list[tuple[str, list[str], pd.DataFrame]]) -> str:
    """Return the first unstarted matchup, or the last matchup once the slate is complete."""
    if not matchups:
        raise ValueError("at least one matchup is required")
    for label, _, group in matchups:
        if not _matchup_is_graded(group) and not _matchup_is_started(group):
            return label
    return matchups[-1][0]


def _mark_matchup_manual(key: str) -> None:
    st.session_state[key] = True


def _seed_matchup_default(
    matchups: list[tuple[str, list[str], pd.DataFrame]], key: str
) -> None:
    labels = {label for label, _, _ in matchups}
    manual_key = f"{key}__manual"
    default = default_matchup_label(matchups)
    current = st.session_state.get(key)
    if current not in labels:
        st.session_state[key] = default
        st.session_state[manual_key] = False
    elif not st.session_state.get(manual_key, False):
        selected = next(item for item in matchups if item[0] == current)
        if _matchup_is_graded(selected[2]) or _matchup_is_started(selected[2]):
            st.session_state[key] = default


def week_summary(df: pd.DataFrame) -> dict:
    return _market_summary(
        df,
        model_probability_col="p_ge1",
        book_probability_col="p_book",
        book_price_col="book_amer",
        outcome_col="scored_anytime",
    )


def _numeric_column(df: pd.DataFrame, column: str | None) -> pd.Series:
    """Always a Series aligned to df's index, even when column is absent.

    df.get(column) on a missing column returns None (not an all-NaN Series),
    and pd.to_numeric(None, errors="coerce") silently collapses to a bare
    scalar nan rather than raising. Any caller that then calls .map() or
    .isna() on the result crashes -- reproduced by switching to the 2025
    demo season (no scored_first/first_amer columns at all) and toggling to
    First TD view. Always route missing columns through this helper instead
    of df.get(...) directly.
    """
    if column and column in df:
        return pd.to_numeric(df[column], errors="coerce")
    return pd.Series(float("nan"), index=df.index, dtype="float64")


def _market_summary(
    df: pd.DataFrame,
    *,
    model_probability_col: str,
    book_probability_col: str | None,
    book_price_col: str,
    outcome_col: str,
) -> dict:
    model_probability = _numeric_column(df, model_probability_col)
    book_price = _numeric_column(df, book_price_col)
    if book_probability_col and book_probability_col in df:
        book_probability = _numeric_column(df, book_probability_col)
    else:
        book_probability = book_price.map(tracker.implied_probability)
    market_rows = model_probability.notna() & book_probability.notna()
    n = int(market_rows.sum())
    outcomes = _numeric_column(df, outcome_col)
    hits = int(outcomes.eq(1).sum())
    graded = int(outcomes.notna().sum())
    return {
        "n": n,
        "hits": hits,
        "graded": graded,
        "hit_rate": (hits / graded) if graded else None,
        "mean_p": float(model_probability[market_rows].mean()) if n else None,
        "mean_book": float(book_probability[market_rows].mean()) if n else None,
    }


@st.cache_data(ttl=900)
def _load_season_tracker(
    paths: tuple[str, ...], modified_at: tuple[int, ...], market: str = "anytime"
) -> dict:
    """Load the newest published file for each live week and score its paper bets."""
    del modified_at  # cache key; the files themselves are read below
    frame = tracker.aggregate_published_csvs(paths)
    if market == "two_plus":
        return tracker.season_tracker(
            frame,
            model_probability_col="p_ge2",
            book_probability_col=None,
            book_price_col="two_plus_amer",
            outcome_col="scored_two_plus",
        )
    if market == "first":
        return tracker.season_tracker(
            frame,
            model_probability_col="p_first",
            book_probability_col="book_first_p_devigged",
            book_price_col="first_amer",
            outcome_col="scored_first",
            threshold=tracker.FIRST_TD_VALUE_THRESHOLD,
        )
    return tracker.season_tracker(frame)


def _published_live_paths(releases: dict[tuple[int, int], Path]) -> tuple[tuple[str, ...], tuple[int, ...]]:
    paths = tuple(
        str(releases[key])
        for key in sorted(releases)
        if key[0] == LIVE_SEASON
    )
    modified_at = tuple(Path(path).stat().st_mtime_ns for path in paths)
    return paths, modified_at


def _pct(value) -> str:
    return "—" if value is None or pd.isna(value) else f"{100 * float(value):+.1f}%"


def _roi_range_value(ci: dict) -> str:
    if not ci.get("available") or ci.get("lower") is None or ci.get("upper") is None:
        return "Pending"
    return f"{100 * ci['lower']:.1f}% to {100 * ci['upper']:.1f}%"


def _has_two_plus_prices(frame: pd.DataFrame) -> bool:
    """Return whether this specific matchup has a published 2+ TD market."""
    if "two_plus_amer" not in frame:
        return False
    return bool(pd.to_numeric(frame["two_plus_amer"], errors="coerce").notna().any())


def _has_first_td_prices(frame: pd.DataFrame) -> bool:
    """Return whether this specific matchup has a published First TD market."""
    if "first_amer" not in frame:
        return False
    return bool(pd.to_numeric(frame["first_amer"], errors="coerce").notna().any())


def _is_display_only_two_plus_matchup(frame: pd.DataFrame) -> bool:
    if "game_id" not in frame:
        return False
    return bool(
        set(frame["game_id"].astype(str).dropna())
        & DISPLAY_ONLY_TWO_PLUS_GAME_IDS
    )


def _is_display_only_first_td_matchup(frame: pd.DataFrame) -> bool:
    if "game_id" not in frame:
        return False
    return bool(
        set(frame["game_id"].astype(str).dropna())
        & DISPLAY_ONLY_FIRST_TD_GAME_IDS
    )


def _two_plus_results_tally(frame: pd.DataFrame) -> dict[str, int]:
    """Count graded 2+ TD outcomes without treating them as historical bets."""
    outcome_col = "_outcome" if "_outcome" in frame else "scored_two_plus"
    if outcome_col not in frame:
        return {"graded": 0, "hits": 0}
    outcomes = pd.to_numeric(frame[outcome_col], errors="coerce")
    graded = outcomes.isin([0, 1])
    return {
        "graded": int(graded.sum()),
        "hits": int(outcomes[graded].eq(1).sum()),
    }


def _first_td_results_tally(frame: pd.DataFrame) -> dict[str, int]:
    """Count graded First TD outcomes without treating them as historical bets."""
    outcome_col = "_outcome" if "_outcome" in frame else "scored_first"
    if outcome_col not in frame:
        return {"graded": 0, "hits": 0}
    outcomes = pd.to_numeric(frame[outcome_col], errors="coerce")
    graded = outcomes.isin([0, 1])
    return {
        "graded": int(graded.sum()),
        "hits": int(outcomes[graded].eq(1).sum()),
    }


_MARKET_LABELS = {"anytime": "Anytime TD", "two_plus": "2+ TD", "first": "First TD"}
_MARKET_SHORT_LABELS = {"anytime": "", "two_plus": "2+ ", "first": "First "}


def _render_scorecards(
    priced: pd.DataFrame,
    season: int,
    releases: dict[tuple[int, int], Path],
    *,
    market: str = "anytime",
) -> None:
    is_two_plus = market == "two_plus"
    is_first = market == "first"
    market_label = _MARKET_LABELS[market]
    summary = _market_summary(
        priced,
        model_probability_col="p_first" if is_first else "p_ge2" if is_two_plus else "p_ge1",
        book_probability_col=(
            "book_first_p_devigged" if is_first
            else None if is_two_plus
            else "p_book"
        ),
        book_price_col="first_amer" if is_first else "two_plus_amer" if is_two_plus else "book_amer",
        outcome_col="scored_first" if is_first else "scored_two_plus" if is_two_plus else "scored_anytime",
    )
    gap_threshold = tracker.FIRST_TD_VALUE_THRESHOLD if is_first else tracker.ATTD_VALUE_THRESHOLD
    if season == LIVE_SEASON:
        paths, modified_at = _published_live_paths(releases)
        if paths:
            paper = _load_season_tracker(paths, modified_at, market)
            result = paper["summary"]
            ci = paper["ci"]
            rule_note = " (wider than Anytime/2+ TD's)" if is_first else ""
            st.caption(
                f"{market_label} paper tracker · "
                f"+{100 * gap_threshold:.1f}pp gap rule{rule_note} · 1U per candidate."
            )
            with st.container(horizontal=True, key="jsa-metric-even-atd"):
                st.metric("Net units", f"{result['net_units']:+.1f}U", border=True)
                st.metric("ROI", _pct(result["roi"]), border=True)
                st.metric(
                    "Record",
                    f"{result['wins']}-{result['losses']}",
                    delta=f"{result['open_bets']} open",
                    delta_color="off",
                    border=True,
                )
                st.metric("Approx. 95% ROI range", _roi_range_value(ci), border=True)
            if ci["available"]:
                st.caption("Empirical uncertainty range, not a guarantee.")
            else:
                st.caption(
                    "Approx. 95% ROI range is pending until at least 5 settled games "
                    "and 20 settled paper bets are available."
                )
            if is_two_plus:
                tally = _two_plus_results_tally(paper["rows"])
                if tally["graded"]:
                    st.caption(
                        "Results-only 2+ TD tally · "
                        f"{tally['hits']} hits / {tally['graded']} graded player-games. "
                        "This is not a betting record."
                    )
                else:
                    st.caption(
                        "Results-only 2+ TD tally is pending final outcome grading; "
                        "it is separate from the betting record."
                    )
            if is_first:
                tally = _first_td_results_tally(paper["rows"])
                if tally["graded"]:
                    st.caption(
                        "Results-only First TD tally · "
                        f"{tally['hits']} hits / {tally['graded']} graded games. "
                        "This is not a betting record."
                    )
                else:
                    st.caption(
                        "Results-only First TD tally is pending final outcome grading; "
                        "it is separate from the betting record."
                    )
            if is_two_plus and result["bets"] == 0:
                st.caption("No quoted 2+ TD candidates meet the gap rule yet.")
            if is_first and result["bets"] == 0:
                st.caption("No quoted First TD candidates meet the gap rule yet.")
        else:
            st.info(
                f"2026 {market_label} paper-betting "
                "tracker is waiting for a published release."
            )
    else:
        with st.container(horizontal=True, key="jsa-metric-even-atd"):
            st.metric("Priced", summary["n"], border=True)
            if summary["graded"]:
                hit_pct = 100 * summary["hit_rate"]
                st.metric(
                    "Scored", f"{summary['hits']}/{summary['graded']}", f"{hit_pct:.0f}%",
                    delta_arrow="off", border=True,
                )
    model_context = "—" if summary["mean_p"] is None else f"{100 * summary['mean_p']:.1f}%"
    book_context = "—" if summary["mean_book"] is None else f"{100 * summary['mean_book']:.1f}%"
    short = _MARKET_SHORT_LABELS[market]
    st.caption(
        f"Supporting context · Model {short}P "
        f"{model_context} · Book {short}P {book_context} · "
        "Model and book probabilities are shown here for context; the table carries the odds."
    )


@st.cache_data(ttl=3600)
def _load_csv(path: str, modified_at: int | None = None) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(ttl=3600)
def _load_meta(path: str) -> dict:
    raw = Path(path)
    if not raw.is_file():
        return {}
    try:
        value = json.loads(raw.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _live_metadata(season: int = LIVE_SEASON, week: int = 1) -> dict:
    files = sorted(_DIR.glob(f"anytime_td_{season}_week{week:02d}_*.json"))
    if not files:
        return {}
    # The newest slate metadata describes the most recent cumulative append.
    return _load_meta(str(files[-1]))


def _amer(value) -> str:
    if pd.isna(value):
        return ""
    n = int(round(float(value)))
    return f"+{n}" if n > 0 else str(n)


def _amer_display(value) -> str:
    """Same American odds as _amer, but abbreviated past +10000 for narrow columns.

    +10805 becomes +10.8k rather than being silently truncated by a fixed
    column width. The cutoff is 10000, not 1000: below that, e.g. +1500,
    abbreviating to +1.5k is the same length as the full number and only
    loses precision for no space saved. This changes only the printed
    digits, never the number used in any value-gap or implied-probability
    calculation -- _amer stays the single source for that; this wraps it
    for display only.
    """
    if pd.isna(value):
        return ""
    n = int(round(float(value)))
    if abs(n) >= 10_000:
        return f"{n / 1000:+.1f}k"
    return _amer(value)


def _signed_int(value) -> str:
    if pd.isna(value):
        return ""
    n = int(round(float(value)))
    return f"{n:+d}" if n else "0"


def _signed_int_display(value) -> str:
    """Same odds-gap integer as _signed_int, abbreviated past 10000 in magnitude.

    Same 10000 cutoff as _amer_display: below that, k-notation is the same
    length as the full number and only costs precision.
    """
    if pd.isna(value):
        return ""
    n = int(round(float(value)))
    if abs(n) >= 10_000:
        return f"{n / 1000:+.1f}k"
    return _signed_int(value)


def _fair_amer_from_probability(value):
    if pd.isna(value):
        return None
    probability = float(value)
    if not 0 < probability < 1:
        return None
    if probability >= 0.5:
        return -100 * probability / (1 - probability)
    return 100 * (1 - probability) / probability


def _odds_probability(american, probability) -> str:
    if pd.isna(probability):
        return ""
    probability_text = f"{100 * float(probability):.1f}%"
    american_text = _amer_display(american)
    return f"{american_text} · {probability_text}" if american_text else probability_text


def _model_odds_probability(american, probability) -> str:
    if pd.isna(probability):
        return "Pending"
    return _odds_probability(american, probability)


def _implied_probability(american):
    if pd.isna(american):
        return None
    value = float(american)
    if value == 0:
        return None
    return 100 / (value + 100) if value > 0 else 100 / (100 + abs(value))


def _value_gap(model_american, book_american, model_probability, book_probability) -> str:
    if pd.isna(model_probability) or pd.isna(book_probability):
        return ""
    probability_gap = 100 * (float(model_probability) - float(book_probability))
    if pd.isna(model_american) or pd.isna(book_american):
        return f"{probability_gap:+.1f}%"
    # Positive American-odds gap means the book is offering longer odds than
    # our fair price, matching the direction of a positive probability gap.
    odds_gap = float(book_american) - float(model_american)
    return f"{_signed_int_display(odds_gap)} · {probability_gap:+.1f}%"


def _display(df: pd.DataFrame) -> pd.DataFrame:
    ranked = df.copy()
    ranked["_value"] = ranked.p_ge1 - ranked.p_book
    ranked = ranked.sort_values(
        ["_value", "p_ge1", "player_display_name"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    outcome = pd.to_numeric(ranked.scored_anytime, errors="coerce")
    hit = outcome.map(lambda value: "Yes" if value == 1 else ("No" if pd.notna(value) else ""))
    model_american = ranked["fair_amer"] if "fair_amer" in ranked else pd.Series(pd.NA, index=ranked.index)
    book_american = ranked["book_amer"] if "book_amer" in ranked else pd.Series(pd.NA, index=ranked.index)
    return pd.DataFrame({
        "#": range(1, len(ranked) + 1),
        "Player": ranked.player_display_name + " · " + ranked.team.astype(str),
        "Pos": ranked.position,
        "Opp": ranked.opponent_team,
        "Model ATTD Odds": [
            _model_odds_probability(american, probability)
            for american, probability in zip(model_american, ranked.p_ge1)
        ],
        "Book ATTD Odds": [
            _odds_probability(american, probability)
            for american, probability in zip(book_american, ranked.p_book)
        ],
        "ATTD Value Gap": [
            _value_gap(model, book, model_p, book_p) or (
                "Pending" if pd.isna(model_p) else ""
            )
            for model, book, model_p, book_p in zip(
                model_american, book_american, ranked.p_ge1, ranked.p_book
            )
        ],
        "Hit": hit,
        "_p": ranked.p_ge1.astype(float),
        "_value": ranked["_value"].astype(float),
        "_candidate": tracker.qualifies_probability_gap(
            ranked["_value"], tracker.ATTD_VALUE_THRESHOLD
        ) & _bet_eligibility(ranked).to_numpy(),
    })


def _two_plus_display(df: pd.DataFrame) -> pd.DataFrame:
    ranked = df.copy()
    ranked["p_ge2"] = pd.to_numeric(ranked.get("p_ge2"), errors="coerce")
    if "two_plus_amer" in ranked:
        ranked["_book_2plus"] = pd.to_numeric(ranked["two_plus_amer"], errors="coerce")
        # A live sportsbook quote is only meaningful for players the book
        # actually offered in this market. If the release has no 2+ market at
        # all, retain the model-only placeholder behavior for older releases.
        if ranked["_book_2plus"].notna().any():
            ranked = ranked[ranked["_book_2plus"].notna()].copy()
    if "_book_2plus" in ranked:
        book_probability = ranked["_book_2plus"].map(_implied_probability)
    else:
        book_probability = pd.Series(pd.NA, index=ranked.index, dtype="Float64")
    ranked["_value"] = ranked["p_ge2"] - book_probability
    ranked = ranked.sort_values(
        ["_value", "player_display_name"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)
    model_odds = [
        _odds_probability(_fair_amer_from_probability(probability), probability)
        for probability in ranked.p_ge2
    ]
    if "_book_2plus" in ranked:
        book_american = ranked["_book_2plus"]
    else:
        book_american = pd.Series(pd.NA, index=ranked.index, dtype="Float64")
    book_probability = book_american.map(_implied_probability)
    book_odds = [
        _odds_probability(american, probability)
        for american, probability in zip(book_american, book_probability)
    ]
    model_american = ranked.p_ge2.map(_fair_amer_from_probability)
    value_gap = [
        _value_gap(model, book, model_p, book_p) or (
            "Pending" if pd.isna(model_p) and pd.notna(book_p) else ""
        )
        for model, book, model_p, book_p in zip(
            model_american, book_american, ranked.p_ge2, book_probability
        )
    ]
    return pd.DataFrame({
        "#": range(1, len(ranked) + 1),
        "Player": ranked.player_display_name + " · " + ranked.team.astype(str),
        "Pos": ranked.position,
        "Opp": ranked.opponent_team,
        "Model 2+ TD Odds": [
            value or ("Pending" if pd.isna(probability) else "Not implemented yet")
            for value, probability in zip(model_odds, ranked.p_ge2)
        ],
        "Book 2+ TD Odds": [value or "Not implemented yet" for value in book_odds],
        "2+ TD Value Gap": [
            value or (
                "Pending"
                if pd.isna(model_p) and pd.notna(book_p)
                else "Not implemented yet"
            )
            for value, model_p, book_p in zip(value_gap, ranked.p_ge2, book_probability)
        ],
        "_value": ranked["_value"].astype(float),
        "_candidate": tracker.qualifies_probability_gap(
            ranked["_value"], tracker.ATTD_VALUE_THRESHOLD
        ) & _bet_eligibility(ranked).to_numpy(),
    })


def _first_td_display(df: pd.DataFrame) -> pd.DataFrame:
    """First TD is a competing-risk allocation, not a per-player marginal price.

    p_first already sums to a fixed empirical constant across the whole game
    (roughly 94%, the historical rate an offensive skill player scores
    first), with the rest split among defense/special-teams/no-TD. book_amer
    here is DK's first_amer, de-vigged WITHIN the game (a genuine one-winner
    market, unlike ATTD's Yes-only quote) -- book_first_p_devigged already
    carries that de-vig, computed upstream in first_td/build_week1_board.py
    and first_td/publish_site_columns.py, not here.
    """
    ranked = df.copy()
    ranked["p_first"] = _numeric_column(ranked, "p_first")
    ranked["_book_first"] = _numeric_column(ranked, "book_first_p_devigged")
    if "first_amer" in ranked:
        ranked["_first_amer"] = pd.to_numeric(ranked["first_amer"], errors="coerce")
        if ranked["_first_amer"].notna().any():
            ranked = ranked[ranked["_first_amer"].notna()].copy()
    else:
        ranked["_first_amer"] = pd.Series(pd.NA, index=ranked.index, dtype="Float64")
    ranked["_value"] = ranked["p_first"] - ranked["_book_first"]
    ranked = ranked.sort_values(
        ["_value", "player_display_name"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)
    outcome = _numeric_column(ranked, "scored_first")
    hit = outcome.map(lambda value: "Yes" if value == 1 else ("No" if pd.notna(value) else ""))
    model_american = ranked["p_first"].map(_fair_amer_from_probability)
    model_odds = [
        _model_odds_probability(american, probability)
        for american, probability in zip(model_american, ranked["p_first"])
    ]
    book_odds = [
        _odds_probability(american, probability)
        for american, probability in zip(ranked["_first_amer"], ranked["_book_first"])
    ]
    value_gap = [
        _value_gap(model, book, model_p, book_p) or (
            "Pending" if pd.isna(model_p) else ""
        )
        for model, book, model_p, book_p in zip(
            model_american, ranked["_first_amer"], ranked["p_first"], ranked["_book_first"]
        )
    ]
    return pd.DataFrame({
        "#": range(1, len(ranked) + 1),
        "Player": ranked.player_display_name + " · " + ranked.team.astype(str),
        "Pos": ranked.position,
        "Opp": ranked.opponent_team,
        "Model First TD Odds": model_odds,
        "Book First TD Odds": [value or "Not implemented yet" for value in book_odds],
        "First TD Value Gap": value_gap,
        "Hit": hit,
        "_p": ranked["p_first"].astype(float),
        "_value": ranked["_value"].astype(float),
        "_candidate": tracker.qualifies_probability_gap(
            ranked["_value"], tracker.FIRST_TD_VALUE_THRESHOLD
        ) & _bet_eligibility(ranked).to_numpy(),
    })


def _style(view: pd.DataFrame):
    # Use an opaque, dark emerald treatment instead of a translucent tint. The
    # latter can be composited as gray by the dataframe grid on dark themes.
    candidate_row_bg = "background-color: #123229"
    candidate_focus = (
        "background-color: #1A4A3B; color: #B7F7D0; font-weight: 700"
    )
    missed_candidate_row_bg = "background-color: #BA797A"
    missed_candidate_focus = (
        "background-color: #BA797A; color: #3F2024; font-weight: 700"
    )

    def _missed_candidate(index: int) -> bool:
        return bool(
            view["_candidate"].iloc[index]
            and "Hit" in view
            and view["Hit"].iloc[index] == "No"
        )

    def _apply(df: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for i, candidate in enumerate(view["_candidate"]):
            if candidate:
                styles.iloc[i, :] = (
                    missed_candidate_row_bg if _missed_candidate(i) else candidate_row_bg
                )
        if "Model ATTD Odds" in df.columns:
            for i, _ in enumerate(view["_p"]):
                style = "color: #FFFFFF"
                if view["_candidate"].iloc[i]:
                    row_bg = missed_candidate_row_bg if _missed_candidate(i) else candidate_row_bg
                    style = f"{style}; {row_bg}"
                styles.iloc[i, df.columns.get_loc("Model ATTD Odds")] = style
        if "ATTD Value Gap" in df.columns:
            for i, value in enumerate(view["_value"]):
                if pd.isna(value):
                    continue
                color = "#35D08A" if value > 0 else "#F08A8A" if value < 0 else "#B8C0CC"
                style = f"color: {color}; font-weight: 700"
                if view["_candidate"].iloc[i]:
                    style = missed_candidate_focus if _missed_candidate(i) else candidate_focus
                styles.iloc[i, df.columns.get_loc("ATTD Value Gap")] = style
        if "Hit" in df.columns:
            for i, mark in enumerate(view["Hit"]):
                if mark == "Yes":
                    style = "color: #35D08A; font-weight: 700"
                    if view["_candidate"].iloc[i]:
                        style = f"{style}; background-color: #1A4A3B"
                    styles.iloc[i, df.columns.get_loc("Hit")] = style
                elif mark == "No" and view["_candidate"].iloc[i]:
                    styles.iloc[i, df.columns.get_loc("Hit")] = missed_candidate_focus
        if "Player" in df.columns:
            for i, candidate in enumerate(view["_candidate"]):
                if candidate:
                    focus = missed_candidate_focus if _missed_candidate(i) else candidate_focus
                    border = "#8F525A" if _missed_candidate(i) else "#35D08A"
                    styles.iloc[i, df.columns.get_loc("Player")] = (
                        f"{focus}; border-left: 3px solid {border}"
                    )
        return styles
    return _apply


def _first_td_style(view: pd.DataFrame):
    """Same opaque candidate treatment as _style, targeting First TD column names."""
    candidate_row_bg = "background-color: #123229"
    candidate_focus = (
        "background-color: #1A4A3B; color: #B7F7D0; font-weight: 700"
    )
    missed_candidate_row_bg = "background-color: #BA797A"
    missed_candidate_focus = (
        "background-color: #BA797A; color: #3F2024; font-weight: 700"
    )

    def _missed_candidate(index: int) -> bool:
        return bool(
            view["_candidate"].iloc[index]
            and "Hit" in view
            and view["Hit"].iloc[index] == "No"
        )

    def _apply(df: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for i, candidate in enumerate(view["_candidate"]):
            if candidate:
                styles.iloc[i, :] = (
                    missed_candidate_row_bg if _missed_candidate(i) else candidate_row_bg
                )
        if "Model First TD Odds" in df.columns:
            for i, _ in enumerate(view["_p"]):
                style = "color: #FFFFFF"
                if view["_candidate"].iloc[i]:
                    row_bg = missed_candidate_row_bg if _missed_candidate(i) else candidate_row_bg
                    style = f"{style}; {row_bg}"
                styles.iloc[i, df.columns.get_loc("Model First TD Odds")] = style
        if "First TD Value Gap" in df.columns:
            for i, value in enumerate(view["_value"]):
                if pd.isna(value):
                    continue
                color = "#35D08A" if value > 0 else "#F08A8A" if value < 0 else "#B8C0CC"
                style = f"color: {color}; font-weight: 700"
                if view["_candidate"].iloc[i]:
                    style = missed_candidate_focus if _missed_candidate(i) else candidate_focus
                styles.iloc[i, df.columns.get_loc("First TD Value Gap")] = style
        if "Hit" in df.columns:
            for i, mark in enumerate(view["Hit"]):
                if mark == "Yes":
                    style = "color: #35D08A; font-weight: 700"
                    if view["_candidate"].iloc[i]:
                        style = f"{style}; background-color: #1A4A3B"
                    styles.iloc[i, df.columns.get_loc("Hit")] = style
                elif mark == "No" and view["_candidate"].iloc[i]:
                    styles.iloc[i, df.columns.get_loc("Hit")] = missed_candidate_focus
        if "Player" in df.columns:
            for i, candidate in enumerate(view["_candidate"]):
                if candidate:
                    focus = missed_candidate_focus if _missed_candidate(i) else candidate_focus
                    border = "#8F525A" if _missed_candidate(i) else "#35D08A"
                    styles.iloc[i, df.columns.get_loc("Player")] = (
                        f"{focus}; border-left: 3px solid {border}"
                    )
        return styles
    return _apply


def _two_plus_style(view: pd.DataFrame):
    """Apply the same opaque candidate treatment to the 2+ market."""
    candidate_row_bg = "background-color: #123229"
    candidate_focus = (
        "background-color: #1A4A3B; color: #B7F7D0; font-weight: 700"
    )

    def _apply(df: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for i, candidate in enumerate(view["_candidate"]):
            if candidate:
                styles.iloc[i, :] = candidate_row_bg
                if "Player" in df.columns:
                    styles.iloc[i, df.columns.get_loc("Player")] = (
                        f"{candidate_focus}; border-left: 3px solid #35D08A"
                    )
                if "2+ TD Value Gap" in df.columns:
                    styles.iloc[i, df.columns.get_loc("2+ TD Value Gap")] = candidate_focus
        if "2+ TD Value Gap" in df.columns:
            for i, value in enumerate(view["_value"]):
                if pd.isna(value) or view["_candidate"].iloc[i]:
                    continue
                color = "#35D08A" if value > 0 else "#F08A8A" if value < 0 else "#B8C0CC"
                styles.iloc[i, df.columns.get_loc("2+ TD Value Gap")] = (
                    f"color: {color}; font-weight: 700"
                )
        return styles

    return _apply


def _desktop_column_config() -> dict:
    return {
        "#": st.column_config.NumberColumn("#", format="%d", width=50, pinned=True,
                                           help="Row number in this list as currently sorted."),
        "Player": st.column_config.TextColumn("Player", help="Name and NFL team."),
        "Opp": st.column_config.TextColumn("Opp", help="Opponent this week."),
        "Model ATTD Odds": st.column_config.TextColumn(
            "Model ATTD Odds",
            help="Our model American odds and percentage chance of a rushing or receiving TD.",
        ),
        "Book ATTD Odds": st.column_config.TextColumn(
            "Book ATTD Odds",
            help="The book's American odds and implied percentage chance of a rushing or receiving TD.",
        ),
        "ATTD Value Gap": st.column_config.TextColumn(
            "ATTD Value Gap",
            help="Book-minus-model American-odds gap and model-minus-book probability differential. Positive means more value in our model.",
        ),
        "Hit": st.column_config.TextColumn(
            "Hit", help="Did they score a rushing or receiving TD?",
        ),
    }


def _phone_column_config() -> dict:
    cfg = _desktop_column_config()
    cfg["#"] = st.column_config.NumberColumn(
        "#", format="%d", width=PHONE_WIDTHS["#"], pinned=True,
        help="Row number in this list as currently sorted.",
    )
    cfg["Player"] = st.column_config.TextColumn(
        "Player", width=PHONE_WIDTHS["Player"], pinned=True,
        help="Name and NFL team.",
    )
    cfg["Model ATTD Odds"] = st.column_config.TextColumn(
        PHONE_LABELS["Model ATTD Odds"],
        width=PHONE_WIDTHS["Model ATTD Odds"],
        help="Model American odds and percentage chance of a rushing or receiving TD.",
    )
    cfg["Book ATTD Odds"] = st.column_config.TextColumn(
        PHONE_LABELS["Book ATTD Odds"],
        width=PHONE_WIDTHS["Book ATTD Odds"],
        help="Book American odds and implied percentage chance of a rushing or receiving TD.",
    )
    cfg["ATTD Value Gap"] = st.column_config.TextColumn(
        PHONE_LABELS["ATTD Value Gap"],
        width=PHONE_WIDTHS["ATTD Value Gap"],
        help="Book-minus-model American-odds gap and model-minus-book percentage differential.",
    )
    cfg["Hit"] = st.column_config.TextColumn(
        "Hit", width=PHONE_WIDTHS["Hit"],
        help="Did they score a rushing or receiving TD?",
    )
    return cfg


def _two_plus_column_config() -> dict:
    return {
        "#": st.column_config.NumberColumn(
            "#", format="%d", width=50, pinned=True,
            help="Row number in this list as currently sorted.",
        ),
        "Player": st.column_config.TextColumn(
            "Player", help="Name and NFL team.",
        ),
        "Model 2+ TD Odds": st.column_config.TextColumn(
            "Model 2+ TD Odds",
            help="Model American odds and percentage chance of two or more rushing or receiving TDs.",
        ),
        "Book 2+ TD Odds": st.column_config.TextColumn(
            "Book 2+ TD Odds",
            help="DraftKings American odds and implied probability for two or more touchdowns.",
        ),
        "2+ TD Value Gap": st.column_config.TextColumn(
            "2+ TD Value Gap",
            help="Book-minus-model American-odds gap and model-minus-book probability differential.",
        ),
    }


def _two_plus_phone_column_config() -> dict:
    cfg = _two_plus_column_config()
    cfg["#"] = st.column_config.NumberColumn(
        "#", format="%d", width=PHONE_WIDTHS["#"], pinned=True,
        help="Row number in this list as currently sorted.",
    )
    cfg["Player"] = st.column_config.TextColumn(
        "Player", width=PHONE_WIDTHS["Player"], pinned=True,
        help="Name and NFL team.",
    )
    cfg["Model 2+ TD Odds"] = st.column_config.TextColumn(
        "Model", width=PHONE_WIDTHS["Model ATTD Odds"],
        help="Model American odds and percentage chance of two or more TDs.",
    )
    cfg["Book 2+ TD Odds"] = st.column_config.TextColumn(
        "Book", width=PHONE_WIDTHS["Book ATTD Odds"],
        help="DraftKings two-plus touchdown odds and implied probability.",
    )
    cfg["2+ TD Value Gap"] = st.column_config.TextColumn(
        "Value", width=PHONE_WIDTHS["ATTD Value Gap"],
        help="Two-plus book-minus-model odds gap and probability differential.",
    )
    return cfg


def _first_td_column_config() -> dict:
    return {
        "#": st.column_config.NumberColumn(
            "#", format="%d", width=50, pinned=True,
            help="Row number in this list as currently sorted.",
        ),
        "Player": st.column_config.TextColumn("Player", help="Name and NFL team."),
        "Opp": st.column_config.TextColumn("Opp", help="Opponent this week."),
        "Model First TD Odds": st.column_config.TextColumn(
            "Model First TD Odds",
            help="Our lambda-share model American odds and percentage chance of scoring the game's first touchdown.",
        ),
        "Book First TD Odds": st.column_config.TextColumn(
            "Book First TD Odds",
            help="DraftKings American odds and de-vigged (within-game) percentage chance of scoring the game's first touchdown.",
        ),
        "First TD Value Gap": st.column_config.TextColumn(
            "First TD Value Gap",
            help="Book-minus-model American-odds gap and model-minus-book probability differential. Positive means more value in our model.",
        ),
        "Hit": st.column_config.TextColumn(
            "Hit", help="Did they score the game's first touchdown?",
        ),
    }


def _first_td_phone_column_config() -> dict:
    cfg = _first_td_column_config()
    cfg["#"] = st.column_config.NumberColumn(
        "#", format="%d", width=PHONE_WIDTHS["#"], pinned=True,
        help="Row number in this list as currently sorted.",
    )
    cfg["Player"] = st.column_config.TextColumn(
        "Player", width=PHONE_WIDTHS["Player"], pinned=True,
        help="Name and NFL team.",
    )
    cfg["Model First TD Odds"] = st.column_config.TextColumn(
        "Model", width=PHONE_WIDTHS["Model ATTD Odds"],
        help="Model American odds and percentage chance of scoring first.",
    )
    cfg["Book First TD Odds"] = st.column_config.TextColumn(
        "Book", width=PHONE_WIDTHS["Book ATTD Odds"],
        help="DraftKings American odds and de-vigged percentage chance of scoring first.",
    )
    cfg["First TD Value Gap"] = st.column_config.TextColumn(
        "Value", width=PHONE_WIDTHS["ATTD Value Gap"],
        help="Book-minus-model American-odds gap and model-minus-book percentage differential.",
    )
    cfg["Hit"] = st.column_config.TextColumn(
        "Hit", width=PHONE_WIDTHS["Hit"],
        help="Did they score the game's first touchdown?",
    )
    return cfg


def _render_week_recommended(
    board_priced: pd.DataFrame, season: int, releases: dict, *, show_first_td: bool,
) -> None:
    """2+ TD and First TD candidates are rare enough that 'recommended only'
    pools every matchup in the week into one board instead of filtering
    one game at a time -- a per-matchup view would mostly show nothing."""
    market = "first" if show_first_td else "two_plus"
    market_label = "First TD" if show_first_td else "2+ TD"
    threshold = tracker.FIRST_TD_VALUE_THRESHOLD if show_first_td else tracker.ATTD_VALUE_THRESHOLD
    st.info(
        f"Important: {market_label} predictions have no historical backtest"
        + (" of any kind" if show_first_td else " yet")
        + f". This view is forward-looking tracking only, not evidence of "
        "accuracy or profitability."
    )
    st.caption(
        f"Every {market_label} candidate across this week's matchups: raw "
        f"value gap of at least +{100 * threshold:.1f} percentage point. "
        "Sorted by value gap, highest first."
    )
    _render_scorecards(board_priced, season, releases, market=market)
    st.markdown(f"#### Recommended {market_label} players this week")
    shown = _board(
        board_priced, f"atd-week-recommended-{market}", "",
        show_two_plus=not show_first_td, show_first_td=show_first_td,
        recommended_only=True, phone_show_opp=True,
    )
    if not shown:
        st.info(
            f"No players clear the {market_label} value-gap threshold this week."
        )


def _board(
    view: pd.DataFrame, slug: str, search: str, *,
    show_two_plus: bool = False, show_first_td: bool = False,
    recommended_only: bool = False, phone_show_opp: bool = False,
) -> int:
    if show_first_td:
        table = _first_td_display(view)
        graded = _numeric_column(view, "scored_first").notna().any()
        desktop_cols = FIRST_TD_DESKTOP_COLS if graded else [c for c in FIRST_TD_DESKTOP_COLS if c != "Hit"]
        phone_cols = FIRST_TD_PHONE_COLS if graded else [c for c in FIRST_TD_PHONE_COLS if c != "Hit"]
        desktop_config = _first_td_column_config()
        phone_config = _first_td_phone_column_config()
    elif show_two_plus:
        table = _two_plus_display(view)
        desktop_cols = TWO_PLUS_DESKTOP_COLS
        phone_cols = TWO_PLUS_PHONE_COLS
        desktop_config = _two_plus_column_config()
        phone_config = _two_plus_phone_column_config()
    else:
        table = _display(view)
        graded = pd.to_numeric(view.scored_anytime, errors="coerce").notna().any()
        desktop_cols = DESKTOP_COLS if graded else [c for c in DESKTOP_COLS if c != "Hit"]
        phone_cols = PHONE_COLS if graded else [c for c in PHONE_COLS if c != "Hit"]
        desktop_config = _desktop_column_config()
        phone_config = _phone_column_config()
    if recommended_only:
        table = table[table["_candidate"]].reset_index(drop=True)
    if table.empty:
        return 0
    if phone_show_opp and "Opp" not in phone_cols:
        insert_at = phone_cols.index("Player") + 1
        phone_cols = phone_cols[:insert_at] + ["Opp"] + phone_cols[insert_at:]
    style_fn = (
        _first_td_style(table) if show_first_td
        else _two_plus_style(table) if show_two_plus
        else _style(table)
    )
    style = table[desktop_cols]
    phone = table[phone_cols]
    desktop_data = style.style.apply(style_fn, axis=None) if style_fn else style
    phone_data = phone.style.apply(style_fn, axis=None) if style_fn else phone
    dataframe_phone_desktop(
        desktop_data,
        phone_data,
        slug=slug,
        hide_index=True,
        width="stretch",
        height=exact_table_height(len(table)),
        column_config=desktop_config,
        phone_column_config=phone_config,
        key=f"atd_grid_{slug}_{search}_{len(table)}_"
            f"{'first' if show_first_td else 'two_plus' if show_two_plus else 'anytime'}_"
            f"{'rec' if recommended_only else 'all'}",
    )
    return len(table)


def _reading_guide() -> None:
    with st.expander("How to read this board"):
        st.markdown("""
Chance a skill player scores a rushing or receiving touchdown. Passing TDs are
out. This is not even money: a typical quote is around one in five, so misses
will outnumber hits. Over full 2025 the sportsbooks were still about 0.08% more
accurate. On these eight demo weeks our numbers were closer in 5; that is not a
betting record. For fun, not a proven edge. Bet responsibly.

**Desktop columns.** #, Player (name and team), Pos, Opp, Model ATTD Odds,
Book ATTD Odds, ATTD Value Gap, Hit. The odds columns combine American odds
with the implied percentage chance. Value Gap combines the book-minus-model
American-odds gap with the model-minus-book percentage differential, such as
`+1.1%`. On live 2026 boards, highlighted rows meet the raw `>= +0.5pp`
paper-bet rule and represent 1U candidates.

**Phone columns.** #, Player, Model, Book, Value, Hit. The full column meanings
are available in each column's help text. The list is sorted by ATTD Value Gap,
highest first.

Use the **Market** control to switch between Anytime TD, 2+ TD, and First TD.
Only one market renders at a time.

**2+ TD.** When the pasted release includes that market, the view shows model
odds, current DraftKings odds, and the value gap for players with a listed 2+
price. Older releases without that market show a clear not-implemented
placeholder before games begin. Completed matchups without a published 2+
market do not receive retroactive model odds; once grading supplies final
outcomes, they contribute only to a results-only tally and never to a betting
W-L, units, ROI, or backtest result. The 2+ TD probabilities have no
historical backtest or published 2+ test results yet, so that view is
forward-looking tracking only—not evidence of model accuracy or
profitability. A verified replacement can appear with Book odds while its
Model and Value cells say Pending when the current-week model input is not
available; it is excluded from value-bet tracking until then.

**First TD.** This is a different kind of probability than Anytime or 2+:
exactly one player can score a game's first touchdown, so it is a
competing-risk allocation across both rosters, not a per-player marginal
chance. Our model splits each game's mass proportionally to each player's
Anytime TD rate, scaled by the historical rate an offensive skill player
scores first at all (roughly 94% of games; the rest go to defense, special
teams, or no score). DraftKings' First TD price is de-vigged within the
game, since first touchdown is a genuine one-winner market (unlike the
Yes-only Anytime quote). There is no historical First TD backtest anywhere
in this project for any season, only a forward Week 1 board, so treat this
view as entertainment, not a proven edge, even more so than 2+ TD. Because
p_first values within a game are not independent (they split a fixed pool,
not separate coin flips) and real bell-cow players already show a
persistent -5pp to -8pp gap vs DraftKings' price, First TD candidates use a
wider +3.0pp gap rule instead of Anytime/2+ TD's +0.5pp.

The live cards track those 1U candidates across the 2026 season: settled/open
paper bets, net units, settled ROI, and an uncertainty range. Open bets stay out
of the P&L. After five settled games and 20 settled bets, the board also shows an
approximate 95% ROI range from a deterministic game-block bootstrap. It is an
empirical uncertainty range, not a guarantee. The 2+ TD view uses the same
+0.5pp rule as Anytime; First TD uses its own wider +3.0pp rule. Each shows
its own cards when prices and graded outcomes are available.
Week 1 is organized by matchup, then by team (for example, NE vs SEA with
separate NE and SEA boards).
        """)


def render() -> None:
    st.title("Touchdown Props")
    st.caption(
        "Anytime, 2+, and First TD scorer odds vs DraftKings. Passing TDs are "
        "out of every market. Live 2026 releases plus a 2025 demo. For fun. Bet responsibly."
    )
    releases = available_releases()
    if not releases:
        st.error("Anytime TD demo files are missing.")
        st.stop()
    live_keys = sorted((key for key in releases if key[0] == LIVE_SEASON), reverse=True)
    demo = available_weeks()
    year_weeks = {
        DEMO_SEASON: sorted(demo),
        LIVE_SEASON: sorted(set([1] + [week for season, week in live_keys if season == LIVE_SEASON])),
    }
    years = sorted(year_weeks, reverse=True)
    with st.container(key="jsa-filter-bar"):
        controls = st.columns([1, 1, 2])
        seeded_year = page_common.seed_widget_from_query("atd_year", "atd_year", years)
        year_kwargs = {"key": "atd_year"}
        if not seeded_year and "atd_year" not in st.session_state:
            year_kwargs["index"] = years.index(LIVE_SEASON) if LIVE_SEASON in years else 0
        season = int(controls[0].selectbox("Year", years, **year_kwargs))
        page_common.sync_query_value("atd_year", season)
        weeks = year_weeks[season]
        if "atd_week" in st.session_state and st.session_state["atd_week"] not in weeks:
            del st.session_state["atd_week"]
        seeded_week = page_common.seed_widget_from_query("atd_week", "atd_week", weeks)
        week_kwargs = {"key": "atd_week"}
        default_week = 1 if season == LIVE_SEASON else (DEFAULT_WEEK if DEFAULT_WEEK in weeks else weeks[0])
        if not seeded_week and "atd_week" not in st.session_state:
            week_kwargs["index"] = weeks.index(default_week)
        week = int(controls[1].selectbox("Week", weeks, **week_kwargs))
        page_common.sync_query_value("atd_week", week)
        search = controls[2].text_input("Search player", placeholder="Barkley, Jefferson", key="atd_search")
    available = releases | {(DEMO_SEASON, w): p for w, p in demo.items()}
    if season == LIVE_SEASON:
        st.caption(
            "Live 2026 prices are manually copied from DraftKings when available. "
            "No odds API is used."
        )
        meta = _live_metadata(season, week)
        if meta:
            book_value = meta.get("book", [])
            books = ", ".join(book_value) if isinstance(book_value, list) else str(book_value)
            st.caption(f"Book: {books or 'manual paste'} · Last capture: {meta.get('capture_max', 'unknown')}")
    with st.container(horizontal=True, vertical_alignment="center"):
        is_live = season == LIVE_SEASON
        st.badge("Live" if is_live else "Demo", icon=":material/live_tv:" if is_live else ":material/science:",
                 color="green" if is_live else "orange")
        st.caption("Priced players only. Sorted by the active market's Value Gap (highest first). " +
                   ("Cumulative 2026 Week 1 release." if is_live else "2025 weeks 10-17 demo."))
    _reading_guide()

    if (season, week) not in available:
        if season == LIVE_SEASON:
            st.info(f"2026 Week {week} is selected and awaiting a manual odds release. "
                    "The 2025 demo remains available from the Year and Week selectors.")
        else:
            st.info(f"{season} Week {week} does not have a published board yet.")
        return

    source = available[(season, week)]
    raw = _load_csv(str(source), source.stat().st_mtime_ns)
    need = [
        "player_display_name", "position", "team", "opponent_team",
        "p_ge1", "p_book", "fair_amer", "book_amer", "scored_anytime",
    ]
    missing = [c for c in need if c not in raw.columns]
    if missing:
        st.error(f"Demo CSV is missing columns: {missing}")
        st.stop()

    priced = priced_rows(raw)
    if priced.empty:
        st.warning("No book Yes prices for this week.")
        st.stop()

    board_priced = priced
    if search:
        board_priced = priced[priced.player_display_name.str.contains(
            search, case=False, na=False, regex=False,
        )]

    model_pending = int(board_priced.p_ge1.isna().sum())
    st.caption(f"{len(board_priced)} priced · all positions")
    if model_pending:
        row_word = "row" if model_pending == 1 else "rows"
        verb = "awaits" if model_pending == 1 else "await"
        st.caption(
            f"{model_pending} quoted replacement {row_word} {verb} model inputs; "
            "Pending rows are excluded from value-bet tracking."
        )
    matchups = list(_matchup_groups(board_priced))
    if not matchups:
        st.info("No matchups match this search.")
        return
    matchup_key = f"atd_matchup_{season}_{week}"

    view = st.segmented_control(
        "Market",
        options=["Anytime TD", "2+ TD", "First TD"],
        default="Anytime TD",
        key=f"atd_view_{season}_{week}",
        help="Anytime TD is our chance a skill player scores a rushing or "
             "receiving TD. 2+ TD and First TD are separate, less-tested markets.",
    )
    if view is None:
        # A segmented_control can be deselected back to no selection; treat
        # that the same as the base Anytime TD view rather than crashing on
        # a None market label below.
        view = "Anytime TD"
    show_two_plus = view == "2+ TD"
    show_first_td = view == "First TD"
    recommended_default = show_two_plus or show_first_td
    recommended_only = st.toggle(
        "Recommended only",
        value=st.session_state.get(f"atd_rec_{season}_{week}_{view}", recommended_default),
        key=f"atd_rec_{season}_{week}_{view}",
        help="2+ TD and First TD show every recommended player across the "
             "full week's matchups, since so few clear the bar. Anytime TD "
             "still filters within the selected matchup.",
    )
    pooled_view = recommended_only and (show_two_plus or show_first_td)
    shadow_key = f"{matchup_key}__shadow"

    if pooled_view:
        # The Matchup selectbox is not rendered in the pooled week view.
        # Streamlit drops a widget's session_state entry once its widget is
        # skipped for a run, which would otherwise erase both the selection
        # and the manual-pick flag. Stash the last selection in a plain
        # (non-widget) key so it can be restored once the selectbox returns.
        if matchup_key in st.session_state:
            st.session_state[shadow_key] = st.session_state[matchup_key]
        _render_week_recommended(
            board_priced, season, releases, show_first_td=show_first_td,
        )
        return

    matchup_labels = [item[0] for item in matchups]
    if matchup_key not in st.session_state and shadow_key in st.session_state:
        shadow_value = st.session_state[shadow_key]
        if shadow_value in matchup_labels:
            st.session_state[matchup_key] = shadow_value
            st.session_state[f"{matchup_key}__manual"] = True
    _seed_matchup_default(matchups, matchup_key)

    selected_label = st.selectbox(
        "Matchup", matchup_labels,
        key=matchup_key,
        on_change=_mark_matchup_manual,
        args=(f"{matchup_key}__manual",),
        help="Choose a game to view both teams' touchdown prop boards.",
    )
    label, teams, matchup = next(item for item in matchups if item[0] == selected_label)

    two_plus_prices_available = _has_two_plus_prices(matchup)
    display_only_two_plus = _is_display_only_two_plus_matchup(matchup)
    completed_without_two_plus_market = (
        _matchup_is_started(matchup)
        and not two_plus_prices_available
        and not display_only_two_plus
    )
    first_td_prices_available = _has_first_td_prices(matchup)
    display_only_first_td = _is_display_only_first_td_matchup(matchup)
    completed_without_first_td_market = (
        _matchup_is_started(matchup)
        and not first_td_prices_available
        and not display_only_first_td
    )
    if show_first_td:
        st.info(
            "Important: First TD predictions have no historical backtest of any "
            "kind. There is no first-touchdown market data anywhere in this "
            "project for any season, so this view is a forward Week 1 board "
            "only—not evidence of accuracy or profitability, even more so than "
            "the 2+ TD view."
        )
        if completed_without_first_td_market:
            st.info(
                "This matchup was completed before First TD prices were "
                "published, so model First TD odds are not shown retroactively. "
                "Once grading supplies the final outcome, it is counted only in "
                "the results-only tally—not in betting W-L, units, ROI, or "
                "backtest results."
            )
        elif first_td_prices_available:
            st.caption(
                "First TD view: model probability (a competing-risk allocation "
                "across the whole game, not a per-player marginal chance), "
                "DraftKings' price de-vigged within the game, and the value gap. "
                f"A wider +{100 * tracker.FIRST_TD_VALUE_THRESHOLD:.1f}pp gap rule "
                "(vs Anytime/2+ TD's +0.5pp) powers the 1U paper tracker below, "
                "since real bell-cow players already show a persistent -5pp to "
                "-8pp gap here that a narrower rule would misread as value."
            )
        elif display_only_first_td:
            st.info(
                f"Display-only historical First TD model view for {label}. "
                "No DraftKings First TD prices were captured, so Book First TD "
                "Odds and the value gap are unavailable; this matchup is "
                "excluded from First TD betting and P&L."
            )
        else:
            st.info(
                "First TD sportsbook prices are not available for this release "
                "yet. The model probability is shown where this release has one."
            )
        _render_scorecards(priced, season, releases, market="first")
    elif show_two_plus:
        st.info(
            "Important: 2+ TD predictions have no historical backtest yet. "
            "No 2+ test results are available, so this view is forward-looking "
            "tracking only—not evidence of accuracy or profitability."
        )
        if completed_without_two_plus_market:
            st.info(
                "This matchup was completed before 2+ TD prices were published, "
                "so model 2+ odds are not shown retroactively. Once grading supplies "
                "the final 2+ outcomes, they are counted only in the results-only "
                "tally—not in betting W-L, units, ROI, or backtest results."
            )
        elif two_plus_prices_available:
            st.caption("2+ TD view: model probability, current DraftKings price, and value gap. The same +0.5pp gap rule powers the 1U paper tracker below. First-TD prices are retained in the release data and shown in the separate First TD view.")
        elif display_only_two_plus:
            st.info(
                f"Display-only historical 2+ TD model view for {label}. "
                "No DraftKings 2+ prices were captured, so Book 2+ TD Odds "
                "and the value gap are unavailable; this matchup is excluded "
                "from 2+ betting and P&L."
            )
        else:
            st.info(
                "2+ TD sportsbook prices are not available for this release yet. "
                "The model probability is shown where this release has one."
            )
        _render_scorecards(priced, season, releases, market="two_plus")
    else:
        _render_scorecards(priced, season, releases)
        st.caption(
            ("Showing only" if recommended_only else "Highlighted rows are")
            + " 1U paper-bet candidates: raw ATTD Value Gap of at least "
            "+0.5 percentage point."
        )

    st.markdown(f"#### {label}")
    if completed_without_first_td_market and show_first_td:
        st.caption("No retroactive First TD prediction table for this completed matchup.")
    elif completed_without_two_plus_market and show_two_plus:
        st.caption("No retroactive 2+ TD prediction table for this completed matchup.")
    else:
        shown_total = 0
        for team in teams:
            team_view = matchup[matchup.team.astype(str).eq(team)]
            if team_view.empty:
                continue
            st.markdown(f"**{team} {view}s**")
            shown_total += _board(
                team_view,
                f"atd-{team.lower()}-{label.replace(' ', '-')}",
                search or "",
                show_two_plus=show_two_plus,
                show_first_td=show_first_td,
                recommended_only=recommended_only,
            )
        if recommended_only and shown_total == 0:
            st.caption("No players clear the value-gap threshold for this matchup and market.")
