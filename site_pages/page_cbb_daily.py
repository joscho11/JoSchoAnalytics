"""College Basketball daily predictions (public, Beta).

Predictions lead the page. Every published card carries a score, margin, total,
winner and win probability for each game. The 8.5-point ATS shadow policy sits
below the games, labeled exploratory. It has plays only on days whose card
metadata says ``line_snapshot_status == "official"``.
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

import cbb_daily_data


ET = ZoneInfo("America/New_York")
BREAK_EVEN = 0.5238
THRESHOLD = 8.5
FINAL_STATES = frozenset({"win", "loss", "push", "no_play"})
SEARCH_KEY = "cbb_team_search"
# Averages over fewer finished games than this swing too much to read as a track record.
MIN_GAMES_TO_READ = 300
# The 2026 holdout: scored once by the frozen model (no retraining, no recalibration)
# before this season. Recorded in the producer's final_test manifest (evaluation
# c3c52ad9): 5,752 games, winner_accuracy 0.7190542420027817, margin_mae
# 9.332414654820811, total_mae 13.779392510067217.
HOLDOUT_2026 = {
    "games": 5752,
    "winner_accuracy": 0.7190542420027817,
    "margin_mae": 9.332414654820811,
    "total_mae": 13.779392510067217,
}
NO_SNAPSHOT_NOTICE = "No official sportsbook line snapshot for this date, so no ATS plays are shown."


def _wilson(wins: int, losses: int) -> tuple[float | None, float | None]:
    trials = int(wins) + int(losses)
    if trials <= 0:
        return None, None
    z = 1.959963984540054
    rate = wins / trials
    denominator = 1 + z * z / trials
    center = (rate + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / trials + z * z / (4 * trials * trials)) / denominator
    return center - half, center + half


def _date_options(manifest: dict) -> list[str]:
    dates = sorted(str(value) for value in manifest.get("dates", {}) if str(value))
    return dates


def _md(text: object) -> str:
    """Escape the markdown characters that could reshape a team name."""
    return re.sub(r"([\\`*_\[\]$~])", r"\\\1", str(text))


def _flag(value: object) -> bool:
    """A CSV boolean that may come back blank. Blank is False, never True."""
    if value is None or value is pd.NA:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _format_clock(value: object) -> str:
    """Tip-off as Eastern clock time, for example ``7:00 PM ET``."""
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return "Tip time unavailable"
    local = parsed.tz_convert(ET)
    return str(local.hour % 12 or 12) + local.strftime(":%M %p ET")


def _format_stamp(value: object) -> str:
    """A UTC timestamp as Eastern date and clock time, or a plain fallback."""
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return "time unavailable"
    local = parsed.tz_convert(ET)
    return local.strftime("%a %b ") + str(local.day) + ", " + str(local.hour % 12 or 12) + local.strftime(":%M %p ET")


def _format_day(day: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(day))
    except ValueError:
        return str(day)
    return parsed.strftime("%A, %B ") + str(parsed.day)


def _format_spread(value: float) -> str:
    """A quoted spread exactly as collected: -3.25, -3, +2.5, PK. Never rounded to one decimal."""
    if abs(value) < 1e-9:
        return "PK"
    return f"{value:+.3f}".rstrip("0").rstrip(".")


def _format_edge(value: float, threshold: float = THRESHOLD) -> str:
    """Model edge to two decimals, never rounded up onto the play threshold.

    An edge of 8.496 is not a play, so it must not display as +8.50.
    """
    shown = round(float(value), 2)
    if abs(value) < threshold <= abs(shown):
        shown = math.copysign(threshold - 0.01, value)
    if shown == 0:
        shown = 0.0
    return f"{shown:+.2f}"


def _format_probability(probability: float) -> str:
    pct = int(math.floor(float(probability) * 100 + 0.5))
    if pct >= 100:
        return ">99%"
    if pct <= 0:
        return "<1%"
    return f"{pct}%"


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _query() -> str:
    """The team search box, shared by the game cards and the ATS list."""
    return str(st.session_state.get(SEARCH_KEY) or "").strip().lower()


def _matches(frame: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query or frame.empty:
        return frame
    names = frame["home_team"].astype(str).str.lower() + "|" + frame["away_team"].astype(str).str.lower()
    return frame[names.str.contains(re.escape(query), regex=True)]


def _history(result_frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [frame for frame in result_frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    result["ats_result"] = result["ats_result"].astype(str)
    return result


def _prediction_frame(card: pd.DataFrame | None, results: pd.DataFrame | None) -> pd.DataFrame:
    """Finished games with the model's prediction beside the actual score.

    Works for any card, with or without sportsbook lines: a finished game counts
    here whether its ATS result is a win, a loss, a push or no play.
    """
    if card is None or card.empty or results is None or results.empty:
        return pd.DataFrame()
    final = results[results["ats_result"].astype(str).isin(FINAL_STATES)].copy()
    if final.empty:
        return pd.DataFrame()
    final["game_id"] = final["game_id"].astype(str)
    left = card[["game_id", "predicted_margin", "predicted_total"]].copy()
    left["game_id"] = left["game_id"].astype(str)
    merged = left.merge(
        final[["game_id", "game_date_et", "home_score", "away_score", "actual_home_margin", "ats_result"]],
        on="game_id", how="inner",
    )
    numeric = ["predicted_margin", "predicted_total", "home_score", "away_score", "actual_home_margin"]
    merged[numeric] = merged[numeric].apply(pd.to_numeric, errors="coerce")
    return merged.dropna(subset=numeric).reset_index(drop=True)


def _prediction_summary(frame: pd.DataFrame) -> dict:
    """Winner accuracy, margin error and total error over finished games."""
    games = int(len(frame))
    if games == 0:
        return {"games": 0}
    correct = int((np.sign(frame["predicted_margin"]) == np.sign(frame["actual_home_margin"])).sum())
    actual_total = frame["home_score"] + frame["away_score"]
    low, high = _wilson(correct, games - correct)
    return {
        "games": games,
        "correct": correct,
        "winner_rate": correct / games,
        "winner_low": low,
        "winner_high": high,
        "margin_mae": float((frame["predicted_margin"] - frame["actual_home_margin"]).abs().mean()),
        "total_mae": float((frame["predicted_total"] - actual_total).abs().mean()),
    }


def _load_history(manifest: dict, dates: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ATS results and finished-game predictions across every published day."""
    result_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []
    for day in dates:
        state = manifest.get("dates", {}).get(day, {})
        if not isinstance(state, dict) or not state.get("results"):
            continue
        try:
            results = cbb_daily_data.load_results(day)
        except Exception:
            continue
        if results is None or results.empty:
            continue
        result_frames.append(results)
        if state.get("status") == "no_games_scheduled":
            continue
        try:
            card, _, _ = cbb_daily_data.load_card(day)
        except Exception:
            continue
        joined = _prediction_frame(card, results)
        if not joined.empty:
            prediction_frames.append(joined)
    predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    return _history(result_frames), predictions


def _matchup(row: pd.Series) -> dict:
    """Who the model picks, by how much, and the winner's win probability."""
    home = str(row.get("home_team") or row.get("home_team_id"))
    away = str(row.get("away_team") or row.get("away_team_id"))
    margin = float(row["predicted_margin"])
    p_home = float(row["home_win_probability"])
    home_score = float(row["predicted_home_score"])
    away_score = float(row["predicted_away_score"])
    home_wins = margin > 0 or (margin == 0 and p_home >= 0.5)
    return {
        "home": home, "away": away, "home_wins": home_wins,
        "winner": home if home_wins else away,
        "loser": away if home_wins else home,
        "winner_score": home_score if home_wins else away_score,
        "loser_score": away_score if home_wins else home_score,
        "by": abs(margin),
        "probability": p_home if home_wins else 1.0 - p_home,
        "total": float(row["predicted_total"]),
        "neutral": _flag(row.get("neutral_site")),
    }


def _game_caption(row: pd.Series, game: dict) -> str:
    joiner = "vs" if game["neutral"] else "at"
    parts = [f"{_md(game['away'])} {joiner} {_md(game['home'])}", _format_clock(row.get("tipoff_utc"))]
    if game["neutral"]:
        parts.append("Neutral site")
    return " · ".join(parts)


def _final_line(game: dict, final: pd.Series, predicted_margin: float) -> str:
    home_score, away_score = float(final["home_score"]), float(final["away_score"])
    if home_score >= away_score:
        score = f"{_md(game['home'])} {home_score:g}, {_md(game['away'])} {away_score:g}"
    else:
        score = f"{_md(game['away'])} {away_score:g}, {_md(game['home'])} {home_score:g}"
    correct = np.sign(predicted_margin) == np.sign(float(final["actual_home_margin"]))
    verdict = ":green[Winner pick correct]" if correct else ":red[Winner pick missed]"
    return f"Final: {score} · {verdict}"


def _render_game_card(row: pd.Series, final_by_game: dict[str, pd.Series]) -> None:
    game = _matchup(row)
    with st.container(border=True):
        st.markdown(f"**{_md(game['winner'])} by {game['by']:.1f}** · {_format_probability(game['probability'])} win probability")
        st.markdown(
            f"Predicted score: {_md(game['winner'])} {game['winner_score']:.1f}, {_md(game['loser'])} {game['loser_score']:.1f}  \n"
            f"Predicted total: {game['total']:.1f}"
        )
        final = final_by_game.get(str(row.get("game_id")))
        if final is not None:
            st.markdown(_final_line(game, final, float(row["predicted_margin"])))
        st.caption(_game_caption(row, game))


def _sorted_for_display(card: pd.DataFrame) -> pd.DataFrame:
    shown = card.copy()
    shown["_tip"] = pd.to_datetime(shown["tipoff_utc"], utc=True, errors="coerce")
    return shown.sort_values(["_tip", "home_team"], kind="mergesort", na_position="last")


def _render_day(selected: str, card: pd.DataFrame, metadata: dict, state: dict, day_final: pd.DataFrame) -> None:
    st.subheader(f"Predictions for {_format_day(selected)}")
    status = str(metadata.get("status", state.get("status", "published"))).replace("_", " ").title()
    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge(status, icon=":material/verified:", color="green")
        st.caption(f"{_plural(len(card), 'game', 'games')} · predictions made {_format_stamp(metadata.get('prediction_at_utc'))}")
    summary = _prediction_summary(day_final)
    if summary["games"]:
        with st.container(horizontal=True, key="jsa-metric-even-cbb-summary"):
            st.metric("Games finished", f"{summary['games']} of {len(card)}", border=True)
            st.metric("Winner picks correct", f"{summary['correct']} of {summary['games']}", f"{summary['winner_rate']:.0%}", delta_color="gray", delta_arrow="off", border=True)

    st.text_input("Find a team", key=SEARCH_KEY, placeholder="Type a team name")
    shown = _matches(_sorted_for_display(card), _query())
    if shown.empty:
        st.info("No games match that search.")
        return
    final_by_game = {str(row["game_id"]): row for _, row in day_final.iterrows()} if not day_final.empty else {}
    rows = [row for _, row in shown.iterrows()]
    # Two across on a wide screen. Streamlit stacks the columns on a phone, in the same order.
    for start in range(0, len(rows), 2):
        for column, row in zip(st.columns(2), rows[start:start + 2]):
            with column:
                _render_game_card(row, final_by_game)


def _render_prediction_record(predictions: pd.DataFrame) -> None:
    st.subheader("Season prediction record")
    summary = _prediction_summary(predictions)
    games = summary["games"]
    if games == 0:
        st.caption("No finished games are graded yet. This record fills in the morning after games are played, using the cards published before tip-off.")
    else:
        with st.container(horizontal=True, key="jsa-metric-even-cbb-record"):
            st.metric("Finished games", f"{games:,}", border=True)
            st.metric("Winner correct", f"{summary['winner_rate']:.1%}", f"{summary['correct']} of {games}", delta_color="gray", delta_arrow="off", border=True)
            st.metric("Avg margin miss", f"{summary['margin_mae']:.2f} pts", border=True)
            st.metric("Avg total miss", f"{summary['total_mae']:.2f} pts", border=True)
        if games < MIN_GAMES_TO_READ:
            st.caption(f"Too early to read. Only {games:,} games have finished, and averages over so few games swing a lot from day to day.")
        else:
            st.caption(f"95% interval for winner correct: {summary['winner_low']:.1%} to {summary['winner_high']:.1%}.")
        st.caption("Margin miss is how far the predicted margin was from the actual margin. Total miss is the same for the combined score. Both are averages in points; smaller is better.")
    st.markdown(
        f"**2026 holdout** (scored once, {HOLDOUT_2026['games']:,} games): winner correct **{HOLDOUT_2026['winner_accuracy']:.1%}** · "
        f"avg margin miss **{HOLDOUT_2026['margin_mae']:.2f} pts** · avg total miss **{HOLDOUT_2026['total_mae']:.2f} pts**"
    )
    st.caption("The model was tested on the 2026 season exactly once, after it was frozen and before this season began, so that row is the best guide to how it should do.")


def _pick_name(row: pd.Series) -> str | None:
    pick = str(row.get("ats_pick"))
    if pick == "home":
        return str(row["home_team"])
    if pick == "away":
        return str(row["away_team"])
    return None


def _outcome(result_by_game: dict[str, str], game_id: str) -> str:
    graded = result_by_game.get(game_id, "")
    return graded.title() if graded in {"win", "loss", "push"} else "Pending"


def _shadow_lines(lined: pd.DataFrame, unlined: pd.DataFrame, threshold: float, result_by_game: dict[str, str]) -> list[str]:
    """One plain-text line per game. Text wraps on a phone and stays readable to a screen reader."""
    lines = []
    for _, row in lined.iterrows():
        pick = _pick_name(row)
        verdict = "No play" if pick is None else f"**Shadow pick: {_md(pick)}** ({_outcome(result_by_game, str(row.get('game_id'))).lower()})"
        lines.append(
            f"- {_md(row['away_team'])} at {_md(row['home_team'])} · {_md(row['home_team'])} {_format_spread(float(row['market_home_spread']))}"
            f" · model edge {_format_edge(float(row['model_edge']), threshold)} · {verdict}"
        )
    for _, row in unlined.iterrows():
        lines.append(f"- {_md(row['away_team'])} at {_md(row['home_team'])} · No line")
    return lines


def _render_ats_shadow(card: pd.DataFrame, metadata: dict, results: pd.DataFrame | None, ats_history: pd.DataFrame) -> None:
    status = str(metadata.get("line_snapshot_status") or "unavailable")
    threshold = float(metadata.get("threshold", THRESHOLD))
    st.subheader("Exploratory ATS shadow (8.5-point policy)")
    st.caption(
        "ATS means against the spread. The shadow policy names a team only when the model's predicted margin and the median sportsbook spread "
        f"differ by {threshold:g} points or more. The model never sees the spread. This is a research experiment, not betting advice, "
        "and it did not pass its own 2026 test."
    )
    if status != "official":
        if status == "rejected":
            st.info(f"{NO_SNAPSHOT_NOTICE} The snapshot we collected did not pass our checks.")
        else:
            st.info(NO_SNAPSHOT_NOTICE)
        return
    market = card["market_status"].astype(str)
    lined = card[market.eq("available")].copy()
    unlined = card[~market.eq("available")].copy()
    lined["_edge"] = pd.to_numeric(lined["model_edge"], errors="coerce")
    lined["_abs_edge"] = lined["_edge"].abs()
    lined["_play"] = lined["ats_pick"].astype(str).isin({"home", "away"})
    lined = lined.sort_values(["_play", "_abs_edge"], ascending=[False, False], kind="mergesort")
    plays = lined[lined["_play"]]
    result_by_game = {}
    if results is not None and not results.empty:
        result_by_game = dict(zip(results["game_id"].astype(str), results["ats_result"].astype(str)))
    wins = losses = pushes = 0
    if not ats_history.empty:
        wins = int((ats_history["ats_result"] == "win").sum())
        losses = int((ats_history["ats_result"] == "loss").sum())
        pushes = int((ats_history["ats_result"] == "push").sum())
    st.caption("Official line snapshot taken between 8:45 and 9:00 AM ET, before tip-off. Spreads come from CollegeBasketballData.com.")
    with st.container(horizontal=True, key="jsa-metric-even-cbb-shadow"):
        st.metric("Games with a line", f"{len(lined)} of {len(card)}", border=True)
        st.metric("Shadow picks", int(len(plays)), border=True)
        st.metric("Season shadow record", f"{wins}-{losses}-{pushes}" if not ats_history.empty else "No graded games", border=True)
    if plays.empty:
        st.caption(f"No game reached the {threshold:g}-point edge on this card, so there are no shadow picks.")
    for _, row in plays.iterrows():
        pick_home = str(row["ats_pick"]) == "home"
        spread = float(row["market_home_spread"]) * (1 if pick_home else -1)
        with st.container(border=True):
            st.markdown(f"**Shadow pick: {_md(_pick_name(row))} {_format_spread(spread)}**")
            st.caption(
                f"{_md(row['away_team'])} at {_md(row['home_team'])} · model edge {_format_edge(float(row['_edge']), threshold)}"
                f" · result: {_outcome(result_by_game, str(row.get('game_id'))).lower()}"
            )
    st.caption(
        "Model edge is the model's predicted margin minus the margin the spread implies, from the home team's side. A positive edge favors the home team "
        f"and a negative edge favors the away team. A game becomes a shadow pick only when its edge reaches {threshold:g} points in either direction."
    )
    query = _query()
    lined_shown, unlined_shown = _matches(lined, query), _matches(unlined, query)
    with st.expander(f"All games on this card ({len(lined)} with a line, {len(unlined)} without)"):
        lines = _shadow_lines(lined_shown, _sorted_for_display(unlined_shown) if not unlined_shown.empty else unlined_shown, threshold, result_by_game)
        if lines:
            st.markdown("\n".join(lines))
        else:
            st.caption("No games match that search.")


def _render_ats_record(graded_history: pd.DataFrame) -> None:
    if graded_history.empty:
        st.subheader("Season-to-date record")
        st.caption("Results will appear here after finalized games are reconciled from genuine timestamped 2026-27 cards.")
        return
    st.subheader("Season-to-date ATS record")
    graded = graded_history[graded_history["ats_result"].isin({"win", "loss", "push"})].copy()
    wins = int((graded["ats_result"] == "win").sum())
    losses = int((graded["ats_result"] == "loss").sum())
    pushes = int((graded["ats_result"] == "push").sum())
    denominator = wins + losses
    rate = wins / denominator if denominator else None
    record = f"{_plural(wins, 'win', 'wins')} · {_plural(losses, 'loss', 'losses')} · {_plural(pushes, 'push', 'pushes')}"
    st.write(f"{record} · ATS rate {rate:.1%}" if rate is not None else "No graded wins/losses yet.")
    if denominator:
        lower, upper = _wilson(wins, losses)
        st.caption(f"Wilson 95% interval: {lower:.1%} to {upper:.1%} · 52.38% is an illustrative -110 break-even reference, not a profitability claim.")
        timeline = graded.assign(win=(graded["ats_result"] == "win").astype(int)).sort_values("game_date_et")
        timeline["ats_rate"] = timeline["win"].cumsum() / timeline["win"].where(timeline["ats_result"].ne("push")).notna().cumsum()
        if timeline["game_date_et"].nunique() >= 2:
            chart = timeline.set_index("game_date_et")[["ats_rate"]].rename(columns={"ats_rate": "ATS win rate"})
            chart["Illustrative -110 break-even"] = BREAK_EVEN
            st.line_chart(chart, y=["ATS win rate", "Illustrative -110 break-even"])
        else:
            st.caption("The running chart appears once graded plays from a second day are in.")
        st.caption("Practical implication: the interval and reference line show whether the current live sample is distinguishable from break-even. This does not establish tradability because sample size is small and historical lines were not point-in-time verified.")


def _render_benchmark_context() -> None:
    st.subheader("Historical benchmark context")
    st.caption("These historical results are descriptive/post-hoc because CBBD does not prove when each historical line became available; they are not live performance claims.")
    history_table = pd.DataFrame([
        {"Period": "2022–2025 OOF", "Record": "344–267–0", "Graded": 611, "ATS rate": 0.5630, "Wilson 95%": "52.34%–60.18%"},
        {"Period": "Season 2026", "Record": "87–64–0", "Graded": 151, "ATS rate": 0.5762, "Wilson 95%": "49.64%–65.21%"},
    ])
    st.dataframe(history_table, hide_index=True, use_container_width=True)
    st.caption("The 2026 descriptive interval includes 50%, so it did not clear the historical confidence gate; the frozen policy remains exploratory shadow-only.")


def render():
    st.title("College basketball daily predictions")
    st.badge("Beta", icon=":material/science:", color="blue")
    st.caption("Model predictions for men’s Division I games, posted each morning before tip-off. Data provided by CollegeBasketballData.com.")
    st.info("Each card shows who the model expects to win, by how many points, and how likely that win is. The model works from team and game data only. It never sees sportsbook lines.")

    try:
        manifest = cbb_daily_data.load_manifest()
    except Exception as exc:
        st.error(f"The CBB release manifest could not be verified: {exc}")
        return
    dates = _date_options(manifest)
    if not dates:
        st.warning("No official College Basketball daily card has been published yet.")
        st.caption("The page will populate after the 2026-27 season begins and a validated release is available.")
        return
    today = datetime.now(ET).date().isoformat()
    latest = str(manifest.get("latest_date") or dates[-1])
    default = today if today in dates else latest
    if default != today:
        st.warning(f"Showing the latest official card from {latest}; today’s card has not been published.")
    selected = st.selectbox("Card date", dates, index=dates.index(default), key="cbb_card_date")
    state = manifest.get("dates", {}).get(selected, {})
    ats_history, prediction_history = _load_history(manifest, dates)

    card = metadata = results = None
    if state.get("status") == "no_games_scheduled":
        st.success(f"No D1-vs-D1 games were scheduled for {selected}.")
    else:
        try:
            card, metadata, _ = cbb_daily_data.load_card(selected)
        except Exception as exc:
            st.error(f"The selected card failed verification: {exc}")
            return
        try:
            results = cbb_daily_data.load_results(selected)
        except Exception as exc:
            results = None
            st.warning(f"Results for this date could not be verified, so they are not shown: {exc}")
        _render_day(selected, card, metadata, state, _prediction_frame(card, results))

    _render_prediction_record(prediction_history)
    if card is not None:
        _render_ats_shadow(card, metadata, results, ats_history)
    _render_ats_record(ats_history)
    _render_benchmark_context()


__all__ = ["render"]
