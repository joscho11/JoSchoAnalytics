"""League History page backed by Sleeper, ESPN, Yahoo, and CBS league endpoints."""
import concurrent.futures as _cf
import glob
import html as _html
import itertools as _it
import json
import os
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
import requests as req
import streamlit as st

import dashboard_data
import page_common
import nav_registry
from dashboard_utils import get_confidence, _md_to_html
from dashboard_chrome import _OFFLINE, TABLE_HEIGHT, dataframe_phone_desktop, send_ga_event

_HERE = Path(__file__).resolve().parents[1]

# Sleeper league IDs in the local history fixture are 18--19 digit snowflakes. This is
# deliberately a plausibility gate, not a claim that every ID in this range exists.
_MIN_LEAGUE_ID_DIGITS = 15
_MAX_LEAGUE_ID_DIGITS = 20
_SLEEPER_GET_CACHE_ENTRIES = 128
_HISTORY_CACHE_ENTRIES = 8
_MATCHUP_FETCH_WORKERS = 6
_MAX_HISTORY_SEASONS = 10
_SEASON_CACHE_ENTRIES = _HISTORY_CACHE_ENTRIES * _MAX_HISTORY_SEASONS
_LEAGUE_PROVIDERS = ("Sleeper", "ESPN", "Yahoo", "CBS")
_LEAGUE_HISTORY_TABS = (
    "🧠 Draft & Roster Insights",
    "🏆 All-Time Leaderboard",
    "🎖️ Hall of Fame",
    "⚔️ Rivalries",
    "📋 Report Cards",
    "📊 Consistency & Luck",
)

# Rivalries score bands: green 70+, yellow 50-69, red below 50.
# Full hairline borders only; no side stripes.


_LEADERBOARD_METRIC_HELP = {
    "Most Titles": (
        "Championship count in this window. Ties share the card. "
        "Three or more leaders show as an N-way tie."
    ),
    "Best Win %": (
        "Regular-season wins divided by wins plus losses. "
        "All Time needs 2 seasons, so a one-year 10-0 does not take it."
    ),
    "Most Points": (
        "Sum of regular-season weekly scores in this window. Playoffs are excluded. "
        "Not adjusted for era, so a high-scoring year counts more."
    ),
    "Most Finals Appearances": (
        "Championship games reached, as champ or runner-up."
    ),
    "Longest Active Playoff Streak": (
        "Consecutive playoff seasons through the latest completed postseason "
        "in this window. Sitting out or missing the playoffs resets it. "
        "An in-progress season does not count against it. Ties share the card. "
        "Three or more leaders show as an N-way tie."
    ),
    "Most Toilet Bowl Titles": (
        "Winner of that season's consolation championship, the toilet bowl. "
        "That is last place. Counted the same way as championship titles. "
        "Ties share the card. Three or more leaders show as an N-way tie."
    ),
    "Most Toilet Bracket Finals Appearances": (
        "Toilet bowl championship games reached, as champ or runner-up. "
        "Same idea as Most Finals Appearances. Ties share the card. "
        "Three or more leaders show as an N-way tie."
    ),
    "Lowest Scoring Team": (
        "Regular-season points per game. Playoffs are excluded. "
        "All Time needs more than 2 seasons, so a one-year disaster does not take it. "
        "Ties share the card."
    ),
}

_LEADERBOARD_COUNT_CARDS = {
    "Most Titles",
    "Most Finals Appearances",
    "Longest Active Playoff Streak",
    "Most Toilet Bowl Titles",
    "Most Toilet Bracket Finals Appearances",
}

_HOF_METRIC_HELP = {
    "🏆 Highest Score": (
        "Highest single-team score in a completed matchup in this window. "
        "Playoffs count."
    ),
    "😤 Most Painful Loss": (
        "Highest losing score in this window. The team put up a big number and still lost. "
        "Playoffs count. Scores of 5 or fewer are ignored."
    ),
    "💥 Biggest Blowout": (
        "Largest point gap between winner and loser in a completed matchup. "
        "Playoffs count."
    ),
    "🤝 Closest Game": (
        "Smallest point gap between winner and loser. A tie counts as 0. "
        "Playoffs count."
    ),
    "💀 Lowest Score": (
        "Lowest single-team score in a completed matchup. "
        "Scores of 5 or fewer are treated as incomplete, so an empty lineup does not take this."
    ),
    "🍀 Luckiest Win (All-Play)": (
        "The win whose score would have beaten the fewest other teams in that same league-week. "
        "This is matchup timing, not the lowest winning score."
    ),
    "🔥 Highest-Scoring Game": (
        "Highest combined score of both teams in one matchup. "
        "A blowout can still win this if one side was huge."
    ),
    "🧊 Lowest-Scoring Game": (
        "Lowest combined score of both teams in one completed matchup. "
        "Scores of 5 or fewer are treated as incomplete."
    ),
}

_CONSISTENCY_LUCK_METRIC_HELP = {
    "Most Consistent": (
        "Lowest week-to-week scoring swing after subtracting that week's league average. "
        "A high-scoring week in a high-scoring environment does not look wild. "
        "Smaller is steadier. Regular season only."
    ),
    "Most Volatile": (
        "Highest week-to-week scoring swing after subtracting that week's league average. "
        "This is scoring variance, not a bad record. Regular season only."
    ),
    "Most Fortunate": (
        "Largest surplus of actual wins over all-play expected wins. "
        "Expected wins ask how often this week's score would have beaten every other team that week. "
        "This is matchup timing, not whether the wins count."
    ),
    "Most Unfortunate": (
        "Largest shortfall of actual wins versus all-play expected wins. "
        "The weekly scores were better than the head-to-head record. "
        "Regular season only."
    ),
}


def _hof_metric(label: str, value, delta: str | None = None) -> None:
    st.metric(
        label, value, delta,
        delta_color="off", delta_arrow="off", border=True,
        help=_HOF_METRIC_HELP[label],
    )


def _leaderboard_metric(
    label: str,
    names: list[str],
    delta: str | None,
    *,
    empty_value: str,
    empty_delta: str | None = None,
    flip_at: int | None = None,
) -> None:
    kwargs = dict(
        delta_color="off", delta_arrow="off", border=True,
        help=_LEADERBOARD_METRIC_HELP.get(label),
    )
    if not names:
        st.metric(label, empty_value, empty_delta, **kwargs)
        return
    from fantasy import league_intelligence as _intel
    st.metric(
        label,
        _intel.scorecard_headline(names, flip_at=flip_at),
        delta,
        **kwargs,
    )


def _rivalry_score_swatch(score: float, locked: bool = False) -> tuple[str, str, str]:
    """Return (ink, border, fill) for a rivalry-week card."""
    if locked:
        return "#60A5FA", "rgba(96,165,250,0.70)", "rgba(96,165,250,0.14)"
    if score >= 70:
        return "#35D08A", "rgba(53,208,138,0.55)", "rgba(53,208,138,0.12)"
    if score >= 50:
        return "#FACC15", "rgba(250,204,21,0.55)", "rgba(250,204,21,0.12)"
    return "#F87171", "rgba(248,113,113,0.55)", "rgba(248,113,113,0.12)"


def _rivalry_slate_card_html(row) -> str:
    manager_a = _html.escape(str(row["manager_a"]))
    manager_b = _html.escape(str(row["manager_b"]))
    reason = _html.escape(str(row.get("reason") or ""))
    locked = bool(row.get("locked"))
    score = float(row["rivalry_score"])
    ink, border, fill = _rivalry_score_swatch(score, locked)
    lock_mark = " 🔒" if locked else ""
    return (
        "<div class='jsa-lh-card' style='background:" + fill + ";border:1px solid " + border
        + ";border-radius:12px;padding:14px 16px;margin:0 0 10px 0;'>"
        "<div class='jsa-lh-card-row' style='display:flex;justify-content:space-between;"
        "gap:16px;align-items:flex-start;'>"
        "<div class='jsa-lh-card-copy' style='min-width:0;'>"
        "<div style='font-size:18px;font-weight:700;color:#E7ECF3;letter-spacing:-0.02em;"
        "overflow-wrap:anywhere;'>"
        + manager_a + " vs " + manager_b + lock_mark + "</div>"
        "<div style='font-size:13px;color:#E7ECF3;margin-top:6px;line-height:1.45;"
        "overflow-wrap:anywhere;'>"
        + reason + "</div>"
        "</div>"
        "<div class='jsa-lh-score' style='text-align:right;flex:0 0 auto;'>"
        "<div style='font-size:11px;font-weight:700;letter-spacing:0.08em;color:"
        + ink + ";'>RIVALRY SCORE</div>"
        "<div style='font-size:28px;font-weight:800;color:" + ink
        + ";font-variant-numeric:tabular-nums;line-height:1.1;'>"
        + f"{score:.1f}" + "</div>"
        "</div></div></div>"
    )


def _rivalry_score_legend_html() -> str:
    chips = (
        ("#35D08A", "rgba(53,208,138,0.16)", "70+ fit"),
        ("#FACC15", "rgba(250,204,21,0.16)", "50-69"),
        ("#F87171", "rgba(248,113,113,0.16)", "below 50"),
    )
    parts = []
    for ink, fill, label in chips:
        parts.append(
            "<span style='display:inline-block;padding:3px 9px;border-radius:999px;"
            "border:1px solid " + ink + ";background:" + fill + ";color:" + ink
            + ";font-size:11px;font-weight:700;letter-spacing:0.04em;'>"
            + label + "</span>"
        )
    return (
        "<div class='jsa-lh-legend' style='display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 12px 0;'>"
        + "".join(parts) + "</div>"
    )


def _lh_plotly(fig) -> None:
    """Stretch charts and keep phone scroll from being stolen by Plotly."""
    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False, "scrollZoom": False},
    )


def _schedule_luck_figure(cl_df):
    """Horizontal luck bars whose outside labels stay off the x-axis title.

    On a phone the plot is ~170px once a 165px right gutter is reserved, and the
    old one-line x-axis title is wider than that, so it ran into the bar labels.
    Short labels plus a wrapped title keep each in its own band on phone and desktop.
    """
    import plotly.graph_objects as go

    luck_sorted = cl_df.sort_values("luck_delta", ascending=True).copy()
    luck_text = [
        f"{actual:.1f} / {expected:.1f}"
        for actual, expected in zip(
            luck_sorted["actual_wins"], luck_sorted["expected_wins"]
        )
    ]
    fig = go.Figure(go.Bar(
        x=luck_sorted["luck_delta"],
        y=luck_sorted["manager"],
        orientation="h",
        text=luck_text,
        textposition="outside",
        textfont={"size": 11},
        cliponaxis=False,
        marker={
            "color": [
                "#34d399" if value >= 0 else "#fb7185"
                for value in luck_sorted["luck_delta"]
            ],
            "line": {"color": "rgba(255,255,255,0.45)", "width": 1},
        },
        customdata=luck_sorted[[
            "actual_win_pct", "expected_win_pct", "below_avg_wins",
            "above_avg_losses", "games",
        ]],
        hovertemplate=(
            "<b>%{y}</b><br>Wins vs expected: %{x:+.2f}<br>"
            "Actual win rate: %{customdata[0]:.1f}%<br>"
            "All-play expected rate: %{customdata[1]:.1f}%<br>"
            "Below-average wins: %{customdata[2]}<br>"
            "Above-average losses: %{customdata[3]}<br>"
            "Games: %{customdata[4]}<extra></extra>"
        ),
    ))
    luck_span = max(1.0, float(luck_sorted["luck_delta"].abs().max()) * 1.3)
    fig.add_vline(x=0, line_color="#94a3b8", line_width=1)
    fig.update_layout(
        title="Schedule Luck: Actual Wins Minus All-Play Expected Wins",
        height=max(430, 40 * len(luck_sorted) + 120),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.36)",
        margin={"l": 25, "r": 96, "t": 70, "b": 84},
        showlegend=False,
        xaxis={
            "title": {
                "text": "Wins vs<br>expected",
                "standoff": 18,
                "font": {"size": 12},
            },
            "range": [-luck_span, luck_span],
            "automargin": True,
            "gridcolor": "rgba(148,163,184,0.16)",
        },
        yaxis={"title": "", "automargin": True},
    )
    return fig


def _league_matrix_figure(
    managers,
    heat_values,
    heat_text,
    heat_games,
    *,
    phone: bool,
):
    """Head-to-head heatmap. Phone drops cell records and draws a wide pannable grid."""
    import plotly.graph_objects as go

    n = len(managers)
    phone_w = max(760, 60 * n + 168) if phone else None
    phone_h = max(760, 60 * n + 220) if phone else None
    heatmap = dict(
        z=heat_values,
        x=managers,
        y=managers,
        text=heat_text,
        customdata=heat_games,
        hoverongaps=False,
        zmin=-50,
        zmax=50,
        zmid=0,
        colorscale=[
            [0, "#9F1239"],
            [0.5, "#121821"],
            [1, "#15803D"],
        ],
        xgap=3 if phone else 2,
        ygap=3 if phone else 2,
        hovertemplate=(
            "<b>%{y} vs %{x}</b><br>Record: %{text}<br>"
            "Win-rate edge: %{z:+.1f} pp<br>Meetings: %{customdata}<extra></extra>"
        ),
    )
    if phone:
        heatmap["showscale"] = False
    else:
        heatmap["texttemplate"] = "%{text}"
        heatmap["textfont"] = {"size": 11}
        heatmap["colorbar"] = {
            "title": "Win-rate edge",
            "ticksuffix": " pp",
        }
    fig = go.Figure(go.Heatmap(**heatmap))
    layout = dict(
        title="League-Wide Head-to-Head Dominance",
        height=phone_h if phone else max(520, 42 * n + 170),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.36)",
        margin=(
            {"l": 108, "r": 16, "t": 56, "b": 128}
            if phone else
            {"l": 72, "r": 24, "t": 64, "b": 96}
        ),
        xaxis={
            "title": "Opponent",
            "tickangle": -90 if phone else -45,
            "side": "bottom",
            "automargin": True,
            "tickfont": {"size": 11 if phone else 10},
        },
        yaxis={
            "title": "Manager",
            "autorange": "reversed",
            "automargin": True,
            "tickfont": {"size": 11 if phone else 10},
        },
    )
    if phone:
        layout["width"] = phone_w
        layout["autosize"] = False
    fig.update_layout(**layout)
    return fig


def _league_id_error(raw_league_id: str) -> str | None:
    league_id = raw_league_id.strip()
    if not league_id:
        return "Enter your Sleeper league ID to load your league history."
    if not league_id.isdigit():
        return "Sleeper league IDs contain digits only."
    if not _MIN_LEAGUE_ID_DIGITS <= len(league_id) <= _MAX_LEAGUE_ID_DIGITS:
        return (
            f"That does not look like a Sleeper league ID. Enter a "
            f"{_MIN_LEAGUE_ID_DIGITS}-{_MAX_LEAGUE_ID_DIGITS} digit ID from your league URL."
        )
    return None


def _league_request_error(
    provider: str,
    raw_league_id: str,
    espn_season: int | None = None,
    espn_access: str = "Public",
    espn_s2: str = "",
    swid: str = "",
    yahoo_season: int | None = None,
    yahoo_access: str = "Public",
    yahoo_y: str = "",
    yahoo_t: str = "",
    cbs_season: int | None = None,
    cbs_token: str = "",
) -> str | None:
    if provider == "ESPN":
        import espn_league_history as _espn

        id_error = _espn.league_id_error(raw_league_id)
        if id_error:
            return id_error
        year_error = _espn.season_error(espn_season, dt.now().year)
        if year_error:
            return year_error
        if espn_access == "Private":
            return _espn.private_credentials_error(espn_s2, swid)
        return None
    if provider == "Yahoo":
        import yahoo_league_history as _yahoo

        id_error = _yahoo.league_id_error(raw_league_id)
        if id_error:
            return id_error
        year_error = _yahoo.season_error(yahoo_season, dt.now().year)
        if year_error:
            return year_error
        if yahoo_access == "Private":
            return _yahoo.private_credentials_error(yahoo_y, yahoo_t)
        return None
    if provider == "CBS":
        import cbs_league_history as _cbs

        id_error = _cbs.league_id_error(raw_league_id)
        if id_error:
            return id_error
        year_error = _cbs.season_error(cbs_season, dt.now().year)
        if year_error:
            return year_error
        return _cbs.private_credentials_error(cbs_token)
    return _league_id_error(raw_league_id)


def _league_import_help_markdown(
    provider: str = "Sleeper",
    espn_access: str = "Public",
) -> str:
    """Return device-specific instructions for the active import method."""
    if provider == "CBS":
        return """
### League ID and season

**On a phone:** Open the league in the CBS Sports Fantasy app or in a browser. Copy the league ID from the league URL. It is the subdomain before `.football.cbssports.com`. A URL like `https://cbshelp.football.cbssports.com` is league ID `cbshelp`. Use the latest season the league played.

**On a computer:** Open the league at `{ID}.football.cbssports.com`. Copy that subdomain into **CBS League ID**, then choose the latest season the league played.

### Access token

CBS Commissioner leagues are not publicly viewable the way ESPN and Yahoo can be. This importer always needs a signed-in access token.

**On a phone:** The normal iPhone and Android browser menus do not expose this value. Get the League ID on the phone, but use a signed-in desktop browser for the token.

**On a computer (Chrome or Edge):**

1. Sign in at your league site, `{ID}.football.cbssports.com`.
2. Open Developer Tools (`F12`, or right-click and select **Inspect**).
3. Select **Network**, reload the page, and click any `/api/league` request.
4. Copy the **Authorization** header value into **CBS access token**. You can also search the page source for `var token`.

In Firefox, use **Developer Tools → Network**. In Safari on Mac, enable developer features, then use **Develop → Show Web Inspector → Network**.

Treat the token like a password. Never paste it into chat or send it to another person. This importer sends it only to CBS, never logs or shared-caches it, and clears the field after a successful load. Use private import only on a deployment you trust.

[CBS's League ID guide](https://help.football.cbssports.com/s/article/How-do-I-find-my-league-ID)
"""

    if provider == "Yahoo":
        if espn_access == "Private":
            return """
### League ID and season

**On a phone:** Open the league in the Yahoo Fantasy app and copy the league ID from league info, or share the league link and copy the number after `/f1/`. Use the latest season the league played.

**On a computer:** Open the league at `football.fantasysports.yahoo.com`. Copy the digits after `/f1/` in the address bar, then choose the latest season the league played. A URL like `/2025/f1/123456` is season 2025 and league ID 123456.

### Y and T cookies

**On a phone:** The normal iPhone and Android browser menus do not expose these cookie values. Get the League ID on the phone, but use a signed-in desktop browser for the two cookies.

**On a computer (Chrome or Edge):**

1. Sign in at `football.fantasysports.yahoo.com` and open the private league.
2. Open Developer Tools (`F12`, or right-click and select **Inspect**).
3. Select **Application → Storage → Cookies**, then the Yahoo origin.
4. Filter for `Y`; copy its **Value** into **Yahoo Y cookie**.
5. Filter for `T`; copy its **Value** into **Yahoo T cookie**.

In Firefox, use **Developer Tools → Storage → Cookies**. In Safari on Mac, enable developer features, then use **Develop → Show Web Inspector → Storage → Cookies**.

Treat both values like passwords. Never paste them into chat or send them to another person. This importer sends them only to Yahoo, never logs or shared-caches them, and clears both fields after a successful load. Use private import only on a deployment you trust.

If Yahoo still denies access, ask the commissioner to make the league publicly viewable and use the Public importer instead.
"""
        return """
### On a phone

1. Open the league in the Yahoo Fantasy app.
2. Open league info or share the league link.
3. Copy the number after `/f1/` into **Yahoo League ID**.
4. Choose the latest season the league played.

### On a computer

1. Open the league at `football.fantasysports.yahoo.com`.
2. Copy the digits after `/f1/` in the address bar. A URL like `/2025/f1/123456` is season 2025 and league ID 123456.
3. Paste that number below and choose the latest season the league played.

### If Yahoo denies public access

Here, **Public** uses Yahoo's publicly viewable setting. Your commissioner exposes league pages with that setting. Otherwise, switch this importer to **Private** and use the signed-in browser instructions.
"""

    if provider == "Sleeper":
        return """
### On a phone

1. Open the league in the Sleeper app.
2. Tap the settings icon, then open **General**.
3. Scroll to the bottom of General League Settings and tap **Copy League ID**.
4. Paste that number into **Sleeper League ID** below.

### On a computer

1. Sign in at [sleeper.app](https://sleeper.app/) and open the league.
2. Copy the numeric league ID at the end of the page URL. It is usually the number after `/leagues/`.
3. Paste only that number below.

[Sleeper's League ID guide](https://support.sleeper.com/en/articles/4121798-how-do-i-find-my-league-id)
"""

    if espn_access == "Private":
        return """
### League ID and season

**On a phone:** In the ESPN Fantasy app, open the league, select the **League** tab, then **League Info**. Copy the League ID shown there. Use the latest season the league played; for an inactive league, use its final active season.

**On a computer:** Open the league at `fantasy.espn.com`. Copy the digits after `leagueId=` in the address bar, then choose the latest season the league played.

### SWID and espn_s2

**On a phone:** The normal iPhone and Android browser menus do not expose these cookie values. Get the League ID on the phone, but use a signed-in desktop browser for the two cookies. Remote phone inspection still requires a computer, and iPhone inspection requires a Mac.

**On a computer (Chrome or Edge):**

1. Sign in at `fantasy.espn.com` and open the private league.
2. Open Developer Tools (`F12`, or right-click and select **Inspect**).
3. Select **Application → Storage → Cookies**, then the `fantasy.espn.com` origin.
4. Filter for `SWID`; copy its **Value** into **ESPN SWID cookie**.
5. Filter for `espn_s2`; copy its **Value** into **ESPN espn_s2 cookie**.

In Firefox, use **Developer Tools → Storage → Cookies**. In Safari on Mac, enable developer features, then use **Develop → Show Web Inspector → Storage → Cookies**.

Treat both values like passwords. Never paste them into chat or send them to another person. This importer sends them only to ESPN, never logs or shared-caches them, and clears both fields after a successful load. Use private import only on a deployment you trust.

[ESPN's League ID guide](https://support.espn.com/hc/en-us/articles/4669614193556-League-ID) · [Chrome cookie instructions](https://developer.chrome.com/docs/devtools/application/cookies/)
"""

    return """
### On a phone

1. Open the league in the ESPN Fantasy app.
2. Select the **League** tab, then **League Info**.
3. Copy the League ID shown there and paste it below.
4. Set **Most recent season** to the latest season the league played. For an inactive league, use its final active season.

### On a computer

1. Open the league at `fantasy.espn.com`.
2. Copy the digits after `leagueId=` in the address bar. An ESPN invite or league email link contains the same value.
3. Paste that number below and choose the latest season the league played.

### If ESPN denies public access

Here, **Public** uses ESPN's **viewable to public** setting. Your League Manager exposes league pages with this setting; ESPN keeps membership invite-only. The League Manager can enable it on a computer under **League → Settings → Basic Settings → Edit Basic Settings**. Otherwise, switch this importer to **Private** and use the signed-in browser instructions.

[ESPN's League ID guide](https://support.espn.com/hc/en-us/articles/4669614193556-League-ID) · [ESPN's public-view setting guide](https://support.espn.com/hc/en-us/articles/360000088231-Making-a-Private-League-Viewable-to-the-Public)
"""


def _visual_history_payload(league_id: str | None = None) -> dict | None:
    """Return a checked-in history payload when visual tests ask for one.

    Production never sets JSA_VISUAL_LH_FIXTURE, so the live page still fails
    closed offline and still fetches live leagues online. The payload only
    applies when the typed league ID matches fixture_league_id, so other IDs
    still hit the offline message.
    """
    raw = os.environ.get("JSA_VISUAL_LH_FIXTURE", "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or "seasons" not in payload:
        return None
    expected = str(payload.get("fixture_league_id") or "").strip()
    if expected and league_id is not None and str(league_id).strip() != expected:
        return None
    return payload


def _render_league_import_help(provider: str, access: str = "Public") -> None:
    with st.expander("Where to find your league details"):
        st.markdown(_league_import_help_markdown(provider, access))


@st.cache_data(ttl=3600, max_entries=_SLEEPER_GET_CACHE_ENTRIES)
def _sleeper_get(url: str):
    if _OFFLINE:
        return None
    try:
        r = req.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _hydrate_sleeper_user(user_id: str, user_map: dict) -> None:
    """Fill a departed owner's display name via Sleeper's user endpoint."""
    uid = str(user_id or "").strip()
    if not uid or uid in user_map:
        return
    payload = _sleeper_get(f"https://api.sleeper.app/v1/user/{uid}")
    if not isinstance(payload, dict):
        return
    name = str(payload.get("display_name") or payload.get("username") or "").strip()
    if not name:
        return
    meta = payload.get("metadata") or {}
    user_map[uid] = {
        "username": name,
        "team_name": meta.get("team_name") if isinstance(meta, dict) else "",
    }


@st.cache_data(ttl=3600, max_entries=_HISTORY_CACHE_ENTRIES)
def _league_history_chain(start_league_id: str) -> list[dict]:
    """Walk previous_league_id links. Newest season first."""
    current_id = start_league_id.strip()
    seen = set()
    chain: list[dict] = []
    while current_id and current_id not in {"0", ""} and current_id not in seen:
        if len(seen) >= _MAX_HISTORY_SEASONS:
            break
        seen.add(current_id)
        info = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}")
        if not info or not isinstance(info, dict) or not info.get("season"):
            break
        chain.append({
            "league_id": current_id,
            "season": str(info.get("season")),
            "name": info.get("name") or "League",
        })
        previous_id = info.get("previous_league_id")
        current_id = previous_id if previous_id and previous_id != "0" else ""
    return chain


def _league_history_season_count(start_league_id: str) -> int:
    """Count the linked Sleeper seasons before the heavier weekly pulls begin."""
    return len(_league_history_chain(start_league_id))


def _history_load_estimate(season_count: int) -> tuple[int, int]:
    """Return a conservative first-load range calibrated to the public fetch path."""
    seasons = max(1, min(int(season_count or 1), _MAX_HISTORY_SEASONS))
    return max(5, seasons * 2), max(10, seasons * 4)


def _fetch_league_weeks(league_id: str, resource: str) -> dict:
    """Fetch weeks 1-18 for matchups or transactions with bounded concurrency."""
    def _fetch_wk(wk):
        try:
            r = req.get(
                f"https://api.sleeper.app/v1/league/{league_id}/{resource}/{wk}",
                timeout=15,
            )
            r.raise_for_status()
            return wk, r.json()
        except Exception:
            return wk, None

    with _cf.ThreadPoolExecutor(max_workers=_MATCHUP_FETCH_WORKERS) as pool:
        return dict(pool.map(_fetch_wk, range(1, 19)))


@st.cache_data(ttl=86400, max_entries=1)
def _fetch_player_directory() -> dict:
    """Sleeper asks consumers to cache the large NFL player directory."""
    override = _visual_history_payload()
    if override is not None:
        return dict(override.get("player_directory") or {})
    payload = _sleeper_get("https://api.sleeper.app/v1/players/nfl")
    return payload if isinstance(payload, dict) else {}


@st.cache_data(ttl=3600, max_entries=_SEASON_CACHE_ENTRIES)
def _fetch_one_season(league_id: str):
    """Return (season, payload) for one Sleeper league-season, or None."""
    current_id = league_id.strip()
    info = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}")
    if not info or not isinstance(info, dict):
        return None
    yr = info.get("season")
    if not yr:
        return None

    users_raw = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/users") or []
    rosters_raw = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/rosters") or []
    bracket_raw = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/winners_bracket") or []
    losers_raw = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/losers_bracket") or []
    draft_id = str(info.get("draft_id") or "")
    draft_picks = (
        _sleeper_get(f"https://api.sleeper.app/v1/draft/{draft_id}/picks") or []
        if draft_id else []
    )

    user_map = {
        str(u["user_id"]): {
            "username": u.get("display_name") or "—",
            "team_name": (u.get("metadata") or {}).get("team_name") or "",
        }
        for u in users_raw
        if isinstance(u, dict) and u.get("user_id") is not None
    }

    from fantasy import league_intelligence as _intel

    draft_list = draft_picks if isinstance(draft_picks, list) else []
    rosters_list = rosters_raw if isinstance(rosters_raw, list) else []
    need_tx = any(
        isinstance(ro, dict) and not _intel.infer_roster_owner_id(
            ro.get("roster_id"),
            roster_owner_id=ro.get("owner_id"),
            draft_picks=draft_list,
        )
        for ro in rosters_list
    )
    tx_rows = _fetch_season_transactions(current_id) if need_tx else []

    playoff_finish = {}
    champion_rid = None
    runner_up_rid = None

    if bracket_raw and info.get("status") == "complete":
        valid = [m for m in bracket_raw if isinstance(m, dict)]
        max_r = max((m.get("r", 0) for m in valid), default=0)
        for m in valid:
            if m.get("r") != max_r or m.get("w") is None or m.get("l") is None:
                continue
            w, l, p = str(m["w"]), str(m["l"]), m.get("p")
            if p == 1:
                champion_rid = w
                runner_up_rid = l
            if p:
                if w not in playoff_finish or p < playoff_finish[w]:
                    playoff_finish[w] = p
                if l not in playoff_finish or p + 1 < playoff_finish[l]:
                    playoff_finish[l] = p + 1

    standings = []
    for ro in rosters_list:
        if not isinstance(ro, dict):
            continue
        rid = str(ro.get("roster_id", ""))
        owner_id = _intel.infer_roster_owner_id(
            ro.get("roster_id"),
            roster_owner_id=ro.get("owner_id"),
            draft_picks=draft_list,
            transactions=tx_rows,
        )
        if owner_id:
            _hydrate_sleeper_user(owner_id, user_map)
        u = user_map.get(owner_id, {"username": "—", "team_name": ""})
        s = ro.get("settings") or {}
        fpts = s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100
        fpts_ag = s.get("fpts_against", 0) + s.get("fpts_against_decimal", 0) / 100
        standings.append({
            "roster_id": ro.get("roster_id"),
            "owner_id": owner_id,
            "username": u["username"],
            "team_name": u["team_name"],
            "wins": s.get("wins", 0),
            "losses": s.get("losses", 0),
            "fpts": round(fpts, 2),
            "fpts_against": round(fpts_ag, 2),
            "playoff_finish": playoff_finish.get(rid),
        })

    standings.sort(key=lambda x: (x["playoff_finish"] or 99, -x["wins"], -x["fpts"]))

    def _by_rid(rid_str):
        for row in standings:
            if str(row["roster_id"]) == rid_str:
                return row
        return {"username": "?", "team_name": ""}

    champ = _by_rid(champion_rid) if champion_rid else {"username": "?", "team_name": ""}
    ruup = _by_rid(runner_up_rid) if runner_up_rid else {"username": "?", "team_name": ""}

    toilet_champions = []
    toilet_bracket: list[str] = []
    if losers_raw and info.get("status") == "complete":
        seen_names: set[str] = set()
        for rid in _intel.bracket_finals_roster_ids(losers_raw):
            name = str(_by_rid(rid).get("username") or "").strip()
            if name and name not in {"?", "—"} and name not in seen_names:
                seen_names.add(name)
                toilet_bracket.append(name)
        toilet_bracket.sort()
        for rid in _intel.bracket_title_roster_ids(losers_raw):
            row = _by_rid(rid)
            toilet_champions.append({
                "username": row.get("username") or "?",
                "team_name": row.get("team_name", ""),
            })

    _lg_settings = info.get("settings") or {}
    _playoff_start = int(_lg_settings.get("playoff_week_start") or 15)
    _wk_data = _fetch_league_weeks(current_id, "matchups")

    _matchups_season: list = []
    _roster_entries_season: list = []
    for _wk in range(1, 19):
        _wk_raw = _wk_data.get(_wk)
        if not _wk_raw or not isinstance(_wk_raw, list):
            continue
        _grps: dict = {}
        for _entry in _wk_raw:
            if not isinstance(_entry, dict):
                continue
            _mid = _entry.get("matchup_id")
            _roster_entries_season.append({
                "season": yr,
                "week": _wk,
                "roster_id": _entry.get("roster_id"),
                "matchup_id": _mid,
                "players": list(_entry.get("players") or []),
                "starters": list(_entry.get("starters") or []),
                "players_points": dict(_entry.get("players_points") or {}),
            })
            if _mid is None:
                continue
            _grps.setdefault(_mid, []).append(_entry)
        for _mid2, _ents in _grps.items():
            if len(_ents) == 2:
                _ma, _mb = _ents[0], _ents[1]
                _sa = float(_ma.get("points") or 0)
                _sb = float(_mb.get("points") or 0)
                if _sa == 0 and _sb == 0:
                    continue
                _matchups_season.append({
                    "season": yr,
                    "week": _wk,
                    "is_playoff": _wk >= _playoff_start,
                    "rid_a": str(_ma.get("roster_id", "")),
                    "score_a": _sa,
                    "rid_b": str(_mb.get("roster_id", "")),
                    "score_b": _sb,
                })

    payload = {
        "league_id": current_id,
        "draft_id": draft_id,
        "status": info.get("status"),
        "champion": {"username": champ["username"], "team_name": champ.get("team_name", "")},
        "runner_up": {"username": ruup["username"], "team_name": ruup.get("team_name", "")},
        "toilet_champion": (
            toilet_champions[0]
            if toilet_champions else {"username": "?", "team_name": ""}
        ),
        "toilet_champions": toilet_champions,
        "toilet_finalists": toilet_bracket,
        "toilet_bracket": toilet_bracket,
        "standings": standings,
        "matchups": _matchups_season,
        "draft_picks": draft_picks if isinstance(draft_picks, list) else [],
        "roster_entries": _roster_entries_season,
        "league_settings": {
            "total_rosters": info.get("total_rosters"),
            "roster_positions": list(info.get("roster_positions") or []),
            "scoring_settings": dict(info.get("scoring_settings") or {}),
            "waiver_type": _lg_settings.get("waiver_type"),
            "waiver_budget": _lg_settings.get("waiver_budget"),
        },
    }
    return str(yr), payload


@st.cache_data(ttl=3600, max_entries=_SEASON_CACHE_ENTRIES)
def _fetch_season_transactions(league_id: str) -> list:
    """All complete-looking weekly transactions for one Sleeper season."""
    override = _visual_history_payload(league_id)
    if override is not None:
        return list(override.get("transactions") or [])
    weeks = _fetch_league_weeks(league_id.strip(), "transactions")
    rows: list = []
    for week in range(1, 19):
        payload = weeks.get(week)
        if isinstance(payload, list):
            rows.extend(payload)
    return rows


def _fetch_sleeper_history(start_league_id: str, max_seasons: int | None = None) -> dict:
    """Compose the cached chain plus per-season payloads. Used by tests."""
    chain = _league_history_chain(start_league_id)
    if max_seasons is not None:
        chain = chain[:max(1, int(max_seasons))]
    seasons = {}
    league_name = chain[0]["name"] if chain else "League"
    for item in chain:
        fetched = _fetch_one_season(item["league_id"])
        if not fetched:
            continue
        yr, payload = fetched
        seasons[yr] = payload
        if league_name == "League":
            league_name = item.get("name") or league_name
    return {"league_name": league_name or "League", "seasons": seasons}


def _render_load_form(provider: str = "Sleeper", access: str = "Public"):
    with st.form("lh_load_form", border=False):
        is_espn = provider == "ESPN"
        is_yahoo = provider == "Yahoo"
        is_cbs = provider == "CBS"
        needs_season = is_espn or is_yahoo or is_cbs
        league_id_input = st.text_input(
            f"{provider} League ID",
            value="",
            placeholder=(
                "e.g. 48153503" if is_espn else
                "e.g. 123456" if is_yahoo else
                "e.g. cbshelp" if is_cbs else
                "e.g. 1255197436951932928"
            ),
            help=(
                "Copy the leagueId value from your ESPN fantasy league URL."
                if is_espn else
                "Copy the number after /f1/ in your Yahoo fantasy league URL."
                if is_yahoo else
                "Copy the subdomain from https://{ID}.football.cbssports.com."
                if is_cbs else
                "Find it in your Sleeper league URL: sleeper.com/leagues/{ID}/league"
            ),
            key="lh_league_id",
        )
        espn_season = None
        yahoo_season = None
        cbs_season = None
        espn_s2 = ""
        swid = ""
        yahoo_y = ""
        yahoo_t = ""
        cbs_token = ""
        if needs_season:
            season_key = (
                "lh_espn_season" if is_espn else
                "lh_yahoo_season" if is_yahoo else
                "lh_cbs_season"
            )
            season_value = st.number_input(
                "Most recent season",
                min_value=2018,
                max_value=dt.now().year,
                value=dt.now().year,
                step=1,
                key=season_key,
                help=(
                    "ESPN league IDs need a season. Use the season shown in the league URL."
                    if is_espn else
                    "Yahoo league IDs need a season. Use the year in the league URL, such as /2025/f1/123456."
                    if is_yahoo else
                    "CBS league IDs need a season. Use the year shown on the league site."
                ),
            )
            if is_espn:
                espn_season = season_value
            elif is_yahoo:
                yahoo_season = season_value
            else:
                cbs_season = season_value
            if is_cbs:
                cbs_token = st.text_input(
                    "CBS access token",
                    type="password",
                    key="lh_cbs_token",
                    help=(
                        "Copy the Authorization header from a signed-in /api/league "
                        "request, or the var token value from the page source."
                    ),
                )
            elif access == "Private":
                if is_espn:
                    swid = st.text_input(
                        "ESPN SWID cookie",
                        type="password",
                        placeholder="{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}",
                        key="lh_espn_swid",
                        help="Copy the SWID value from fantasy.espn.com in your browser's cookie storage.",
                    )
                    espn_s2 = st.text_input(
                        "ESPN espn_s2 cookie",
                        type="password",
                        key="lh_espn_s2",
                        help="Copy the espn_s2 value from the same signed-in ESPN browser session.",
                    )
                else:
                    yahoo_y = st.text_input(
                        "Yahoo Y cookie",
                        type="password",
                        key="lh_yahoo_y",
                        help="Copy the Y value from football.fantasysports.yahoo.com in your browser's cookie storage.",
                    )
                    yahoo_t = st.text_input(
                        "Yahoo T cookie",
                        type="password",
                        key="lh_yahoo_t",
                        help="Copy the T value from the same signed-in Yahoo browser session.",
                    )
        history_depth = st.segmented_control(
            "History depth",
            ["Last 3 seasons", "All available seasons"],
            default="Last 3 seasons",
            required=True,
            key="lh_history_depth",
            help=(
                "Recent 3 is the faster first view. Private results stay only in this browser session."
                if access == "Private" or is_cbs else
                "Recent 3 is the faster first view. Per-season results stay cached for an hour."
            ),
        )
        load_requested = st.form_submit_button("Load league history", type="primary")
    return (
        league_id_input, espn_season, espn_s2, swid, history_depth, load_requested,
        yahoo_season, yahoo_y, yahoo_t, cbs_season, cbs_token,
    )


def _load_history_with_status(
    league_id: str,
    max_seasons: int | None = None,
) -> tuple[dict, str | None]:
    """Fetch with a visible per-season status panel. Returns (history, error)."""
    with st.status("Finding linked Sleeper seasons…", expanded=True) as status:
        full_chain = _league_history_chain(league_id)
        if not full_chain:
            status.update(
                label="Sleeper did not return a league for that ID.",
                state="error",
                expanded=True,
            )
            return {"league_name": "League", "seasons": {}}, (
                "Sleeper did not return a league for that ID. "
                "Check the number in your league URL."
            )
        chain = (
            full_chain[:max(1, int(max_seasons))]
            if max_seasons is not None else full_chain
        )
        n = len(chain)
        low, high = _history_load_estimate(n)
        years = ", ".join(item["season"] for item in chain)
        season_word = "season" if n == 1 else "seasons"
        if len(chain) < len(full_chain):
            st.write(
                f"Found {len(full_chain)} linked seasons. Loading the newest {n}: {years}."
            )
        else:
            st.write(f"Found {n} {season_word}: {years}.")
        st.write(f"First load usually takes {low} to {high} seconds. Reloads of this ID are instant for an hour.")
        seasons = {}
        league_name = chain[0]["name"]
        for i, item in enumerate(chain, 1):
            yr = item["season"]
            status.update(label=f"Loading {yr} (season {i} of {n})")
            st.write(f"{yr}: standings, draft board, weekly scores")
            fetched = _fetch_one_season(item["league_id"])
            if fetched:
                fetched_year, payload = fetched
                seasons[fetched_year] = payload
        if not seasons:
            status.update(
                label="This league exists, but no season history came back.",
                state="error",
                expanded=True,
            )
            return {"league_name": league_name, "seasons": {}}, (
                "This league exists, but no season history came back. "
                "It may be too new or still empty."
            )
        loaded_word = "season" if len(seasons) == 1 else "seasons"
        status.update(
            label=f"Loaded {len(seasons)} {loaded_word}.",
            state="complete",
            expanded=False,
        )
        return {"league_name": league_name or "League", "seasons": seasons}, None


def _fetch_espn_history(
    league_id: str,
    season: int,
    max_seasons: int | None = None,
) -> dict:
    import espn_league_history as _espn

    return _espn.fetch_history(league_id, season, max_seasons=max_seasons)


def _load_espn_history_with_status(
    league_id: str,
    season: int,
    max_seasons: int | None = None,
    private_credentials: tuple[str, str] | None = None,
) -> tuple[dict, str | None]:
    """Fetch ESPN seasons; credentialed responses remain outside shared caches."""
    import espn_league_history as _espn

    empty = {
        "league_name": "League",
        "seasons": {},
        "player_directory": {},
        "provider": "ESPN",
    }
    is_private = private_credentials is not None
    with st.status("Finding linked ESPN seasons…", expanded=True) as status:
        try:
            if is_private:
                espn_s2, swid = private_credentials
                full_chain = _espn.history_chain_private(
                    league_id, int(season), espn_s2, swid,
                )
            else:
                full_chain = _espn.history_chain(league_id, int(season))
        except _espn.EspnLeagueError as exc:
            status.update(label=str(exc), state="error", expanded=True)
            return empty, str(exc)
        if not full_chain:
            message = "ESPN did not return a league for that ID and season."
            status.update(label=message, state="error", expanded=True)
            return empty, message
        chain = (
            full_chain[:max(1, int(max_seasons))]
            if max_seasons is not None else full_chain
        )
        years = ", ".join(item["season"] for item in chain)
        if len(chain) < len(full_chain):
            st.write(
                f"Found {len(full_chain)} linked seasons. Loading the newest "
                f"{len(chain)}: {years}."
            )
        else:
            st.write(
                f"Found {len(chain)} {'season' if len(chain) == 1 else 'seasons'}: {years}."
            )
        low = max(10, len(chain) * 8)
        high = max(25, len(chain) * 20)
        st.write(
            f"ESPN weekly rosters are a larger pull. First load usually takes {low} to "
            f"{high} seconds; "
            + (
                "private results stay only in this browser session."
                if is_private else
                "reloads are instant for an hour."
            )
        )
        seasons = {}
        player_directory = {}
        errors = []
        for index, item in enumerate(chain, 1):
            year = int(item["season"])
            status.update(label=f"Loading {year} (season {index} of {len(chain)})")
            st.write(f"{year}: standings, draft board, weekly scores and rosters")
            try:
                if is_private:
                    fetched_year, payload, players = _espn.fetch_one_season_private(
                        item["league_id"], year, espn_s2, swid,
                    )
                else:
                    fetched_year, payload, players = _espn.fetch_one_season(
                        item["league_id"], year,
                    )
            except _espn.EspnLeagueError as exc:
                errors.append(f"{year}: {exc}")
                st.write(f"{year} could not be loaded: {exc}")
                continue
            seasons[fetched_year] = payload
            player_directory.update(players)
        if not seasons:
            message = errors[0].split(": ", 1)[-1] if errors else (
                "This ESPN league exists, but no season history came back."
            )
            status.update(label=message, state="error", expanded=True)
            return empty, message
        if errors:
            status.update(
                label=f"Loaded {len(seasons)} seasons; {len(errors)} could not be loaded.",
                state="complete",
                expanded=False,
            )
        else:
            status.update(
                label=f"Loaded {len(seasons)} {'season' if len(seasons) == 1 else 'seasons'}.",
                state="complete",
                expanded=False,
            )
        return {
            "league_name": chain[0]["name"] or "League",
            "seasons": seasons,
            "player_directory": player_directory,
            "provider": "ESPN",
        }, None


def _fetch_yahoo_history(
    league_id: str,
    season: int,
    max_seasons: int | None = None,
    game_key: str | None = None,
) -> dict:
    import yahoo_league_history as _yahoo

    return _yahoo.fetch_history(
        league_id, season, max_seasons=max_seasons, game_key=game_key,
    )


def _load_yahoo_history_with_status(
    league_id: str,
    season: int,
    max_seasons: int | None = None,
    private_credentials: tuple[str, str] | None = None,
    game_key: str | None = None,
) -> tuple[dict, str | None]:
    """Fetch Yahoo seasons; credentialed responses remain outside shared caches."""
    import yahoo_league_history as _yahoo

    empty = {
        "league_name": "League",
        "seasons": {},
        "player_directory": {},
        "provider": "Yahoo",
    }
    is_private = private_credentials is not None
    with st.status("Finding linked Yahoo seasons…", expanded=True) as status:
        try:
            if is_private:
                yahoo_y, yahoo_t = private_credentials
                full_chain = _yahoo.history_chain_private(
                    league_id, int(season), yahoo_y, yahoo_t, game_key,
                )
            else:
                full_chain = _yahoo.history_chain(league_id, int(season), game_key)
        except _yahoo.YahooLeagueError as exc:
            status.update(label=str(exc), state="error", expanded=True)
            return empty, str(exc)
        if not full_chain:
            message = "Yahoo did not return a league for that ID and season."
            status.update(label=message, state="error", expanded=True)
            return empty, message
        chain = (
            full_chain[:max(1, int(max_seasons))]
            if max_seasons is not None else full_chain
        )
        years = ", ".join(item["season"] for item in chain)
        if len(chain) < len(full_chain):
            st.write(
                f"Found {len(full_chain)} linked seasons. Loading the newest "
                f"{len(chain)}: {years}."
            )
        else:
            st.write(
                f"Found {len(chain)} {'season' if len(chain) == 1 else 'seasons'}: {years}."
            )
        low = max(10, len(chain) * 8)
        high = max(25, len(chain) * 20)
        st.write(
            f"Yahoo weekly rosters are a larger pull. First load usually takes {low} to "
            f"{high} seconds; "
            + (
                "private results stay only in this browser session."
                if is_private else
                "reloads are instant for an hour."
            )
        )
        seasons = {}
        player_directory = {}
        errors = []
        for index, item in enumerate(chain, 1):
            year = int(item["season"])
            status.update(label=f"Loading {year} (season {index} of {len(chain)})")
            st.write(f"{year}: standings, draft board, weekly scores and rosters")
            try:
                if is_private:
                    yahoo_y, yahoo_t = private_credentials
                    fetched_year, payload, players = _yahoo.fetch_one_season_private(
                        item["league_id"], year, yahoo_y, yahoo_t, item.get("game_key"),
                    )
                else:
                    fetched_year, payload, players = _yahoo.fetch_one_season(
                        item["league_id"], year, item.get("game_key"),
                    )
            except _yahoo.YahooLeagueError as exc:
                errors.append(f"{year}: {exc}")
                st.write(f"{year} could not be loaded: {exc}")
                continue
            seasons[fetched_year] = payload
            player_directory.update(players)
        if not seasons:
            message = errors[0].split(": ", 1)[-1] if errors else (
                "This Yahoo league exists, but no season history came back."
            )
            status.update(label=message, state="error", expanded=True)
            return empty, message
        if errors:
            status.update(
                label=f"Loaded {len(seasons)} seasons; {len(errors)} could not be loaded.",
                state="complete",
                expanded=False,
            )
        else:
            status.update(
                label=f"Loaded {len(seasons)} {'season' if len(seasons) == 1 else 'seasons'}.",
                state="complete",
                expanded=False,
            )
        return {
            "league_name": chain[0]["name"] or "League",
            "seasons": seasons,
            "player_directory": player_directory,
            "provider": "Yahoo",
        }, None


def _load_cbs_history_with_status(
    league_id: str,
    season: int,
    max_seasons: int | None = None,
    access_token: str = "",
) -> tuple[dict, str | None]:
    """Fetch CBS seasons; credentialed responses remain outside shared caches."""
    import cbs_league_history as _cbs

    empty = {
        "league_name": "League",
        "seasons": {},
        "player_directory": {},
        "provider": "CBS",
    }
    with st.status("Finding linked CBS seasons…", expanded=True) as status:
        try:
            full_chain = _cbs.history_chain_private(
                league_id, int(season), access_token,
            )
        except _cbs.CbsLeagueError as exc:
            status.update(label=str(exc), state="error", expanded=True)
            return empty, str(exc)
        if not full_chain:
            message = "CBS did not return a league for that ID and season."
            status.update(label=message, state="error", expanded=True)
            return empty, message
        chain = (
            full_chain[:max(1, int(max_seasons))]
            if max_seasons is not None else full_chain
        )
        years = ", ".join(item["season"] for item in chain)
        if len(chain) < len(full_chain):
            st.write(
                f"Found {len(full_chain)} linked seasons. Loading the newest "
                f"{len(chain)}: {years}."
            )
        else:
            st.write(
                f"Found {len(chain)} {'season' if len(chain) == 1 else 'seasons'}: {years}."
            )
        low = max(10, len(chain) * 8)
        high = max(25, len(chain) * 20)
        st.write(
            f"CBS weekly rosters are a larger pull. First load usually takes {low} to "
            f"{high} seconds; private results stay only in this browser session."
        )
        seasons = {}
        player_directory = {}
        errors = []
        for index, item in enumerate(chain, 1):
            year = int(item["season"])
            status.update(label=f"Loading {year} (season {index} of {len(chain)})")
            st.write(f"{year}: standings, draft board, weekly scores and rosters")
            try:
                fetched_year, payload, players = _cbs.fetch_one_season_private(
                    item["league_id"], year, access_token,
                )
            except _cbs.CbsLeagueError as exc:
                errors.append(f"{year}: {exc}")
                st.write(f"{year} could not be loaded: {exc}")
                continue
            seasons[fetched_year] = payload
            player_directory.update(players)
        if not seasons:
            message = errors[0].split(": ", 1)[-1] if errors else (
                "This CBS league exists, but no season history came back."
            )
            status.update(label=message, state="error", expanded=True)
            return empty, message
        if errors:
            status.update(
                label=f"Loaded {len(seasons)} seasons; {len(errors)} could not be loaded.",
                state="complete",
                expanded=False,
            )
        else:
            status.update(
                label=f"Loaded {len(seasons)} {'season' if len(seasons) == 1 else 'seasons'}.",
                state="complete",
                expanded=False,
            )
        return {
            "league_name": chain[0]["name"] or "League",
            "seasons": seasons,
            "player_directory": player_directory,
            "provider": "CBS",
        }, None


def render():
    if st.session_state.pop("lh_clear_espn_credentials", False):
        st.session_state.pop("lh_espn_s2", None)
        st.session_state.pop("lh_espn_swid", None)
    if st.session_state.pop("lh_clear_yahoo_credentials", False):
        st.session_state.pop("lh_yahoo_y", None)
        st.session_state.pop("lh_yahoo_t", None)
    if st.session_state.pop("lh_clear_cbs_credentials", False):
        st.session_state.pop("lh_cbs_token", None)

    st.title("Fantasy league history")
    st.caption("Turn a Sleeper, ESPN, Yahoo, or CBS league into a multi-season manager and roster review.")
    if (help_page := nav_registry.PAGES.get("help")) is not None:
        st.page_link(help_page, label="Watch the League History guide", icon=":material/play_circle:",
                     query_params={"help_topic": "Site Guide", "guide": "league-history-guide"})


    _provider_input = st.segmented_control(
        "League platform",
        _LEAGUE_PROVIDERS,
        default="Sleeper",
        required=True,
        key="lh_provider",
        help="Private ESPN, Yahoo, and CBS leagues require signed-in session values from your browser.",
    )
    _access_input = "Public"
    if _provider_input == "ESPN":
        _access_input = st.segmented_control(
            "ESPN league access",
            ("Public", "Private"),
            default="Public",
            required=True,
            key="lh_espn_access",
        )
        if _access_input == "Private":
            st.caption(
                "Private import needs the SWID and espn_s2 values from a signed-in desktop "
                "browser. Treat them like passwords. Do not paste them into chat, and use this "
                "only on a deployment you trust. The importer never logs or shared-caches them "
                "and clears both fields after a successful load."
            )
    elif _provider_input == "Yahoo":
        _access_input = st.segmented_control(
            "Yahoo league access",
            ("Public", "Private"),
            default="Public",
            required=True,
            key="lh_yahoo_access",
        )
        if _access_input == "Private":
            st.caption(
                "Private import needs the Y and T values from a signed-in desktop "
                "browser. Treat them like passwords. Do not paste them into chat, and use this "
                "only on a deployment you trust. The importer never logs or shared-caches them "
                "and clears both fields after a successful load."
            )
    elif _provider_input == "CBS":
        _access_input = "Private"
        st.caption(
            "CBS Commissioner leagues need the signed-in access token from a desktop "
            "browser. Treat it like a password. Do not paste it into chat, and use this "
            "only on a deployment you trust. The importer never logs or shared-caches it "
            "and clears the field after a successful load. CBS has no public-view importer."
        )

    _render_league_import_help(_provider_input, _access_input)

    # A form batches text entry. Without it, every numeric keystroke could start a
    # multi-season public API crawl on the next Streamlit rerun.
    (
        _league_id_input,
        _espn_season_input,
        _espn_s2_input,
        _espn_swid_input,
        _history_depth,
        _load_requested,
        _yahoo_season_input,
        _yahoo_y_input,
        _yahoo_t_input,
        _cbs_season_input,
        _cbs_token_input,
    ) = _render_load_form(_provider_input, _access_input)

    _form_error = None
    _private_credentials = None
    _yahoo_game_key = None
    if _load_requested:
        _submitted_lid = _league_id_input.strip()
        if _provider_input == "Yahoo":
            import yahoo_league_history as _yahoo

            _submitted_lid, _yahoo_game_key, _ = _yahoo.parse_league_ref(
                _submitted_lid
            )
        elif _provider_input == "CBS":
            import cbs_league_history as _cbs

            _submitted_lid = _cbs.parse_league_ref(_submitted_lid)
        _form_error = _league_request_error(
            _provider_input,
            _submitted_lid,
            _espn_season_input,
            _access_input if _provider_input == "ESPN" else "Public",
            _espn_s2_input,
            _espn_swid_input,
            _yahoo_season_input,
            _access_input if _provider_input == "Yahoo" else "Public",
            _yahoo_y_input,
            _yahoo_t_input,
            cbs_season=_cbs_season_input,
            cbs_token=_cbs_token_input,
        )
        if _form_error is None:
            _submitted_limit = 3 if _history_depth == "Last 3 seasons" else None
            st.session_state["lh_loaded_league_id"] = _submitted_lid
            st.session_state["lh_loaded_provider"] = _provider_input
            st.session_state["lh_loaded_espn_season"] = (
                int(_espn_season_input) if _provider_input == "ESPN" else None
            )
            st.session_state["lh_loaded_yahoo_season"] = (
                int(_yahoo_season_input) if _provider_input == "Yahoo" else None
            )
            st.session_state["lh_loaded_cbs_season"] = (
                int(_cbs_season_input) if _provider_input == "CBS" else None
            )
            st.session_state["lh_loaded_yahoo_game_key"] = (
                _yahoo_game_key if _provider_input == "Yahoo" else None
            )
            st.session_state["lh_loaded_espn_access"] = (
                _access_input if _provider_input == "ESPN" else "Public"
            )
            st.session_state["lh_loaded_yahoo_access"] = (
                _access_input if _provider_input == "Yahoo" else "Public"
            )
            st.session_state["lh_loaded_history_limit"] = _submitted_limit
            st.session_state.pop("lh_acq_league_id", None)
            st.session_state.pop("lh_history_ready_for", None)
            st.session_state.pop("lh_private_history_ready_for", None)
            st.session_state.pop("lh_private_history", None)
            if _provider_input == "ESPN" and _access_input == "Private":
                _private_credentials = (_espn_s2_input, _espn_swid_input)
            elif _provider_input == "Yahoo" and _access_input == "Private":
                _private_credentials = (_yahoo_y_input, _yahoo_t_input)
            elif _provider_input == "CBS":
                _private_credentials = (_cbs_token_input,)

    # Keep a successfully loaded result visible while users change page controls or
    # prepare a different ID. Only an explicit, valid Load submits a new public request.
    _lid = st.session_state.get("lh_loaded_league_id", "")
    _provider = st.session_state.get("lh_loaded_provider", "Sleeper")
    _espn_season = st.session_state.get("lh_loaded_espn_season")
    _yahoo_season = st.session_state.get("lh_loaded_yahoo_season")
    _cbs_season = st.session_state.get("lh_loaded_cbs_season")
    _yahoo_game_key = st.session_state.get("lh_loaded_yahoo_game_key")
    _espn_access = st.session_state.get("lh_loaded_espn_access", "Public")
    _yahoo_access = st.session_state.get("lh_loaded_yahoo_access", "Public")
    _history_limit = st.session_state.get("lh_loaded_history_limit", 3)
    _ready_key = "|".join((
        _provider,
        _lid,
        str(_espn_season or _yahoo_season or _cbs_season or ""),
        _espn_access if _provider == "ESPN" else _yahoo_access if _provider == "Yahoo" else "Private" if _provider == "CBS" else "public",
        str(_yahoo_game_key or ""),
        str(_history_limit if _history_limit is not None else "all"),
    ))
    if _form_error:
        st.warning(_form_error)

    if not _lid:
        if not _form_error:
            if _provider_input == "ESPN":
                if _access_input == "Private":
                    st.info(
                        "Enter your ESPN league ID, most recent season, SWID, and espn_s2 "
                        "values, then select Load league history.  \n\n"
                        "Last 3 seasons is the faster default. Private results stay only "
                        "in your current browser session; the credential fields are cleared "
                        "after the import. Find the ID in your ESPN URL as the leagueId value."
                    )
                else:
                    st.info(
                        "Enter your public ESPN league ID and its most recent season, then select "
                        "Load league history.  \n\n"
                        "Last 3 seasons is the faster default. ESPN weekly rosters are a larger "
                        "pull than Sleeper, so the first import can take 10-25 seconds per season; "
                        "the same seasons are instant for an hour.  \n\n"
                        "Find the ID in your ESPN URL as the leagueId value."
                    )
            elif _provider_input == "Yahoo":
                if _access_input == "Private":
                    st.info(
                        "Enter your Yahoo league ID, most recent season, Y cookie, and T cookie "
                        "values, then select Load league history.  \n\n"
                        "Last 3 seasons is the faster default. Private results stay only "
                        "in your current browser session; the credential fields are cleared "
                        "after the import. Find the ID after /f1/ in your Yahoo URL."
                    )
                else:
                    st.info(
                        "Enter your public Yahoo league ID and its most recent season, then select "
                        "Load league history.  \n\n"
                        "Last 3 seasons is the faster default. Yahoo weekly rosters are a larger "
                        "pull than Sleeper, so the first import can take 10-25 seconds per season; "
                        "the same seasons are instant for an hour.  \n\n"
                        "Find the ID after /f1/ in your Yahoo URL."
                    )
            elif _provider_input == "CBS":
                st.info(
                    "Enter your CBS league ID, most recent season, and access token, "
                    "then select Load league history.  \n\n"
                    "Last 3 seasons is the faster default. Private results stay only "
                    "in your current browser session; the token field is cleared after "
                    "the import. Find the ID as the subdomain of "
                    "https://{ID}.football.cbssports.com."
                )
            else:
                st.info(
                    "Enter your Sleeper league ID, then select Load league history.  \n\n"
                    "Last 3 seasons is the faster default; choose All available seasons when you "
                    "need the complete archive. A 3-year league is usually about 6-12 seconds. "
                    "A 10-year league can take about 40. The same seasons are instant for an "
                    "hour after that.  \n\n"
                    "Find the ID in your league URL: sleeper.com/leagues/{ID}/league"
                )
    elif _OFFLINE and _visual_history_payload(_lid) is None:
        st.info(
            f"League history needs a live connection to {_provider} and is unavailable offline."
        )
    else:
        _visual_override = _visual_history_payload(_lid)
        if _visual_override is not None:
            _is_private_espn = False
            _is_private_yahoo = False
            _is_private_cbs = False
            _is_private_import = False
            _private_credentials = None
            _just_loaded = True
            _lh = dict(_visual_override)
            _lh.setdefault("provider", _provider)
            _load_error = None if _lh.get("seasons") else (
                f"This {_provider} league exists, but no season history came back. "
                "It may be too new or still empty."
            )
        else:
            _is_private_espn = _provider == "ESPN" and _espn_access == "Private"
            _is_private_yahoo = _provider == "Yahoo" and _yahoo_access == "Private"
            _is_private_cbs = _provider == "CBS"
            _is_private_import = _is_private_espn or _is_private_yahoo or _is_private_cbs
            _just_loaded = False
            if (
                _is_private_import
                and st.session_state.get("lh_private_history_ready_for") == _ready_key
            ):
                _lh = st.session_state.get("lh_private_history") or {
                    "league_name": "League", "seasons": {}, "provider": _provider,
                }
                _load_error = None if _lh.get("seasons") else (
                    f"Private {_provider} history is no longer in this browser session. "
                    "Select Load league history again."
                )
            elif _is_private_import:
                if _private_credentials is None:
                    _lh = {"league_name": "League", "seasons": {}, "provider": _provider}
                    _credential_noun = (
                        "access token" if _is_private_cbs else "cookie values"
                    )
                    _load_error = (
                        f"Re-enter the {_provider} {_credential_noun} and select Load league history."
                    )
                elif _is_private_espn:
                    _lh, _load_error = _load_espn_history_with_status(
                        _lid,
                        int(_espn_season),
                        max_seasons=_history_limit,
                        private_credentials=_private_credentials,
                    )
                    _just_loaded = True
                elif _is_private_yahoo:
                    _lh, _load_error = _load_yahoo_history_with_status(
                        _lid,
                        int(_yahoo_season),
                        max_seasons=_history_limit,
                        private_credentials=_private_credentials,
                        game_key=_yahoo_game_key,
                    )
                    _just_loaded = True
                else:
                    _lh, _load_error = _load_cbs_history_with_status(
                        _lid,
                        int(_cbs_season),
                        max_seasons=_history_limit,
                        access_token=_private_credentials[0],
                    )
                    _just_loaded = True
            elif st.session_state.get("lh_history_ready_for") == _ready_key:
                if _provider == "ESPN":
                    _lh = _fetch_espn_history(
                        _lid,
                        int(_espn_season),
                        max_seasons=_history_limit,
                    )
                elif _provider == "Yahoo":
                    _lh = _fetch_yahoo_history(
                        _lid,
                        int(_yahoo_season),
                        max_seasons=_history_limit,
                        game_key=_yahoo_game_key,
                    )
                else:
                    _lh = _fetch_sleeper_history(_lid, max_seasons=_history_limit)
                    _lh["provider"] = "Sleeper"
                _load_error = None if _lh["seasons"] else (
                    f"This {_provider} league exists, but no season history came back. "
                    "It may be too new or still empty."
                )
            else:
                if _provider == "ESPN":
                    _lh, _load_error = _load_espn_history_with_status(
                        _lid,
                        int(_espn_season),
                        max_seasons=_history_limit,
                    )
                elif _provider == "Yahoo":
                    _lh, _load_error = _load_yahoo_history_with_status(
                        _lid,
                        int(_yahoo_season),
                        max_seasons=_history_limit,
                        game_key=_yahoo_game_key,
                    )
                else:
                    _lh, _load_error = _load_history_with_status(
                        _lid,
                        max_seasons=_history_limit,
                    )
                    _lh["provider"] = "Sleeper"
                _just_loaded = True

        if _just_loaded and _load_error is None and _lh["seasons"]:
            if _is_private_import:
                st.session_state["lh_private_history"] = _lh
                st.session_state["lh_private_history_ready_for"] = _ready_key
            else:
                st.session_state["lh_history_ready_for"] = _ready_key
            send_ga_event(
                "league_history_loaded",
                {
                    "provider": _provider.lower(),
                    "access": (
                        _espn_access.lower() if _provider == "ESPN"
                        else _yahoo_access.lower() if _provider == "Yahoo"
                        else "private" if _provider == "CBS"
                        else "public"
                    ),
                    "season_count": len(_lh["seasons"]),
                    "history_depth": "recent_3" if _history_limit else "all",
                },
            )
            if _is_private_espn:
                st.session_state["lh_clear_espn_credentials"] = True
                st.rerun()
            if _is_private_yahoo:
                st.session_state["lh_clear_yahoo_credentials"] = True
                st.rerun()
            if _is_private_cbs:
                st.session_state["lh_clear_cbs_credentials"] = True
                st.rerun()

        if _is_private_import and _load_error and _private_credentials is not None:
            for _state_key in (
                "lh_loaded_league_id",
                "lh_loaded_provider",
                "lh_loaded_espn_season",
                "lh_loaded_espn_access",
                "lh_loaded_yahoo_season",
                "lh_loaded_yahoo_access",
                "lh_loaded_yahoo_game_key",
                "lh_loaded_cbs_season",
                "lh_loaded_history_limit",
            ):
                st.session_state.pop(_state_key, None)

        if _load_error:
            st.error(_load_error)
        elif not _lh["seasons"]:
            st.error(
                f"This {_provider} league exists, but no season history came back. "
                "It may be too new or still empty."
            )
        else:
            st.header(_lh["league_name"])
            st.caption(
                f"Loaded {len(_lh['seasons'])} "
                f"{'season' if len(_lh['seasons']) == 1 else 'seasons'}. "
                + (
                    "Stored only in this browser session."
                    if _is_private_import else
                    "Cached for an hour."
                )
            )

            # Season filter
            _seasons_list = sorted(_lh["seasons"].keys())
            _season_filter = st.selectbox(
                "Season",
                ["All Time"] + _seasons_list,
                key="lh_season_filter",
            )

            # Build cross-season helpers
            from fantasy import league_intelligence as _league_intel

            _identity_names = _league_intel.manager_identity_map(_lh["seasons"])
            _identity_labels = _league_intel.manager_display_labels(_identity_names)
            _rid_to_user: dict = {}
            _rid_to_owner: dict = {}
            for _yr0, _sd0 in _lh["seasons"].items():
                for _row0 in _sd0["standings"]:
                    _rid_to_user[(_yr0, str(_row0["roster_id"]))] = _row0["username"]
                    _owner0 = str(_row0.get("owner_id") or "").strip()
                    if _owner0:
                        _rid_to_owner[(_yr0, str(_row0["roster_id"]))] = _owner0

            _all_matchups = [
                _m for _sd0 in _lh["seasons"].values()
                for _m in _sd0.get("matchups", [])
            ]

            def _guser(_yr_g, _rid_g):
                return _rid_to_user.get((_yr_g, _rid_g), "?")

            def _gowner(_yr_g, _rid_g):
                return _rid_to_owner.get((_yr_g, _rid_g), "")

            # Expand matchups into per-player game records (full, unfiltered)
            _game_records = []
            _stable_h2h_records = []
            for _m0 in _all_matchups:
                _ua0 = _guser(_m0["season"], _m0["rid_a"])
                _ub0 = _guser(_m0["season"], _m0["rid_b"])
                if "?" in (_ua0, _ub0):
                    continue
                _sa0, _sb0 = _m0["score_a"], _m0["score_b"]
                _game_records += [
                    {"season": _m0["season"], "week": _m0["week"],
                     "is_playoff": _m0["is_playoff"],
                     "username": _ua0, "score": _sa0, "won": _sa0 > _sb0,
                     "opp": _ub0, "opp_score": _sb0},
                    {"season": _m0["season"], "week": _m0["week"],
                     "is_playoff": _m0["is_playoff"],
                     "username": _ub0, "score": _sb0, "won": _sb0 > _sa0,
                     "opp": _ua0, "opp_score": _sa0},
                ]
                _oa0 = _gowner(_m0["season"], _m0["rid_a"])
                _ob0 = _gowner(_m0["season"], _m0["rid_b"])
                _la0 = _identity_labels.get(_oa0)
                _lb0 = _identity_labels.get(_ob0)
                if _oa0 and _ob0 and _la0 and _lb0 and _oa0 != _ob0:
                    _stable_h2h_records += [
                        {"season": _m0["season"], "week": _m0["week"],
                         "is_playoff": _m0["is_playoff"],
                         "username": _la0, "score": _sa0, "won": _sa0 > _sb0,
                         "opp": _lb0, "opp_score": _sb0},
                        {"season": _m0["season"], "week": _m0["week"],
                         "is_playoff": _m0["is_playoff"],
                         "username": _lb0, "score": _sb0, "won": _sb0 > _sa0,
                         "opp": _la0, "opp_score": _sa0},
                    ]

            _latest_season_key = max(
                _lh["seasons"],
                key=lambda value: (
                    pd.to_numeric(value, errors="coerce")
                    if pd.notna(pd.to_numeric(value, errors="coerce")) else -1
                ),
            )
            _active_rivalry_managers = []
            for _standing0 in _lh["seasons"][_latest_season_key].get("standings", []):
                _active_owner0 = str(_standing0.get("owner_id") or "").strip()
                _active_label0 = _identity_labels.get(_active_owner0)
                if _active_label0 and _active_label0 not in _active_rivalry_managers:
                    _active_rivalry_managers.append(_active_label0)
            _active_rivalry_managers.sort()

            # Apply season filter
            if _season_filter == "All Time":
                _filt_records  = _game_records
                _filt_matchups = _all_matchups
                _filt_seasons  = _lh["seasons"]
            else:
                _filt_records  = [r for r in _game_records  if r["season"] == _season_filter]
                _filt_matchups = [m for m in _all_matchups  if m["season"] == _season_filter]
                _filt_seasons  = {k: v for k, v in _lh["seasons"].items() if k == _season_filter}

            _all_managers = sorted(set(r["username"] for r in _game_records))

            # Compute manager list once, before sub-tabs (used in both C and D)
            _h2h_managers = sorted(set(r["username"] for r in _filt_records)) if _season_filter != "All Time" else _all_managers

            # Sub-tabs
            _lhG, _lhA, _lhB, _lhC, _lhD, _lhE = st.tabs(
                _LEAGUE_HISTORY_TABS
            )

            # ── Sub-tab A: All-Time Leaderboard ────────────────────────────────
            with _lhA:
                import plotly.graph_objects as go

                from fantasy import league_intelligence as _league_intel

                _rec_label = _season_filter if _season_filter != "All Time" else "All-Time"
                st.subheader(f"{_rec_label} Leaderboard")
                st.caption(
                    "Regular-season record plus weekly scoring adjusted to the league's "
                    "own scoring environment. Bubble size represents seasons played."
                )

                _leader_df = _league_intel.manager_leaderboard_frame(
                    _filt_seasons, _filt_records
                )
                if _leader_df.empty:
                    st.info("No manager records are available for this selection yet.")
                else:
                    _played = _leader_df[_leader_df["win_pct"].notna()].copy()
                    _scored = _leader_df[_leader_df["avg_above_league"].notna()].copy()
                    _eligible = _played
                    if _season_filter == "All Time":
                        _established = _played[_played["seasons"].ge(2)]
                        if not _established.empty:
                            _eligible = _established

                    _title_names, _title_n = _league_intel.tied_leaders(
                        _leader_df, "titles", min_value=1,
                    )
                    _win_names, _win_n = _league_intel.tied_leaders(_eligible, "win_pct")
                    _point_names, _point_n = _league_intel.tied_leaders(
                        _leader_df, "total_points",
                    )
                    _final_names, _final_n = _league_intel.tied_leaders(
                        _leader_df, "finals", min_value=1,
                    )
                    _streak_names, _streak_n = _league_intel.tied_leaders(
                        _leader_df, "active_playoff_streak", min_value=1,
                    )
                    _toilet_names, _toilet_n = _league_intel.tied_leaders(
                        _leader_df, "toilet_titles", min_value=1,
                    )
                    _toilet_app_names, _toilet_app_n = _league_intel.tied_leaders(
                        _leader_df, "toilet_appearances", min_value=1,
                    )
                    _low_pool = _leader_df[_leader_df["avg_score"].notna()].copy()
                    if _season_filter == "All Time":
                        _low_pool = _low_pool[_low_pool["seasons"].gt(2)]
                    _low_names, _low_n = _league_intel.tied_leaders(
                        _low_pool, "avg_score", ascending=True,
                    )
                    _adj_names, _adj_n = _league_intel.tied_leaders(
                        _scored, "avg_above_league",
                    )

                    _title_delta = None
                    if _title_names:
                        _title_delta = (
                            f"{int(_title_n)} " + ("championship" if int(_title_n) == 1 else "championships")
                            + (" each" if len(_title_names) > 1 else "")
                        )
                    _win_delta = None
                    if _win_names and _win_n is not None:
                        if len(_win_names) == 1:
                            _win_row = _eligible[_eligible["manager"].eq(_win_names[0])].iloc[0]
                            _win_delta = (
                                f"{_win_n:.1f}% · "
                                f"{int(_win_row['wins'])}-{int(_win_row['losses'])}"
                            )
                        else:
                            _win_delta = f"{_win_n:.1f}% each"
                    _point_delta = None
                    if _point_names and _point_n is not None:
                        _point_delta = (
                            f"{_point_n:,.1f} pts"
                            + (" each" if len(_point_names) > 1 else "")
                        )
                    _final_delta = None
                    if _final_names:
                        _final_n_int = int(_final_n)
                        _final_word = "appearance" if _final_n_int == 1 else "appearances"
                        _final_delta = (
                            f"{_final_n_int} {_final_word}"
                            + (" each" if len(_final_names) > 1 else "")
                        )
                    _streak_delta = None
                    if _streak_names:
                        _streak_n_int = int(_streak_n)
                        _streak_word = "season" if _streak_n_int == 1 else "seasons"
                        _streak_delta = (
                            f"{_streak_n_int} {_streak_word}"
                            + (" each" if len(_streak_names) > 1 else "")
                        )
                    _toilet_delta = None
                    if _toilet_names:
                        _toilet_n_int = int(_toilet_n)
                        _toilet_word = (
                            "last-place finish" if _toilet_n_int == 1 else "last-place finishes"
                        )
                        _toilet_delta = (
                            f"{_toilet_n_int} {_toilet_word}"
                            + (" each" if len(_toilet_names) > 1 else "")
                        )
                    _toilet_app_delta = None
                    if _toilet_app_names:
                        _toilet_app_n_int = int(_toilet_app_n)
                        _toilet_app_word = (
                            "appearance" if _toilet_app_n_int == 1 else "appearances"
                        )
                        _toilet_app_delta = (
                            f"{_toilet_app_n_int} {_toilet_app_word}"
                            + (" each" if len(_toilet_app_names) > 1 else "")
                        )
                    _low_delta = None
                    if _low_names and _low_n is not None:
                        _low_delta = (
                            f"{_low_n:.2f} ppg"
                            + (" each" if len(_low_names) > 1 else "")
                        )

                    _cards = [
                        ("Most Titles", _title_names, _title_delta,
                         "No champion yet", "0 championships"),
                        ("Most Finals Appearances", _final_names, _final_delta,
                         "No finals yet", "0 championship games"),
                        ("Longest Active Playoff Streak", _streak_names, _streak_delta,
                         "No active streak", "0 seasons"),
                        ("Best Win %", _win_names, _win_delta,
                         "No games yet", None),
                        ("Most Points", _point_names, _point_delta,
                         "No scores yet", None),
                         ("Most Toilet Bowl Titles", _toilet_names, _toilet_delta,
                         "No toilet champ yet", "0 last-place finishes"),
                        ("Most Toilet Bracket Finals Appearances", _toilet_app_names,
                         _toilet_app_delta, "No consolation finals", "0 toilet-bowl games"),
                        ("Lowest Scoring Team", _low_names, _low_delta,
                         (
                             "—"
                             if _season_filter == "All Time" else "No scores yet"
                         ),
                         ("Needs 3+ seasons" if _season_filter == "All Time" else None)),
                    ]
                    with st.container(key="jsa-lh-leaderboard-cards"):
                        for _row in (_cards[:4], _cards[4:]):
                            _metric_cols = st.columns(4)
                            for _col, (_label, _names, _delta, _empty, _empty_delta) in zip(
                                _metric_cols, _row,
                            ):
                                with _col:
                                    _leaderboard_metric(
                                        _label, _names, _delta,
                                        empty_value=_empty, empty_delta=_empty_delta,
                                        flip_at=3 if _label in _LEADERBOARD_COUNT_CARDS else None,
                                    )
                    _caption_md = _league_intel.n_way_tie_bullets((
                        ("Most Titles", _title_names),
                        ("Most Finals Appearances", _final_names),
                        ("Longest Active Playoff Streak", _streak_names),
                        ("Most Toilet Bowl Titles", _toilet_names),
                        ("Most Toilet Bracket Finals Appearances", _toilet_app_names),
                    ))
                    if _caption_md:
                        with st.container(key="jsa-lh-leaderboard-ties"):
                            st.markdown(_caption_md)
                    elif any(len(_names) > 1 for _names in (
                        _title_names, _win_names, _point_names,
                        _final_names, _streak_names,
                        _toilet_names, _toilet_app_names, _low_names,
                    )):
                        st.caption("Tied leaders share a card.")

                    if not _scored.empty:
                        _bubble = _scored[_scored["win_pct"].notna()].copy()
                        _fig_map = go.Figure()
                        for _label, _color, _group in (
                            ("Title", "#fbbf24", _bubble[_bubble["titles"].gt(0)]),
                            ("No title", "#38bdf8", _bubble[_bubble["titles"].eq(0)]),
                        ):
                            if _group.empty:
                                continue
                            _fig_map.add_trace(go.Scatter(
                                x=_group["win_pct"],
                                y=_group["avg_above_league"],
                                text=_group["manager"],
                                name=_label,
                                customdata=_group[[
                                    "titles", "seasons", "wins", "losses", "avg_score",
                                ]],
                                mode="markers+text",
                                textposition="top center",
                                marker={
                                    "size": 15 + _group["seasons"].astype(float) * 5,
                                    "color": _color,
                                    "line": {"color": "rgba(255,255,255,0.75)", "width": 1},
                                    "opacity": 0.9,
                                },
                                hovertemplate=(
                                    "<b>%{text}</b><br>Win rate: %{x:.1f}%<br>"
                                    "Points vs league: %{y:+.2f}/week<br>Avg score: %{customdata[4]:.2f}<br>"
                                    "Record: %{customdata[2]}-%{customdata[3]}<br>"
                                    "Seasons: %{customdata[1]}<br>Titles: %{customdata[0]}<extra></extra>"
                                ),
                            ))
                        _x_min = max(0, float(_bubble["win_pct"].min()) - 8)
                        _x_max = min(100, float(_bubble["win_pct"].max()) + 8)
                        if _x_max - _x_min < 16:
                            _x_mid = (_x_min + _x_max) / 2
                            _x_min, _x_max = max(0, _x_mid - 8), min(100, _x_mid + 8)
                        _y_span = max(2.0, float(_bubble["avg_above_league"].abs().max()) + 2)
                        _fig_map.add_vline(x=50, line_dash="dot", line_color="#94a3b8")
                        _fig_map.add_hline(y=0, line_dash="dot", line_color="#94a3b8")
                        _fig_map.update_layout(
                            title="Win Rate vs Scoring Performance",
                            height=500,
                            template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(15,23,42,0.36)",
                            margin={"l": 55, "r": 45, "t": 70, "b": 70},
                            legend={
                                "orientation": "h",
                                "yanchor": "top",
                                "y": -0.18,
                                "x": 0,
                                "title": "",
                            },
                            xaxis={
                                "title": "Regular-Season Win Rate",
                                "ticksuffix": "%",
                                "range": [_x_min, _x_max],
                                "gridcolor": "rgba(148,163,184,0.16)",
                            },
                            yaxis={
                                "title": "Avg Points Above League / Week",
                                "range": [-_y_span, _y_span],
                                "gridcolor": "rgba(148,163,184,0.16)",
                                "zeroline": False,
                            },
                        )
                        page_common.plotly_labeled_scatter(_fig_map, slug="leaderboard-map")

                        def _names(_frame):
                            return ", ".join(_frame.sort_values(
                                "avg_above_league", ascending=False
                            )["manager"].tolist())

                        _upper_right = _bubble[
                            _bubble["win_pct"].ge(50) & _bubble["avg_above_league"].ge(0)
                        ]
                        _upper_left = _bubble[
                            _bubble["win_pct"].lt(50) & _bubble["avg_above_league"].ge(0)
                        ]
                        _lower_right = _bubble[
                            _bubble["win_pct"].ge(50) & _bubble["avg_above_league"].lt(0)
                        ]
                        _map_takeaways = []
                        if not _upper_right.empty:
                            _map_takeaways.append(
                                f"**{_names(_upper_right)}** paired above-average scoring with a winning "
                                "record—the strongest evidence of repeatable roster quality."
                            )
                        if not _upper_left.empty:
                            _map_takeaways.append(
                                f"**{_names(_upper_left)}** scored above the league but won fewer than half "
                                "their games, suggesting matchup timing cost them wins more than weak scoring did."
                            )
                        if not _lower_right.empty:
                            _map_takeaways.append(
                                f"**{_names(_lower_right)}** won despite below-average scoring; that record may "
                                "be harder to repeat without stronger weekly production."
                            )
                        if _adj_names and _adj_n is not None:
                            _season_equiv = float(_adj_n) * 14
                            _score_label = _league_intel.format_tied_names(_adj_names)
                            _lead_verb = "lead" if len(_adj_names) > 1 else "leads"
                            _map_takeaways.append(
                                f"**{_score_label}** {_lead_verb} adjusted scoring at "
                                f"{_adj_n:+.2f} points per week, roughly "
                                f"{_season_equiv:+.1f} points over a 14-game regular season versus an average "
                                "team in the same weeks."
                            )
                        st.markdown(" **What it means:** " + " ".join(_map_takeaways))
                    else:
                        st.info("No completed regular-season scores are available for this selection yet.")

                    if not _played.empty:
                        _ranked = _played.sort_values("win_pct", ascending=True).copy()
                        _rank_text = [
                            f'{pct:.1f}%  ' + (f'🏆 × {int(titles)}' if titles else "")
                            for pct, titles in zip(_ranked["win_pct"], _ranked["titles"])
                        ]
                        _fig_rank = go.Figure(go.Bar(
                            x=_ranked["win_pct"],
                            y=_ranked["manager"],
                            orientation="h",
                            text=_rank_text,
                            textposition="outside",
                            cliponaxis=False,
                            marker={
                                "color": [
                                    "#fbbf24" if titles else "#38bdf8"
                                    for titles in _ranked["titles"]
                                ],
                                "line": {"color": "rgba(255,255,255,0.45)", "width": 1},
                            },
                            customdata=_ranked[["wins", "losses", "seasons", "titles"]],
                            hovertemplate=(
                                "<b>%{y}</b><br>Win rate: %{x:.1f}%<br>"
                                "Record: %{customdata[0]}-%{customdata[1]}<br>"
                                "Seasons: %{customdata[2]}<br>Titles: %{customdata[3]}<extra></extra>"
                            ),
                        ))
                        _fig_rank.add_vline(x=50, line_dash="dot", line_color="#94a3b8")
                        _fig_rank.update_layout(
                            title="Regular-Season Win Rate Ranking",
                            height=max(380, 42 * len(_ranked) + 105),
                            template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(15,23,42,0.36)",
                            margin={"l": 25, "r": 95, "t": 70, "b": 50},
                            xaxis={
                                "title": "Win Rate",
                                "range": [0, 100],
                                "ticksuffix": "%",
                                "gridcolor": "rgba(148,163,184,0.16)",
                            },
                            yaxis={"title": "", "automargin": True},
                            showlegend=False,
                        )
                        _lh_plotly(_fig_rank)

                        _rank_desc = _played.sort_values("win_pct", ascending=False).reset_index(drop=True)
                        _rank_leader = _rank_desc.iloc[0]
                        _runner_gap = (
                            float(_rank_leader["win_pct"] - _rank_desc.iloc[1]["win_pct"])
                            if len(_rank_desc) > 1 else 0.0
                        )
                        _sample_note = (
                            f" Their rate covers only {int(_rank_leader['seasons'])} season, so treat it as "
                            "an early lead rather than an established edge."
                            if int(_rank_leader["seasons"]) == 1 and _season_filter == "All Time"
                            else ""
                        )
                        st.markdown(
                            f" **What it means:** **{_rank_leader['manager']}** has the best raw win rate at "
                            f"{_rank_leader['win_pct']:.1f}%, {_runner_gap:.1f} percentage points ahead of second."
                            f"{_sample_note} The 50% line separates managers who have won more often than they lost."
                        )

                    _details = _leader_df.copy()
                    _details["Record"] = (
                        _details["wins"].astype(int).astype(str)
                        + "-" + _details["losses"].astype(int).astype(str)
                    )
                    _details["Best Finish"] = _details["best_finish"].apply(
                        lambda value: str(int(value)) if pd.notna(value) else "DNQ"
                    )
                    _details = _details.rename(columns={
                        "manager": "Manager",
                        "titles": "Titles",
                        "finals": "Finals",
                        "active_playoff_streak": "Playoff Streak",
                        "seasons": "Seasons",
                        "win_pct": "Win %",
                        "total_points": "Total Points",
                        "avg_score": "Avg Weekly Score",
                        "avg_above_league": "Pts Above League Avg",
                    })[[
                        "Manager", "Titles", "Finals", "Playoff Streak", "Seasons",
                        "Record", "Win %", "Total Points", "Avg Weekly Score",
                        "Pts Above League Avg", "Best Finish",
                    ]].sort_values(["Titles", "Win %"], ascending=[False, False])
                    with st.expander("View complete manager records"):
                        dataframe_phone_desktop(
                            _details,
                            _details[[
                                c for c in (
                                    "Manager", "Titles", "Record", "Win %", "Best Finish",
                                ) if c in _details.columns
                            ]],
                            slug="lh-leaderboard-records",
                            width="stretch",
                            hide_index=True,
                            column_config={
                                "Titles": st.column_config.NumberColumn(
                                    "Titles", help="Championship wins"
                                ),
                                "Finals": st.column_config.NumberColumn(
                                    "Finals", help="Championship appearances"
                                ),
                                "Playoff Streak": st.column_config.NumberColumn(
                                    "Playoff Streak",
                                    help="Consecutive playoff seasons through the latest completed postseason in this window.",
                                ),
                                "Total Points": st.column_config.NumberColumn(
                                    "Total Points", format="%.1f",
                                    help="Sum of regular-season weekly scores in this window. Playoffs are excluded.",
                                ),
                                "Win %": st.column_config.NumberColumn("Win %", format="%.1f%%"),
                                "Avg Weekly Score": st.column_config.NumberColumn(
                                    "Avg Weekly Score", format="%.2f"
                                ),
                                "Pts Above League Avg": st.column_config.NumberColumn(
                                    "Pts Above League Avg", format="%+.2f",
                                    help="Average weekly score minus that same league-week's average",
                                ),
                            },
                        )

            # ── Sub-tab B: Hall of Fame / Shame ───────────────────────────────
            with _lhB:
                import plotly.graph_objects as go

                from fantasy import league_intelligence as _league_intel

                _hof_scope = _season_filter if _season_filter != "All Time" else "all seasons"
                st.subheader("League Record Book")
                st.caption(
                    f"The best, worst, closest, and strangest games from {_hof_scope}, "
                    "including playoffs. Scores of 5 points or fewer are treated as incomplete."
                )

                if not _filt_records:
                    st.info("No weekly matchup data available.")
                else:
                    _played_recs = [
                        r for r in _filt_records
                        if r["score"] > 5 and r["opp_score"] > 5
                    ]
                    _best_score  = max(_played_recs, key=lambda r: r["score"]) if _played_recs else None
                    _worst_score = min(_played_recs, key=lambda r: r["score"]) if _played_recs else None
                    _losses_recs = [r for r in _played_recs if r["score"] < r["opp_score"]]
                    _best_loss   = max(_losses_recs, key=lambda r: r["score"]) if _losses_recs else None
                    _matchup_df = _league_intel.matchup_record_frame(_filt_records)
                    if _matchup_df.empty or not _played_recs:
                        st.info("No completed matchup scores are available for this selection.")
                    else:
                        _blowout = _matchup_df.loc[_matchup_df["margin"].idxmax()].to_dict()
                        _closest = _matchup_df.loc[_matchup_df["margin"].idxmin()].to_dict()
                        _hi_combined = _matchup_df.loc[
                            _matchup_df["combined"].idxmax()
                        ].to_dict()
                        _lo_combined = _matchup_df.loc[
                            _matchup_df["combined"].idxmin()
                        ].to_dict()
                        _luck_pool = _matchup_df[
                            _matchup_df["all_play_win_pct"].notna()
                        ].sort_values(
                            ["all_play_win_pct", "winner_score"], ascending=[True, True]
                        )
                        _luck_win = _luck_pool.iloc[0].to_dict() if not _luck_pool.empty else None

                        def _matchup_text(record):
                            if record.get("is_tie"):
                                return f"{record['team_a']} tied {record['team_b']}"
                            return f"{record['winner']} def. {record['loser']}"

                        _hof_cards = [
                            (
                                "🏆 Highest Score",
                                f"{_best_score['score']:.2f} pts",
                                _league_intel.hall_of_fame_delta(_best_score),
                            ),
                            (
                                "😤 Most Painful Loss",
                                f"{_best_loss['score']:.2f} pts" if _best_loss else "No losses",
                                _league_intel.hall_of_fame_delta(_best_loss),
                            ),
                            (
                                "💥 Biggest Blowout",
                                f"{_blowout['margin']:.2f} pts",
                                _league_intel.hall_of_fame_delta(_blowout),
                            ),
                            (
                                "🤝 Closest Game",
                                f"{_closest['margin']:.2f} pts",
                                _league_intel.hall_of_fame_delta(_closest),
                            ),
                            (
                                "💀 Lowest Score",
                                f"{_worst_score['score']:.2f} pts",
                                _league_intel.hall_of_fame_delta(_worst_score),
                            ),
                            (
                                "🍀 Luckiest Win (All-Play)",
                                (
                                    f"{_luck_win['winner_score']:.2f} pts"
                                    if _luck_win else "Unavailable"
                                ),
                                _league_intel.hall_of_fame_delta(_luck_win),
                            ),
                            (
                                "🔥 Highest-Scoring Game",
                                f"{_hi_combined['combined']:.2f} pts",
                                _league_intel.hall_of_fame_delta(_hi_combined),
                            ),
                            (
                                "🧊 Lowest-Scoring Game",
                                f"{_lo_combined['combined']:.2f} pts",
                                _league_intel.hall_of_fame_delta(_lo_combined),
                            ),
                        ]
                        with st.container(key="jsa-lh-hof-cards"):
                            for _row in (_hof_cards[:4], _hof_cards[4:]):
                                _cols = st.columns(4)
                                for _col, (_label, _value, _delta) in zip(_cols, _row):
                                    with _col:
                                        _hof_metric(_label, _value, _delta)
                        _era_caption = _league_intel.hall_of_fame_era_caption(
                            _best_score, _played_recs,
                        )
                        if _era_caption:
                            st.caption(_era_caption)
                        st.caption(
                            "All-play luck compares the winner's score with every other team in that same "
                            "league-week. A winner that would have beaten very few teams received the most "
                            "favorable matchup timing."
                        )

                        _matchup_df = _matchup_df.copy()
                        _matchup_df["matchup_label"] = _matchup_df.apply(
                            _matchup_text, axis=1
                        )
                        _fig_chaos = go.Figure()
                        _season_colors = [
                            "#38bdf8", "#a78bfa", "#34d399", "#fb7185",
                            "#fbbf24", "#22d3ee", "#f472b6", "#a3e635",
                        ]
                        for _color_i, (_season, _season_games) in enumerate(
                            _matchup_df.groupby("season", sort=True)
                        ):
                            _fig_chaos.add_trace(go.Scatter(
                                x=_season_games["combined"],
                                y=_season_games["margin"],
                                name=str(_season),
                                mode="markers",
                                marker={
                                    "size": 10,
                                    "color": _season_colors[_color_i % len(_season_colors)],
                                    "opacity": 0.72,
                                    "line": {"color": "rgba(255,255,255,0.38)", "width": 1},
                                },
                                customdata=_season_games[[
                                    "matchup_label", "winner_score", "loser_score", "week",
                                ]],
                                hovertemplate=(
                                    "<b>%{customdata[0]}</b><br>Score: %{customdata[1]:.2f}–"
                                    "%{customdata[2]:.2f}<br>Week %{customdata[3]}<br>"
                                    "Combined: %{x:.2f}<br>Margin: %{y:.2f}<extra>%{fullData.name}</extra>"
                                ),
                            ))

                        _highlight_labels = _league_intel.scorecard_highlight_labels(
                            _matchup_df,
                            [
                                (_best_score, "Highest Score"),
                                (_best_loss, "Most Painful Loss"),
                                (_blowout, "Biggest Blowout"),
                                (_closest, "Closest Game"),
                                (_worst_score, "Lowest Score"),
                                (_luck_win, "Luckiest Win"),
                                (_hi_combined, "Highest-Scoring Game"),
                                (_lo_combined, "Lowest-Scoring Game"),
                            ],
                        )
                        if _highlight_labels:
                            _highlighted = _matchup_df.loc[list(_highlight_labels)].copy()
                            _highlighted["record_label"] = [
                                " / ".join(_highlight_labels[index])
                                for index in _highlighted.index
                            ]
                            _fig_chaos.add_trace(go.Scatter(
                                x=_highlighted["combined"],
                                y=_highlighted["margin"],
                                text=_highlighted["record_label"],
                                customdata=_highlighted[["matchup_label", "season", "week"]],
                                mode="markers+text",
                                textposition="top center",
                                name="Records",
                                marker={
                                    "size": 17, "symbol": "diamond-open",
                                    "color": "#f8fafc", "line": {"width": 2.5},
                                },
                                hovertemplate=(
                                    "<b>%{text}</b><br>%{customdata[0]}<br>"
                                    "%{customdata[1]} Week %{customdata[2]}<br>"
                                    "Combined: %{x:.2f}<br>Margin: %{y:.2f}<extra></extra>"
                                ),
                            ))
                        _median_total = float(_matchup_df["combined"].median())
                        _median_margin = float(_matchup_df["margin"].median())
                        _fig_chaos.add_vline(
                            x=_median_total, line_dash="dot", line_color="#64748b"
                        )
                        _fig_chaos.add_hline(
                            y=_median_margin, line_dash="dot", line_color="#64748b"
                        )
                        _fig_chaos.update_layout(
                            title="The Chaos Map: Every Matchup",
                            height=520,
                            template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(15,23,42,0.36)",
                            margin={"l": 55, "r": 35, "t": 70, "b": 55},
                            xaxis={
                                "title": "Combined Points",
                                "gridcolor": "rgba(148,163,184,0.16)",
                            },
                            yaxis={
                                "title": "Victory Margin",
                                "gridcolor": "rgba(148,163,184,0.16)",
                                "rangemode": "tozero",
                            },
                            legend={"title": "Season", "orientation": "h", "y": -0.18},
                        )
                        page_common.plotly_labeled_scatter(_fig_chaos, slug="hof-chaos")

                        _shootout_type = (
                            "a true shootout—both teams contributed to the record total"
                            if float(_hi_combined["margin"]) <= _median_margin
                            else "high scoring but one-sided, so one team drove much of the record total"
                        )
                        _blowout_multiple = (
                            float(_blowout["margin"]) / _median_margin
                            if _median_margin > 0 else 0
                        )
                        st.markdown(
                            f" **What it means:** **{_matchup_text(_hi_combined)}** was {_shootout_type}. "
                            f"The **{_blowout['winner']}** blowout was {_blowout_multiple:.1f}× the typical "
                            f"margin, making it a genuine outlier rather than merely a comfortable win. "
                            f"The dotted lines mark the typical combined score and margin, so distance from "
                            "their intersection shows how unusual each matchup was."
                        )

            # ── Sub-tab C: Rivalries ──────────────────────────────────────────
            with _lhC:
                import plotly.graph_objects as go

                from fantasy import league_intelligence as _league_intel

                _all_h2h_matchups = _league_intel.matchup_record_frame(
                    _stable_h2h_records
                )

                st.subheader("Rivalries")
                st.caption(
                    "Build a rivalry week, inspect one matchup, or compare the full "
                    "league. Only the selected view is shown."
                )
                _rivalry_view = st.radio(
                    "Rivalry view",
                    ("Build a Week", "Explore a Matchup", "League Matrix"),
                    horizontal=True,
                    key="lh_rivalry_view",
                    label_visibility="collapsed",
                )

                if _rivalry_view == "Build a Week":
                    st.markdown("#### Rivalry Week Builder")
                    st.caption(
                        "The best full-week slate for the league's current managers. "
                        "Scores describe historical rivalry fit, not predictions."
                    )

                    _builder_left, _builder_right = st.columns(2)
                    with _builder_left:
                        _rivalry_mode = st.selectbox(
                            "Slate style",
                            list(_league_intel.RIVALRY_WEEK_MODES),
                            key="lh_rivalry_mode",
                        )
                        st.caption(
                            "Classic Rivalries: longest series and playoff history. "
                            "Maximum Drama: close, back-and-forth games. "
                            "Fresh Blood: managers who rarely play each other and have similar records."
                        )
                    with _builder_right:
                        _rivalry_history = st.selectbox(
                            "History window",
                            ["All history", "Last 3 completed seasons"],
                            key="lh_rivalry_history",
                        )

                    _builder_matchups = _all_h2h_matchups.copy()
                    if (
                        _rivalry_history == "Last 3 completed seasons"
                        and not _builder_matchups.empty
                    ):
                        _played_seasons = sorted(
                            _builder_matchups["season"].astype(str).unique().tolist(),
                            key=lambda value: (
                                pd.to_numeric(value, errors="coerce")
                                if pd.notna(pd.to_numeric(value, errors="coerce")) else -1
                            ),
                        )
                        _recent_seasons = set(_played_seasons[-3:])
                        _builder_matchups = _builder_matchups[
                            _builder_matchups["season"].astype(str).isin(_recent_seasons)
                        ].copy()

                    _pair_scores = _league_intel.rivalry_pair_score_frame(
                        _builder_matchups,
                        _active_rivalry_managers,
                        mode=_rivalry_mode,
                    )
                    _rivalry_slate = _league_intel.rivalry_week_slate_frame(
                        _pair_scores,
                    )

                    if len(_active_rivalry_managers) < 2:
                        st.info(
                            f"At least two current managers with stable {_provider} owner IDs are "
                            "needed to build a rivalry slate."
                        )
                    elif _rivalry_slate.empty:
                        st.info("No rivalry slate is available for the current league yet.")
                    else:
                        _scored_slate = pd.to_numeric(
                            _rivalry_slate["rivalry_score"], errors="coerce"
                        ).dropna()
                        _matchup_count = int(
                            _rivalry_slate["manager_b"].notna().sum()
                        )
                        _average_score = (
                            f"{_scored_slate.mean():.1f}/100"
                            if not _scored_slate.empty else "—"
                        )
                        st.caption(
                            f"{_matchup_count} matchups for "
                            f"{len(_active_rivalry_managers)} current managers · "
                            f"average score {_average_score}. "
                            "Green is 70+ fit, yellow is 50-69, red is below 50."
                        )
                        st.markdown(
                            _rivalry_score_legend_html(),
                            unsafe_allow_html=True,
                        )

                        for _, _slate_row in _rivalry_slate.iterrows():
                            if pd.isna(_slate_row.get("manager_b")):
                                st.warning(
                                    f"**{_slate_row['manager_a']}** has the open slot because "
                                    "the league currently has an odd number of managers."
                                )
                                continue
                            st.markdown(
                                _rivalry_slate_card_html(_slate_row),
                                unsafe_allow_html=True,
                            )
                    st.caption(_league_intel.RIVALRY_SCORE_EXPLAIN[_rivalry_mode])

                elif _rivalry_view == "Explore a Matchup":
                    _h2h_scope = _season_filter if _season_filter != "All Time" else "all-time"
                    st.markdown("#### Matchup Explorer")
                    st.caption(
                        f"Inspect one completed series {_h2h_scope}. Includes playoffs; "
                        "scores of 5 points or fewer are excluded."
                    )

                    _h2h_matchups = _all_h2h_matchups
                    if _season_filter != "All Time":
                        _h2h_matchups = _h2h_matchups[
                            _h2h_matchups["season"].astype(str).eq(str(_season_filter))
                        ].copy()
                    _rivalries = _league_intel.rivalry_summary_frame(_h2h_matchups)
                    if _rivalries.empty:
                        st.info("No completed head-to-head matchups are available for this selection.")
                    else:
                        _rivalry_managers = sorted(set(_rivalries["manager_a"]).union(
                            _rivalries["manager_b"]
                        ))
                        _manager_meetings = {manager: 0 for manager in _rivalry_managers}
                        for _, _series in _rivalries.iterrows():
                            _manager_meetings[_series["manager_a"]] += int(_series["games"])
                            _manager_meetings[_series["manager_b"]] += int(_series["games"])
                        _default_a = sorted(
                            _rivalry_managers,
                            key=lambda manager: (-_manager_meetings[manager], manager),
                        )[0]
                        if st.session_state.get("lh_h2h_manager_a") not in _rivalry_managers:
                            st.session_state.pop("lh_h2h_manager_a", None)
                        _select_a, _select_b = st.columns(2)
                        with _select_a:
                            _manager_a = st.selectbox(
                                "Manager A",
                                _rivalry_managers,
                                index=_rivalry_managers.index(_default_a),
                                key="lh_h2h_manager_a",
                            )

                        _opponent_series = _rivalries[
                            (_rivalries["manager_a"] == _manager_a)
                            | (_rivalries["manager_b"] == _manager_a)
                        ].copy()
                        _opponent_series["opponent"] = _opponent_series.apply(
                            lambda row: (
                                row["manager_b"]
                                if row["manager_a"] == _manager_a else row["manager_a"]
                            ),
                            axis=1,
                        )
                        _opponent_series["series_gap"] = (
                            _opponent_series["manager_a_wins"]
                            - _opponent_series["manager_b_wins"]
                        ).abs()
                        _opponent_series = _opponent_series.sort_values(
                            ["games", "series_gap", "opponent"],
                            ascending=[False, True, True],
                        )
                        _manager_b_options = sorted(
                            _opponent_series["opponent"].unique().tolist()
                        )
                        _default_b = _opponent_series.iloc[0]["opponent"]
                        if st.session_state.get("lh_h2h_manager_b") not in _manager_b_options:
                            st.session_state.pop("lh_h2h_manager_b", None)
                        with _select_b:
                            _manager_b = st.selectbox(
                                "Manager B",
                                _manager_b_options,
                                index=_manager_b_options.index(_default_b),
                                key="lh_h2h_manager_b",
                            )

                        _selected_series = _rivalries[
                            ((_rivalries["manager_a"] == _manager_a)
                             & (_rivalries["manager_b"] == _manager_b))
                            | ((_rivalries["manager_a"] == _manager_b)
                               & (_rivalries["manager_b"] == _manager_a))
                        ]
                        if _selected_series.empty:
                            st.info(
                                f"{_manager_a} and {_manager_b} did not play during this selection."
                            )
                        else:
                            _series = _selected_series.iloc[0]
                            if _series["manager_a"] == _manager_a:
                                _a_wins = int(_series["manager_a_wins"])
                                _b_wins = int(_series["manager_b_wins"])
                                _a_avg = float(_series["manager_a_avg_score"])
                                _b_avg = float(_series["manager_b_avg_score"])
                                _a_diff = float(_series["avg_point_diff"])
                            else:
                                _a_wins = int(_series["manager_b_wins"])
                                _b_wins = int(_series["manager_a_wins"])
                                _a_avg = float(_series["manager_b_avg_score"])
                                _b_avg = float(_series["manager_a_avg_score"])
                                _a_diff = -float(_series["avg_point_diff"])
                            _ties = int(_series["ties"])
                            if _a_wins > _b_wins:
                                _series_leader = _manager_a
                            elif _b_wins > _a_wins:
                                _series_leader = _manager_b
                            else:
                                _series_leader = "Series tied"
                            if _a_diff > 0:
                                _point_edge_manager = _manager_a
                            elif _a_diff < 0:
                                _point_edge_manager = _manager_b
                            else:
                                _point_edge_manager = None
                            _streak_manager = _series["current_streak_manager"]
                            _streak_count = int(_series["current_streak"])
                            _streak_value = (
                                "Latest game tied"
                                if _streak_manager == "Tie"
                                else f"{_streak_manager} · W{_streak_count}"
                            )

                            _series_ink = (
                                "#93A0B1" if _series_leader == "Series tied"
                                else "#35D08A"
                            )
                            st.markdown(
                                "<div class='jsa-lh-series' style='font-size:22px;font-weight:700;color:"
                                + _series_ink + ";letter-spacing:-0.02em;margin:4px 0 12px 0;"
                                "overflow-wrap:anywhere;'>"
                                + _html.escape(str(_manager_a)) + " vs "
                                + _html.escape(str(_manager_b)) + "</div>",
                                unsafe_allow_html=True,
                            )
                            _r1, _r2, _r3, _r4 = st.columns(4)
                            with _r1:
                                st.metric(
                                    "Series Record",
                                    f"{_a_wins}–{_b_wins}" + (f"–{_ties}T" if _ties else ""),
                                    (
                                        "Series tied"
                                        if _series_leader == "Series tied"
                                        else f"{_series_leader} leads"
                                    ),
                                    delta_color="off", delta_arrow="off", border=True,
                                )
                            with _r2:
                                st.metric(
                                    f"{_manager_a} Avg Score", f"{_a_avg:.1f} pts",
                                    (
                                        f"{_a_diff:+.2f} per meeting"
                                        if _a_diff else "Even per meeting"
                                    ),
                                    delta_color="off", delta_arrow="off", border=True,
                                )
                            with _r3:
                                st.metric(
                                    f"{_manager_b} Avg Score", f"{_b_avg:.1f} pts",
                                    (
                                        f"{-_a_diff:+.2f} per meeting"
                                        if _a_diff else "Even per meeting"
                                    ),
                                    delta_color="off", delta_arrow="off", border=True,
                                )
                            with _r4:
                                st.metric(
                                    "Current Streak", _streak_value,
                                    f"{int(_series['playoff_meetings'])} playoff meetings",
                                    delta_color="off", delta_arrow="off", border=True,
                                )

                            _pair_mask = (
                                ((_h2h_matchups["team_a"] == _manager_a)
                                 & (_h2h_matchups["team_b"] == _manager_b))
                                | ((_h2h_matchups["team_a"] == _manager_b)
                                   & (_h2h_matchups["team_b"] == _manager_a))
                            )
                            _rivalry_games = _h2h_matchups[_pair_mask].copy()
                            _rivalry_games["season_sort"] = pd.to_numeric(
                                _rivalry_games["season"], errors="coerce"
                            ).fillna(0)
                            _rivalry_games = _rivalry_games.sort_values(
                                ["season_sort", "week"]
                            ).reset_index(drop=True)

                            def _score_for_manager(row, manager):
                                if row["is_tie"]:
                                    return float(row["winner_score"])
                                return float(
                                    row["winner_score"]
                                    if row["winner"] == manager else row["loser_score"]
                                )

                            _rivalry_games["manager_a_score"] = _rivalry_games.apply(
                                lambda row: _score_for_manager(row, _manager_a), axis=1
                            )
                            _rivalry_games["manager_b_score"] = _rivalry_games.apply(
                                lambda row: _score_for_manager(row, _manager_b), axis=1
                            )
                            _rivalry_games["signed_margin"] = (
                                _rivalry_games["manager_a_score"]
                                - _rivalry_games["manager_b_score"]
                            )
                            _rivalry_games["game_label"] = _rivalry_games.apply(
                                lambda row: f"{row['season']} W{int(row['week'])}", axis=1
                            )
                            _bar_colors = [
                                "#38bdf8" if margin > 0 else "#fb7185" if margin < 0 else "#94a3b8"
                                for margin in _rivalry_games["signed_margin"]
                            ]
                            _fig_rivalry = go.Figure(go.Bar(
                                x=_rivalry_games["game_label"],
                                y=_rivalry_games["signed_margin"],
                                marker={
                                    "color": _bar_colors,
                                    "line": {"color": "rgba(255,255,255,0.45)", "width": 1},
                                },
                                customdata=_rivalry_games[[
                                    "manager_a_score", "manager_b_score", "winner", "is_playoff",
                                ]],
                                hovertemplate=(
                                    f"<b>%{{x}}</b><br>{_manager_a}: %{{customdata[0]:.2f}}<br>"
                                    f"{_manager_b}: %{{customdata[1]:.2f}}<br>"
                                    "Winner: %{customdata[2]}<br>Margin: %{y:+.2f}"
                                    "<br>Playoff: %{customdata[3]}<extra></extra>"
                                ),
                            ))
                            _playoff_games = _rivalry_games[_rivalry_games["is_playoff"]]
                            if not _playoff_games.empty:
                                _fig_rivalry.add_trace(go.Scatter(
                                    x=_playoff_games["game_label"],
                                    y=_playoff_games["signed_margin"],
                                    mode="markers",
                                    name="Playoff meeting",
                                    marker={
                                        "symbol": "diamond", "size": 11,
                                        "color": "#fbbf24",
                                        "line": {"color": "#f8fafc", "width": 1},
                                    },
                                    hovertemplate="Playoff meeting<extra></extra>",
                                ))
                            _fig_rivalry.add_hline(
                                y=0, line_color="#94a3b8", line_width=1
                            )
                            _fig_rivalry.update_layout(
                                title=f"{_manager_a} vs {_manager_b}: Game-by-Game Margin",
                                height=460,
                                template="plotly_dark",
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(15,23,42,0.36)",
                                margin={"l": 55, "r": 35, "t": 70, "b": 70},
                                showlegend=not _playoff_games.empty,
                                xaxis={
                                    "title": "Meeting",
                                    "tickangle": -35,
                                    "gridcolor": "rgba(148,163,184,0.08)",
                                },
                                yaxis={
                                    "title": f"Margin: {_manager_a} (+) / {_manager_b} (–)",
                                    "gridcolor": "rgba(148,163,184,0.16)",
                                    "zeroline": False,
                                },
                                legend={"orientation": "h", "y": -0.28},
                            )
                            _lh_plotly(_fig_rivalry)

                            _largest_game = _rivalry_games.loc[
                                _rivalry_games["signed_margin"].abs().idxmax()
                            ]
                            if _series_leader == "Series tied":
                                _series_meaning = (
                                    "Neither manager has established a repeatable advantage in the win column"
                                )
                            elif _point_edge_manager == _series_leader:
                                _series_meaning = (
                                    f"{_series_leader} leads both the series and average scoring, so the edge is "
                                    "supported by weekly production rather than only close-game timing"
                                )
                            else:
                                _series_meaning = (
                                    f"{_series_leader} leads the series, but {_point_edge_manager} owns the average "
                                    "scoring edge; the record is therefore less dominant than the W–L line looks"
                                )
                            _recent_meaning = (
                                "the latest meeting ended level"
                                if _streak_manager == "Tie"
                                else (
                                    f"{_streak_manager} has won the last {_streak_count} meetings, creating recent momentum"
                                    if _streak_count > 1
                                    else f"{_streak_manager} won the latest meeting, but there is no multi-game streak"
                                )
                            )
                            _largest_winner = (
                                _manager_a
                                if _largest_game["signed_margin"] > 0 else _manager_b
                            )
                            st.markdown(
                                f" **What it means:** {_series_meaning}. {_recent_meaning.capitalize()}. "
                                f"The rivalry's biggest separation was {_largest_winner}'s "
                                f"{abs(_largest_game['signed_margin']):.2f}-point win in "
                                f"{_largest_game['game_label']}; the rest of the bars show whether that result was "
                                "typical or an isolated blowout."
                            )

                else:
                    _h2h_scope = (
                        _season_filter
                        if _season_filter != "All Time" else "all-time"
                    )
                    st.markdown("#### League Matrix")
                    st.caption(
                        f"Compare every completed series {_h2h_scope}. Includes playoffs; "
                        "scores of 5 points or fewer are excluded. "
                        "Green means the row manager's win rate is higher. "
                        "Rose means the column manager's is."
                    )
                    _h2h_matchups = _all_h2h_matchups
                    if _season_filter != "All Time":
                        _h2h_matchups = _h2h_matchups[
                            _h2h_matchups["season"].astype(str).eq(
                                str(_season_filter)
                            )
                        ].copy()
                    _rivalries = _league_intel.rivalry_summary_frame(_h2h_matchups)
                    if _rivalries.empty:
                        st.info(
                            "No completed head-to-head matchups are available for "
                            "this selection."
                        )
                    else:
                        _rivalry_managers = sorted(
                            set(_rivalries["manager_a"]).union(
                                _rivalries["manager_b"]
                            )
                        )
                        _pair_lookup = {
                            frozenset((row["manager_a"], row["manager_b"])): row
                            for _, row in _rivalries.iterrows()
                        }

                        def _record_for(manager, opponent):
                            row = _pair_lookup.get(frozenset((manager, opponent)))
                            if row is None:
                                return 0, 0, 0
                            if row["manager_a"] == manager:
                                return (
                                    int(row["manager_a_wins"]),
                                    int(row["manager_b_wins"]),
                                    int(row["ties"]),
                                )
                            return (
                                int(row["manager_b_wins"]),
                                int(row["manager_a_wins"]),
                                int(row["ties"]),
                            )

                        _manager_h2h_stats = {}
                        for _manager in _rivalry_managers:
                            _wins = _losses = _ties_total = _games_total = 0
                            for _opponent in _rivalry_managers:
                                if _manager == _opponent:
                                    continue
                                _w, _l, _t = _record_for(_manager, _opponent)
                                _wins += _w
                                _losses += _l
                                _ties_total += _t
                                _games_total += _w + _l + _t
                            _manager_h2h_stats[_manager] = (
                                (_wins + 0.5 * _ties_total) / _games_total
                                if _games_total else 0,
                                _games_total,
                            )
                        _mgrs_sorted = sorted(
                            _rivalry_managers,
                            key=lambda manager: (
                                -_manager_h2h_stats[manager][0],
                                -_manager_h2h_stats[manager][1],
                                manager,
                            ),
                        )
                        _heat_values = []
                        _heat_text = []
                        _heat_games = []
                        _matrix_rows = []
                        for _row_manager in _mgrs_sorted:
                            _z_row = []
                            _text_row = []
                            _games_row = []
                            _matrix_row = {"Manager": _row_manager}
                            for _col_manager in _mgrs_sorted:
                                if _row_manager == _col_manager:
                                    _z_row.append(None)
                                    _text_row.append("—")
                                    _games_row.append(0)
                                    _matrix_row[_col_manager] = "—"
                                    continue
                                _wins, _losses, _ties = _record_for(
                                    _row_manager, _col_manager
                                )
                                _games = _wins + _losses + _ties
                                _edge = (
                                    ((_wins + 0.5 * _ties) / _games * 100) - 50
                                    if _games else None
                                )
                                _record_text = f"{_wins}–{_losses}" if _games else "—"
                                if _games and _ties:
                                    _record_text += f"–{_ties}T"
                                _z_row.append(_edge)
                                _text_row.append(_record_text)
                                _games_row.append(_games)
                                _matrix_row[_col_manager] = _record_text
                            _heat_values.append(_z_row)
                            _heat_text.append(_text_row)
                            _heat_games.append(_games_row)
                            _matrix_rows.append(_matrix_row)

                        _fig_h2h = _league_matrix_figure(
                            _mgrs_sorted, _heat_values, _heat_text, _heat_games,
                            phone=False,
                        )
                        _fig_h2h_phone = _league_matrix_figure(
                            _mgrs_sorted, _heat_values, _heat_text, _heat_games,
                            phone=True,
                        )
                        page_common.plotly_phone_desktop(
                            _fig_h2h, _fig_h2h_phone, slug="league-matrix",
                        )

                        _analysis_pairs = _rivalries.copy()
                        _analysis_pairs["series_gap"] = (
                            _analysis_pairs["manager_a_wins"]
                            - _analysis_pairs["manager_b_wins"]
                        ).abs()
                        _analysis_pairs["dominance"] = _analysis_pairs["series_gap"].div(
                            _analysis_pairs["games"]
                        )
                        _established_pairs = _analysis_pairs[
                            _analysis_pairs["games"].ge(3)
                        ]
                        if _established_pairs.empty:
                            _established_pairs = _analysis_pairs
                        _dominant = _established_pairs.sort_values(
                            ["dominance", "games"], ascending=[False, False]
                        ).iloc[0]
                        _competitive = _established_pairs.sort_values(
                            ["series_gap", "games"], ascending=[True, False]
                        ).iloc[0]
                        _dominant_leader = (
                            _dominant["manager_a"]
                            if _dominant["manager_a_wins"] > _dominant["manager_b_wins"]
                            else _dominant["manager_b"]
                        )
                        _dominant_wins = max(
                            int(_dominant["manager_a_wins"]),
                            int(_dominant["manager_b_wins"]),
                        )
                        _dominant_losses = min(
                            int(_dominant["manager_a_wins"]),
                            int(_dominant["manager_b_wins"]),
                        )
                        _winning_opponents = {}
                        for _manager in _mgrs_sorted:
                            _winning_opponents[_manager] = sum(
                                _record_for(_manager, opponent)[0]
                                > _record_for(_manager, opponent)[1]
                                for opponent in _mgrs_sorted if opponent != _manager
                            )
                        _broadest = sorted(
                            _mgrs_sorted,
                            key=lambda manager: (-_winning_opponents[manager], manager),
                        )[0]
                        st.markdown(
                            f" **What it means:** **{_broadest}** owns a winning record against "
                            f"{_winning_opponents[_broadest]} different managers, the broadest matchup edge in "
                            f"this view. The most one-sided established series is **{_dominant_leader}** over "
                            f"**{_dominant['manager_b'] if _dominant_leader == _dominant['manager_a'] else _dominant['manager_a']}** "
                            f"at {_dominant_wins}–{_dominant_losses}, showing a repeated opponent-specific advantage. "
                            f"**{_competitive['manager_a']} vs {_competitive['manager_b']}** is the most balanced "
                            f"established rivalry at {int(_competitive['manager_a_wins'])}–"
                            f"{int(_competitive['manager_b_wins'])}; neither side has separated consistently. "
                            "Green cells favor the row manager, red cells favor the column opponent."
                        )

                        _h2h_df = pd.DataFrame(_matrix_rows).set_index("Manager")
                        with st.expander("View complete head-to-head record matrix"):
                            st.dataframe(_h2h_df, width="stretch")

            # ── Sub-tab D: Report Cards ───────────────────────────────────────
            with _lhD:
                import plotly.graph_objects as go

                from fantasy import league_intelligence as _league_intel

                _rc_scope = _season_filter if _season_filter != "All Time" else "all-time"
                st.subheader("Manager Report Cards")
                st.caption(
                    f"Peer-ranked regular-season performance for {_rc_scope}. Head-to-head "
                    "records exclude platform median-game bonuses; postseason results are shown separately."
                )

                _manager_performance = _league_intel.manager_performance_frame(_filt_records)
                _report_managers = (
                    sorted(_manager_performance["manager"].tolist())
                    if not _manager_performance.empty else []
                )
                if not _report_managers:
                    st.info("No completed manager games are available for this filter.")
                    _sel_mgr = None
                else:
                    _preferred_manager = st.session_state.get("lh_h2h_manager_a")
                    if _preferred_manager not in _report_managers:
                        _preferred_manager = _manager_performance.sort_values(
                            ["games", "avg_above_league"], ascending=[False, False]
                        ).iloc[0]["manager"]
                    if st.session_state.get("lh_manager") not in _report_managers:
                        st.session_state.pop("lh_manager", None)
                    _sel_mgr = st.selectbox(
                        "Manager",
                        _report_managers,
                        index=_report_managers.index(_preferred_manager),
                        key="lh_manager",
                    )

                _mgr_games_all = [
                    r for r in _filt_records
                    if r["username"] == _sel_mgr
                    and r["score"] > 5 and r["opp_score"] > 5
                ] if _sel_mgr else []

                # Season history always shows full career (not filtered)
                _mgr_season_rows: dict = {}
                for _yr3, _sd3 in _lh["seasons"].items():
                    for _row3 in _sd3["standings"]:
                        if _row3["username"] == _sel_mgr:
                            _mgr_season_rows[_yr3] = _row3

                if not _mgr_games_all:
                    st.info(f"No data for this manager in {_rc_scope}.")
                else:
                    _manager_performance = _manager_performance.copy()
                    _manager_performance["win_rank"] = _manager_performance["win_pct"].rank(
                        method="min", ascending=False
                    ).astype(int)
                    _manager_performance["scoring_rank"] = _manager_performance[
                        "avg_above_league"
                    ].rank(method="min", ascending=False).astype(int)
                    _manager_performance["consistency_rank"] = _manager_performance[
                        "std_dev"
                    ].rank(method="min", ascending=True).astype(int)
                    _profile = _manager_performance[
                        _manager_performance["manager"] == _sel_mgr
                    ].iloc[0]
                    _peer_count = len(_manager_performance)
                    _titles = sum(1 for _sd4 in _filt_seasons.values()
                                  if _sd4["champion"]["username"] == _sel_mgr)
                    _runner_ups = sum(1 for _sd4 in _filt_seasons.values()
                                     if _sd4["runner_up"]["username"] == _sel_mgr)
                    _playoff_apps = sum(
                        1 for _yr3p, _s4 in _mgr_season_rows.items()
                        if _s4.get("playoff_finish") is not None
                        and (_season_filter == "All Time" or _yr3p == _season_filter)
                    )

                    with st.container(key="jsa-lh-report-cards"):
                        _d1, _d2, _d3, _d4 = st.columns(4)
                        with _d1:
                            _record_value = (
                                f"{int(_profile['wins'])}–{int(_profile['losses'])}"
                                + (f"–{int(_profile['ties'])}T" if _profile["ties"] else "")
                            )
                            st.metric(
                                "Regular-Season Record", _record_value,
                                f"{_profile['win_pct']:.1f}% · rank #{int(_profile['win_rank'])}/{_peer_count}",
                                delta_color="off", delta_arrow="off", border=True,
                            )
                        with _d2:
                            st.metric(
                                "Scoring vs League",
                                f"{_profile['avg_above_league']:+.1f}/wk",
                                f"rank #{int(_profile['scoring_rank'])}/{_peer_count}",
                                delta_color="off", delta_arrow="off", border=True,
                            )
                        with _d3:
                            st.metric(
                                "Consistency",
                                f"±{_profile['std_dev']:.1f} pts",
                                (
                                    f"rank #{int(_profile['consistency_rank'])}/{_peer_count} "
                                    "· smaller swing is steadier"
                                ),
                                delta_color="off", delta_arrow="off", border=True,
                                help=(
                                    "Typical distance of a weekly score from this manager's own average. "
                                    "±23 pts means a normal week is about 23 points above or below their mean. "
                                    "Smaller is steadier. Ranked against the rest of the league."
                                ),
                            )
                        with _d4:
                            st.metric(
                                "Postseason Résumé", f"{_titles} {'title' if _titles == 1 else 'titles'}",
                                f"{_titles + _runner_ups} finals · {_playoff_apps} playoff apps",
                                delta_color="off", delta_arrow="off", border=True,
                            )

                    st.caption(
                        "All-time is scoring versus the league, season by season. "
                        "Flip to one season and it goes weekly."
                    )
                    if _season_filter == "All Time":
                        _trajectory_rows = []
                        for _season in sorted(_filt_seasons):
                            _season_records = [
                                record for record in _game_records
                                if record["season"] == _season
                            ]
                            _season_performance = _league_intel.manager_performance_frame(
                                _season_records
                            )
                            _season_profile = _season_performance[
                                _season_performance["manager"] == _sel_mgr
                            ]
                            if _season_profile.empty:
                                continue
                            _season_profile = _season_profile.iloc[0]
                            _trajectory_rows.append({
                                "Season": str(_season),
                                "Avg Score": float(_season_profile["avg_score"]),
                                "Pts vs League": float(_season_profile["avg_above_league"]),
                                "Win %": float(_season_profile["win_pct"]),
                                "Record": (
                                    f"{int(_season_profile['wins'])}–"
                                    f"{int(_season_profile['losses'])}"
                                ),
                            })
                        _trajectory_df = pd.DataFrame(_trajectory_rows)
                        if not _trajectory_df.empty:
                            _fig_trajectory = go.Figure(go.Bar(
                                x=_trajectory_df["Season"],
                                y=_trajectory_df["Pts vs League"],
                                name="Points vs league / week",
                                marker={
                                    "color": [
                                        "#38bdf8" if value >= 0 else "#fb7185"
                                        for value in _trajectory_df["Pts vs League"]
                                    ],
                                    "line": {"color": "rgba(255,255,255,0.45)", "width": 1},
                                },
                                customdata=_trajectory_df[["Avg Score", "Record", "Win %"]],
                                hovertemplate=(
                                    "<b>%{x}</b><br>Points vs league: %{y:+.2f}/week<br>"
                                    "Avg score: %{customdata[0]:.2f}<br>"
                                    "Record: %{customdata[1]}<br>"
                                    "Win rate: %{customdata[2]:.1f}%<extra></extra>"
                                ),
                            ))
                            _fig_trajectory.add_hline(
                                y=0, line_dash="dot", line_color="#94a3b8",
                            )
                            _fig_trajectory.update_layout(
                                title=f"{_sel_mgr}'s Season-by-Season Trajectory",
                                height=470,
                                template="plotly_dark",
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(15,23,42,0.36)",
                                margin={"l": 55, "r": 55, "t": 70, "b": 55},
                                showlegend=False,
                                hovermode="x unified",
                                xaxis={
                                    "title": "Season",
                                    "gridcolor": "rgba(148,163,184,0.12)",
                                },
                                yaxis={
                                    "title": "Avg Points vs League / Week",
                                    "gridcolor": "rgba(148,163,184,0.16)",
                                },
                            )
                            _lh_plotly(_fig_trajectory)

                            _best_scoring_season = _trajectory_df.loc[
                                _trajectory_df["Pts vs League"].idxmax()
                            ]
                            _best_winning_season = _trajectory_df.loc[
                                _trajectory_df["Win %"].idxmax()
                            ]
                            _first_season = _trajectory_df.iloc[0]
                            _latest_season = _trajectory_df.iloc[-1]
                            _trend_delta = (
                                _latest_season["Pts vs League"]
                                - _first_season["Pts vs League"]
                            )
                            if _best_scoring_season["Season"] == _best_winning_season["Season"]:
                                _peak_meaning = (
                                    f"the scoring peak in {_best_scoring_season['Season']} translated directly "
                                    "into the best win rate"
                                )
                            else:
                                _peak_meaning = (
                                    f"the scoring peak came in {_best_scoring_season['Season']}, but the best "
                                    f"win rate came in {_best_winning_season['Season']}; matchup timing and close "
                                    "games changed the record"
                                )
                            _multi_season = len(_trajectory_df) >= 2
                            _trend_meaning = (
                                f"weekly scoring relative to the league improved by {_trend_delta:+.2f} points "
                                "from the first completed season to the latest"
                                if _trend_delta >= 0 else
                                f"weekly scoring relative to the league fell by {abs(_trend_delta):.2f} points "
                                "from the first completed season to the latest"
                            ) if _multi_season else ""
                            _trend_sentence = (
                                f" Across the full timeline, {_trend_meaning}." if _multi_season else ""
                            )
                            st.markdown(
                                f" **What it means:** For **{_sel_mgr}**, {_peak_meaning}.{_trend_sentence} Bars measure performance against each season's "
                                "own scoring environment, so the direction is not inflated by league-wide scoring changes."
                            )
                    else:
                        _valid_regular = [
                            record for record in _filt_records
                            if not record["is_playoff"]
                            and record["score"] > 5 and record["opp_score"] > 5
                        ]
                        _week_scores: dict = {}
                        for _record in _valid_regular:
                            _week_scores.setdefault(_record["week"], []).append(
                                _record["score"]
                            )
                        _week_averages = {
                            week: sum(scores) / len(scores)
                            for week, scores in _week_scores.items() if scores
                        }
                        _weekly_rows = []
                        for _record in _valid_regular:
                            if _record["username"] != _sel_mgr:
                                continue
                            _result = (
                                "Win" if _record["score"] > _record["opp_score"]
                                else "Loss" if _record["score"] < _record["opp_score"]
                                else "Tie"
                            )
                            _weekly_rows.append({
                                "Week": int(_record["week"]),
                                "Score": float(_record["score"]),
                                "League Avg": float(_week_averages[_record["week"]]),
                                "Vs League": float(
                                    _record["score"] - _week_averages[_record["week"]]
                                ),
                                "Opponent": _record["opp"],
                                "Opponent Score": float(_record["opp_score"]),
                                "Result": _result,
                            })
                        _weekly_df = pd.DataFrame(_weekly_rows).sort_values("Week")
                        if not _weekly_df.empty:
                            _weekly_colors = _weekly_df["Result"].map({
                                "Win": "#38bdf8", "Loss": "#fb7185", "Tie": "#94a3b8",
                            })
                            _fig_weekly = go.Figure(go.Bar(
                                x=_weekly_df["Week"],
                                y=_weekly_df["Vs League"],
                                marker={
                                    "color": _weekly_colors,
                                    "line": {"color": "rgba(255,255,255,0.45)", "width": 1},
                                },
                                customdata=_weekly_df[[
                                    "Score", "League Avg", "Opponent", "Opponent Score", "Result",
                                ]],
                                hovertemplate=(
                                    "<b>Week %{x}</b><br>%{customdata[4]} vs %{customdata[2]}<br>"
                                    "Score: %{customdata[0]:.2f}–%{customdata[3]:.2f}<br>"
                                    "League average: %{customdata[1]:.2f}<br>"
                                    "Points vs league: %{y:+.2f}<extra></extra>"
                                ),
                            ))
                            _fig_weekly.add_hline(
                                y=0, line_dash="dot", line_color="#94a3b8"
                            )
                            _fig_weekly.update_layout(
                                title=f"{_sel_mgr}'s Weekly Performance — {_season_filter}",
                                height=450,
                                template="plotly_dark",
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(15,23,42,0.36)",
                                margin={"l": 55, "r": 35, "t": 70, "b": 55},
                                showlegend=False,
                                xaxis={
                                    "title": "Week", "dtick": 1,
                                    "gridcolor": "rgba(148,163,184,0.08)",
                                },
                                yaxis={
                                    "title": "Points Above / Below League Average",
                                    "gridcolor": "rgba(148,163,184,0.16)",
                                },
                            )
                            _lh_plotly(_fig_weekly)

                            _above_weeks = int(_weekly_df["Vs League"].gt(0).sum())
                            _lucky_wins = len(_weekly_df[
                                _weekly_df["Result"].eq("Win")
                                & _weekly_df["Vs League"].lt(0)
                            ])
                            _unlucky_losses = len(_weekly_df[
                                _weekly_df["Result"].eq("Loss")
                                & _weekly_df["Vs League"].gt(0)
                            ])
                            _best_week = _weekly_df.loc[_weekly_df["Vs League"].idxmax()]
                            st.markdown(
                                f" **What it means:** **{_sel_mgr}** scored above the league average in "
                                f"{_above_weeks} of {len(_weekly_df)} completed weeks. The strongest relative "
                                f"performance was Week {int(_best_week['Week'])} at "
                                f"{_best_week['Vs League']:+.2f} points versus the league. "
                                f"{_lucky_wins} below-average wins and {_unlucky_losses} above-average losses "
                                "show how often matchup timing changed the record beyond the manager's scoring output."
                            )

                    _opponent_rows = []
                    for _opponent, _games in pd.DataFrame(_mgr_games_all).groupby("opp"):
                        _wins = int((_games["score"] > _games["opp_score"]).sum())
                        _losses = int((_games["score"] < _games["opp_score"]).sum())
                        _ties = int((_games["score"] == _games["opp_score"]).sum())
                        _opponent_rows.append({
                            "Opponent": _opponent,
                            "Wins": _wins,
                            "Losses": _losses,
                            "Ties": _ties,
                            "Record": f"{_wins}–{_losses}" + (f"–{_ties}T" if _ties else ""),
                            "Meetings": len(_games),
                            "Avg Score": float(_games["score"].mean()),
                            "Avg Point Diff": round(
                                float((_games["score"] - _games["opp_score"]).mean()),
                                2,
                            ),
                            "Playoff Meetings": int(_games["is_playoff"].sum()),
                        })
                    _opponent_df = pd.DataFrame(_opponent_rows).sort_values(
                        "Avg Point Diff", ascending=True
                    )
                    if not _opponent_df.empty:
                        _opponent_colors = [
                            "#38bdf8" if value >= 0 else "#fb7185"
                            for value in _opponent_df["Avg Point Diff"]
                        ]
                        _fig_opponents = go.Figure(go.Bar(
                            x=_opponent_df["Avg Point Diff"],
                            y=_opponent_df["Opponent"],
                            orientation="h",
                            text=[
                                f"{record} · {int(meetings)}"
                                for record, meetings in zip(
                                    _opponent_df["Record"], _opponent_df["Meetings"]
                                )
                            ],
                            textposition="outside",
                            cliponaxis=False,
                            marker={
                                "color": _opponent_colors,
                                "line": {"color": "rgba(255,255,255,0.45)", "width": 1},
                            },
                            customdata=_opponent_df[[
                                "Meetings", "Avg Score", "Playoff Meetings", "Record",
                            ]],
                            hovertemplate=(
                                "<b>%{y}</b><br>Record: %{customdata[3]}<br>"
                                "Avg point differential: %{x:+.2f}<br>"
                                "Avg score: %{customdata[1]:.2f}<br>"
                                "Meetings: %{customdata[0]}<br>"
                                "Playoff meetings: %{customdata[2]}<extra></extra>"
                            ),
                        ))
                        _opponent_span = max(
                            5.0, float(_opponent_df["Avg Point Diff"].abs().max()) * 1.25
                        )
                        _fig_opponents.add_vline(
                            x=0, line_color="#94a3b8", line_width=1
                        )
                        _fig_opponents.update_layout(
                            title=f"Where {_sel_mgr} Gains and Loses Ground",
                            height=max(420, 38 * len(_opponent_df) + 115),
                            template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(15,23,42,0.36)",
                            margin={"l": 25, "r": 110, "t": 70, "b": 55},
                            showlegend=False,
                            xaxis={
                                "title": "Average Point Differential vs Opponent",
                                "range": [-_opponent_span, _opponent_span],
                                "tickformat": "+.2f",
                                "gridcolor": "rgba(148,163,184,0.16)",
                            },
                            yaxis={"title": "", "automargin": True},
                        )
                        _lh_plotly(_fig_opponents)

                        _best_matchup = _opponent_df.loc[
                            _opponent_df["Avg Point Diff"].idxmax()
                        ]
                        _worst_matchup = _opponent_df.loc[
                            _opponent_df["Avg Point Diff"].idxmin()
                        ]
                        _best_n = int(_best_matchup["Meetings"])
                        _worst_n = int(_worst_matchup["Meetings"])
                        _best_games = "meeting" if _best_n == 1 else "meetings"
                        _worst_games = "meeting" if _worst_n == 1 else "meetings"
                        if _best_matchup["Opponent"] == _worst_matchup["Opponent"]:
                            st.markdown(
                                f" **What it means:** Average scoring margin vs "
                                f"**{_best_matchup['Opponent']}** is "
                                f"{_best_matchup['Avg Point Diff']:+.2f} over "
                                f"{_best_n} {_best_games}. Meeting count on the bar is "
                                "the sample size. A one-game blowout can sit at either end of this chart."
                            )
                        else:
                            st.markdown(
                                f" **What it means:** The highest average scoring margin is vs "
                                f"**{_best_matchup['Opponent']}** at "
                                f"{_best_matchup['Avg Point Diff']:+.2f} over "
                                f"{_best_n} {_best_games}. The lowest is vs "
                                f"**{_worst_matchup['Opponent']}** at "
                                f"{_worst_matchup['Avg Point Diff']:+.2f} over "
                                f"{_worst_n} {_worst_games}. A one-game blowout can sit "
                                "at either end. Meeting count on each bar is the sample size."
                            )

                    _s_hist = []
                    for _yr4 in sorted(_mgr_season_rows):
                        _row4 = _mgr_season_rows[_yr4]
                        _pf4  = _row4.get("playoff_finish")
                        _fin4 = {1: "🥇 Champion", 2: "🥈 Runner-up", 3: "🥉 3rd"}.get(
                            _pf4, f"{_pf4}th" if _pf4 else "DNQ")
                        _season_records = [
                            record for record in _game_records
                            if record["season"] == _yr4
                        ]
                        _season_performance = _league_intel.manager_performance_frame(
                            _season_records
                        )
                        _season_profile = _season_performance[
                            _season_performance["manager"] == _sel_mgr
                        ]
                        _season_profile = (
                            _season_profile.iloc[0] if not _season_profile.empty else None
                        )
                        _s_hist.append({
                            "Season":    _yr4,
                            "Team Name": _row4.get("team_name") or "—",
                            "Official Record": f"{_row4['wins']}–{_row4['losses']}",
                            "H2H Win %": (
                                float(_season_profile["win_pct"])
                                if _season_profile is not None else None
                            ),
                            "Avg Score": (
                                float(_season_profile["avg_score"])
                                if _season_profile is not None else None
                            ),
                            "Vs League / Wk": (
                                float(_season_profile["avg_above_league"])
                                if _season_profile is not None else None
                            ),
                            "PF":        _row4["fpts"],
                            "PA":        _row4["fpts_against"],
                            "Finish":    _fin4,
                        })
                    with st.expander("View complete career season history"):
                        _season_hist = pd.DataFrame(_s_hist)
                        dataframe_phone_desktop(
                            _season_hist,
                            _season_hist[[
                                c for c in (
                                    "Season", "Official Record", "Finish",
                                    "Avg Score", "H2H Win %",
                                ) if c in _season_hist.columns
                            ]],
                            slug="lh-season-history",
                            hide_index=True,
                            width="stretch",
                            column_config={
                                "H2H Win %": st.column_config.NumberColumn(
                                    "H2H Win %", format="%.1f%%"
                                ),
                                "Avg Score": st.column_config.NumberColumn(
                                    "Avg Score", format="%.2f"
                                ),
                                "Vs League / Wk": st.column_config.NumberColumn(
                                    "Vs League / Wk", format="%+.2f"
                                ),
                                "PF": st.column_config.NumberColumn("PF", format="%.2f"),
                                "PA": st.column_config.NumberColumn("PA", format="%.2f"),
                            },
                        )
                    with st.expander("View complete opponent breakdown"):
                        st.dataframe(
                            _opponent_df.sort_values(
                                "Avg Point Diff", ascending=False
                            ),
                            hide_index=True,
                            width="stretch",
                            column_config={
                                "Avg Score": st.column_config.NumberColumn(
                                    "Avg Score", format="%.2f"
                                ),
                                "Avg Point Diff": st.column_config.NumberColumn(
                                    "Avg Point Diff", format="%+.2f"
                                ),
                            },
                        )

            # ── Sub-tab E: Consistency & Luck ─────────────────────────────────
            with _lhE:
                import plotly.graph_objects as go

                from fantasy import league_intelligence as _league_intel

                _cl_scope = _season_filter if _season_filter != "All Time" else "all seasons"
                st.subheader("Consistency & Schedule Luck")
                st.caption(
                    f"Regular season only · {_cl_scope}. Expected wins use all-play probability: "
                    "how often each weekly score would have beaten every other team that week."
                )

                _cl_df = _league_intel.consistency_luck_frame(_filt_records)
                if _cl_df.empty:
                    st.info("No completed regular-season scores are available for this selection.")
                else:
                    _sample_floor = min(3, int(_cl_df["games"].max()))
                    _eligible_cl = _cl_df[_cl_df["games"].ge(_sample_floor)].copy()
                    _most_consistent = _eligible_cl.loc[
                        _eligible_cl["volatility"].idxmin()
                    ]
                    _most_volatile = _eligible_cl.loc[
                        _eligible_cl["volatility"].idxmax()
                    ]
                    _most_fortunate = _eligible_cl.loc[
                        _eligible_cl["luck_delta"].idxmax()
                    ]
                    _most_unfortunate = _eligible_cl.loc[
                        _eligible_cl["luck_delta"].idxmin()
                    ]

                    _c1, _c2, _c3, _c4 = st.columns(4)
                    with _c1:
                        st.metric(
                            "Most Consistent", _most_consistent["manager"],
                            f"{_most_consistent['volatility']:.2f} adjusted SD",
                            delta_color="off", delta_arrow="off", border=True,
                            help=_CONSISTENCY_LUCK_METRIC_HELP["Most Consistent"],
                        )
                    with _c2:
                        st.metric(
                            "Most Volatile", _most_volatile["manager"],
                            f"{_most_volatile['volatility']:.2f} adjusted SD",
                            delta_color="off", delta_arrow="off", border=True,
                            help=_CONSISTENCY_LUCK_METRIC_HELP["Most Volatile"],
                        )
                    with _c3:
                        st.metric(
                            "Most Fortunate", _most_fortunate["manager"],
                            f"{_most_fortunate['luck_delta']:+.2f} wins vs expected",
                            delta_color="off", delta_arrow="off", border=True,
                            help=_CONSISTENCY_LUCK_METRIC_HELP["Most Fortunate"],
                        )
                    with _c4:
                        st.metric(
                            "Most Unfortunate", _most_unfortunate["manager"],
                            f"{_most_unfortunate['luck_delta']:+.2f} wins vs expected",
                            delta_color="off", delta_arrow="off", border=True,
                            help=_CONSISTENCY_LUCK_METRIC_HELP["Most Unfortunate"],
                        )

                    _median_volatility = float(_cl_df["volatility"].median())
                    _vol_top = max(
                        1.0,
                        float(_cl_df["volatility"].max()) * 1.15,
                        _median_volatility * 1.15,
                    )
                    _fig_consistency = go.Figure(go.Scatter(
                        x=_cl_df["avg_above_league"],
                        y=_cl_df["volatility"],
                        text=_cl_df["manager"],
                        customdata=_cl_df[[
                            "games", "avg_score", "actual_wins", "expected_wins", "luck_delta",
                        ]],
                        mode="markers+text",
                        textposition="bottom center",
                        marker={
                            "size": 14,
                            "color": "#38bdf8",
                            "line": {"color": "rgba(255,255,255,0.7)", "width": 1},
                            "opacity": 0.9,
                        },
                        hovertemplate=(
                            "<b>%{text}</b><br>Points vs league: %{x:+.2f}/week<br>"
                            "Adjusted volatility: %{y:.2f}<br>Avg score: %{customdata[1]:.2f}<br>"
                            "Actual wins: %{customdata[2]:.2f}<br>"
                            "Expected wins: %{customdata[3]:.2f}<br>"
                            "Luck delta: %{customdata[4]:+.2f}<br>Games: %{customdata[0]}<extra></extra>"
                        ),
                    ))
                    _fig_consistency.add_vline(
                        x=0, line_dash="dot", line_color="#94a3b8"
                    )
                    _fig_consistency.add_hline(
                        y=_median_volatility, line_dash="dot", line_color="#94a3b8"
                    )
                    _fig_consistency.update_layout(
                        title="Scoring Quality vs Week-to-Week Volatility",
                        height=520,
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(15,23,42,0.36)",
                        margin={"l": 55, "r": 45, "t": 70, "b": 55},
                        showlegend=False,
                        xaxis={
                            "title": "Average Points Above League / Week",
                            "gridcolor": "rgba(148,163,184,0.16)",
                        },
                        yaxis={
                            "title": "Week-to-week swing vs league (steadier at top)",
                            "range": [_vol_top, -0.4],
                            "gridcolor": "rgba(148,163,184,0.16)",
                        },
                    )
                    page_common.plotly_labeled_scatter(_fig_consistency, slug="consistency")

                    _top_scorer = _cl_df.loc[_cl_df["avg_above_league"].idxmax()]
                    _above_average = _eligible_cl[_eligible_cl["avg_above_league"].gt(0)]
                    _reliable = (
                        _above_average.loc[_above_average["volatility"].idxmin()]
                        if not _above_average.empty else _most_consistent
                    )
                    _top_scorer_style = (
                        "steadier than the league median"
                        if _top_scorer["volatility"] <= _median_volatility
                        else "more volatile than the league median"
                    )
                    _consistency_caveat = (
                        f"**{_most_consistent['manager']}** is the steadiest manager, but their "
                        f"{_most_consistent['avg_above_league']:+.2f} scoring margin shows that consistency "
                        "does not automatically mean strong scoring."
                        if _most_consistent["avg_above_league"] <= 0 else
                        f"**{_most_consistent['manager']}** combines the league's lowest volatility with "
                        f"above-average scoring, a genuinely dependable profile."
                    )
                    st.markdown(
                        f" **What it means:** **{_top_scorer['manager']}** has the strongest weekly scoring "
                        f"edge at {_top_scorer['avg_above_league']:+.2f} points and is {_top_scorer_style}. "
                        f"Among above-average scorers, **{_reliable['manager']}** is the most reliable, meaning "
                        "their advantage is less dependent on occasional spike weeks. "
                        f"{_consistency_caveat} The upper-right area is the ideal combination: strong and steady."
                    )

                    _lh_plotly(_schedule_luck_figure(_cl_df))

                    _most_aligned = _cl_df.loc[_cl_df["luck_delta"].abs().idxmin()]
                    _fortunate_meaning = (
                        f"won roughly {_most_fortunate['luck_delta']:.1f} more games than their weekly scores "
                        "would predict, so favorable opponent timing boosted the record"
                        if _most_fortunate["luck_delta"] > 0 else
                        "finished almost exactly where their weekly scoring predicted"
                    )
                    _unfortunate_gap = abs(float(_most_unfortunate["luck_delta"]))
                    _unfortunate_meaning = (
                        f"won roughly {_unfortunate_gap:.1f} fewer games than expected, so their record "
                        "understates the quality of their weekly scores"
                        if _most_unfortunate["luck_delta"] < 0 else
                        "also finished close to expectation"
                    )
                    st.markdown(
                        f" **What it means:** **{_most_fortunate['manager']}** {_fortunate_meaning}. "
                        f"**{_most_unfortunate['manager']}** {_unfortunate_meaning}. "
                        f"**{_most_aligned['manager']}** is closest to zero, meaning their actual record most "
                        "closely matches what an all-play schedule would expect. Luck here describes matchup "
                        "timing—not whether the wins count or whether roster decisions were good."
                    )

                    _cl_details = _cl_df.rename(columns={
                        "manager": "Manager",
                        "games": "Games",
                        "avg_score": "Avg Score",
                        "avg_above_league": "Pts vs League / Wk",
                        "volatility": "Adjusted Volatility",
                        "actual_wins": "Actual Wins",
                        "expected_wins": "Expected Wins",
                        "luck_delta": "Wins vs Expected",
                        "actual_win_pct": "Actual Win %",
                        "expected_win_pct": "Expected Win %",
                        "below_avg_wins": "Below-Avg Wins",
                        "above_avg_losses": "Above-Avg Losses",
                    })
                    with st.expander("View complete consistency and luck metrics"):
                        dataframe_phone_desktop(
                            _cl_details,
                            _cl_details[[
                                c for c in (
                                    "Manager", "Avg Score", "Wins vs Expected",
                                    "Actual Win %", "Expected Win %",
                                ) if c in _cl_details.columns
                            ]],
                            slug="lh-consistency",
                            hide_index=True,
                            width="stretch",
                            column_config={
                                "Avg Score": st.column_config.NumberColumn(
                                    "Avg Score", format="%.2f"
                                ),
                                "Pts vs League / Wk": st.column_config.NumberColumn(
                                    "Pts vs League / Wk", format="%+.2f"
                                ),
                                "Adjusted Volatility": st.column_config.NumberColumn(
                                    "Adjusted Volatility", format="%.2f",
                                    help="Standard deviation of weekly points relative to that week's league average",
                                ),
                                "Actual Wins": st.column_config.NumberColumn(
                                    "Actual Wins", format="%.2f"
                                ),
                                "Expected Wins": st.column_config.NumberColumn(
                                    "Expected Wins", format="%.2f"
                                ),
                                "Wins vs Expected": st.column_config.NumberColumn(
                                    "Wins vs Expected", format="%+.2f"
                                ),
                                "Actual Win %": st.column_config.NumberColumn(
                                    "Actual Win %", format="%.1f%%"
                                ),
                                "Expected Win %": st.column_config.NumberColumn(
                                    "Expected Win %", format="%.1f%%"
                                ),
                            },
                        )

            # ── Sub-tab G: Draft & Roster Insights ────────────────────────────
            with _lhG:
                # Kept in a separate renderer so this already-large history page remains
                # navigable and the analytics stay independently testable.
                import league_insights_view as _insights_mod
                _insights_mod = page_common.reload_if_stale(_insights_mod)
                if _provider in {"ESPN", "Yahoo", "CBS"}:
                    _player_directory_loader = lambda: _lh.get("player_directory", {})
                    _transaction_loader = None
                else:
                    _player_directory_loader = _fetch_player_directory
                    _transaction_loader = _fetch_season_transactions
                _insights_mod.render(
                    _lh,
                    _season_filter,
                    _player_directory_loader,
                    _transaction_loader,
                    provider_name=_provider,
                )



# ══════════════════════════════════════════════════════════════════════════════
# TAB 7: HELP & GUIDE
# ══════════════════════════════════════════════════════════════════════════════
