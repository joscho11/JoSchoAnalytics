"""Chart-first Draft & Roster Insights view for the League History page."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fantasy import league_intelligence as li
import page_common


_HERE = Path(__file__).resolve().parents[1]
_BENCHMARK_PATH = _HERE / "fantasy" / "league_intelligence_benchmarks.json"
_POSITION_COLORS = {
    "QB": "#3D95CE",
    "RB": "#00c853",
    "WR": "#a66cff",
    "TE": "#ffb000",
    "": "#8a93a0",
}
_SERIES_LINE_LIMIT = 3
_INSIGHT_VIEWS = ("My Team", "Best Values", "Draft Room")
_DEFAULT_INSIGHT_VIEW = "My Team"
_VIEW_KEY = "lh_insight_segment"
_LEGACY_VIEW_KEY = "lh_insight_view"
_PAID_FAAB_COLOR = "#38BDF8"
_PAID_FAAB_SCATTER_COLOR = "#C4A35A"
_VIEW_SWITCHER_CSS = """
<style>
[class*="st-key-lh_insight_segment"]{
  margin:0.15rem 0 0.9rem 0;
}
[class*="st-key-lh_insight_segment"] label p{
  font-size:0.98rem !important;
  font-weight:650 !important;
  letter-spacing:0.02em;
  color:#f2f5f7 !important;
  margin-bottom:0.35rem !important;
}
[class*="st-key-lh_insight_segment"] [data-testid="stButtonGroup"]{
  width:auto;
}
[class*="st-key-lh_insight_segment"] button{
  flex:0 0 auto !important;
  min-height:2.5rem !important;
  font-size:0.98rem !important;
  font-weight:650 !important;
  padding:0.45rem 0.95rem !important;
}
[class*="st-key-lh_insight_segment"] [aria-checked="true"]{
  background:rgba(53,208,138,0.22) !important;
  border-color:#35D08A !important;
  color:#f2f5f7 !important;
}
@media (max-width:640px){
  [class*="st-key-lh_insight_segment"] [data-testid="stButtonGroup"]{
    flex-wrap:wrap !important;
    width:100% !important;
  }
  [class*="st-key-lh_insight_segment"] button{
    flex:1 1 auto !important;
    min-height:2.6rem !important;
    font-size:0.92rem !important;
    padding:0.5rem 0.4rem !important;
  }
}
</style>
"""


def _dark_layout(fig: go.Figure, *, height: int, title: str | None = None) -> go.Figure:
    fig.update_layout(
        title=title,
        height=height,
        margin=dict(l=55, r=20, t=55 if title else 25, b=45),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#f2f5f7"),
        legend_title_text="",
        hoverlabel=dict(bgcolor="#17202b", font_color="#ffffff"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,.08)", zerolinecolor="rgba(255,255,255,.15)")
    fig.update_yaxes(
        gridcolor="rgba(255,255,255,.08)",
        zerolinecolor="rgba(255,255,255,.15)",
        automargin=True,
    )
    return fig


def _chart(fig: go.Figure) -> None:
    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False, "scrollZoom": False},
    )


def _chart_labeled(fig: go.Figure, *, slug: str) -> None:
    page_common.plotly_labeled_scatter(fig, slug=slug)


def _sorted_seasons(seasons: dict) -> list[str]:
    def _key(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return str(value)

    return sorted((str(value) for value in seasons), key=_key)


def _phone_round_heatmap(heat: go.Figure, round_count: int) -> go.Figure:
    """Keep the complete draft heatmap readable on a phone by allocating room per round."""
    phone = go.Figure(heat.to_dict())
    margin = phone.layout.margin.to_plotly_json()
    width = int((margin.get("l") or 55) + (margin.get("r") or 20) + 44 * round_count + 90)
    phone.update_layout(width=width, autosize=False)
    return phone


def _scope_history(history: dict, season_filter: str) -> tuple[dict, str]:
    seasons = history.get("seasons", {})
    if season_filter != "All Time":
        keep = [str(season_filter)]
        label = str(season_filter)
    else:
        completed = [
            season for season in _sorted_seasons(seasons)
            if seasons[season].get("draft_picks")
        ]
        default_index = list(li.INSIGHT_WINDOWS).index(li.DEFAULT_INSIGHT_WINDOW)
        window = st.radio(
            "Insight window", li.INSIGHT_WINDOWS, index=default_index,
            horizontal=True, key="lh_insight_window",
            help="Last 3 seasons is the default so current behavior is not overwhelmed by old league eras.",
        )
        keep = li.select_insight_seasons(
            _sorted_seasons(seasons), completed, window,
        )
        if not keep:
            label = "No completed drafts"
        elif len(keep) == 1:
            label = keep[0]
        else:
            label = f"{keep[0]}-{keep[-1]}"
    scoped = {season: seasons[season] for season in keep if season in seasons}
    return {"league_name": history.get("league_name"), "seasons": scoped}, label


def _manager_control(scoped: dict) -> tuple[str | None, str]:
    identities = li.manager_identity_map(scoped["seasons"])
    if not identities:
        return None, "Manager"
    labels: dict[str, str] = {}
    for user_id, username in identities.items():
        label = username
        if label in labels:
            label = f"{username} · {user_id[-4:]}"
        labels[label] = user_id
    ordered = sorted(labels, key=str.casefold)
    selected_label = st.selectbox("Manager profile", ordered, key="lh_insight_manager")
    return labels[selected_label], selected_label.split(" · ")[0]


def _load_benchmarks() -> dict:
    try:
        return json.loads(_BENCHMARK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _format_matches_benchmark(scoped: dict) -> bool:
    usable = [data for data in scoped["seasons"].values() if data.get("draft_picks")]
    if not usable:
        return False
    for data in usable:
        settings = data.get("league_settings") or {}
        scoring = settings.get("scoring_settings") or {}
        rounds = max(
            [int(pick.get("round") or 0) for pick in data.get("draft_picks", [])] or [0]
        )
        if not (
            int(settings.get("total_rosters") or 0) == 12
            and rounds == 14
            and float(scoring.get("rec") or 0) == 0.5
            and float(scoring.get("pass_td") or 0) == 4.0
            and "SUPER_FLEX" not in (settings.get("roster_positions") or [])
        ):
            return False
    return True


def _render_insight_bullets(
    insights: list[dict], draft_count: int, scope_label: str,
) -> None:
    if not insights:
        return
    st.subheader("What the evidence suggests")
    if draft_count < 2:
        st.caption("One draft. Treat this as a snapshot, not a habit.")
    for insight in insights[:5]:
        st.markdown(f"- {insight.get('bullet') or insight['finding']}")
    if draft_count >= 2:
        st.caption(f"Based on {draft_count} drafts in {scope_label}.")


def _point_labels(frame: pd.DataFrame, season_count: int, y: str) -> list[str]:
    """Label every point in a small window; otherwise only the outliers."""
    work = frame.reset_index(drop=True)
    if work.empty:
        return []
    if season_count <= _SERIES_LINE_LIMIT and len(work) <= 24:
        return list(work["player_name"].astype(str))
    labels = [""] * len(work)
    chosen: set[int] = set(work[y].nlargest(min(6, len(work))).index.tolist())
    if "round" in work.columns:
        late = work[work["round"].fillna(99).ge(6)]
        chosen.update(late.nlargest(min(3, len(late)), y).index.tolist())
    if "lane" in work.columns:
        pickups = work[work["lane"].eq("Pickup")]
        chosen.update(pickups.nlargest(min(3, len(pickups)), y).index.tolist())
    for idx in chosen:
        labels[int(idx)] = str(work.at[idx, "player_name"])
    return labels


def _add_cumulative_traces(
    fig: go.Figure,
    position_data: pd.DataFrame,
    position: str,
    color: str,
    overlay_season: str | None,
) -> None:
    seasons = [str(value) for value in position_data["season"].tolist()]
    unique = sorted(set(seasons), key=lambda value: int(value) if str(value).isdigit() else str(value))
    latest = unique[-1] if unique else None
    if len(unique) <= _SERIES_LINE_LIMIT:
        for season, season_data in position_data.groupby("season", sort=True):
            fig.add_trace(go.Scatter(
                x=season_data["round"], y=season_data["cumulative"],
                mode="lines+markers", name=str(season),
                line=dict(width=3),
                hovertemplate=f"{season} · Round %{{x}}<br>{position}s drafted: %{{y}}<extra></extra>",
            ))
        return
    pivot = position_data.pivot_table(
        index="round", columns="season", values="cumulative", aggfunc="max",
    )
    upper = pivot.max(axis=1)
    lower = pivot.min(axis=1)
    median = pivot.median(axis=1)
    fig.add_trace(go.Scatter(
        x=upper.index, y=upper, mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=lower.index, y=lower, mode="lines", fill="tonexty",
        fillcolor="rgba(242,245,247,0.12)",
        line=dict(width=0), name="Season range",
        hovertemplate="Round %{x}<br>Range: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=median.index, y=median, mode="lines",
        name="Typical (median)",
        line=dict(width=3, color=color),
        hovertemplate="Round %{x}<br>Median: %{y}<extra></extra>",
    ))
    if latest is not None:
        latest_data = position_data[position_data["season"].astype(str).eq(latest)]
        fig.add_trace(go.Scatter(
            x=latest_data["round"], y=latest_data["cumulative"],
            mode="lines+markers", name=str(latest),
            line=dict(width=3, color="#f2f5f7"),
            hovertemplate=f"{latest} · Round %{{x}}<br>{position}s drafted: %{{y}}<extra></extra>",
        ))
    if overlay_season and overlay_season not in {None, "None", latest}:
        extra = position_data[position_data["season"].astype(str).eq(str(overlay_season))]
        if not extra.empty:
            fig.add_trace(go.Scatter(
                x=extra["round"], y=extra["cumulative"],
                mode="lines+markers", name=str(overlay_season),
                line=dict(width=2, dash="dot", color=color),
                hovertemplate=(
                    f"{overlay_season} · Round %{{x}}<br>{position}s drafted: %{{y}}<extra></extra>"
                ),
            ))


def _render_draft_room(
    scoped: dict, selected_user_id: str | None, manager_name: str, scope_label: str,
) -> None:
    picks = li.draft_pick_frame(scoped["seasons"])
    if picks.empty:
        st.info("No completed draft boards are linked to this history window.")
        return

    manager_seasons = li.manager_season_frame(picks)
    drafts = int(picks["draft_id"].replace("", pd.NA).nunique())
    firsts = li.first_pick_timing_frame(picks)
    first_qb = firsts[firsts["position"].eq("QB")]["round"].median()
    first_te = firsts[firsts["position"].eq("TE")]["round"].median()
    construction = li.roster_construction_frame(manager_seasons)
    extra_onesies = (
        float((construction["avg_qb"] - 1).mean() + (construction["avg_te"] - 1).mean())
        if not construction.empty else 0
    )

    with st.container(key="jsa-metric-even-lh-draft"):
        m1, m2, m3, m4 = st.columns(4)
    m1.metric("Drafts analyzed", drafts)
    m2.metric("Median first QB", f"Round {first_qb:g}" if pd.notna(first_qb) else "—")
    m3.metric("Median first TE", f"Round {first_te:g}" if pd.notna(first_te) else "—")
    m4.metric("Extra QB/TE picks", f"{extra_onesies:.2f} / team")

    matrix = li.position_round_matrix(picks)
    if not matrix.empty:
        heat = go.Figure(go.Heatmap(
            z=matrix.values,
            x=[int(value) for value in matrix.columns],
            y=list(matrix.index),
            text=[[f"{value:.1f}" for value in row] for row in matrix.values],
            texttemplate="%{text}",
            colorscale=[
                [0.0, "#101821"], [0.35, "#173a4c"],
                [0.7, "#087a64"], [1.0, "#00c853"],
            ],
            colorbar=dict(title="Picks<br>per draft"),
            hovertemplate="%{y} · Round %{x}<br>%{z:.2f} picks/draft<extra></extra>",
        ))
        _dark_layout(heat, height=350, title="Where the room spends each round")
        heat.update_xaxes(title="Round", dtick=1)
        heat.update_yaxes(title="")
        page_common.plotly_phone_desktop(
            heat,
            _phone_round_heatmap(heat, len(matrix.columns)),
            slug="lh-draft-rounds",
        )
        peak_position, peak_round = matrix.stack().idxmax()
        peak_value = float(matrix.loc[peak_position, peak_round])
        st.caption(
            f"The most concentrated cell is {peak_position} in Round {int(peak_round)} "
            f"({peak_value:.1f} selections per draft). Dark cells show where waiting is usually safe; "
            "bright cells show where a tier can disappear between turns."
        )

    cumulative = li.cumulative_position_frame(picks)
    if not cumulative.empty:
        timing_seasons = sorted(
            {str(value) for value in cumulative["season"].tolist()},
            key=lambda value: int(value) if str(value).isdigit() else str(value),
        )
        overlay = None
        if len(timing_seasons) > _SERIES_LINE_LIMIT:
            older = ["None"] + timing_seasons[:-1]
            overlay = st.selectbox(
                "Compare one extra season on the QB/TE timing charts",
                older, key="lh_timing_overlay",
            )
            st.caption(
                "The band is every season in this window. The solid line is the median. "
                "Last season is overlaid so you can see whether this year was the exception."
            )
        left, right = st.columns(2)
        for container, position, color in (
            (left, "QB", _POSITION_COLORS["QB"]),
            (right, "TE", _POSITION_COLORS["TE"]),
        ):
            with container:
                fig = go.Figure()
                position_data = cumulative[cumulative["position"].eq(position)]
                _add_cumulative_traces(fig, position_data, position, color, overlay)
                _dark_layout(fig, height=360, title=f"{position} draft timing")
                fig.update_xaxes(title="Round", dtick=1)
                fig.update_yaxes(title=f"Cumulative {position}s", rangemode="tozero")
                _chart(fig)
                st.caption(
                    "A steep section is the run to anticipate. A flat section means that position "
                    "barely moved, so chasing the previous run would have sacrificed value elsewhere."
                )

    if not construction.empty:
        tax = go.Figure()
        tax.add_trace(go.Bar(
            x=construction["season"], y=construction["avg_qb"], name="QB per team",
            marker_color=_POSITION_COLORS["QB"],
        ))
        tax.add_trace(go.Bar(
            x=construction["season"], y=construction["avg_te"], name="TE per team",
            marker_color=_POSITION_COLORS["TE"],
        ))
        tax.add_hline(y=1, line_dash="dash", line_color="#f2f5f7",
                      annotation_text="One starter", annotation_position="top left")
        _dark_layout(tax, height=380, title="The backup QB/TE tax")
        tax.update_layout(barmode="group")
        tax.update_yaxes(title="Players drafted per team", rangemode="tozero")
        _chart(tax)
        st.caption(
            f"The room spends {extra_onesies:.2f} picks per team beyond one QB and one TE. "
            "A lean onesie build converts that draft capital into an extra RB/WR lottery ticket; "
            "the tradeoff is accepting a waiver decision during byes or injuries."
        )

    profile = manager_seasons[manager_seasons["user_id"].eq(str(selected_user_id))]
    if not profile.empty:
        profile = profile.sort_values("season")
        tendency = go.Figure()
        tendency.add_trace(go.Scatter(
            x=profile["season"], y=profile["first_qb_round"],
            name="First QB", mode="lines+markers", marker_color=_POSITION_COLORS["QB"],
        ))
        tendency.add_trace(go.Scatter(
            x=profile["season"], y=profile["first_te_round"],
            name="First TE", mode="lines+markers", marker_color=_POSITION_COLORS["TE"],
        ))
        _dark_layout(tendency, height=350, title=f"{manager_name}'s QB/TE timing")
        tendency.update_yaxes(title="Round selected", autorange="reversed", dtick=1)
        tendency.update_xaxes(title="Season")
        _chart(tendency)
        qb_range = profile["first_qb_round"].dropna()
        if len(qb_range) >= 3 and qb_range.max() - qb_range.min() <= 1:
            interpretation = (
                f"{manager_name} has taken the first QB within a one-round band in every observed draft. "
                "That is actionable when this manager sits between two of your turns."
            )
        else:
            interpretation = (
                f"{manager_name}'s timing moves with the board, so the chart is a bias check rather than "
                "a dependable prediction of one exact round."
            )
        st.caption(interpretation)

    benchmarks = _load_benchmarks()
    if _format_matches_benchmark(scoped):
        market = benchmarks.get("first_pick_market_medians", {})
        compare_rows = []
        for row in firsts.itertuples(index=False):
            baseline = market.get(str(row.season), {}).get(row.position)
            if baseline is None:
                continue
            compare_rows.append({
                "season": str(row.season), "position": row.position,
                "gap": float(row.pick_no) - float(baseline),
                "league_pick": int(row.pick_no), "market_pick": float(baseline),
                "player": row.player_name,
            })
        if compare_rows:
            compare = pd.DataFrame(compare_rows)
            market_fig = go.Figure()
            for position in ("QB", "TE"):
                part = compare[compare["position"].eq(position)]
                market_fig.add_trace(go.Bar(
                    x=part["season"], y=part["gap"], name=position,
                    marker_color=_POSITION_COLORS[position],
                    customdata=part[["league_pick", "market_pick", "player"]],
                    hovertemplate=(
                        "%{x} " + position + "<br>League first: #%{customdata[0]} (%{customdata[2]})"
                        "<br>Comparable median: #%{customdata[1]}<br>Difference: %{y:+.1f}<extra></extra>"
                    ),
                ))
            market_fig.add_hline(y=0, line_color="#f2f5f7", line_width=1)
            _dark_layout(market_fig, height=360, title="Does this room delay the first QB or TE?")
            market_fig.update_layout(barmode="group")
            market_fig.update_yaxes(title="Picks later than comparable Sleeper median")
            _chart(market_fig)
            st.caption(
                "Positive bars are real discounts relative to comparable 12-team, half-PPR, four-point-passing-TD "
                "drafts. A single positive season is not a promise that the same player tier will fall again."
            )

    _render_insight_bullets(
        li.draft_insights(picks, manager_seasons, selected_user_id),
        drafts, scope_label,
    )


def _manager_player_data(scoped: dict, selected_user_id: str, player_directory_loader):
    with st.spinner("Matching player names…"):
        player_directory = player_directory_loader() or {}
    weeks = li.player_week_frame(scoped["seasons"], player_directory)
    weeks = weeks[weeks["user_id"].eq(str(selected_user_id))].copy()
    seasons = li.player_season_summary(weeks, min_roster_weeks=4)
    career = li.player_career_summary(seasons)
    eligible_weeks = li.eligible_player_weeks(weeks, seasons)
    return weeks, seasons, career, eligible_weeks


def _render_player_facts(
    career: pd.DataFrame,
    eligible_weeks: pd.DataFrame,
    manager_name: str,
    scope_label: str,
) -> None:
    if career.empty or eligible_weeks.empty:
        return
    top = career.iloc[0]
    active_starts = eligible_weeks[
        eligible_weeks["active_matchup"] & eligible_weeks["is_starter"]
    ]
    bench = eligible_weeks[
        eligible_weeks["active_matchup"] & ~eligible_weeks["is_starter"]
    ]
    best_start = active_starts.loc[active_starts["points"].idxmax()] if not active_starts.empty else None
    bench_high = bench.loc[bench["points"].idxmax()] if not bench.empty else None

    weekly_winners = []
    for _, group in active_starts.groupby(["season", "week"]):
        if not group.empty:
            weekly_winners.append(group.loc[group["points"].idxmax(), "player_name"])
    weekly_mvp = pd.Series(weekly_winners).value_counts().index[0] if weekly_winners else "—"
    weekly_mvp_count = int(pd.Series(weekly_winners).value_counts().iloc[0]) if weekly_winners else 0
    window_note = f"Window: {scope_label}."

    with st.container(key="jsa-metric-even-lh-mvp"):
        c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Scoring king", top["player_name"], f"{top['lineup_points']:.1f} lineup pts",
        help=(
            f"Most points that actually entered this manager's starting lineup. {window_note} "
            "Bench points do not count. A player-season needs four rostered weeks to qualify."
        ),
    )
    if best_start is not None:
        c2.metric(
            "Best start", best_start["player_name"], f"{best_start['points']:.1f} pts",
            help=(
                f"Single highest scoring week as a starter in a real matchup. {window_note} "
                "Bye weeks and empty matchup slots are excluded."
            ),
        )
        c2.caption(f"{best_start['season']} Week {int(best_start['week'])}")
    if bench_high is not None:
        c3.metric(
            "Biggest bench regret", bench_high["player_name"], f"{bench_high['points']:.1f} pts",
            help=(
                f"Highest scoring week left on the bench during a real matchup. {window_note} "
                "This is one week, not a season-long ranking."
            ),
        )
        c3.caption(f"{bench_high['season']} Week {int(bench_high['week'])}")
    c4.metric(
        "Most weekly MVPs", weekly_mvp, f"Led {manager_name} {weekly_mvp_count} times",
        help=(
            f"The player who led this manager's starting lineup most often. {window_note} "
            "Ties in a week are broken by the first listed starter."
        ),
    )


def _render_my_team(
    scoped: dict, selected_user_id: str | None, manager_name: str,
    player_directory_loader, scope_label: str,
) -> None:
    if not selected_user_id:
        st.info("Choose a manager to load player history.")
        return
    _, player_seasons, career, eligible_weeks = _manager_player_data(
        scoped, selected_user_id, player_directory_loader
    )
    if career.empty:
        st.info("No player-season passed the four-week roster filter in this window.")
        return

    st.caption(
        "A player-season qualifies after four rostered weeks, with separate stints combined. "
        "Scoring counts only weeks containing a real matchup; the main ranking uses points that entered the lineup."
    )
    _render_player_facts(career, eligible_weeks, manager_name, scope_label)

    top = career.head(12).sort_values("lineup_points")
    scorer = go.Figure(go.Bar(
        x=top["lineup_points"], y=top["player_name"], orientation="h",
        marker_color=[_POSITION_COLORS.get(position, "#8a93a0") for position in top["position"]],
        customdata=top[["position", "starts", "seasons"]],
        hovertemplate=(
            "%{y} · %{customdata[0]}<br>Lineup points: %{x:.1f}<br>Starts: %{customdata[1]}"
            "<br>Seasons: %{customdata[2]}<extra></extra>"
        ),
    ))
    _dark_layout(scorer, height=500, title=f"Who scored the most for {manager_name}?")
    scorer.update_xaxes(title="Points in the starting lineup")
    scorer.update_yaxes(title="")
    _chart(scorer)
    leader = career.iloc[0]
    st.caption(
        f"{leader['player_name']} leads because {leader['lineup_points']:.1f} points actually entered "
        f"the lineup across {leader['season_count']} qualifying season(s). Bench production is intentionally "
        "not allowed to inflate this ranking."
    )

    leaders = (
        player_seasons.sort_values(["season", "lineup_points"], ascending=[True, False])
        .groupby("season", as_index=False).first()
    )
    position_points = (
        player_seasons.groupby("position", as_index=False)["lineup_points"].sum()
        .sort_values("lineup_points", ascending=False)
    )
    position_points = position_points[position_points["lineup_points"].gt(0)]
    show_donut = not position_points.empty
    pair_height = 360 if show_donut else 390

    show_names = len(leaders) <= 8
    season_fig = go.Figure(go.Bar(
        x=leaders["season"], y=leaders["lineup_points"],
        marker_color=[_POSITION_COLORS.get(position, "#8a93a0") for position in leaders["position"]],
        text=leaders["player_name"] if show_names else None,
        textposition="outside" if show_names else None,
        cliponaxis=False,
        customdata=leaders[["player_name", "position"]],
        hovertemplate="%{x}: %{customdata[0]} (%{customdata[1]})<br>%{y:.1f} lineup pts<extra></extra>",
    ))
    _dark_layout(season_fig, height=pair_height, title="The player who carried each season")
    season_fig.update_yaxes(title="Starting-lineup points", rangemode="tozero")
    season_caption = None
    if len(leaders) > 1:
        high = leaders.loc[leaders["lineup_points"].idxmax()]
        season_caption = (
            f"The strongest individual season was {high['player_name']} in {high['season']} "
            f"with {high['lineup_points']:.1f} lineup points. This identifies the season's engine, "
            "not merely the player who stayed rostered longest."
        )

    donut = None
    donut_caption = None
    if show_donut:
        donut = go.Figure(go.Pie(
            labels=position_points["position"], values=position_points["lineup_points"],
            hole=.5,
            marker_colors=[
                _POSITION_COLORS.get(position, "#8a93a0")
                for position in position_points["position"]
            ],
            textinfo="label+percent",
            textposition="inside",
            insidetextorientation="horizontal",
            hovertemplate="%{label}: %{value:.1f} lineup pts (%{percent})<extra></extra>",
        ))
        donut.update_layout(
            title=dict(
                text="Where lineup points came from",
                font=dict(size=16, color="#f2f5f7"),
            ),
            height=pair_height,
            margin=dict(l=8, r=8, t=48, b=8),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#f2f5f7", size=12),
            showlegend=False,
            hoverlabel=dict(bgcolor="#17202b", font_color="#ffffff"),
        )
        lead_position = position_points.iloc[0]
        share = lead_position["lineup_points"] / position_points["lineup_points"].sum()
        donut_caption = (
            f"{lead_position['position']} supplied the largest share at {share:.1%}. Because the four-week "
            "filter excludes short stays, use this as a roster-construction fingerprint rather than a complete "
            "accounting of every emergency start."
        )

    if donut is not None:
        left, right = st.columns(2)
        with left:
            _chart(season_fig)
            if season_caption:
                st.caption(season_caption)
        with right:
            _chart(donut)
            st.caption(donut_caption)
    else:
        _chart(season_fig)
        if season_caption:
            st.caption(season_caption)


def _roster_owner_map(scoped: dict) -> dict[tuple[str, str], str]:
    owners: dict[tuple[str, str], str] = {}
    for season, data in scoped["seasons"].items():
        for row in data.get("standings", []):
            roster_id = str(row.get("roster_id") or "")
            user_id = str(row.get("owner_id") or "")
            if roster_id and user_id:
                owners[(str(season), roster_id)] = user_id
    return owners


def _load_season_transactions(scoped: dict, transaction_loader) -> dict[str, list]:
    if transaction_loader is None:
        return {}
    by_season: dict[str, list] = {}
    with st.spinner("Loading waiver bids and trades…"):
        for season, data in scoped["seasons"].items():
            league_id = str(data.get("league_id") or "")
            if not league_id:
                continue
            by_season[str(season)] = transaction_loader(league_id) or []
    return by_season


def _strip_values(values: pd.Series, width: float = 0.7) -> pd.Series:
    """Spread identical x values sideways. Hover still shows the true value."""
    plot_x = values.astype(float).copy()
    width = max(float(width), 0.05)
    for value, group in values.groupby(values):
        n = len(group)
        if n <= 1:
            continue
        step = width / max(n - 1, 1)
        offsets = [(i - (n - 1) / 2) * step for i in range(n)]
        plot_x.loc[group.index] = [float(value) + off for off in offsets]
    return plot_x


def _render_trade_grades(trades: pd.DataFrame, manager_name: str) -> None:
    if trades.empty:
        st.caption("No completed player trades in this window.")
        return
    shown = li.select_trade_chart_rows(trades, li.TRADE_CHART_LIMIT)
    shown = shown.copy()
    shown["owner_label"] = li.trade_opponent_labels(shown)
    shown["got_label"] = [
        f"{li.compact_name_list(name)}  {pts:.0f}"
        for name, pts in zip(shown["got_names"], shown["got_points"])
    ]
    shown["gave_label"] = [
        f"{li.compact_name_list(name)}  {pts:.0f}"
        for name, pts in zip(shown["gave_names"], shown["gave_points"])
    ]
    extras = [
        extra if extra else "Players only"
        for extra in shown["extra"]
    ]
    hover = list(zip(
        shown["got_names"], shown["gave_names"], extras,
        [f"{net:+.1f}" for net in shown["net"]],
        shown["got_points"], shown["gave_points"],
        shown["label"],
    ))
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Got",
        y=shown["owner_label"],
        x=shown["got_points"],
        orientation="h",
        marker_color="#35D08A",
        text=shown["got_label"],
        textposition="outside",
        cliponaxis=False,
        customdata=hover,
        hovertemplate=(
            "%{customdata[6]}<br>Got: %{customdata[0]} (%{customdata[4]:.1f})"
            "<br>Gave up: %{customdata[1]} (%{customdata[5]:.1f})"
            "<br>Net: %{customdata[3]}<br>%{customdata[2]}<extra></extra>"
        ),
    ))
    fig.add_trace(go.Bar(
        name="Gave up",
        y=shown["owner_label"],
        x=shown["gave_points"],
        orientation="h",
        marker_color="#FB7185",
        text=shown["gave_label"],
        textposition="outside",
        cliponaxis=False,
        customdata=hover,
        hovertemplate=(
            "%{customdata[6]}<br>Got: %{customdata[0]} (%{customdata[4]:.1f})"
            "<br>Gave up: %{customdata[1]} (%{customdata[5]:.1f})"
            "<br>Net: %{customdata[3]}<br>%{customdata[2]}<extra></extra>"
        ),
    ))
    fig.update_layout(barmode="group")
    _dark_layout(
        fig,
        height=max(400, 64 * len(shown) + 140),
        title=f"Did {manager_name} win these trades?",
    )
    fig.update_xaxes(title="Starting-lineup points after the trade", rangemode="tozero")
    fig.update_yaxes(title="", automargin=True)
    _chart(fig)
    st.caption(
        "Got is starting-lineup points the players you received scored for you from the week "
        "after the trade through the rest of that season. Gave up is what the players you sent "
        "scored for their new team over the same stretch. Picks and FAAB show in the hover, "
        "not as points. Late-season trades still count."
    )
    if len(trades) > len(shown):
        st.caption(
            f"Showing the {len(shown)} most lopsided of {len(trades)} player trades. "
            "Even deals are dropped so the chart stays readable."
        )
    if not bool(shown["player_only"].all()):
        st.caption(
            "At least one deal also moved picks or FAAB, so the point gap is not the whole package."
        )
    best = shown.loc[shown["net"].idxmax()]
    if float(best["net"]) > 0:
        st.caption(
            f"The clearest player win is {best['label']}: {best['net']:+.1f} "
            f"({best['got_names']} vs {best['gave_names']})."
        )


def _paid_production_chart(producers: pd.DataFrame, manager_name: str, height: int) -> go.Figure:
    paid_seasons = int(producers["season"].nunique())
    paid_labels = _point_labels(producers, paid_seasons, "lineup_points")
    fig = go.Figure(go.Scatter(
        x=_strip_values(producers["faab"]), y=producers["lineup_points"],
        mode="markers+text", text=paid_labels, textposition="top center",
        marker=dict(
            size=11,
            opacity=0.7 if len(producers) > 24 else 0.88,
            color=_PAID_FAAB_SCATTER_COLOR,
        ),
        customdata=list(zip(
            producers["player_name"], producers["position"],
            producers["season"], producers["faab"], producers["acq_week"],
        )),
        hovertemplate=(
            "%{customdata[0]} · %{customdata[1]}<br>%{customdata[2]}"
            "<br>FAAB: $%{customdata[3]:.0f}<br>Lineup points: %{y:.1f}<extra></extra>"
        ),
    ))
    _dark_layout(
        fig, height=height,
        title=f"${li.FAAB_PAID_MIN}+ bids for {manager_name}",
    )
    fig.update_xaxes(title="FAAB spent", rangemode="tozero")
    fig.update_yaxes(title="Starting-lineup points", rangemode="tozero")
    return fig


def _paid_bust_chart(busts: pd.DataFrame, height: int | None = None) -> tuple[go.Figure, pd.DataFrame]:
    bust_top = busts.sort_values("faab", ascending=False).head(li.BUST_CHART_LIMIT)
    bust_top = bust_top.sort_values("faab")
    fig = go.Figure(go.Bar(
        x=bust_top["faab"], y=bust_top["player_name"],
        orientation="h",
        marker_color=_PAID_FAAB_COLOR,
        text=[f"${int(bid)}" for bid in bust_top["faab"]],
        textposition="outside",
        customdata=list(zip(
            bust_top["season"], bust_top["position"],
        )),
        hovertemplate=(
            "%{y} · %{customdata[1]}<br>%{customdata[0]}"
            "<br>FAAB: $%{x:.0f}<br>Lineup points: 0<extra></extra>"
        ),
    ))
    _dark_layout(
        fig,
        height=height if height is not None else max(280, 28 * len(bust_top) + 80),
        title=f"Paid ${li.FAAB_PAID_MIN}+ with no lineup points",
    )
    fig.update_xaxes(title="FAAB spent")
    fig.update_yaxes(title="")
    return fig, bust_top


def _cheap_waiver_chart(cheap: pd.DataFrame, manager_name: str, height: int | None = None) -> go.Figure:
    cheap_top = cheap.sort_values("lineup_points", ascending=False).head(12)
    cheap_top = cheap_top.sort_values("lineup_points")
    fig = go.Figure(go.Bar(
        x=cheap_top["lineup_points"], y=cheap_top["player_name"],
        orientation="h",
        marker_color=[
            _POSITION_COLORS.get(position, "#8a93a0")
            for position in cheap_top["position"]
        ],
        text=[f"${int(bid)}" for bid in cheap_top["faab"]],
        textposition="outside",
        customdata=list(zip(
            cheap_top["season"], cheap_top["position"], cheap_top["faab"],
        )),
        hovertemplate=(
            "%{y} · %{customdata[1]}<br>%{customdata[0]} · $%{customdata[2]:.0f}"
            "<br>Lineup points: %{x:.1f}<extra></extra>"
        ),
    ))
    _dark_layout(
        fig,
        height=height if height is not None else max(320, 28 * len(cheap_top) + 80),
        title=(
            f"Cheap claims ($0-${li.FAAB_PAID_MIN - 1}, "
            f"4+ weeks) for {manager_name}"
        ),
    )
    fig.update_xaxes(title="Starting-lineup points")
    fig.update_yaxes(title="")
    return fig


def _render_faab_charts(
    cheap: pd.DataFrame, paid: pd.DataFrame, manager_name: str,
) -> None:
    producers = pd.DataFrame()
    busts = pd.DataFrame()
    if not paid.empty:
        producers, busts = li.split_paid_production_frames(paid)
    show_cheap = not cheap.empty
    show_paid = not producers.empty
    show_busts = not busts.empty
    if not (show_cheap or show_paid or show_busts):
        st.caption("This window has FAAB, but this manager has no waiver claims to plot.")
        return

    cheap_caption = (
        f"Most waiver bids in a FAAB league cluster at $0-$1, so claims under "
        f"${li.FAAB_PAID_MIN} are ranked here instead of piled on the scatter. "
        "Only players with four rostered weeks in that season appear. "
        "One-week streamers are excluded. Free-agent adds and trades stay off the FAAB charts."
    )
    bust_caption = (
        "These bids never scored in a starting lineup. They sit here instead of "
        "stacking on the scatter at zero. Ranked by dollars spent."
    )

    if show_paid:
        _chart_labeled(_paid_production_chart(producers, manager_name, 420), slug="faab-paid")
        scatter_note = (
            f"Every completed bid of ${li.FAAB_PAID_MIN} or more that produced starting-lineup "
            "points, including players you later dropped. No roster-week minimum. "
            "Same-dollar bids are spread sideways."
        )
        if show_busts and show_cheap:
            scatter_note += " Zero-point bids sit beside cheap claims."
        elif show_busts:
            scatter_note += " Zero-point bids are in the ranked bar below."
        st.caption(scatter_note)

    pair_height = None
    if show_cheap and show_busts:
        pair_height = max(
            320,
            28 * max(
                min(12, len(cheap)),
                min(li.BUST_CHART_LIMIT, len(busts)),
            ) + 80,
        )
    cheap_fig = _cheap_waiver_chart(cheap, manager_name, pair_height) if show_cheap else None
    bust_fig = bust_top = None
    if show_busts:
        bust_fig, bust_top = _paid_bust_chart(busts, pair_height)

    if show_cheap and show_busts:
        left, right = st.columns(2)
        with left:
            _chart(cheap_fig)
            st.caption(cheap_caption)
        with right:
            _chart(bust_fig)
            st.caption(bust_caption)
            if len(busts) > len(bust_top):
                st.caption(
                    f"Showing the {len(bust_top)} most expensive of {len(busts)} zero-point bids."
                )
    elif show_cheap:
        _chart(cheap_fig)
        st.caption(cheap_caption)
    elif show_busts:
        _chart(bust_fig)
        st.caption(bust_caption)
        if len(busts) > len(bust_top):
            st.caption(
                f"Showing the {len(bust_top)} most expensive of {len(busts)} zero-point bids."
            )


def _render_values(
    scoped: dict, selected_user_id: str | None, manager_name: str,
    player_directory_loader, transaction_loader, scope_label: str,
) -> None:
    if not selected_user_id:
        st.info("Choose a manager to load acquisition value.")
        return
    with st.spinner("Matching player names…"):
        player_directory = player_directory_loader() or {}
    weeks = li.player_week_frame(scoped["seasons"], player_directory)
    manager_weeks = weeks[weeks["user_id"].eq(str(selected_user_id))].copy()
    player_seasons = li.player_season_summary(manager_weeks, min_roster_weeks=4)
    picks = li.draft_pick_frame(scoped["seasons"])
    picks = picks[picks["user_id"].eq(str(selected_user_id))]
    values = li.value_frame(player_seasons, picks)
    owners = _roster_owner_map(scoped)
    by_season = _load_season_transactions(scoped, transaction_loader)
    acquisitions = li.first_acquisition_frame(by_season, owners)
    identities = li.manager_identity_map(scoped["seasons"])
    trades = li.trade_outcome_frame(
        by_season, owners, weeks, str(selected_user_id), identities,
    )
    paid = li.paid_waiver_claim_frame(
        by_season, owners, weeks, str(selected_user_id),
    )
    if values.empty and trades.empty and paid.empty:
        st.info("No qualifying player-seasons are available for this manager.")
        return

    if not values.empty:
        values = li.attach_acquisitions(values, acquisitions)
    drafted = values[values["source"].eq("Drafted")].copy() if not values.empty else values
    season_count = int(values["season"].nunique()) if not values.empty else 0

    if not drafted.empty:
        st.caption(
            "Drafted players sit on their actual round. Same-round picks are spread sideways. "
            "Free-agent adds are not on this scatter. No combined value score is used."
        )
        if season_count > _SERIES_LINE_LIMIT:
            st.caption("More than three seasons: only the outlier names are labeled.")
        draft_fig = go.Figure()
        labels = _point_labels(drafted, season_count, "lineup_points")
        draft_opacity = 0.65 if len(drafted) > 24 else 0.85
        draft_fig.add_trace(go.Scatter(
            x=_strip_values(drafted["round"], width=0.28), y=drafted["lineup_points"],
            mode="markers+text",
            name="Drafted", text=labels, textposition="top center",
            marker=dict(size=11, opacity=draft_opacity),
            customdata=list(zip(
                drafted["player_name"], drafted["position"], drafted["starts"],
                drafted["season"], drafted["round"],
            )),
            hovertemplate=(
                "%{customdata[0]} · %{customdata[1]}<br>%{customdata[3]} · Round %{customdata[4]:.0f}"
                "<br>Lineup points: %{y:.1f}<br>Starts: %{customdata[2]}<extra></extra>"
            ),
        ))
        _dark_layout(draft_fig, height=520, title=f"{manager_name}'s draft cost versus realized production")
        draft_fig.update_xaxes(title="Draft round", dtick=1, autorange="reversed")
        draft_fig.update_yaxes(title="Starting-lineup points", rangemode="tozero")
        _chart_labeled(draft_fig, slug="draft-value")
        late = drafted[drafted["round"].ge(6)].sort_values("lineup_points", ascending=False)
        if not late.empty:
            hit = late.iloc[0]
            st.caption(
                f"The clearest late-round return is {hit['player_name']}: Round {int(hit['round'])}, "
                f"{hit['lineup_points']:.1f} lineup points in {hit['season']}."
            )

    cheap, _ = li.split_faab_waiver_frames(values)
    if li.league_uses_faab(scoped["seasons"]):
        _render_faab_charts(cheap, paid, manager_name)
    elif not acquisitions.empty:
        st.caption("This league does not use FAAB, so there is no bid to plot.")

    _render_trade_grades(trades, manager_name)


def _render_view_switcher() -> str:
    previous = st.session_state.pop(_LEGACY_VIEW_KEY, None)
    if previous in _INSIGHT_VIEWS and _VIEW_KEY not in st.session_state:
        st.session_state[_VIEW_KEY] = previous
    st.markdown(_VIEW_SWITCHER_CSS, unsafe_allow_html=True)
    view = st.segmented_control(
        "View",
        list(_INSIGHT_VIEWS),
        default=_DEFAULT_INSIGHT_VIEW,
        required=True,
        key=_VIEW_KEY,
        width="content",
        help="My Team, Best Values, and Draft Room are the three insight pages.",
    )
    if view not in _INSIGHT_VIEWS:
        return _DEFAULT_INSIGHT_VIEW
    return view


def render(
    history: dict,
    season_filter: str,
    player_directory_loader,
    transaction_loader=None,
    *,
    provider_name: str = "Sleeper",
) -> None:
    st.subheader("Draft & Roster Insights")
    view = _render_view_switcher()
    st.caption(
        f"League-specific tendencies and manager history from {provider_name}'s completed drafts and weekly roster snapshots. "
        "Three drafts can reveal repeated habits, but every recommendation below keeps its sample visible."
    )
    if provider_name in {"ESPN", "Yahoo", "CBS"} and view == "Best Values":
        st.caption(
            f"{provider_name} imports do not yet include complete waiver-bid and trade history, so "
            "in-season additions are identified from weekly roster changes without "
            "FAAB or trade-grade detail."
        )
    scoped, scope_label = _scope_history(history, season_filter)
    selected_user_id, manager_name = _manager_control(scoped)
    st.caption(f"Analysis window: {scope_label}")
    if view == "Draft Room":
        _render_draft_room(scoped, selected_user_id, manager_name, scope_label)
    elif view == "My Team":
        _render_my_team(
            scoped, selected_user_id, manager_name, player_directory_loader, scope_label,
        )
    else:
        _render_values(
            scoped, selected_user_id, manager_name, player_directory_loader,
            transaction_loader, scope_label,
        )
