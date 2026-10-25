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
from publishing import first_td_v3
from publishing.td_releases import MANIFEST_NAME, canonical_td_releases, read_td_release
from publishing.first_td_strategy import (
    attach_first_td_v3,
    frozen_pick_ids_v3,
    load_first_td_best_value_v3,
    published_board_rankings,
)
from dashboard_chrome import dataframe_phone_desktop, exact_table_height
from team_display import public_team_abbr

_HERE = Path(__file__).resolve().parents[1]
_DIR = _HERE / "betting" / "anytime_td"
DEMO_SEASON = 2025
LIVE_SEASON = 2026
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
RECOMMENDED_LABEL = "Recommended"
ALL_RESULTS_LABEL = "All results"
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
    # Measured 2026-09-29: "{first} {last} · {team}" at 128px ellipsized the
    # team code mid-abbreviation ("DET" -> "DE", "SEA" -> "SE") for longer names
    # (e.g. "Amon-Ra St. Brown · DET"). Player stays pinned; the extra width
    # is absorbed by panning the row sideways, which the plan allows.
    "Player": 175,
    "Model ATTD Odds": 132,
    "Book ATTD Odds": 132,
    "ATTD Value Gap": 190,
    "Hit": 150,
    # First TD book cells read "+1200 · 7.7% implied" (20 characters), wider than
    # the Anytime "+89.1k · 100.0%" worst case; Expected Return is a short "+12%" that
    # may carry a tag such as " · over cap".
    "Book First TD Odds": 176,
    "Expected Return": 140,
}
TWO_PLUS_DESKTOP_COLS = [
    "#", "Player", "Pos", "Opp", "Model 2+ TD Odds", "Book 2+ TD Odds",
    "2+ TD Value Gap", "Hit",
]
TWO_PLUS_PHONE_COLS = [
    "#", "Player", "Model 2+ TD Odds", "Book 2+ TD Odds", "2+ TD Value Gap", "Hit",
]
FIRST_TD_DESKTOP_COLS = [
    "#", "Player", "Pos", "Opp", "Model First TD Odds", "Book First TD Odds",
    "Expected Return", "Hit",
]
# Expected Return is the sort key, so on a phone it sits first among the panning columns.
FIRST_TD_PHONE_COLS = [
    "#", "Player", "Expected Return", "Model First TD Odds", "Book First TD Odds", "Hit",
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
    return {key: entry["csv_path"] for key, entry in canonical_td_releases(_DIR).items()}


def default_release(options: list[tuple[int, int]]) -> tuple[int, int]:
    """Prefer the latest published live 2026 board when one is available."""
    if not options:
        raise ValueError("at least one release is required")
    live = sorted(
        (key for key in options if key[0] == LIVE_SEASON),
        reverse=True,
    )
    return live[0] if live else sorted(options)[0]


def _missing_scheduled_markets(frame: pd.DataFrame, season: int, week: int) -> list[str]:
    """Name scheduled 2026 games absent from a published weekly board."""
    if int(season) != LIVE_SEASON:
        return []
    schedule_path = _HERE / "betting" / "nfl_2026_schedule.csv"
    if not schedule_path.is_file():
        return []
    schedule = pd.read_csv(schedule_path)
    slate = schedule.loc[
        pd.to_numeric(schedule.season, errors="coerce").eq(int(season))
        & pd.to_numeric(schedule.week, errors="coerce").eq(int(week))
        & schedule.game_type.astype(str).eq("REG")
    ]
    covered = set(frame.get("game_id", pd.Series(dtype=str)).dropna().astype(str))
    return sorted(
        f"{row.away_team} at {row.home_team}"
        for row in slate.itertuples(index=False)
        if str(row.game_id) not in covered
    )


def available_weeks() -> dict[int, Path]:
    return {week: entry["csv_path"] for (season, week), entry in canonical_td_releases(_DIR).items()
            if season == DEMO_SEASON}


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


NO_HISTORY_REASONS = {"synthetic_or_unresolved_identity", "zero_prior_games", "missing_history"}


def _eligibility_tags(df: pd.DataFrame) -> list[str]:
    """Suffix explaining why a row with a real-looking gap is never highlighted.

    A rookie or unmatched player is priced by the model with no NFL form
    history, so the gap is a guess and the row is barred from candidates.
    """
    eligible = _bet_eligibility(df).to_numpy()
    if "eligibility_reason" in df:
        reasons = df["eligibility_reason"].astype("string").fillna("").to_numpy()
    else:
        reasons = [""] * len(df)
    tags = []
    for ok, reason in zip(eligible, reasons):
        if ok:
            tags.append("")
        elif reason in NO_HISTORY_REASONS or not reason:
            tags.append(" · no history")
        else:
            tags.append(" · not eligible")
    return tags


def _with_tag(value: str, tag: str) -> str:
    """Attach a tag only to a real gap, never to Pending or a placeholder."""
    if not tag or not value or value in {"Pending", "Not implemented yet"}:
        return value
    return value + tag


def _pending_replacement_caption(model_pending: int) -> str | None:
    if model_pending <= 0:
        return None
    row_word = "row" if model_pending == 1 else "rows"
    verb = "awaits" if model_pending == 1 else "await"
    return (
        f"{model_pending} quoted replacement {row_word} {verb} model inputs; "
        "Pending rows are excluded from value-bet tracking."
    )


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
        shown = [public_team_abbr(team) for team in teams]
        label = f"{shown[0]} vs {shown[1]}" if len(shown) >= 2 else str(shown[0])
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


def _week_is_complete(frame: pd.DataFrame, season: int, week: int) -> bool:
    """Use final-game coverage from the grading stamp, independent of player rows.

    A final game can still have player settlements awaiting evidence. The stamp
    counts final games while the release supplies the scheduled game set, so
    completion must not depend on every row having a result.
    """
    if int(season) != LIVE_SEASON or frame.empty or "game_id" not in frame:
        return False
    scheduled_games = int(frame.game_id.dropna().astype(str).nunique())
    if scheduled_games == 0:
        return False
    path = _DIR / f"grading_{int(season)}_week{int(week):02d}.json"
    try:
        stamp = json.loads(path.read_text(encoding="utf-8"))
        final_games = int(stamp.get("final_games", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    return final_games >= scheduled_games


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
    paths: tuple[str, ...], modified_at: tuple[int, ...], market: str = "anytime",
    prediction_mode: str | None = None, model_version: str | None = None,
    through_week: int | None = None,
) -> dict:
    """Load the newest published file for each live week and score its paper bets."""
    del modified_at  # cache key; the files themselves are read below
    frame = tracker.aggregate_published_csvs(paths)
    if prediction_mode is not None:
        frame = frame[frame.prediction_mode.eq(prediction_mode)]
    if model_version is not None:
        frame = frame[frame.model_version.eq(model_version)]
    if through_week is not None and "week" in frame:
        weeks = pd.to_numeric(frame["week"], errors="coerce")
        frame = frame[weeks.le(int(through_week))]
    return _tracker_for_market(frame, market)


@st.cache_data(ttl=900)
def _load_retrospective_first_td_tally(
    paths: tuple[str, ...], modified_at: tuple[int, ...], through_week: int,
) -> dict[str, int]:
    """Load outcome coverage only; retrospective probabilities are not bets."""
    del modified_at
    frame = tracker.aggregate_published_csvs(paths)
    if "prediction_mode" in frame:
        frame = frame[frame.prediction_mode.eq("retrospective")]
    if "week" in frame:
        frame = frame[pd.to_numeric(frame.week, errors="coerce").le(int(through_week))]
    return _first_td_results_tally(frame)


def _tracker_for_market(frame: pd.DataFrame, market: str) -> dict:
    """Apply the market's fixed selection and settlement rules to one scope."""
    if market == "two_plus":
        return tracker.season_tracker(
            frame,
            model_probability_col="p_ge2",
            book_probability_col=None,
            book_price_col="two_plus_amer",
            outcome_col="scored_two_plus",
            threshold=tracker.TWO_PLUS_RATIO_THRESHOLD,
            qualifies=lambda f: tracker.qualifies_two_plus_ratio(
                f["_model_probability"], f["_book_probability"],
            ),
        )
    if market == "first":
        return tracker.season_tracker(
            frame,
            model_probability_col="p_first",
            book_probability_col="book_first_p_devigged",
            book_price_col="first_amer",
            outcome_col="scored_first",
            threshold=tracker.FIRST_TD_VALUE_THRESHOLD,
            qualifies=lambda f: tracker.qualifies_first_td_ev(
                f["_model_probability"], f["_book_price"], f["_value_gap"],
            ),
        )
    return tracker.season_tracker(frame)


def _first_td_game_results(source: Path, season: int, week: int) -> tuple[dict[str, dict], str | None]:
    """Read the grader's adjacent game-result sidecar for a published release."""
    path = source.with_name(f"first_td_results_{int(season)}_week{int(week):02d}.json")
    if not path.is_file():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"First TD result sidecar could not be read: {exc}"
    if not isinstance(payload, dict):
        return {}, "First TD result sidecar has an invalid top-level value."
    if (
        payload.get("schema_version") != 1
        or str(payload.get("season", "")) != str(season)
        or str(payload.get("week", "")) != str(week)
        or Path(str(payload.get("source_release", ""))).name != source.name
    ):
        return {}, "First TD result sidecar does not match this published release."
    games = payload.get("games", [])
    if not isinstance(games, list):
        return {}, "First TD result sidecar has an invalid games list."
    return {str(game["game_id"]): game for game in games if isinstance(game, dict) and game.get("game_id")}, None


def _published_board_ranking_display(raw: pd.DataFrame, results: dict[str, dict]):
    """Attach readable matchup labels to the published-board ranking table."""
    table, summary = published_board_rankings(raw, results)
    labels = {
        str(group.game_id.iloc[0]): label
        for label, _, group in _matchup_groups(raw)
        if not group.empty and "game_id" in group
    }
    if not table.empty:
        table["Game"] = table["Game"].map(labels).fillna(table["Game"])
    return table, summary


def _render_published_board_rankings(raw: pd.DataFrame, source: Path, season: int, week: int) -> None:
    """Show Top-1/Top-3 outcomes independently of quotes and no-vig pools."""
    st.markdown("#### Published board rankings")
    st.caption(
        "Frozen model probabilities rank every published player, whether or not a First TD price or full market is available. "
        "Outside-board scorers, defensive scores, and no-touchdown games count as misses; unresolved games remain pending."
    )
    results, issue = _first_td_game_results(source, season, week)
    if issue:
        st.warning(issue)
    try:
        table, summary = _published_board_ranking_display(raw, results)
    except Exception as exc:
        st.info(f"Published-board rankings are unavailable for this release: {exc}")
        return
    graded = summary["graded_games"]
    top1 = f"{summary['top1_hits']}/{graded}" if graded else "Pending"
    top3 = f"{summary['top3_hits']}/{graded}" if graded else "Pending"
    with st.container(horizontal=True):
        st.metric("Top 1 hits", top1, border=True)
        st.metric("Top 3 hits", top3, border=True)
        st.metric("Resolved games", str(graded), border=True)
        st.metric("Pending games", str(summary["pending_games"]), border=True)
    st.caption("Top-1 and Top-3 counts use resolved games only. These are published-board rankings, separate from paper betting record and ROI.")
    if not table.empty:
        table = table.rename(columns={"Game": "Matchup"})
        phone_cols = [c for c in ("Matchup", "Top 1", "Top 3", "First TD result") if c in table.columns]
        widths = {"Matchup": 84, "Top 1": 110, "Top 3": 110, "First TD result": 120}
        phone_cfg = {
            c: st.column_config.TextColumn(c, width=widths[c], pinned=(c == "Matchup"))
            for c in phone_cols
        }
        dataframe_phone_desktop(
            table, table[phone_cols], slug=f"atd-rankings-{season}-{week}",
            hide_index=True, phone_column_config=phone_cfg,
        )


def _first_td_v3_paper(scoped: pd.DataFrame, cap_state: tuple[bool, int | None]) -> dict:
    """Score frozen v3 picks with the shared tracker: fixed rule, 1U each."""
    available, price_cap = cap_state
    if available:
        def qualifies(frame):
            return tracker.qualifies_first_td_best_value_v3(
                frame["_model_probability"], frame["_book_price"], price_cap=price_cap,
            )
    else:
        # Without the params copy to read, the ledger itself still guarantees the
        # cap: the freeze only writes picks priced at or below it.
        def qualifies(frame):
            return tracker.qualifies_first_td_actual_ev(frame["_model_probability"], frame["_book_price"])
    return tracker.season_tracker(
        scoped,
        model_probability_col="p_first_v3",
        book_probability_col=None,
        book_price_col="first_amer",
        outcome_col="scored_first",
        qualifies=qualifies,
        eligibility_col="bet_eligible_first_best_value_v3",
    )


def _render_first_td_v3_scope(
    scoped: pd.DataFrame, decisions: list[dict], key: str, scope: str, cap_state: tuple[bool, int | None],
) -> None:
    zero_picks = sum(int(game.get("selected_bet_count", 0)) == 0 for game in decisions)
    if scoped.empty:
        st.caption(
            f"{_MARKET_LABELS['first']} paper tracker · {scope} · no picks yet. "
            f"{len(decisions)} game decision(s) are frozen, {zero_picks} with no qualifying player."
        )
        return
    _render_scorecard_metrics(
        _first_td_v3_paper(scoped, cap_state), "first", key,
        f"{scope} · frozen best-value picks · {len(decisions)} game decisions.",
    )
    st.caption(f"Frozen picks: {len(scoped)} · games with no qualifying player: {zero_picks}.")


def _render_first_td_best_value_v3(season: int, week: int, releases: dict[tuple[int, int], Path]) -> None:
    """Show the immutable best-value First TD paper ledger: one pick per game, tracked from Week 7."""
    st.markdown("#### Best-value picks · one per game")
    cap_state = tracker.first_td_v3_cap_state()
    st.caption(
        "One paper unit on each game's best value: the player with the highest expected return at the quoted "
        f"DraftKings price, only when that return is above zero{tracker.first_td_v3_cap_phrase()}. "
        "Picks are frozen before kickoff, a frozen game keeps its pick when a later paste re-prices it, "
        "and results are tracked from Week 7 on. "
        "The sample is small, so early results mostly reflect luck. This tracks a rule; it does not prove an edge."
    )
    try:
        bets, ledger = load_first_td_best_value_v3(releases=releases)
    except Exception:
        st.warning("The First TD best-value ledger could not be verified, so its picks and record are hidden.")
        return
    season_decisions = [
        game for game in ledger.get("games", [])
        if int(game.get("season", season)) == int(season) and int(game.get("week", week)) <= int(week)
    ]
    if not season_decisions:
        st.info("No First TD best-value picks are frozen yet. Picks lock before each game's kickoff.")
        return
    if bets.empty:
        season_bets = week_bets = bets
    else:
        in_season = pd.to_numeric(bets.season, errors="coerce").eq(int(season))
        weeks = pd.to_numeric(bets.week, errors="coerce")
        season_bets = bets[in_season & weeks.le(int(week))].copy()
        week_bets = bets[in_season & weeks.eq(int(week))].copy()
    week_decisions = [game for game in season_decisions if int(game.get("week", week)) == int(week)]
    if len(week_decisions) == len(season_decisions):
        # The week is a subset of the season, so equal counts mean the same frozen games
        # (the first tracked week): one card carries both scopes instead of repeating it.
        both = f"Season to date and Week {week}"
        if int(week) == first_td_v3.FIRST_V3_WEEK:
            both += " (first tracked week)"
        _render_first_td_v3_scope(
            season_bets, season_decisions, f"first-td-v3-season-{season}-{week}", both, cap_state,
        )
        return
    _render_first_td_v3_scope(
        season_bets, season_decisions, f"first-td-v3-season-{season}-{week}",
        f"Season to date, from Week {first_td_v3.FIRST_V3_WEEK}", cap_state,
    )
    _render_first_td_v3_scope(
        week_bets, week_decisions, f"first-td-v3-week-{season}-{week}", f"Week {week}", cap_state,
    )


def _published_live_paths(releases: dict[tuple[int, int], Path]) -> tuple[tuple[str, ...], tuple[int, ...]]:
    paths = tuple(
        str(releases[key])
        for key in sorted(releases)
        if key[0] == LIVE_SEASON
    )
    modified_at = tuple(Path(path).stat().st_mtime_ns for path in paths)
    manifest = _DIR / MANIFEST_NAME
    if manifest.is_file():
        modified_at += (manifest.stat().st_mtime_ns,)
    modified_at += tuple(entry["metadata_path"].stat().st_mtime_ns
                         for entry in canonical_td_releases(_DIR).values()
                         if "metadata_path" in entry)
    return paths, modified_at


def _pct(value) -> str:
    return "—" if value is None or pd.isna(value) else f"{100 * float(value):+.1f}%"


def _loss_css(key: str, units, roi) -> None:
    """Color negative Net units / ROI values red and shrink the ROI range value."""
    rules = []
    for idx, value in ((1, units), (2, roi)):
        if value is not None and not pd.isna(value) and float(value) < 0:
            rules.append(
                f'.st-key-jsa-metric-even-atd-{key} > [data-testid="stElementContainer"]:nth-child({idx})'
                ' [data-testid="stMetricValue"], '
                f'.st-key-jsa-metric-even-atd-{key} > [data-testid="stElementContainer"]:nth-child({idx})'
                ' [data-testid="stMetricValue"] *{color:#d64545 !important}'
            )
    rules.append(
        f'.st-key-jsa-metric-even-atd-{key} > [data-testid="stElementContainer"]:nth-child(4)'
        ' [data-testid="stMetricValue"], '
        f'.st-key-jsa-metric-even-atd-{key} > [data-testid="stElementContainer"]:nth-child(4)'
        ' [data-testid="stMetricValue"] *{font-size:1.1rem !important}'
    )
    st.markdown("<style>" + "".join(rules) + "</style>", unsafe_allow_html=True)


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
    """Count settled games with an identifiable scorer among the listed rows."""
    outcome_col = "_outcome" if "_outcome" in frame else "scored_first"
    if outcome_col not in frame:
        return {"graded": 0, "hits": 0}
    outcomes = pd.to_numeric(frame[outcome_col], errors="coerce")
    status_col = "settlement_status_first" if "settlement_status_first" in frame else None
    if status_col:
        settled = frame[status_col].astype("string").str.strip().str.lower().eq("settled")
        graded = settled
    else:
        graded = outcomes.isin([0, 1])
    if "game_id" in frame:
        game_ids = frame["game_id"].astype("string").str.strip()
        valid_game = game_ids.notna() & game_ids.ne("")
        graded_games = set(game_ids[graded & valid_game])
        hit_games = set(game_ids[graded & valid_game & outcomes.eq(1)])
        return {"graded": len(graded_games), "hits": len(hit_games)}
    return {
        "graded": int(graded.sum()),
        "hits": int((graded & outcomes.eq(1)).sum()),
    }


_MARKET_LABELS = {"anytime": "Anytime TD", "two_plus": "2+ TD", "first": "First TD"}
_MARKET_SHORT_LABELS = {"anytime": "", "two_plus": "2+ ", "first": "First "}


def _render_scorecards(priced, season, releases, *, market="anytime") -> None:
    """Render one season-to-date set and one selected-week set for 2026."""
    if season != LIVE_SEASON:
        _render_single_scorecards(priced, season, releases, market=market)
        return
    frame = priced.copy()
    for column, default in (("prediction_mode", "live"), ("model_version", "legacy")):
        if column not in frame:
            frame[column] = default
    modes = sorted(frame["prediction_mode"].dropna().astype(str).unique())
    mode = "live" if "live" in modes else modes[-1] if modes else "live"
    week_values = pd.to_numeric(frame.get("week", pd.Series(dtype=float)), errors="coerce").dropna()
    week = int(week_values.max()) if not week_values.empty else None
    paths, modified_at = _published_live_paths(releases)
    if not paths or week is None:
        _render_single_scorecards(frame, season, releases, market=market,
                                  prediction_mode=mode, model_version="all")
        return

    season_paper = _load_season_tracker(
        paths, modified_at, market, through_week=week,
    )
    week_paper = _tracker_for_market(frame, market)
    mode_label = {
        "live": "live-published rows",
        "retrospective": "retrospective reconstruction rows",
    }.get(mode, f"{mode} rows")
    model_versions = sorted(frame["model_version"].dropna().astype(str).unique())
    model_label = ", ".join(model_versions) if model_versions else "unspecified model version"
    # These cards always score the earlier First TD rule (Weeks 1 to 6); the v3
    # best-value rule has its own card.
    rule_text = tracker.rule_description("first_legacy" if market == "first" else market)
    st.markdown("#### Season to date")
    _render_scorecard_metrics(
        season_paper, market, "season-to-date",
        f"Through Week {week} · fixed rule: {rule_text}.",
    )
    season_rows = season_paper["rows"]
    retro_weeks = sorted(
        pd.to_numeric(
            season_rows.loc[season_rows.prediction_mode.eq("retrospective"), "week"],
            errors="coerce",
        ).dropna().astype(int).unique()
    )
    if retro_weeks:
        st.caption(
            "Season totals include retrospective Weeks "
            + ", ".join(str(value) for value in retro_weeks)
            + ", whose predictions were recomputed after the games."
        )
    if market == "first":
        _render_first_td_results_note(season_paper["rows"])
        if mode == "live":
            historical = _load_retrospective_first_td_tally(paths, modified_at, week)
            if historical["graded"]:
                st.caption(
                    "Earlier Weeks 1 to 3 retrospective outcomes only · a listed scorer was identifiable in "
                    f"{historical['hits']} of {historical['graded']} settled games. These releases had no "
                    "NGS First TD probabilities, so the tally is excluded from paper betting and model accuracy."
                )
    st.markdown(f"#### Week {week}")
    _render_scorecard_metrics(
        week_paper, market, f"week-{week}",
        f"Selected week · {mode_label} · model versions in this board: {model_label} · fixed rule: {rule_text}.",
    )
    if market == "first":
        _render_first_td_results_note(week_paper["rows"])

    summary = _market_summary(
        frame,
        model_probability_col="p_first" if market == "first" else "p_ge2" if market == "two_plus" else "p_ge1",
        book_probability_col="book_first_p_devigged" if market == "first" else None if market == "two_plus" else "p_book",
        book_price_col="first_amer" if market == "first" else "two_plus_amer" if market == "two_plus" else "book_amer",
        outcome_col="scored_first" if market == "first" else "scored_two_plus" if market == "two_plus" else "scored_anytime",
    )
    model_context = "—" if summary["mean_p"] is None else f"{100 * summary['mean_p']:.1f}%"
    book_context = "—" if summary["mean_book"] is None else f"{100 * summary['mean_book']:.1f}%"
    short = _MARKET_SHORT_LABELS[market]
    st.caption(
        f"Supporting context · Model {short}P {model_context} · Book {short}P {book_context} · "
        "Model and book probabilities are shown here for context; the table carries the odds."
    )


def _render_scorecard_metrics(paper: dict, market: str, key: str, scope: str) -> None:
    result = paper["summary"]
    ci = paper["ci"]
    st.caption(f"{_MARKET_LABELS[market]} paper tracker · {scope}")
    _loss_css(key, result["net_units"] if result["bets"] else None, result["roi"])
    with st.container(horizontal=True, key=f"jsa-metric-even-atd-{key}"):
        st.metric("Net units", f"{result['net_units']:+.1f}U" if result["bets"] else "—", border=True)
        st.metric("ROI", _pct(result["roi"]), border=True)
        st.metric(
            "Record", f"{result['wins']}-{result['losses']}" if result["bets"] else "No bets",
            delta=(f"{result['open_bets']} open · {result['void_bets']} void"
                   if result["bets"] else "No qualifying picks"),
            delta_color="off", delta_arrow="off", border=True,
        )
        st.metric("Plausible ROI range (95%)", _roi_range_value(ci), border=True)
    if ci["available"]:
        st.caption("Empirical uncertainty range, not a guarantee.")
    elif result["settled_bets"]:
        st.caption(
            "Plausible ROI range (95%) is pending until at least 5 settled games "
            "and 20 settled paper bets are available."
        )
    elif result["bets"]:
        st.caption("Qualifying picks are still open or void, so settled ROI is not available yet.")
    else:
        st.caption("No qualifying model-backed bets in this scope; the cards show no settled betting record.")
    if market == "two_plus":
        tally = _two_plus_results_tally(paper["rows"])
        if tally["graded"]:
            st.caption(
                "Results-only 2+ TD tally · "
                f"{tally['hits']} hits / {tally['graded']} graded player-games. This is not a betting record."
            )


def _render_first_td_results_note(frame: pd.DataFrame) -> None:
    tally = _first_td_results_tally(frame)
    if tally["graded"]:
        st.caption(
            "First TD outcomes only · "
            f"a scorer is identifiable among the listed players in {tally['hits']} of "
            f"{tally['graded']} settled games. This is outcome coverage, not model accuracy or ROI."
        )
    else:
        st.caption(
            "No settled First TD outcome coverage in this scope. Retrospective releases with an "
            "incomplete scorer pool do not have model-backed First TD probabilities or picks."
        )


def _render_single_scorecards(
    priced: pd.DataFrame,
    season: int,
    releases: dict[tuple[int, int], Path],
    *,
    market: str = "anytime",
    prediction_mode: str = "live",
    model_version: str = "legacy",
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
    # These cards always score the earlier First TD rule (Weeks 1 to 6); the v3
    # best-value rule has its own card.
    rule_text = tracker.rule_description("first_legacy" if market == "first" else market)
    if season == LIVE_SEASON:
        paths, modified_at = _published_live_paths(releases)
        if paths:
            paper = _load_season_tracker(paths, modified_at, market, prediction_mode, model_version)
            result = paper["summary"]
            ci = paper["ci"]
            st.caption(
                f"{market_label} paper tracker · {'retrospective reconstruction' if prediction_mode == 'retrospective' else 'live published'} · "
                f"model {model_version} · "
                f"candidate rule: {rule_text} · 1U per candidate."
            )
            _loss_css(f"{prediction_mode}-{model_version}", result["net_units"], result["roi"])
            with st.container(horizontal=True, key=f"jsa-metric-even-atd-{prediction_mode}-{model_version}"):
                st.metric("Net units", f"{result['net_units']:+.1f}U", border=True)
                st.metric("ROI", _pct(result["roi"]), border=True)
                st.metric(
                    "Record",
                    f"{result['wins']}-{result['losses']}",
                    delta=f"{result['open_bets']} open · {result['void_bets']} void",
                    delta_color="off",
                    delta_arrow="off",
                    border=True,
                )
                st.metric("Plausible ROI range (95%)", _roi_range_value(ci), border=True)
            if ci["available"]:
                st.caption("Empirical uncertainty range, not a guarantee.")
            else:
                st.caption(
                    "Plausible ROI range (95%) is pending until at least 5 settled games "
                    "and 20 settled paper bets are available."
                )
            calib = paper.get("calibration")
            if calib and calib["available"]:
                st.caption(
                    f"Selected-bet calibration (n={calib['n']} settled) · model averaged "
                    f"{100 * calib['mean_model_probability']:.1f}% on these specific picks, "
                    f"book averaged {100 * calib['mean_book_probability']:.1f}%, actual hit "
                    f"rate was {100 * calib['hit_rate']:.1f}%. This is the paper record's own "
                    "selection, not the model's overall accuracy -- see Supporting context below "
                    "for that."
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
                st.caption("No quoted 2+ TD candidates meet the rule yet.")
            if is_first and result["bets"] == 0:
                st.caption("No quoted First TD candidates meet the rule yet.")
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
def _load_csv(path: str, modified_at: int | tuple[int, int] | None = None) -> pd.DataFrame:
    return read_td_release(path)


@st.cache_data(ttl=3600)
def _load_meta(path: str, modified_at: int | None = None) -> dict:
    raw = Path(path)
    if not raw.is_file():
        return {}
    try:
        value = json.loads(raw.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _live_metadata(season: int = LIVE_SEASON, week: int = 1) -> dict:
    entry = canonical_td_releases(_DIR).get((season, week), {})
    if "metadata_path" in entry:
        path = entry["metadata_path"]
        return _load_meta(str(path), path.stat().st_mtime_ns)
    files = sorted(_DIR.glob(f"anytime_td_{season}_week{week:02d}_*.json"))
    if not files:
        return {}
    metadata = [(path, _load_meta(str(path))) for path in files]
    timestamped = [(path, meta) for path, meta in metadata if meta.get("publish_now_et")]
    # Slate names sort alphabetically, not by publication time (e.g. Monday
    # sorts before Sunday), so use the publisher's capture timestamp.
    if timestamped:
        return max(timestamped, key=lambda item: str(item[1]["publish_now_et"]))[1]
    return metadata[-1][1]


def _n_final(count: int) -> str:
    return f"{count} final game" + ("" if count == 1 else "s")


def _grading_stamp_caption(season: int, week: int) -> str:
    """One line saying when Anytime, 2+ TD and First TD results were last refreshed.

    The three markets are graded in a single pass, so they share one stamp
    (written by publishing.grader.write_td_grading_stamps). Empty when no
    grading has run for the week yet.
    """
    path = _DIR / f"grading_{season}_week{week:02d}.json"
    try:
        stamp = json.loads(path.read_text(encoding="utf-8"))
        moment = pd.Timestamp(stamp["graded_at"]).tz_convert("America/New_York")
    except (OSError, ValueError, KeyError, TypeError):
        return ""
    text = (
        f"Results last updated {moment.strftime('%a %b')} {moment.day}, "
        f"{moment.strftime('%I:%M %p').lstrip('0')} ET. Anytime TD, 2+ TD and First TD "
        f"are graded together. {_n_final(int(stamp.get('final_games', 0)))} in this week."
    )
    waiting = int(stamp.get("awaiting_stat_rows", 0) or 0)
    if waiting:
        noun = "player" if waiting == 1 else "players"
        text += (
            f" {waiting} quoted {noun} on final games "
            "not yet in the stat feed, left blank until they appear."
        )
    return text


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
    hit = _hit_labels(ranked, "scored_anytime", "settlement_status_anytime")
    model_american = ranked["fair_amer"] if "fair_amer" in ranked else pd.Series(pd.NA, index=ranked.index)
    book_american = ranked["book_amer"] if "book_amer" in ranked else pd.Series(pd.NA, index=ranked.index)
    return pd.DataFrame({
        "#": range(1, len(ranked) + 1),
        "Player": ranked.player_display_name + " · " + ranked.team.map(public_team_abbr),
        "Pos": ranked.position,
        "Opp": ranked.opponent_team.map(public_team_abbr),
        "Model ATTD Odds": [
            _model_odds_probability(american, probability)
            for american, probability in zip(model_american, ranked.p_ge1)
        ],
        "Book ATTD Odds": [
            _odds_probability(american, probability)
            for american, probability in zip(book_american, ranked.p_book)
        ],
        "ATTD Value Gap": [
            _with_tag(
                _value_gap(model, book, model_p, book_p) or (
                    "Pending" if pd.isna(model_p) else ""
                ),
                tag,
            )
            for model, book, model_p, book_p, tag in zip(
                model_american, book_american, ranked.p_ge1, ranked.p_book,
                _eligibility_tags(ranked),
            )
        ],
        "Hit": hit,
        "_p": ranked.p_ge1.astype(float),
        "_value": ranked["_value"].astype(float),
        "_candidate": tracker.qualifies_probability_gap(
            ranked["_value"], tracker.ATTD_VALUE_THRESHOLD
        ) & _bet_eligibility(ranked).to_numpy(),
    })


def _two_plus_display(df: pd.DataFrame, *, include_unpriced: bool = False) -> pd.DataFrame:
    ranked = df.copy()
    ranked["p_ge2"] = pd.to_numeric(ranked.get("p_ge2"), errors="coerce")
    if "two_plus_amer" in ranked:
        ranked["_book_2plus"] = pd.to_numeric(ranked["two_plus_amer"], errors="coerce")
        # A live sportsbook quote is only meaningful for players the book
        # actually offered in this market. If the release has no 2+ market at
        # all, retain the model-only placeholder behavior for older releases.
        if ranked["_book_2plus"].notna().any() and not include_unpriced:
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
    hit = _hit_labels(ranked, "scored_two_plus", "settlement_status_two_plus")
    return pd.DataFrame({
        "#": range(1, len(ranked) + 1),
        "Player": ranked.player_display_name + " · " + ranked.team.map(public_team_abbr),
        "Pos": ranked.position,
        "Opp": ranked.opponent_team.map(public_team_abbr),
        "Model 2+ TD Odds": [
            value or ("Pending" if pd.isna(probability) else "Not implemented yet")
            for value, probability in zip(model_odds, ranked.p_ge2)
        ],
        "Book 2+ TD Odds": [value or "Not implemented yet" for value in book_odds],
        "2+ TD Value Gap": [
            _with_tag(
                value or (
                    "Pending"
                    if pd.isna(model_p) and pd.notna(book_p)
                    else "Not implemented yet"
                ),
                tag,
            )
            for value, model_p, book_p, tag in zip(
                value_gap, ranked.p_ge2, book_probability, _eligibility_tags(ranked)
            )
        ],
        "Hit": hit,
        "_value": ranked["_value"].astype(float),
        "_candidate": tracker.qualifies_two_plus_ratio(
            ranked["p_ge2"], book_probability
        ) & _bet_eligibility(ranked).to_numpy(),
    })


def _decimal_or_nan(american) -> float:
    if pd.isna(american) or float(american) == 0:
        return float("nan")
    return float(tracker.american_to_decimal(american))


def _signed_pct(value) -> str:
    """Expected return as a whole percent: +12%, -35%, 0%."""
    if value is None or pd.isna(value):
        return ""
    rounded = int(round(100 * float(value)))
    return f"{rounded:+d}%" if rounded else "0%"


def _first_td_tags(ranked: pd.DataFrame, uses_v3: bool) -> list[str]:
    """Eligibility tags, plus " · over cap" on v3 quotes the price cap rules out.

    A positive expected return that is not highlighted needs a reason on the row.
    """
    tags = _eligibility_tags(ranked)
    if uses_v3 and "first_td_v3_over_cap" in ranked:
        over = ranked["first_td_v3_over_cap"].fillna(False).astype(bool).to_numpy()
        tags = [" · over cap" if flag and not tag else tag for flag, tag in zip(over, tags)]
    return tags


def _first_td_display(df: pd.DataFrame, *, include_unpriced: bool = False) -> pd.DataFrame:
    """First TD is a competing-risk allocation, not a per-player marginal price.

    The model chance splits one fixed pool per game (roughly 94%, the
    historical rate an offensive skill player scores first, with the rest going
    to defense, special teams or no score). Boards from 2026 Week 7 carry
    ``p_first_v3`` (and the game-level ``first_td_v3_pick``); earlier boards
    only have the flat ``p_first``.

    Expected return is the model chance times DraftKings' actual payout, minus
    one. Rows sort by it, then by model chance, then by player_id: never by
    name, and rows with no price or no model chance come last.
    """
    ranked = df.copy()
    uses_v3 = "p_first_v3" in ranked
    ranked["p_first"] = _numeric_column(ranked, "p_first")
    ranked["_q"] = _numeric_column(ranked, "p_first_v3") if uses_v3 else ranked["p_first"]
    ranked["_book_first"] = _numeric_column(ranked, "book_first_p_devigged")
    ranked["_first_amer"] = _numeric_column(ranked, "first_amer")
    if ranked["_first_amer"].notna().any() and not include_unpriced:
        ranked = ranked[ranked["_first_amer"].notna()].copy()
    decimal = ranked["_first_amer"].map(_decimal_or_nan)
    ranked["_ev"] = ranked["_q"] * decimal - 1.0
    ranked["_book_raw"] = 1.0 / decimal
    # The old no-vig gap still drives the Weeks 1 to 6 highlight.
    ranked["_value"] = ranked["p_first"] - ranked["_book_first"]
    ranked["_pid"] = ranked["player_id"].astype(str) if "player_id" in ranked else ""
    ranked = ranked.sort_values(
        ["_ev", "_q", "_pid"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    hit = _hit_labels(ranked, "scored_first", "settlement_status_first")
    model_american = ranked["_q"].map(_fair_amer_from_probability)
    model_odds = []
    for american, probability, flat in zip(model_american, ranked["_q"], ranked["p_first"]):
        if pd.isna(probability) and uses_v3 and pd.notna(flat):
            model_odds.append("")  # only the v3 chance is unavailable: leave it blank
        else:
            model_odds.append(_model_odds_probability(american, probability))
    book_phone, book_desktop = [], []
    for american, implied, no_vig in zip(ranked["_first_amer"], ranked["_book_raw"], ranked["_book_first"]):
        base = f"{_amer_display(american)} · {100 * implied:.1f}% implied" if pd.notna(american) else ""
        book_phone.append(base)
        book_desktop.append(f"{base} · no-vig {100 * no_vig:.1f}%" if base and pd.notna(no_vig) else base)
    expected_return = []
    for ev, probability, flat, priced in zip(
        ranked["_ev"], ranked["_q"], ranked["p_first"], ranked["_first_amer"].notna(),
    ):
        if pd.notna(ev):
            expected_return.append(_signed_pct(ev))
        elif priced and pd.isna(probability) and not (uses_v3 and pd.notna(flat)):
            expected_return.append("Pending")
        else:
            expected_return.append("")
    if uses_v3:
        picks = (
            ranked["first_td_v3_pick"].fillna(False).astype(bool)
            if "first_td_v3_pick" in ranked else pd.Series(False, index=ranked.index)
        )
        candidate = picks & _bet_eligibility(ranked).to_numpy()
    else:
        candidate = tracker.qualifies_first_td_ev(
            ranked["p_first"], ranked["_first_amer"], ranked["_value"]
        ) & _bet_eligibility(ranked).to_numpy()
    return pd.DataFrame({
        "#": range(1, len(ranked) + 1),
        "Player": ranked.player_display_name + " · " + ranked.team.map(public_team_abbr),
        "Pos": ranked.position,
        "Opp": ranked.opponent_team.map(public_team_abbr),
        "Model First TD Odds": model_odds,
        "Book First TD Odds": [value or "Not implemented yet" for value in book_desktop],
        "Expected Return": [
            _with_tag(value, tag)
            for value, tag in zip(expected_return, _first_td_tags(ranked, uses_v3))
        ],
        "Hit": hit,
        "_p": ranked["_q"].astype(float),
        "_value": ranked["_value"].astype(float),
        "_ev": ranked["_ev"].astype(float),
        "_book_phone": [value or "Not implemented yet" for value in book_phone],
        "_candidate": candidate,
    })


def _hit_labels(df: pd.DataFrame, outcome_col: str, settlement_col: str) -> pd.Series:
    """Show settled outcomes and distinguish no-action/pending rows."""
    outcomes = _numeric_column(df, outcome_col)
    settlements = (
        df[settlement_col].astype("string").str.strip().str.lower()
        if settlement_col in df else pd.Series("", index=df.index, dtype="string")
    )
    if "status" in df:
        legacy_void = df["status"].astype("string").str.strip().str.lower().eq("void")
    else:
        legacy_void = pd.Series(False, index=df.index)
    labels = pd.Series("", index=df.index, dtype="string")
    labels.loc[outcomes.eq(1)] = "Yes"
    labels.loc[outcomes.eq(0)] = "No"
    labels.loc[settlements.eq("void") | legacy_void] = "Void"
    labels.loc[settlements.eq("awaiting_evidence")] = "Awaiting evidence"
    return labels


def _render_week_all_results(
    matchups: list[tuple[str, list[str], pd.DataFrame]], *,
    market_label: str, show_first_td: bool,
) -> None:
    st.caption(f"Every listed {market_label} outcome across completed matchups.")
    st.markdown(f"#### All {market_label} results across matchups")
    for label, teams, matchup in matchups:
        st.markdown(f"**{label}**")
        for team in teams:
            team_view = matchup[matchup.team.astype(str).eq(team)]
            if team_view.empty:
                continue
            st.markdown(f"{public_team_abbr(team)} {market_label}s")
            _board(
                team_view,
                f"atd-results-{market_label}-{team.lower()}-{label.replace(' ', '-')}",
                "",
                show_two_plus=market_label == "2+ TD", show_first_td=show_first_td,
                phone_show_opp=True, force_hit=True, include_unpriced=True,
            )


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
    """Same opaque candidate treatment as _style, targeting First TD column names.

    The Expected Return cell is green above zero, red below it and grey at zero,
    unless the row is a highlighted pick."""
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
        if "Expected Return" in df.columns:
            for i, value in enumerate(view["_ev"]):
                if pd.isna(value):
                    continue
                color = "#35D08A" if value > 0 else "#F08A8A" if value < 0 else "#B8C0CC"
                style = f"color: {color}; font-weight: 700"
                if view["_candidate"].iloc[i]:
                    style = missed_candidate_focus if _missed_candidate(i) else candidate_focus
                styles.iloc[i, df.columns.get_loc("Expected Return")] = style
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
    """Same opaque candidate treatment as First TD, including the missed-candidate row."""
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
                missed = _missed_candidate(i)
                focus = missed_candidate_focus if missed else candidate_focus
                styles.iloc[i, :] = missed_candidate_row_bg if missed else candidate_row_bg
                if "Player" in df.columns:
                    border = "#8F525A" if missed else "#35D08A"
                    styles.iloc[i, df.columns.get_loc("Player")] = (
                        f"{focus}; border-left: 3px solid {border}"
                    )
                if "2+ TD Value Gap" in df.columns:
                    styles.iloc[i, df.columns.get_loc("2+ TD Value Gap")] = focus
        if "2+ TD Value Gap" in df.columns:
            for i, value in enumerate(view["_value"]):
                if pd.isna(value) or view["_candidate"].iloc[i]:
                    continue
                color = "#35D08A" if value > 0 else "#F08A8A" if value < 0 else "#B8C0CC"
                styles.iloc[i, df.columns.get_loc("2+ TD Value Gap")] = (
                    f"color: {color}; font-weight: 700"
                )
        if "Hit" in df.columns:
            for i, mark in enumerate(view["Hit"]):
                if mark == "Yes":
                    style = "color: #35D08A; font-weight: 700"
                    if view["_candidate"].iloc[i]:
                        style = f"{style}; background-color: #1A4A3B"
                    styles.iloc[i, df.columns.get_loc("Hit")] = style
                elif mark == "No" and view["_candidate"].iloc[i]:
                    styles.iloc[i, df.columns.get_loc("Hit")] = missed_candidate_focus
        return styles

    return _apply


def _desktop_column_config() -> dict:
    return {
        "#": st.column_config.NumberColumn("#", format="%d", width=50, pinned=True,
                                           help="Row number in this list as currently sorted."),
        "Player": st.column_config.TextColumn("Player", width=185, help="Name and NFL team."),
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
            width=140,
            help="Book-minus-model American-odds gap and model-minus-book probability differential. Positive means more value in our model.",
        ),
        "Hit": st.column_config.TextColumn(
            "Hit", width=150, help="Did they score a rushing or receiving TD?",
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
            "Player", width=185, help="Name and NFL team.",
        ),
        "Model 2+ TD Odds": st.column_config.TextColumn(
            "Model 2+ TD Odds",
            help="Model American odds and percentage chance of two or more rushing or receiving TDs.",
        ),
        "Book 2+ TD Odds": st.column_config.TextColumn(
            "Book 2+ TD Odds",
            help="Sportsbook American odds and implied probability for two or more touchdowns.",
        ),
        "2+ TD Value Gap": st.column_config.TextColumn(
            "2+ TD Value Gap",
            width=140,
            help="Book-minus-model American-odds gap and model-minus-book probability differential.",
        ),
        "Hit": st.column_config.TextColumn(
            "Hit", width=150, help="Did they score two or more rushing or receiving TDs?",
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
        help="Sportsbook two-plus touchdown odds and implied probability.",
    )
    cfg["2+ TD Value Gap"] = st.column_config.TextColumn(
        "Value", width=PHONE_WIDTHS["ATTD Value Gap"],
        help="Two-plus book-minus-model odds gap and probability differential.",
    )
    cfg["Hit"] = st.column_config.TextColumn(
        "Hit", width=PHONE_WIDTHS["Hit"],
        help="Did they score two or more rushing or receiving TDs?",
    )
    return cfg


def _first_td_column_config() -> dict:
    return {
        "#": st.column_config.NumberColumn(
            "#", format="%d", width=50, pinned=True,
            help="Row number in this list as currently sorted.",
        ),
        "Player": st.column_config.TextColumn("Player", width=185, help="Name and NFL team."),
        "Opp": st.column_config.TextColumn("Opp", help="Opponent this week."),
        "Model First TD Odds": st.column_config.TextColumn(
            "Model First TD Odds",
            help="Our model's American odds and percentage chance that this player scores the game's first touchdown.",
        ),
        "Book First TD Odds": st.column_config.TextColumn(
            "Book First TD Odds",
            width=250,
            help=(
                "DraftKings' quoted First TD price and the chance it implies, which includes the book's built-in margin. "
                "A no-vig percentage is added only when the full within-game market was captured."
            ),
        ),
        "Expected Return": st.column_config.TextColumn(
            "Expected Return",
            width=170,
            help=(
                "The model's estimate of average profit per unit staked at the quoted DraftKings price: "
                "model chance times the payout, minus 1. First TD prices carry a large built-in margin, "
                "so most players show a negative number. A row tagged over cap has a positive estimate but a "
                "price longer than the cap, so it is not picked. It is an estimate, not a promise."
            ),
        ),
        "Hit": st.column_config.TextColumn(
            "Hit", width=150, help="Did they score the game's first touchdown?",
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
        "Book", width=PHONE_WIDTHS["Book First TD Odds"],
        help="DraftKings' quoted First TD price and the chance it implies, including the book's margin.",
    )
    cfg["Expected Return"] = st.column_config.TextColumn(
        "EV", width=PHONE_WIDTHS["Expected Return"],
        help="Expected return: the model's estimate of average profit per unit at the quoted price. Most First TD rows are negative.",
    )
    cfg["Hit"] = st.column_config.TextColumn(
        "Hit", width=PHONE_WIDTHS["Hit"],
        help="Did they score the game's first touchdown?",
    )
    return cfg


def _attach_first_td_v3(
    raw: pd.DataFrame, source: Path, meta: dict, season: int, week: int,
) -> tuple[pd.DataFrame, str | None]:
    """Attach v3 probabilities and picks; on any failure leave the v3 cells blank.

    A game already frozen keeps its frozen pick highlighted even when a later
    release re-scores it; only games not yet frozen show the live rule's pick.
    """
    try:
        try:
            frozen = frozen_pick_ids_v3(season, week)
        except Exception:
            frozen = None  # the card reports an unreadable ledger; the board falls back to the live rule
        return attach_first_td_v3(
            raw, source, metadata=meta if meta.get("first_td_candidate_mass") else None, frozen_picks=frozen,
        ), None
    except Exception:
        blank = raw.copy()
        blank["p_first_v3"] = float("nan")
        blank["first_td_v3_pick"] = False
        blank["first_td_v3_over_cap"] = False
        return blank, (
            "The sharpened First TD probabilities are unavailable for this release, so the Model and "
            "Expected Return cells and the picks are blank. DraftKings prices are still shown."
        )


def _frame_uses_v3(df: pd.DataFrame) -> bool:
    """True for boards that carry First TD v3 probabilities (2026 Week 7 on)."""
    return "p_first_v3" in df.columns


def _render_week_recommended(
    board_priced: pd.DataFrame, season: int, releases: dict, *, show_first_td: bool,
) -> None:
    """2+ TD and First TD candidates are rare enough that 'recommended only'
    pools every matchup in the week into one board instead of filtering
    one game at a time -- a per-matchup view would mostly show nothing."""
    market = "first" if show_first_td else "two_plus"
    market_label = "First TD" if show_first_td else "2+ TD"
    first_v3 = show_first_td and _frame_uses_v3(board_priced)
    rule_text = tracker.rule_description(
        "first" if first_v3 else "first_legacy" if show_first_td else market
    )
    retrospective = (
        "prediction_mode" in board_priced
        and board_priced["prediction_mode"].astype(str).eq("retrospective").all()
    )
    if show_first_td and retrospective:
        st.info(
            "Important: the NGS retrospective release has no First TD probabilities because its full scorer pool "
            "could not be verified. The listed scorer outcomes are coverage only, not a model backtest."
        )
    elif first_v3:
        st.info(
            "Expected return is the model's estimate of average profit per unit at the quoted DraftKings price. "
            "First TD prices carry a large built-in margin, so most players are negative. Each game's pick is "
            f"its highest expected return, if that is above zero{tracker.first_td_v3_cap_phrase()}. Picks are "
            "frozen before kickoff and results are tracked from Week 7 on. Published-board Top-1 and Top-3 "
            "results are shown above and are tracked separately."
        )
    elif show_first_td:
        st.info(
            "Published-board Top-1 and Top-3 results are shown above. The paper strategy record below follows "
            "the earlier value-gap rule and is tracked separately from ranking outcomes."
        )
    else:
        st.info(
            f"Important: {market_label} predictions have no historical backtest"
            + (" of any kind" if show_first_td else " yet")
            + f". This view is forward-looking tracking only, not evidence of "
            "accuracy or profitability."
        )
    if first_v3:
        st.caption(
            f"First TD picks across this week's matchups. Rule: {rule_text}. "
            "Sorted by expected return, highest first."
        )
    else:
        st.caption(
            f"Every {market_label} candidate across this week's matchups: {rule_text}. "
            f"Sorted by {'expected return' if show_first_td else 'value gap'}, highest first."
        )
    price_column = "first_amer" if show_first_td else "two_plus_amer"
    if price_column in board_priced:
        all_game_ids = set(board_priced.game_id.astype(str))
        has_price = pd.to_numeric(board_priced[price_column], errors="coerce").notna()
        game_has_price = has_price.groupby(board_priced.game_id.astype(str)).any()
        no_price_game_ids = set(game_has_price.index[~game_has_price])
        if no_price_game_ids and no_price_game_ids < all_game_ids:
            missing_labels = sorted(
                (
                    f"{public_team_abbr(str(game_id).split('_')[-2])} at "
                    f"{public_team_abbr(str(game_id).split('_')[-1])}"
                )
                if len(str(game_id).split("_")) >= 4
                else str(game_id)
                for game_id in no_price_game_ids
            )
            if missing_labels:
                st.caption(
                    f"No DraftKings {market_label} prices were supplied for: "
                    + ", ".join(missing_labels)
                    + ". Those markets remain blank."
                )
    if not first_v3:
        # From Week 7 the v3 card above replaces the earlier First TD cards.
        _render_scorecards(board_priced, season, releases, market=market)
    candidate_table = (
        _first_td_display(board_priced) if show_first_td
        else _two_plus_display(board_priced)
    )
    st.markdown(f"#### Recommended {market_label} players this week")
    if candidate_table["_candidate"].any():
        _board(
            board_priced, f"atd-week-recommended-{market}", "",
            show_two_plus=not show_first_td, show_first_td=show_first_td,
            recommended_only=True, phone_show_opp=True,
        )
        return

    st.info(f"No players clear the {market_label} candidate rule this week.")
    if show_first_td:
        model_ready = candidate_table["_p"].notna().any()
        book_ready = (
            "book_first_p_devigged" in board_priced
            and pd.to_numeric(board_priced["book_first_p_devigged"], errors="coerce").notna().any()
        )
        if first_v3 and model_ready:
            st.caption(
                "A game shows no pick when no player has a positive expected return"
                + (" at a price within the cap" if tracker.first_td_v3_cap_state() != (True, None) else "")
                + ". Open a matchup to see every priced player."
            )
        elif model_ready and not book_ready:
            st.caption(
                "Model First TD odds are available on priced players, but no-vig "
                "book probabilities are still pending where the captured First TD "
                "quote pool is incomplete. Open a matchup to see the full board."
            )
        elif not model_ready:
            st.caption(
                "Model First TD odds are pending for games whose contestant "
                "denominator could not be frozen. Open a matchup to see captured "
                "DraftKings prices."
            )


def _board(
    view: pd.DataFrame, slug: str, search: str, *,
    show_two_plus: bool = False, show_first_td: bool = False,
    recommended_only: bool = False, phone_show_opp: bool = False,
    force_hit: bool = False, include_unpriced: bool = False,
) -> int:
    if show_first_td:
        table = _first_td_display(view, include_unpriced=include_unpriced)
        graded = force_hit or _numeric_column(view, "scored_first").notna().any()
        desktop_cols = FIRST_TD_DESKTOP_COLS if graded else [c for c in FIRST_TD_DESKTOP_COLS if c != "Hit"]
        phone_cols = FIRST_TD_PHONE_COLS if graded else [c for c in FIRST_TD_PHONE_COLS if c != "Hit"]
        desktop_config = _first_td_column_config()
        phone_config = _first_td_phone_column_config()
    elif show_two_plus:
        table = _two_plus_display(view, include_unpriced=include_unpriced)
        graded = force_hit or _numeric_column(view, "scored_two_plus").notna().any()
        desktop_cols = TWO_PLUS_DESKTOP_COLS if graded else [c for c in TWO_PLUS_DESKTOP_COLS if c != "Hit"]
        phone_cols = TWO_PLUS_PHONE_COLS if graded else [c for c in TWO_PLUS_PHONE_COLS if c != "Hit"]
        desktop_config = _two_plus_column_config()
        phone_config = _two_plus_phone_column_config()
    else:
        table = _display(view)
        graded = force_hit or pd.to_numeric(view.scored_anytime, errors="coerce").notna().any()
        desktop_cols = DESKTOP_COLS if graded else [c for c in DESKTOP_COLS if c != "Hit"]
        phone_cols = PHONE_COLS if graded else [c for c in PHONE_COLS if c != "Hit"]
        desktop_config = _desktop_column_config()
        phone_config = _phone_column_config()
    if recommended_only:
        table = table[table["_candidate"]].reset_index(drop=True)
        # "#" is the row number in this list, so a one-row pick list starts at 1.
        table["#"] = range(1, len(table) + 1)
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
    if show_first_td and "_book_phone" in table:
        # Desktop may add a no-vig percentage to the book cell; the phone cell stays short.
        phone = phone.assign(**{"Book First TD Odds": table["_book_phone"]})
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
    first_rule = tracker.rule_description("first")
    with st.expander("How to read this board"):
        st.markdown(f"""
Chance a skill player scores a rushing or receiving touchdown. Passing TDs are
out. This is not even money: a typical quote is around one in five, so misses
will outnumber hits. The 2025 demo uses the earlier model. Over full 2025 the sportsbooks were still about 0.08% more
accurate. On these eight demo weeks our numbers were closer in 5; that is not a
betting record. For fun, not a proven edge. Bet responsibly.

**Desktop columns.** #, Player (name and team), Pos, Opp, Model ATTD Odds,
Book ATTD Odds, ATTD Value Gap, Hit. The odds columns combine American odds
with the implied percentage chance. Value Gap combines the book-minus-model
American-odds gap with the model-minus-book percentage differential, such as
`+1.1%`. On live 2026 boards, highlighted Anytime rows meet the raw
`>= +1.0pp` paper-bet rule and represent 1U candidates.

**Phone columns.** #, Player, Model, Book, Value, Hit. The full column meanings
are available in each column's help text. The list is sorted by ATTD Value Gap,
highest first.

Use the **Market** control to switch between Anytime TD, 2+ TD, and First TD.
Only one market renders at a time. Completed 2026 weeks default to **All
results** across matchups; **Recommended** and individual matchup views remain
available. The Hit column distinguishes Yes, No, Void, and Awaiting evidence.

**2+ TD.** When the pasted release includes that market, the view shows model
odds, current sportsbook odds, and the value gap for players with a listed 2+
price. Older releases without that market show a clear not-implemented
placeholder before games begin. Completed matchups without a published 2+
market do not receive retroactive model odds; once grading supplies final
outcomes, they contribute only to a results-only tally and never to a betting
W-L, units, ROI, or backtest result. The 2+ TD probabilities have no
historical backtest or published 2+ test results yet, so that view is
forward-looking tracking only—not evidence of model accuracy or
profitability. A verified replacement can appear with Book odds while its
Model and Value cells say Pending when the current-week model input is not
available; it is excluded from value-bet tracking until then. Since
2026-09-19, a 2+ TD candidate needs the model probability at least 1.25x
DraftKings' price, with that price at least 2%. A flat percentage-point gap
rewarded long shots: the same gap is a far bigger relative edge on a 1% price
than a 15% one, so it mostly flagged players where a small model error reads
as a huge edge.

**First TD.** This is a different kind of probability than Anytime or 2+:
exactly one player can score a game's first touchdown, so it is a share of one
fixed pool across both rosters, not a per-player chance. Our model splits each
game's pool by each player's Anytime TD rate, scaled by the historical rate an
offensive skill player scores first at all (roughly 94% of games; the rest go to
defense, special teams, or no score). From Week 7 the split uses a setting fit on
past seasons and frozen before the games. DraftKings' First TD prices carry a
large built-in margin: the raw implied chances in a game add up to well over
100%, so the average bet loses money before any edge. **Expected Return** is the
model's estimate of average profit per unit at the quoted price (model chance
times the payout, minus 1), so most rows are negative. Rows sort by it, highest
first.

**Best-value picks (from Week 7).** For each game the tracker picks one player:
{first_rule}. Each pick is 1U, frozen before kickoff and
tracked from Week 7 on. The sample is small, so early results mostly reflect
luck; this tracks a rule and is not a proven edge. Weeks 1 to 6 were tracked
under an earlier rule (a +3.0pp gap against the de-vigged price AND a positive
expected return) and keep that record. Weeks 1 to 3 of the 2026 NGS
retrospective release have no First TD probabilities because the complete
scorer pool could not be verified; their partly mapped scorer outcomes are
shown as coverage only, not NGS accuracy or a betting record.

The cards show one four-metric set for season to date through the selected
week and another for that week alone. Each set tracks 1U candidates: settled/open
paper bets, net units, settled ROI, and an uncertainty range. Season totals
use each week's latest published predictions, including retrospective
reconstructions identified in the season caption. Open bets stay out
of the P&L. After five settled games and 20 settled bets, the board also shows an
approximate 95% ROI range from a deterministic game-block bootstrap. It is an
empirical uncertainty range, not a guarantee. Anytime uses a +1.0pp value-gap
rule, 2+ TD needs the model at least 1.25x the price with the price at least
2%, and First TD uses the best-value rule above from Week 7 (Weeks 1 to 6 used
the earlier gap rule). Each shows its own cards when prices and graded outcomes
are available.
Live weeks are organized by matchup, then by team (for example, NE vs SEA with
separate NE and SEA boards).
        """)


def render() -> None:
    st.title("Touchdown Props")
    st.badge("Beta", icon=":material/science:", color="orange")
    st.caption(
        "Anytime, 2+, and First TD scorer odds compared with sportsbook prices. Passing TDs are "
        "out of every market. Live 2026 releases plus a 2025 demo. For fun. Bet responsibly."
    )
    releases = available_releases()
    if not releases:
        st.error("Anytime TD demo files are missing.")
        st.stop()
    live_keys = sorted((key for key in releases if key[0] == LIVE_SEASON), reverse=True)
    live_default = default_release(live_keys) if live_keys else None
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
        default_week = (
            live_default[1]
            if season == LIVE_SEASON and live_default is not None
            else (DEFAULT_WEEK if DEFAULT_WEEK in weeks else weeks[0])
        )
        if not seeded_week and "atd_week" not in st.session_state:
            week_kwargs["index"] = weeks.index(default_week)
        week = int(controls[1].selectbox("Week", weeks, **week_kwargs))
        page_common.sync_query_value("atd_week", week)
        search = controls[2].text_input("Search player", placeholder="Search player, e.g. Barkley", key="atd_search")
        st.markdown(
            "<style>.st-key-atd_search input::placeholder{opacity:.45 !important}</style>",
            unsafe_allow_html=True,
        )
    available = releases | {(DEMO_SEASON, w): p for w, p in demo.items()}
    meta = {}
    retrospective = False
    notes: list[str] = []
    if season == LIVE_SEASON:
        notes.append(
            "Live 2026 prices are manually copied from US sportsbook pages when available. "
            "The source is shown for each matchup. No odds API is used."
        )
        meta = _live_metadata(season, week)
        retrospective = meta.get("prediction_mode") == "retrospective"
        if meta:
            if retrospective:
                notes.append("Retrospective reconstruction; historical input availability unverified. "
                             "These probabilities were recomputed after the games, and were not published picks before kickoff.")
            book_value = meta.get("book", [])
            books = ", ".join(book_value) if isinstance(book_value, list) else str(book_value)
            notes.append(f"Latest paste: {books or 'manual paste'} · Captured: {meta.get('capture_max', 'unknown')}")
        graded_line = _grading_stamp_caption(season, week)
        if graded_line:
            notes.append(graded_line)
    _reading_guide()
    status_slot = st.container()

    if (season, week) not in available:
        if season == LIVE_SEASON:
            st.info(f"2026 Week {week} is selected and awaiting a manual odds release. "
                    "The 2025 demo remains available from the Year and Week selectors.")
        else:
            st.info(f"{season} Week {week} does not have a published board yet.")
        return

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
    notes_slot = st.container()

    source = available[(season, week)]
    manifest = _DIR / MANIFEST_NAME
    csv_cache_key = (source.stat().st_mtime_ns, manifest.stat().st_mtime_ns if manifest.is_file() else 0)
    raw = _load_csv(str(source), csv_cache_key)
    v3_issue = None
    if first_td_v3.uses_first_td_v3(season, week) and not retrospective:
        raw, v3_issue = _attach_first_td_v3(raw, source, meta, season, week)
    missing_markets = _missing_scheduled_markets(raw, season, week)
    if missing_markets:
        st.warning("No published touchdown prices for: " + ", ".join(missing_markets) + ".")
    unresolved_count = int(meta.get("unresolved_player_count") or 0)
    if unresolved_count:
        notes.append(
            f"{unresolved_count} pasted player name(s) could not be mapped to the player universe and were left out of the modeled board."
        )
    if meta.get("capture_window_warning"):
        notes.append("Pasted prices were captured across a wide time window and may reflect different market moments.")
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
    notes.append(f"{len(board_priced)} priced · all positions")
    if (~_bet_eligibility(board_priced)).any():
        notes.append(
            "\"no history\" rows have no prior NFL form for the model to read, so their "
            "gap is a guess and they are never highlighted."
        )
    if retrospective and model_pending:
        notes.append(
            f"{model_pending} quoted rows have no reproducible retrospective probability; "
            "they are excluded from performance scorecards."
        )
    elif pending_caption := _pending_replacement_caption(model_pending):
        notes.append(pending_caption)
    with notes_slot:
        with st.expander("Data notes", expanded=False, icon=":material/info:"):
            for note in notes:
                st.caption(note)
    completed_week = _week_is_complete(raw, season, week)
    with status_slot, st.container(horizontal=True, vertical_alignment="center"):
        is_live = season == LIVE_SEASON
        if retrospective:
            badge = "Retrospective"
        elif completed_week:
            badge = "Postgame"
        else:
            badge = "Live" if is_live else "Demo"
        st.badge(
            badge,
            icon=(":material/science:" if retrospective else
                  ":material/check_circle:" if completed_week else
                  ":material/live_tv:" if is_live else ":material/science:"),
            color=("orange" if retrospective or not is_live else
                   "blue" if completed_week else "green"),
        )
        st.caption("Priced players only. Anytime and 2+ TD sort by Value Gap, First TD by Expected Return, highest first. " +
                   (f"Cumulative 2026 Week {week} release." if is_live else "2025 weeks 10-17 demo."))
    matchups = list(_matchup_groups(board_priced))
    if not matchups:
        st.info("No matchups match this search.")
        return
    matchup_key = f"atd_matchup_{season}_{week}"

    show_two_plus = view == "2+ TD"
    show_first_td = view == "First TD"
    pool_eligible = show_two_plus or show_first_td
    if show_first_td and season == LIVE_SEASON:
        complete_pools = (
            raw.get("first_quote_pool_complete", pd.Series(False, index=raw.index))
            .fillna(False).astype(str).str.lower().eq("true")
        )
        if not complete_pools.any():
            first_games = int(
                raw.loc[
                    pd.to_numeric(
                        raw.get("first_amer", pd.Series(index=raw.index, dtype="float64")),
                        errors="coerce",
                    ).notna(),
                    "game_id",
                ].nunique()
            )
            st.caption(f"First TD prices appear in {first_games} of {raw.game_id.nunique()} published matchups.")
    if show_first_td and v3_issue:
        st.warning(v3_issue)

    if show_first_td and season == LIVE_SEASON and not retrospective:
        _render_published_board_rankings(raw, source, season, week)
        if first_td_v3.uses_first_td_v3(season, week):
            _render_first_td_best_value_v3(season, week, releases)

    if pool_eligible:
        # 2+ TD and First TD: "Recommended" (every candidate across the week)
        # is the first and default dropdown entry. Any real matchup shows all
        # of its priced players with the candidates highlighted, like ATTD.
        # Own widget key so each visit to these markets lands on Recommended.
        recommended_only = False
        matchup_options = [RECOMMENDED_LABEL] + [item[0] for item in matchups]
        if is_live and completed_week:
            matchup_options = [ALL_RESULTS_LABEL] + matchup_options
        props_matchup_key = f"atd_props_matchup_{season}_{week}"
        props_manual_key = f"{props_matchup_key}__manual"
        default_props_matchup = (
            ALL_RESULTS_LABEL if is_live and completed_week else RECOMMENDED_LABEL
        )
        current_props_matchup = st.session_state.get(props_matchup_key)
        if current_props_matchup not in matchup_options:
            st.session_state[props_matchup_key] = default_props_matchup
            st.session_state[props_manual_key] = False
        elif not st.session_state.get(props_manual_key, False):
            st.session_state[props_matchup_key] = default_props_matchup
        selected_label = st.selectbox(
            "Matchup", matchup_options,
            key=props_matchup_key,
            on_change=_mark_matchup_manual,
            args=(props_manual_key,),
            help=(
                "All results shows every listed player across completed matchups. "
                "Recommended shows candidates across the week. Choose a game "
                "to inspect its full market board."
                if is_live and completed_week else
                "Recommended lists every player who clears the market's "
                "candidate rule across the week. Pick a game to see all of "
                "its priced players, with qualifying players highlighted."
            ),
        )
        if selected_label == ALL_RESULTS_LABEL:
            _render_week_all_results(
                matchups, market_label="First TD" if show_first_td else "2+ TD",
                show_first_td=show_first_td,
            )
            return
        if selected_label == RECOMMENDED_LABEL:
            _render_week_recommended(
                board_priced, season, releases, show_first_td=show_first_td,
            )
            return
    else:
        recommended_only = st.toggle(
            "Recommended only",
            value=False,
            key=f"atd_rec_{season}_{week}_{view}",
            help="Show only players clearing the value-gap threshold in the "
                 "selected matchup.",
        )
        _seed_matchup_default(matchups, matchup_key)
        selected_label = st.selectbox(
            "Matchup", [item[0] for item in matchups],
            key=matchup_key,
            on_change=_mark_matchup_manual,
            args=(f"{matchup_key}__manual",),
            help="Choose a game to view both teams' touchdown prop boards.",
        )
    label, teams, matchup = next(item for item in matchups if item[0] == selected_label)
    matchup_books = sorted(matchup["book"].dropna().astype(str).unique()) if "book" in matchup else []
    if matchup_books:
        st.caption(f"{label} book: {', '.join(matchup_books)}")

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
        retrospective = (
            "prediction_mode" in matchup
            and matchup["prediction_mode"].astype(str).eq("retrospective").all()
        )
        if retrospective:
            st.info(
                "Important: the NGS retrospective release has no First TD probabilities because its full scorer pool "
                "could not be verified. Listed scorer outcomes are coverage only, not a model backtest."
            )
        else:
            st.info(
                "Published-board Top-1 and Top-3 results are shown above. Paper strategy record and ROI are separate."
            )
        if completed_without_first_td_market:
            st.info(
                "This matchup has no captured First TD price. Published-board model ranks and verified outcomes "
                "remain visible above; it is excluded from paper betting."
            )
        elif first_td_prices_available and _frame_uses_v3(matchup):
            st.caption(
                "First TD view: the model's chance, DraftKings' quoted price and the expected return at that price. "
                "Expected return is the model's estimate, and First TD prices carry a large built-in margin, so most "
                "rows are negative. The highlighted row is the game's pick under the frozen rule; picks are frozen "
                "before kickoff and tracked from Week 7 on."
            )
        elif first_td_prices_available:
            st.caption(
                "First TD view: the model's chance, DraftKings' quoted price and the expected return at that price. "
                "A no-vig comparison is added when the full within-game market was captured. Highlighted rows follow "
                "the earlier value-gap rule used for Weeks 1 to 6."
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
        if not _frame_uses_v3(priced):
            # From Week 7 the v3 card above replaces the earlier First TD cards.
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
            st.caption(
                "2+ TD view: model probability, current sportsbook price, and "
                f"value gap. The rule powering the 1U paper tracker below is "
                f"{tracker.rule_description('two_plus')}. First-TD prices are "
                "retained in the release data and shown in the separate First TD view."
            )
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
            f"+{100 * tracker.ATTD_VALUE_THRESHOLD:.1f} percentage point. "
            "ATTD Value Gap (Anytime TD value gap) is how many percentage points higher "
            "our modeled chance is than the sportsbook's implied chance."
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
            st.markdown(f"**{public_team_abbr(team)} {view}s**")
            shown_total += _board(
                team_view,
                f"atd-{team.lower()}-{label.replace(' ', '-')}",
                search or "",
                show_two_plus=show_two_plus,
                show_first_td=show_first_td,
                recommended_only=recommended_only,
            )
        if recommended_only and shown_total == 0:
            st.caption("No players clear the candidate rule for this matchup and market.")
        if pool_eligible and shown_total:
            first_v3 = show_first_td and _frame_uses_v3(matchup)
            pool_market = "first" if first_v3 else "first_legacy" if show_first_td else "two_plus"
            rule_text = tracker.rule_description(pool_market)
            display = _first_td_display(matchup) if show_first_td else _two_plus_display(matchup)
            n_recommended = int(display["_candidate"].sum())
            if n_recommended and first_v3:
                st.caption(f"Highlighted rows are this matchup's pick under the frozen rule ({rule_text}).")
            elif n_recommended:
                st.caption(
                    f"Highlighted rows clear the rule ({rule_text}); "
                    f"{n_recommended} in this matchup."
                )
            else:
                st.caption(
                    f"No players clear the {view} candidate rule "
                    f"({rule_text}) in this matchup."
                )
