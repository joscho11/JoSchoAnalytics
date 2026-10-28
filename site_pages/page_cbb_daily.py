"""College Basketball daily predictions (public, Beta).

Predictions lead the page. Every published card carries a score, margin, total,
winner and win probability for each game. A "View" menu shows the day's games as
the AP Top 25 or one conference at a time (a game between two conferences is in
both), largest gap between the model and the line first. The 8.5-point ATS shadow
policy sits below the games, labeled exploratory. It has plays only on days whose
card metadata says the row is ``available`` under an official or mixed snapshot.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
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
VIEW_KEY = "cbb_view"
DAY_KEY = "cbb_view_day"
TOP25 = "Top 25"
OTHER = "Other"
MAX_RANK = 25
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
# The intro is one visible sentence; the rest sits one tap away so a phone shows the games without a long scroll.
INTRO_VISIBLE = "Each card shows who the model expects to win, by how many points, and how likely that win is."
INTRO_MORE = (
    "The model works from team and game data only. It never sees sportsbook lines. "
    "Early in the season the model leans on last season's results, so predictions are less certain until teams have played more games. Treat predicted totals as rough estimates then."
)
# Last season's priors dominate until teams have played several games.
EARLY_SEASON_THROUGH = date(2026, 11, 30)
EARLY_SEASON_NOTE = (
    "Early season: these predictions rely heavily on last season's results. "
    "Treat predicted totals as rough estimates until teams have played more games."
)
HOWTO_LABEL = "How to read these cards"
PAGE_KEY = "cbb-page"
HOWTO_KEY = "cbb-howto"
STATUS_KEY = "cbb-status"
CARD_KEY_PREFIX = "cbb-card-"
BENCHMARK_SLUG = "cbb-benchmark"

# Presentation only. Every rule hangs off a cbb-* key (or the View / Card date / search widget keys), so no other page changes.
# Phones: tighter vertical rhythm so the View menu and the first game card sit near the top, 44px controls, 16px control
# text (iOS zooms the page when a focused field is smaller), 12px minimum text. Wider screens: equal-height card pairs.
_CSS = """
<style>
[data-testid="stLayoutWrapper"]:has(> .st-key-cbb-keyboard) { display: none !important; }
/* The win probability stays whole: a long team name wraps inside its own bold run, never between "95%" and "win". */
.st-key-cbb-page [class*="st-key-cbb-card-"] > [data-testid="stElementContainer"]:first-child p {
  display: flex; flex-wrap: wrap; align-items: baseline; column-gap: .3em;
}
.st-key-cbb-page [class*="st-key-cbb-card-"] p { text-wrap: pretty; }
.st-key-cbb-howto [data-testid="stMarkdownContainer"] p { font-size: .9rem; line-height: 1.5; }
.st-key-cbb-howto summary { width: 100% !important; box-sizing: border-box !important; }
/* Phones, portrait or landscape: a tighter vertical rhythm. */
@media (max-width: 640px), (max-height: 500px) and (orientation: landscape) {
  .st-key-cbb-page { gap: .7rem !important; }
  .st-key-cbb-page h1 { padding-top: .25rem !important; padding-bottom: .45rem !important; }
  .st-key-cbb-page h2, .st-key-cbb-page h3 { padding-top: .6rem !important; padding-bottom: .25rem !important; }
  .st-key-cbb-page [data-testid="stAlertContainer"] { padding: .5rem .75rem !important; }
  .st-key-cbb-status { row-gap: .15rem !important; }
}
/* Touch screens (any width): 44px controls, and 16px text in them so iOS does not zoom the page on focus. */
@media (max-width: 640px), (pointer: coarse) {
  .st-key-cbb-howto summary { min-height: 2.75rem !important; }
  .st-key-cbb_card_date [role="group"], .st-key-cbb_view [role="group"],
  .st-key-cbb_team_search [data-testid="stTextInputRootElement"] { min-height: 2.75rem !important; }
  .st-key-cbb_card_date input, .st-key-cbb_view input, .st-key-cbb_team_search input { font-size: 16px !important; }
}
/* Landscape phones are short: trim the desktop title and heading sizes and the top padding. */
@media (max-height: 500px) and (orientation: landscape) {
  [data-testid="stMainBlockContainer"]:has(.st-key-cbb-page) { padding-top: 4rem !important; }
  .st-key-cbb-page h1 { font-size: 1.9rem !important; line-height: 1.2 !important; }
  .st-key-cbb-page h2 { font-size: 1.45rem !important; line-height: 1.25 !important; }
  .st-key-cbb-page h3 { font-size: 1.2rem !important; line-height: 1.3 !important; }
}
/* Metric tiles on phones: rows keep their own height (the shared rule makes every row as tall as the tallest) and no text under 12px. */
@media (max-width: 640px) {
  .st-key-cbb-page [class*="st-key-jsa-metric-even-cbb"]:has(> [data-testid="stElementContainer"] [data-testid="stMetric"]) { grid-auto-rows: auto !important; }
  .st-key-cbb-page [data-testid="stMetricDelta"], .st-key-cbb-page [data-testid="stMetricDelta"] * { font-size: .78rem !important; }
}
/* Two cards side by side share one row height: let each link in the column chain grow (a percentage height would switch off the column stretch). */
@media (min-width: 641px) {
  .st-key-cbb-page [data-testid="stColumn"]:has([class*="st-key-cbb-card-"]) { display: flex; flex-direction: column; }
  .st-key-cbb-page [data-testid="stColumn"]:has([class*="st-key-cbb-card-"]) > [data-testid="stVerticalBlock"],
  .st-key-cbb-page [data-testid="stColumn"]:has([class*="st-key-cbb-card-"]) > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"],
  .st-key-cbb-page [class*="st-key-cbb-card-"] { flex: 1 1 auto; }
  .st-key-cbb-page [class*="st-key-cbb-card-"] > [data-testid="stElementContainer"]:last-child { margin-top: auto; }
}
</style>
"""

# A text-type combobox raises the on-screen keyboard when tapped. The View menu cannot be typed into, so tell the
# browser it needs no keyboard. The team search is typed into, so it gets a Search key and no autocorrect (a phone
# keyboard turns "Gonzaga" into "Gonzales"). Attributes are reapplied whenever Streamlit redraws the widgets.
_NO_KEYBOARD_JS = """
<script>
(function () {
  if (!document.querySelector('.st-key-cbb-keyboard')) { return; }
  var queued = false;
  function set(el, name, value) {
    if (el.getAttribute(name) !== value) { el.setAttribute(name, value); }
  }
  function apply() {
    queued = false;
    var keyboardRoot = document.querySelector('.st-key-cbb-keyboard');
    var pageRoot = document.querySelector('.st-key-cbb-page');
    if (!keyboardRoot || !pageRoot) { return; }
    pageRoot.querySelectorAll('input[role="combobox"][aria-label="View"]').forEach(function (el) { set(el, 'inputmode', 'none'); });
    pageRoot.querySelectorAll('input[aria-label="Find a team"]').forEach(function (el) {
      set(el, 'enterkeyhint', 'search'); set(el, 'autocorrect', 'off'); set(el, 'autocapitalize', 'off'); set(el, 'spellcheck', 'false');
    });
  }
  if (!window.__cbbNoKeyboardObserver) {
    window.__cbbNoKeyboardObserver = new MutationObserver(function () {
      if (!queued) { queued = true; window.requestAnimationFrame(apply); }
    });
    window.__cbbNoKeyboardObserver.observe(document.body, { childList: true, subtree: true });
  }
  apply();
})();
</script>
"""



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


def _format_short_date(day: object) -> str | None:
    """An ISO date as ``Oct 24, 2026``, or None when it is not a date."""
    try:
        parsed = datetime.fromisoformat(str(day))
    except ValueError:
        return None
    return f"{parsed:%b} {parsed.day}, {parsed.year}"


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
    """Model gap (the card's ``model_edge``) to two decimals, never rounded up onto the play threshold.

    A gap of 8.496 is not a play, so it must not display as +8.50.
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


def _rank(value: object) -> int | None:
    """An AP rank 1-25 from a card cell, or None for blank, unranked or out-of-range."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number != int(number) or not 1 <= int(number) <= MAX_RANK:
        return None
    return int(number)


def _tag(name: str, rank: int | None) -> str:
    """A team name for display, with ``#N `` in front when the team is ranked."""
    return f"#{rank} {_md(name)}" if rank else _md(name)


def _query() -> str:
    """The team search box. A non-empty query searches every game of the day, whatever the view."""
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
    home_rank, away_rank = _rank(row.get("home_rank")), _rank(row.get("away_rank"))
    return {
        "home": home, "away": away, "home_wins": home_wins,
        "home_rank": home_rank, "away_rank": away_rank,
        "winner": home if home_wins else away,
        "winner_rank": home_rank if home_wins else away_rank,
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
    parts = [f"{_tag(game['away'], game['away_rank'])} {joiner} {_tag(game['home'], game['home_rank'])}", _format_clock(row.get("tipoff_utc"))]
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


def _line_row(row: pd.Series, game: dict, threshold: float) -> str:
    """The sportsbook line and the model's gap from it, for example ``Line: Kentucky -5.5 · Gap 1.90 toward Kentucky``.

    ``market_home_spread`` is the HOME team's spread, so a negative number means the home team is
    favored. The line names whichever team it favors, and the gap (``model_edge``, positive toward
    the home team) names the team the model leans to relative to the line.
    """
    if _flag(row.get("_has_late_line")):
        spread = float(row["market_home_spread"])
        if abs(spread) < 1e-9:
            line = "Line: pick'em"
        else:
            favored = game["home"] if spread < 0 else game["away"]
            line = f"Line: {_md(favored)} {_format_spread(-abs(spread))}"
        return f"{line} · recovery snapshot"
    if not _flag(row.get("_has_line")):
        return "No line yet"
    spread, edge = float(row["market_home_spread"]), float(row["model_edge"])
    if abs(spread) < 1e-9:
        line = "Line: pick'em"
    else:
        favored = game["home"] if spread < 0 else game["away"]
        line = f"Line: {_md(favored)} {_format_spread(-abs(spread))}"
    gap = _format_edge(abs(edge), threshold).lstrip("+")
    if float(gap) == 0:
        return f"{line} · Gap {gap}"
    return f"{line} · Gap {gap} toward {_md(game['home'] if edge > 0 else game['away'])}"


def _is_play(row: pd.Series) -> bool:
    return _flag(row.get("_has_line")) and str(row.get("ats_pick")) in {"home", "away"}


def _render_game_card(row: pd.Series, final_by_game: dict[str, pd.Series], threshold: float = THRESHOLD) -> None:
    game = _matchup(row)
    card_key = CARD_KEY_PREFIX + re.sub(r"[^A-Za-z0-9]+", "-", str(row.get("game_id")))
    with st.container(border=True, key=card_key, gap="xsmall"):
        st.markdown(f"**{_tag(game['winner'], game['winner_rank'])} by {game['by']:.1f}** · {_format_probability(game['probability'])} win probability")
        st.markdown(
            f"Predicted score: {_md(game['winner'])} {game['winner_score']:.1f}, {_md(game['loser'])} {game['loser_score']:.1f}  \n"
            f"Predicted total: {game['total']:.1f}"
        )
        if _is_play(row):
            # Beside the line on a wide card so two cards side by side keep the same height; wraps below it on a phone.
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(_line_row(row, game, threshold))
                st.badge(f"{threshold:g}+ gap, exploratory", color="orange")
        else:
            st.markdown(_line_row(row, game, threshold))
        final = final_by_game.get(str(row.get("game_id")))
        if final is not None:
            st.markdown(_final_line(game, final, float(row["predicted_margin"])))
        st.caption(_game_caption(row, game))


def _conference_names(card: pd.DataFrame, column: str) -> pd.Series:
    if column not in card:
        return pd.Series("", index=card.index, dtype="object")
    return card[column].astype("string").fillna("").str.strip().astype(object)


def _prepare(card: pd.DataFrame, official: bool, conference_order: dict, catch_up: bool = False) -> pd.DataFrame:
    """The card plus helper columns: who has a line and the gap, tip time, AP ranks, and each team's conference group.

    Official rows can carry gaps and picks. Recovery rows can show spread context only. A card
    whose metadata lost its status shows no lines, no gaps and no plays.
    """
    games = card.copy()
    edge = pd.to_numeric(games["model_edge"], errors="coerce")
    spread = pd.to_numeric(games["market_home_spread"], errors="coerce")
    games["_has_line"] = bool(official) & games["market_status"].astype(str).eq("available") & edge.notna() & spread.notna()
    games["_has_late_line"] = bool(catch_up) & games["market_status"].astype(str).eq("late_available") & spread.notna()
    games["_gap"] = edge.abs().where(games["_has_line"])
    games["_tip"] = pd.to_datetime(games["tipoff_utc"], utc=True, errors="coerce")
    aliases = conference_order["aliases"] if conference_order["available"] else {}
    raw = {side: _conference_names(games, f"{side}_conference") for side in ("home", "away")}
    if conference_order["available"]:
        known = set(conference_order["order"])
    else:
        known = {name for names in raw.values() for name in names if name}
    for side in ("home", "away"):
        resolved = raw[side].map(lambda name: aliases.get(name, name))
        games[f"_{side}_group"] = resolved.where(resolved.isin(known), OTHER)
        games[f"_{side}_ranked"] = games[f"{side}_rank"].map(_rank).notna() if f"{side}_rank" in games else False
    games["_ranked"] = games["_home_ranked"] | games["_away_ranked"]
    return games


def _view_options(games: pd.DataFrame, conference_order: dict) -> list[tuple[str, int]]:
    """Menu entries as (view, game count): Top 25, then each conference with a game in file order, then Other.

    Without the order file the conferences go alphabetically. A game between two conferences counts in both.
    """
    present = set(games["_home_group"]) | set(games["_away_group"])
    names = conference_order["order"] if conference_order["available"] else sorted(present - {OTHER}, key=str.casefold)
    views = [name for name in names if name in present] + ([OTHER] if OTHER in present else [])
    options = [(TOP25, int(games["_ranked"].sum()))]
    options += [(name, int(((games["_home_group"] == name) | (games["_away_group"] == name)).sum())) for name in views]
    return options


def _default_view(options: list[tuple[str, int]]) -> str:
    """Top 25 when a ranked team plays, otherwise the first conference on the menu."""
    return TOP25 if options[0][1] or len(options) == 1 else options[1][0]


def _in_view(games: pd.DataFrame, view: str) -> pd.DataFrame:
    if view == TOP25:
        return games[games["_ranked"]]
    return games[(games["_home_group"] == view) | (games["_away_group"] == view)]


def _sorted_for_display(games: pd.DataFrame) -> pd.DataFrame:
    """Largest gap first for games with a line, then games without one by tip time, then home team."""
    return games.sort_values(
        ["_has_line", "_gap", "_tip", "home_team"], ascending=[False, False, True, True], kind="mergesort", na_position="last",
    )


def _poll_text(top25: object) -> str | None:
    """``AP poll of Oct 20, 2026 (preseason)`` from the card's poll metadata, or None when there is no poll."""
    if not isinstance(top25, dict):
        return None
    when = _format_short_date(top25.get("poll_date"))
    if when is None:
        return None
    return f"AP poll of {when}" + (" (preseason)" if top25.get("week") == 1 else "")


def _view_caption(top25: object, conference_order: dict) -> str:
    poll = _poll_text(top25)
    first = f"Top 25: {poll}." if poll else "Top 25: no AP poll is available for this date."
    if not conference_order["available"]:
        return f"{first} Conference order: alphabetical, because the conference ranking list could not be loaded."
    snapshot = _format_short_date(conference_order.get("captured_on"))
    return f"{first} Conference order: WarrenNolan.com conference ranking" + (f", snapshot of {snapshot}." if snapshot else ".")


COVERAGE_REASONS = {
    "start_time_tbd": "with no confirmed start time",
    "invalid_tipoff": "with a start time that could not be read",
    "already_started": "already started when predictions were made",
    "missing_neutral_site": "with the game site not confirmed",
}
OTHER_REASON = "with other data gaps"
# The page covers Division I games only. Current cards no longer count other games; an older card might.
NON_D1_REASON = "not_d1_v_d1"


def _coverage_caption(metadata: dict) -> str | None:
    """Say how many scheduled Division I games the card covers, when the card records it and some were left out."""
    coverage = metadata.get("coverage")
    if not isinstance(coverage, dict):
        return None
    try:
        scheduled, predicted = int(coverage["scheduled_games"]), int(coverage["predicted_games"])
        excluded = int(coverage["excluded_games"])
        reasons = {str(key): int(value) for key, value in dict(coverage.get("excluded_by_reason") or {}).items() if int(value) > 0}
    except (KeyError, TypeError, ValueError):
        return None
    non_d1 = reasons.pop(NON_D1_REASON, 0)
    scheduled, excluded = scheduled - non_d1, excluded - non_d1
    if excluded <= 0:
        return None
    by_label: dict[str, int] = {}
    for reason, count in reasons.items():
        label = COVERAGE_REASONS.get(reason, OTHER_REASON)
        by_label[label] = by_label.get(label, 0) + count
    parts = [f"{count} {label}" for label, count in sorted(by_label.items(), key=lambda item: (-item[1], item[0]))]
    caption = f"Showing {predicted} of {scheduled} Division I games on the schedule."
    return f"{caption} Not shown: {', '.join(parts)}." if parts else caption


def _start_day(selected: str) -> None:
    """Drop the search and any Top 25 choice when the card date changes, so neither carries over stale.

    A conference choice survives if the new date has that conference; ``_render_day`` resets it when not.
    """
    if st.session_state.get(DAY_KEY) == selected:
        return
    st.session_state[DAY_KEY] = selected
    st.session_state[SEARCH_KEY] = ""
    if st.session_state.get(VIEW_KEY) == TOP25:
        del st.session_state[VIEW_KEY]


def _render_day(selected: str, card: pd.DataFrame, metadata: dict, state: dict, day_final: pd.DataFrame, notes=None) -> None:
    """One day's card. ``notes`` is the "How to read these cards" box, where the menu and sort captions go (inline when None)."""
    notes = notes if notes is not None else st.container()
    st.subheader(f"Predictions for {_format_day(selected)}")
    coverage_caption = _coverage_caption(metadata)
    if coverage_caption:
        st.caption(coverage_caption)
    status = str(metadata.get("status", state.get("status", "published"))).replace("_", " ").title()
    with st.container(horizontal=True, vertical_alignment="center", key=STATUS_KEY):
        st.badge(status, icon=":material/verified:", color="green")
        st.caption(f"{_plural(len(card), 'game', 'games')} · predictions made {_format_stamp(metadata.get('prediction_at_utc'))}")
    summary = _prediction_summary(day_final)
    if summary["games"]:
        with st.container(horizontal=True, key="jsa-metric-even-cbb-summary"):
            st.metric("Games finished", f"{summary['games']} of {len(card)}", border=True)
            st.metric("Winner picks correct", f"{summary['correct']} of {summary['games']}", f"{summary['winner_rate']:.0%}", delta_color="gray", delta_arrow="off", border=True)

    snapshot_status = str(metadata.get("line_snapshot_status") or "")
    official = snapshot_status in {"official", "mixed"}
    catch_up = snapshot_status in {"catch_up", "mixed"}
    threshold = float(metadata.get("threshold", THRESHOLD))
    top25 = metadata.get("top25")
    conference_order = cbb_daily_data.load_conference_order()
    games = _prepare(card, official, conference_order, catch_up)
    options = _view_options(games, conference_order)
    views = [view for view, _ in options]
    labels = {view: f"{view} ({_plural(count, 'game', 'games')})" for view, count in options}
    if st.session_state.get(VIEW_KEY) not in views:
        st.session_state[VIEW_KEY] = _default_view(options)
    query = _query()
    view = st.selectbox("View", views, format_func=labels.__getitem__, key=VIEW_KEY, filter_mode=None, disabled=bool(query))
    with notes:
        st.caption(_view_caption(top25, conference_order))
        if games["_has_line"].any() and games["_has_late_line"].any():
            st.caption(f"Official lines are listed by gap. Recovery spreads captured {_format_stamp(metadata.get('line_retrieved_at_utc'))} are shown for context only and are not graded. Games without a line follow, by tip time.")
        elif games["_has_line"].any():
            st.caption("Games are listed by gap: how far the model's predicted margin is from the sportsbook line, largest first. Games with no line follow, by tip time.")
        elif games["_has_late_line"].any():
            st.caption(f"Recovery spreads captured {_format_stamp(metadata.get('line_retrieved_at_utc'))} are shown for context only and are not graded. Games are listed by tip time.")
        else:
            st.caption("No sportsbook line is available for this date, so games are listed by tip time.")

    if not query and date.fromisoformat(str(selected)[:10]) <= EARLY_SEASON_THROUGH:
        st.caption(EARLY_SEASON_NOTE)
    st.text_input("Find a team", key=SEARCH_KEY, placeholder="Type a team name")
    if query:
        st.caption("Searching all of this date's games. Clear the box to use the View menu again.")
        shown = _matches(games, query)
    else:
        shown = _in_view(games, view)
    if shown.empty:
        if query:
            st.info("No games match that search.")
        elif view == TOP25:
            st.info("No ranked team plays on this date." if _poll_text(top25) else "The AP Top 25 poll is not available for this date, so there are no ranked teams to show.")
        return
    shown = _sorted_for_display(shown)
    final_by_game = {str(row["game_id"]): row for _, row in day_final.iterrows()} if not day_final.empty else {}
    rows = [row for _, row in shown.iterrows()]
    # Two across on a wide screen. Streamlit stacks the columns on a phone, in the same order.
    for start in range(0, len(rows), 2):
        for column, row in zip(st.columns(2), rows[start:start + 2]):
            with column:
                _render_game_card(row, final_by_game, threshold)


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


def _render_ats_shadow(card: pd.DataFrame, metadata: dict, results: pd.DataFrame | None, ats_history: pd.DataFrame) -> None:
    status = str(metadata.get("line_snapshot_status") or "unavailable")
    threshold = float(metadata.get("threshold", THRESHOLD))
    st.subheader("Exploratory ATS shadow (8.5-point policy)")
    st.caption(
        "ATS means against the spread. The shadow policy names a team only when the model's predicted margin and the median sportsbook spread "
        f"differ by {threshold:g} points or more. The model never sees the spread. This is a research experiment, not betting advice, "
        "and it did not pass its own 2026 test."
    )
    if status == "mixed":
        st.info("Recovery spreads are shown for context only and are not scored.")
    elif status != "official":
        if status == "rejected":
            st.info(f"{NO_SNAPSHOT_NOTICE} The snapshot we collected did not pass our checks.")
        elif status == "catch_up":
            st.info("Recovery spreads are shown for context only and are not scored.")
        else:
            st.info(NO_SNAPSHOT_NOTICE)
        return
    market = card["market_status"].astype(str)
    lined = card[market.eq("available")].copy()
    lined["_edge"] = pd.to_numeric(lined["model_edge"], errors="coerce")  # the card's model_edge column is the gap
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
        st.caption(f"No game reached the {threshold:g}-point gap on this card, so there are no shadow picks.")
    for _, row in plays.iterrows():
        pick_home = str(row["ats_pick"]) == "home"
        spread = float(row["market_home_spread"]) * (1 if pick_home else -1)
        with st.container(border=True, gap="xsmall"):
            st.markdown(f"**Shadow pick: {_md(_pick_name(row))} {_format_spread(spread)}**")
            st.caption(
                f"{_md(row['away_team'])} at {_md(row['home_team'])} · model gap {_format_edge(float(row['_edge']), threshold)}"
                f" · result: {_outcome(result_by_game, str(row.get('game_id'))).lower()}"
            )
    st.caption(
        "Model gap is the model's predicted margin minus the margin the spread implies, from the home team's side. A positive gap favors the home team "
        f"and a negative gap favors the away team. A game becomes a shadow pick only when its gap reaches {threshold:g} points in either direction."
    )


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
            st.line_chart(chart, y=["ATS win rate", "Illustrative -110 break-even"], color=["#35D08A", "#93A0B1"], height=260)
        else:
            st.caption("The running chart appears once graded plays from a second day are in.")
        st.caption("Practical implication: the interval and reference line show whether the current live sample is distinguishable from break-even. This does not establish tradability because sample size is small and historical lines were not point-in-time verified.")


def _benchmark_for_phone(table: pd.DataFrame) -> pd.DataFrame:
    """The benchmark table turned on its side: one column per period, the same cell text as the wide grid."""
    shown = table.set_index("Period").astype(object).map(lambda value: f"{value:g}" if isinstance(value, float) else str(value))
    shown.index.name = None
    return shown.T


def _render_benchmark_context() -> None:
    st.subheader("Historical benchmark context")
    st.caption("These historical results are descriptive/post-hoc because CBBD does not prove when each historical line became available; they are not live performance claims.")
    history_table = pd.DataFrame([
        {"Period": "2022–2025 OOF", "Record": "344–267–0", "Graded": 611, "ATS rate": 0.5630, "Wilson 95%": "52.34%–60.18%"},
        {"Period": "Season 2026", "Record": "87–64–0", "Graded": 151, "ATS rate": 0.5762, "Wilson 95%": "49.64%–65.21%"},
    ])
    # Both copies render and CSS shows one (mobile.py, jsa-table-*): the five-column grid overflows a phone, so phones get
    # the same cells with periods across the top and fields down the side.
    with st.container(key=f"jsa-table-desktop-{BENCHMARK_SLUG}"):
        st.dataframe(history_table, hide_index=True, width="stretch")
    with st.container(key=f"jsa-table-phone-{BENCHMARK_SLUG}"):
        st.dataframe(_benchmark_for_phone(history_table), width="stretch")
    st.caption("The 2026 descriptive interval includes 50%, so it did not clear the historical confidence gate; the frozen policy remains exploratory shadow-only.")


def render():
    st.html(_CSS)  # style only: lands in the event container, takes no space
    with st.container(key="cbb-keyboard"):
        st.html(_NO_KEYBOARD_JS, unsafe_allow_javascript=True)
    with st.container(key=PAGE_KEY):
        _render_page()


def _render_page() -> None:
    st.title("College basketball daily predictions")
    st.badge("Beta", icon=":material/science:", color="blue")
    st.caption("Model predictions for men’s Division I games, posted each morning before tip-off. Data provided by CollegeBasketballData.com.")
    st.info(INTRO_VISIBLE)
    notes = st.expander(HOWTO_LABEL, key=HOWTO_KEY)
    with notes:
        st.markdown(INTRO_MORE)

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
    _start_day(selected)
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
        _render_day(selected, card, metadata, state, _prediction_frame(card, results), notes)

    _render_prediction_record(prediction_history)
    if card is not None:
        _render_ats_shadow(card, metadata, results, ats_history)
    _render_ats_record(ats_history)
    _render_benchmark_context()


__all__ = ["render"]
